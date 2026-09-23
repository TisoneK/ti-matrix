/*
 * The Electron main process: the sidecar's parent and the renderer's gatekeeper.
 *
 * Responsibilities, in order: spawn the Python sidecar (dev: the repo venv; prod: the PyInstaller
 * bundle in resources/), read exactly one line of its stdout — the TM handshake — health-check it,
 * and only then tell the renderer where the socket is. The handshake token stays in this process:
 * the renderer receives a ready-to-use ws:// URL with the token already appended, spoken over IPC
 * the preload allows and nowhere else. On quit, the child and its whole process tree go with us —
 * on Windows explicitly, because orphans do not die on their own there.
 */
import { app, BrowserWindow, ipcMain } from "electron";
import { spawn, ChildProcess } from "child_process";
import * as fs from "fs";
import * as http from "http";
import * as path from "path";

const HANDSHAKE = /^TM(\d+) (\d+) ([0-9a-f]{32})$/;
const START_TIMEOUT_MS = 15000;

let sidecar: ChildProcess | null = null;
let mainWindow: BrowserWindow | null = null;
// The handshake lands before any window exists, and a window can be reloaded at any time — so the renderer
// asks for the connection when it is ready to use it, and a request that arrives early waits here.
let readyConn: { url: string } | null = null;
let waiting: ((conn: { url: string }) => void)[] = [];

function whenReady(): Promise<{ url: string }> {
  if (readyConn) return Promise.resolve(readyConn);
  return new Promise((resolve) => { waiting.push(resolve); });
}

function announceReady(conn: { url: string }): void {
  readyConn = conn;
  for (const resolve of waiting) resolve(conn);
  waiting = [];
}

function sidecarCommand(): { cmd: string; args: string[]; cwd?: string } {
  if (process.env.VITE_DEV) {
    // __dirname is app/dist-electron/main at runtime; the repo root is three levels up.
    const repo = path.join(__dirname, "..", "..", "..");
    const win = process.platform === "win32";
    const python = process.env.TI_MATRIX_PYTHON
      || path.join(repo, ".venv", win ? "Scripts" : "bin", win ? "python.exe" : "python");
    // `python -m appserver` (see appserver/__main__.py), run from server/ so the package imports
    return { cmd: python, args: ["-X", "utf8", "-m", "appserver"], cwd: path.join(repo, "server") };
  }
  const bundled = path.join(process.resourcesPath ?? "", "sidecar", "ti-matrix-server")
    + (process.platform === "win32" ? ".exe" : "");
  return { cmd: bundled, args: [] };
}

function healthz(port: number): Promise<boolean> {
  return new Promise((resolve) => {
    const req = http.get({ host: "127.0.0.1", port, path: "/healthz", timeout: 1000 }, (res) => {
      res.resume();
      resolve(res.statusCode === 200);
    });
    req.on("error", () => resolve(false));
    req.on("timeout", () => { req.destroy(); resolve(false); });
  });
}

async function waitForHealth(port: number): Promise<boolean> {
  const deadline = Date.now() + START_TIMEOUT_MS;
  while (Date.now() < deadline) {
    if (await healthz(port)) return true;
    await new Promise((r) => setTimeout(r, 150));
  }
  return false;
}

function startSidecar(): Promise<void> {
  return new Promise((resolve, reject) => {
    const { cmd, args, cwd } = sidecarCommand() as { cmd: string; args: string[]; cwd?: string };
    if (!fs.existsSync(cmd)) {
      reject(new Error(`the sidecar is not where it should be: ${cmd}`));
      return;
    }
    sidecar = spawn(cmd, args, { cwd, stdio: ["ignore", "pipe", "pipe"], windowsHide: true });

    let buffer = "";
    let settled = false;
    const fail = (err: Error) => { if (!settled) { settled = true; reject(err); } };

    sidecar.stdout!.setEncoding("utf8");
    sidecar.stdout!.on("data", async (chunk: string) => {
      buffer += chunk;
      const line = buffer.split("\n").find((l) => l.trim().length > 0);
      if (line === undefined || settled) return;
      const match = HANDSHAKE.exec(line.trim());
      if (!match) return; // not the handshake; ignore everything else on stdout
      settled = true;
      const protocol = Number(match[1]);
      const port = Number(match[2]);
      const token = match[3];
      if (protocol !== 1) { fail(new Error(`the sidecar speaks TM${protocol}, this app speaks TM1`)); return; }
      if (!(await waitForHealth(port))) { fail(new Error("the sidecar never became healthy")); return; }
      announceReady({ url: `ws://127.0.0.1:${port}/ws?token=${token}` });
      resolve();
    });
    sidecar.stderr!.setEncoding("utf8");
    sidecar.stderr!.on("data", (chunk: string) => process.stderr.write(`[sidecar] ${chunk}`));
    sidecar.on("exit", (code) => {
      sidecar = null;
      mainWindow?.webContents.send("tm:sidecar-exit", { code });
    });
  });
}

function createWindow(): void {
  mainWindow = new BrowserWindow({
    width: 1280,
    height: 860,
    backgroundColor: "#0e1015",
    webPreferences: {
      preload: path.join(__dirname, "..", "preload", "index.js"),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });
  // Dev mode serves the renderer from Vite (hot reload); prod loads the built bundle.
  if (process.env.VITE_DEV) {
    mainWindow.loadURL("http://localhost:5173");
  } else {
    mainWindow.loadFile(path.join(__dirname, "..", "..", "dist", "index.html"));
  }
}

const gotLock = app.requestSingleInstanceLock();
if (!gotLock) {
  app.quit();
} else {
  app.on("second-instance", () => {
    if (mainWindow) { mainWindow.restore(); mainWindow.focus(); }
  });

  app.whenReady().then(async () => {
    ipcMain.handle("tm:pick-directory", async () => {
      const { dialog } = await import("electron");
      const result = await dialog.showOpenDialog(mainWindow!, { properties: ["openDirectory"] });
      return result.canceled || result.filePaths.length === 0 ? null : result.filePaths[0];
    });
    ipcMain.handle("tm:user-data", () => app.getPath("userData"));
    // The renderer's way in: ask when you are ready, whether that is before or after the sidecar answered.
    ipcMain.handle("tm:connection", () => whenReady());

    try {
      await startSidecar();
    } catch (err) {
      const { dialog } = await import("electron");
      dialog.showErrorBox("Ti Matrix could not start", String(err));
      app.quit();
      return;
    }
    createWindow();
  });

  app.on("window-all-closed", () => {
    if (process.platform !== "darwin") app.quit();
  });

  app.on("before-quit", () => {
    if (sidecar && sidecar.pid) {
      // Windows needs the tree killed explicitly; POSIX children die with the pipe closed.
      if (process.platform === "win32") {
        spawn("taskkill", ["/pid", String(sidecar.pid), "/T", "/F"]);
      } else {
        sidecar.kill();
      }
    }
  });
}
