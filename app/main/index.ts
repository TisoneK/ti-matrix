/*
 * The Electron main process: the sidecar's parent and the renderer's gatekeeper.
 *
 * Responsibilities, in order: spawn the Python sidecar (dev: the repo venv; prod: the PyInstaller
 * bundle in resources/), read exactly one line of its stdout — the TM handshake — health-check it,
 * and only then tell the renderer where the socket is. The handshake token stays in this process:
 * the renderer receives a ready-to-use ws:// URL with the token already appended, spoken over IPC
 * the preload allows and nowhere else. On quit, the child and its whole process tree go with us —
 * on Windows explicitly, because orphans do not die on their own there.
 *
 * It is also, and only, the filesystem: the renderer has none (context isolation, no node integration),
 * so the session library lives here. Every id that arrives over IPC is checked against a strict pattern
 * and resolved inside the runs directory before a file is touched — the renderer is not trusted with a
 * path, even though in this app the caller happens to be our own code.
 */
import { app, BrowserWindow, ipcMain } from "electron";
import { spawn, ChildProcess } from "child_process";
import * as fs from "fs";
import * as http from "http";
import * as path from "path";

const HANDSHAKE = /^TM(\d+) (\d+) ([0-9a-f]{32})$/;
const START_TIMEOUT_MS = 15000;
/** Run ids are minted by the renderer, so they are validated here: no dots, no separators, nothing to climb. */
const RUN_ID = /^[A-Za-z0-9_-]{1,64}$/;
const MAX_ARTIFACT_BYTES = 64 * 1024 * 1024;

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

// ── the session library: the only place in the app that touches a disk ──────
//
// One directory per run under the app's user-data folder:
//
//   runs/<id>/run.json      the artifact — the events verbatim, the world, the model, how it ended
//   runs/<id>/meta.json     the library row, written by the renderer at the same moment
//   runs/<id>/events.jsonl  the engine's own run log, appended by the sidecar as the run streams
//
// The third file is not ours: it is `ti_matrix.adapters.run_log`'s format, so a run watched in this window
// can be read back by the CLIs, and a run recorded by a CLI can be compared against one from the window.

function runsDir(): string {
  return path.join(app.getPath("userData"), "runs");
}

/** A run directory, or null when the id could not name one — the caller never sees a path it did not earn. */
function runDir(id: unknown): string | null {
  if (typeof id !== "string" || !RUN_ID.test(id)) return null;
  const dir = path.join(runsDir(), id);
  const root = path.resolve(runsDir());
  return path.resolve(dir).startsWith(root + path.sep) ? dir : null;
}

async function writeJson(file: string, value: unknown): Promise<void> {
  await fs.promises.writeFile(file, JSON.stringify(value), "utf8");
}

async function readJson<T>(file: string): Promise<T | null> {
  try {
    const stat = await fs.promises.stat(file);
    if (!stat.isFile() || stat.size > MAX_ARTIFACT_BYTES) return null;
    return JSON.parse(await fs.promises.readFile(file, "utf8")) as T;
  } catch {
    return null; // a missing or half-written run is not an error, it is a run that is not there
  }
}

function registerLibrary(): void {
  ipcMain.handle("tm:runs-dir", async () => {
    await fs.promises.mkdir(runsDir(), { recursive: true });
    return runsDir();
  });

  ipcMain.handle("tm:run-begin", async (_e, id: unknown) => {
    // The renderer mints the id (it has to: the artifact saved later must carry the same one) and main
    // only says yes or no to it, after checking it names a directory directly under runs/.
    const dir = runDir(id);
    if (dir === null) return null;
    await fs.promises.mkdir(dir, { recursive: true });
    return { id, dir, recordPath: path.join(dir, "events.jsonl") };
  });

  ipcMain.handle("tm:run-save", async (_e, artifact: unknown, meta: unknown) => {
    const id = (artifact as { id?: unknown } | null)?.id;
    const dir = runDir(id);
    if (dir === null || artifact === null || typeof artifact !== "object") return false;
    try {
      await fs.promises.mkdir(dir, { recursive: true });
      await writeJson(path.join(dir, "run.json"), artifact);
      if (meta !== null && typeof meta === "object") await writeJson(path.join(dir, "meta.json"), meta);
      return true;
    } catch {
      return false;
    }
  });

  ipcMain.handle("tm:runs-list", async () => {
    let names: string[] = [];
    try {
      names = await fs.promises.readdir(runsDir());
    } catch {
      return [];
    }
    const metas = await Promise.all(names.map((name) => readJson<Record<string, unknown>>(path.join(runsDir(), name, "meta.json"))));
    return metas.filter((m): m is Record<string, unknown> => m !== null && typeof m["id"] === "string");
  });

  ipcMain.handle("tm:run-load", async (_e, id: unknown) => {
    const dir = runDir(id);
    return dir === null ? null : readJson(path.join(dir, "run.json"));
  });

  ipcMain.handle("tm:run-delete", async (_e, id: unknown) => {
    const dir = runDir(id);
    if (dir === null) return false;
    try {
      await fs.promises.rm(dir, { recursive: true, force: true });
      return true;
    } catch {
      return false;
    }
  });
}

// ── the window's own chrome ────────────────────────────────────────────────
//
// The title bar is the app's top rail, not a strip of OS chrome above it: the rail already carries what a
// title bar carries (the name, the state, the way in), so drawing it twice would be a waste of the one
// strip of screen a run never gets back. That means the frame is ours to own, and these are the controls.
//
// macOS keeps its traffic lights and insets them over the rail (`hiddenInset`) — a Mac user reaches for
// those in muscle memory, and reimplementing them would only be worse. Everywhere else the frame is gone
// and the rail draws its own minimize/maximize/close.

function registerWindow(): void {
  const win = (): BrowserWindow | null => mainWindow;

  ipcMain.handle("tm:window-minimize", () => { win()?.minimize(); });
  ipcMain.handle("tm:window-toggle-maximize", () => {
    const w = win();
    if (!w) return;
    if (w.isMaximized()) w.unmaximize(); else w.maximize();
  });
  ipcMain.handle("tm:window-close", () => { win()?.close(); });
  ipcMain.handle("tm:window-state", () => ({
    maximized: Boolean(mainWindow?.isMaximized()),
    fullScreen: Boolean(mainWindow?.isFullScreen()),
  }));
}

/** Both of these change how the rail should draw its button, so both are pushed rather than polled. */
function watchWindowState(window: BrowserWindow): void {
  const tell = (): void => {
    window.webContents.send("tm:window-state", {
      maximized: window.isMaximized(),
      fullScreen: window.isFullScreen(),
    });
  };
  window.on("maximize", tell);
  window.on("unmaximize", tell);
  window.on("enter-full-screen", tell);
  window.on("leave-full-screen", tell);
}

function createWindow(): void {
  const mac = process.platform === "darwin";
  mainWindow = new BrowserWindow({
    width: 1280,
    height: 860,
    minWidth: 760,
    minHeight: 520,
    backgroundColor: "#090c12",
    // A one-pixel sliver of the rail showing above the traffic lights reads as a bug; the rail's own
    // padding below is what makes room for them.
    titleBarStyle: mac ? "hiddenInset" : "hidden",
    trafficLightPosition: mac ? { x: 14, y: 15 } : undefined,
    frame: mac ? undefined : false,
    webPreferences: {
      preload: path.join(__dirname, "..", "preload", "index.js"),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });
  watchWindowState(mainWindow);
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
    registerLibrary();
    registerWindow();

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
