/*
 * The Electron main process: the sidecar's parent and the renderer's gatekeeper.
 *
 * The boot, in order: a small splash window opens at once (app/splash.html — a maze that reveals itself
 * stage by stage), the Python sidecar spawns underneath it (dev: the repo venv; prod: the PyInstaller
 * bundle in resources/, with the venv as a fallback for a dev machine running the bare build), main reads
 * exactly one line of the child's stdout — the TM handshake — and health-checks it while the splash
 * reports each stage. Only then does the real app window load, hidden; the moment it has painted, it
 * takes the screen and the splash closes. That swap is the difference between "it is starting" and a
 * black frame: the splash stays up until there is something to replace it, so the two surfaces hand over
 * with no gap where neither is showing.
 *
 * A boot that fails (bad handshake, never healthy, sidecar exited, renderer never loaded) fails *into
 * the splash* — the reason, a restart button — instead of into a modal dialog that throws away the very
 * window it is telling the user about. The handshake token stays in this process: the renderer receives
 * a ready-to-use ws:// URL, spoken over IPC the preload allows and nowhere else. On quit, the child and
 * its whole process tree go with us — on Windows explicitly, because orphans do not die on their own.
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
/** The splash: small, first on screen, closed the moment the app takes over. */
let splashWindow: BrowserWindow | null = null;
/** The app: loaded hidden while the splash still holds the screen, shown once it has painted. */
let mainWindow: BrowserWindow | null = null;
let revealed = false;
/** When the boot began — the splash holds the screen at least SPLASH_MIN_MS past this. */
let bootedAt = 0;
// The handshake lands before any window exists, and a window can be reloaded at any time — so the renderer
// asks for the connection when it is ready to use it, and a request that arrives early waits here.
let readyConn: { url: string } | null = null;
let waiting: { resolve: (conn: { url: string }) => void; reject: (err: Error) => void }[] = [];
/** Why the last boot failed, if it did — so a renderer asking for a connection is told, not left hanging. */
let bootFailure: string | null = null;

function whenReady(): Promise<{ url: string }> {
  if (readyConn) return Promise.resolve(readyConn);
  // A boot that already failed must answer now. This used to return a promise that simply never settled:
  // the renderer sat at "reaching the sidecar…" forever with the one fact that explained it — the reason
  // the spawn failed — sitting right here, unsaid.
  if (bootFailure !== null) return Promise.reject(new Error(bootFailure));
  return new Promise((resolve, reject) => { waiting.push({ resolve, reject }); });
}

function announceReady(conn: { url: string }): void {
  readyConn = conn;
  bootFailure = null;
  for (const w of waiting) w.resolve(conn);
  waiting = [];
}

/** The boot failed: everyone still waiting hears why, and so does everyone who asks after this. */
function announceFailure(reason: string): void {
  bootFailure = reason;
  for (const w of waiting) w.reject(new Error(reason));
  waiting = [];
}

// ── boot stages, streamed to the splash ─────────────────────────────────────

type BootStage = "spawn" | "handshake" | "health" | "renderer";
type BootStatus = "active" | "done" | "failed";
interface BootReport { id: BootStage; status: BootStatus; detail?: string }

const bootLog: BootReport[] = [];

const stageNote = (detail: string): string =>
  detail.length > 160 ? detail.slice(0, 157) + "…" : detail;

function stage(id: BootStage, status: BootStatus, detail?: string): void {
  const report: BootReport = { id, status, detail: detail ? stageNote(detail) : undefined };
  if (status === "failed") bootLog.push(report);
  // Whoever is on screen hears it: the splash while it holds the window, the app afterwards.
  const audience = splashWindow && !splashWindow.isDestroyed() ? splashWindow
    : mainWindow && !mainWindow.isDestroyed() ? mainWindow : null;
  if (audience) audience.webContents.send("tm:boot-stage", report);
}

/** Which engine runs the world: the PyInstaller bundle in prod, the repo venv in dev — or as a fallback. */
function sidecarCommand(): { cmd: string; args: string[]; cwd?: string; note?: string } {
  const win = process.platform === "win32";
  // __dirname is app/dist-electron/main at runtime; the repo root is three levels up.
  const repo = path.join(__dirname, "..", "..", "..");
  const venv = {
    cmd: process.env.TI_MATRIX_PYTHON
      || path.join(repo, ".venv", win ? "Scripts" : "bin", win ? "python.exe" : "python"),
    args: ["-X", "utf8", "-m", "appserver"],
    cwd: path.join(repo, "server"),
  };
  if (process.env.VITE_DEV) return venv;
  // Prod prefers the bundled engine. But a dev machine running the bare build (plain `npx electron .`)
  // has no bundle — falling back to the repo venv beats dead-ending on a missing exe.
  const bundled = path.join(process.resourcesPath ?? "", "sidecar", "ti-matrix-server") + (win ? ".exe" : "");
  if (fs.existsSync(bundled)) return { cmd: bundled, args: [] };
  return { ...venv, note: "no bundled engine — using the repo's python" };
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

function startSidecar(onExit: (code: number | null) => void): Promise<void> {
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
      stage("handshake", "done", `TM1 on port ${port}`);
      stage("health", "active", `port ${port}`);
      if (!(await waitForHealth(port))) {
        fail(new Error(`the engine never became healthy within ${Math.round(START_TIMEOUT_MS / 1000)}s (port ${port})`));
        return;
      }
      stage("health", "done");
      announceReady({ url: `ws://127.0.0.1:${port}/ws?token=${token}` });
      resolve();
    });
    sidecar.stderr!.setEncoding("utf8");
    sidecar.stderr!.on("data", (chunk: string) => process.stderr.write(`[sidecar] ${chunk}`));
    sidecar.on("error", (err) => fail(err));
    sidecar.on("exit", (code) => {
      sidecar = null;
      // The URL we handed out names a port nothing is listening on any more. Forgetting it is what makes
      // `tm:sidecar-restart` able to hand out a new one instead of the stale one.
      readyConn = null;
      // A sidecar that dies while the splash is still up is a boot failure, not a lifecycle event.
      if (!readyConn) fail(new Error(`the engine exited while starting (code ${code ?? "signal"})`));
      // Always forwarded: before the renderer exists nobody is listening (harmless), after it the app
      // marks itself crashed.
      if (mainWindow && !mainWindow.isDestroyed()) {
        mainWindow.webContents.send("tm:sidecar-exit", { code });
      }
      onExit(code);
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
  /**
   * Where a world's accumulated experience lives. One file per world, because what the maze taught a
   * run has nothing to say about a filesystem, and pooling them would make the record noise.
   *
   * The engine has shipped `recall` and `LearningProposer` since v0.1 and `benchmarks/bench.py`
   * measures what they are worth — once the record holds anything, the same goals settle in 1 round
   * and 3 probes instead of 2 and 6. The app never sent `remember`, so `stats_path` was always None,
   * so neither was ever constructed. The whole layer was switched off in the product that most needed
   * it, where a model call is twenty to forty-five seconds.
   */
  ipcMain.handle("tm:memory-path", async (_e, world: unknown) => {
    if (typeof world !== "string" || !/^[a-z][a-z0-9_-]{0,31}$/.test(world)) return null;
    const dir = path.join(app.getPath("userData"), "memory");
    await fs.promises.mkdir(dir, { recursive: true });
    return path.join(dir, `${world}.json`);
  });

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
// and the rail draws its own minimize/maximize/close. The splash drags itself by the same rule — its
// title strip only, never the whole page.

function registerWindow(): void {
  const win = (): BrowserWindow | null => mainWindow;

  ipcMain.handle("tm:window-minimize", () => { win()?.minimize(); });
  ipcMain.handle("tm:window-toggle-maximize", () => {
    const w = win();
    if (!w) return;
    if (w.isMaximized()) w.unmaximize(); else w.maximize();
  });
  ipcMain.handle("tm:window-close", () => {
    // From the app, close the app; from the splash (the quit button), close the process.
    const w = win();
    if (w) w.close(); else app.quit();
  });
  ipcMain.handle("tm:window-state", () => ({
    maximized: Boolean(mainWindow?.isMaximized()),
    fullScreen: Boolean(mainWindow?.isFullScreen()),
  }));
  // The splash's "try again" — a fresh process is the only honest retry, because a half-started sidecar
  // may hold the port.
  ipcMain.handle("tm:relaunch", () => { app.relaunch(); app.exit(0); });
  /**
   * The window's "try again": spawn a new engine without throwing the window away.
   *
   * `tm:relaunch` restarts everything, which is the right answer on the splash — there is nothing on
   * screen yet to lose. Once the app is up there is: the run on screen, the library, the config someone
   * just typed. A sidecar that died should not cost all of that, so this replaces only the child, and
   * the renderer picks the new URL up by asking for the connection again.
   */
  ipcMain.handle("tm:sidecar-restart", async () => {
    if (sidecar && sidecar.pid) {
      // A sidecar still alive holds the port we are about to want back.
      try { sidecar.kill(); } catch { /* already gone is the state we wanted */ }
      sidecar = null;
    }
    readyConn = null;
    bootFailure = null;
    try {
      await startSidecar(() => undefined);
      return { ok: true };
    } catch (err) {
      const reason = String(err instanceof Error ? err.message : err);
      announceFailure(reason);
      return { ok: false, error: reason };
    }
  });
  // A splash that loads after a stage was reported replays the log instead of sitting idle forever.
  ipcMain.handle("tm:boot-log", () => bootLog);
  // Settings that outlive the window. One JSON file under userData, written whole on every change —
  // small enough that atomicity is a rename away, and never holding a secret (the renderer strips
  // key values before they get here; this side never accepts one).
  ipcMain.handle("tm:settings-load", async () => {
    try {
      return await readJson<Record<string, unknown>>(path.join(app.getPath("userData"), "settings.json"));
    } catch {
      return null;
    }
  });
  ipcMain.handle("tm:settings-save", async (_e, value: unknown) => {
    if (value === null || typeof value !== "object" || Array.isArray(value)) return false;
    try {
      await fs.promises.writeFile(
        path.join(app.getPath("userData"), "settings.json"),
        JSON.stringify(value, null, 2), "utf8");
      return true;
    } catch {
      return false;
    }
  });
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

/** The splash: small, fast, and the whole story of the boot until the app replaces it. */
function createSplash(): void {
  const mac = process.platform === "darwin";
  splashWindow = new BrowserWindow({
    width: 440,
    height: 620,
    backgroundColor: "#090c12",
    titleBarStyle: mac ? "hiddenInset" : "hidden",
    trafficLightPosition: mac ? { x: 14, y: 15 } : undefined,
    frame: mac ? undefined : false,
    show: false,
    resizable: false,
    maximizable: false,
    webPreferences: {
      preload: path.join(__dirname, "..", "preload", "index.js"),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });
  splashWindow.loadFile(path.join(__dirname, "..", "..", "splash.html"))
    .catch(() => { splashWindow?.loadURL("data:text/html,<body style=\"background:#090c12\"></body>"); });
  splashWindow.once("ready-to-show", () => splashWindow?.show());
}

/** The app window: created hidden, shown only once it has actually painted — see revealApp. */
function createAppWindow(): void {
  const mac = process.platform === "darwin";
  const appWin = new BrowserWindow({
    width: 1280,
    height: 860,
    minWidth: 760,
    minHeight: 520,
    backgroundColor: "#090c12",
    titleBarStyle: mac ? "hiddenInset" : "hidden",
    trafficLightPosition: mac ? { x: 14, y: 15 } : undefined,
    frame: mac ? undefined : false,
    show: false,
    webPreferences: {
      preload: path.join(__dirname, "..", "preload", "index.js"),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });
  watchWindowState(appWin);
  mainWindow = appWin;
  stage("renderer", "active", process.env.VITE_DEV ? "from the vite dev server" : "from the built bundle");
  // True while dev-mode connect retries are outstanding: during that window did-fail-load is the loop's
  // business, not a boot failure.
  let retrying = false;
  if (process.env.VITE_DEV) {
    // The dev server may still be waking up; a refused connection here is worth a few retries before
    // it counts as "not running". Every callback is destroy-safe: the window can die (splash's quit
    // button, app quit) while a retry is pending, and a `loadURL` on a destroyed window is an uncaught
    // exception in the main process — the crash dialog this guard exists to prevent.
    let tries = 0;
    let alive = true;
    retrying = true;
    appWin.on("closed", () => { alive = false; });
    const load = (): void => {
      if (!alive || appWin.isDestroyed()) { alive = false; return; }
      appWin.loadURL("http://127.0.0.1:5173").catch(() => {
        if (!alive || appWin.isDestroyed()) return;
        if (tries < 40) { tries += 1; setTimeout(load, 500); return; }
        retrying = false;
        rendererFailed("could not reach the dev server at http://127.0.0.1:5173 — is `npm run dev` running?");
      });
    };
    load();
    appWin.webContents.on("did-fail-load", () => {
      if (!alive || appWin.isDestroyed()) return;
      if (retrying && tries < 40) {
        tries += 1;
        setTimeout(load, 500);
      }
    });
  } else {
    appWin.loadFile(path.join(__dirname, "..", "..", "dist", "index.html"))
      .catch((err: Error) => rendererFailed(err.message));
  }
  appWin.webContents.on("did-fail-load", (_e, code, desc, _url, isMainFrame) => {
    // In dev the retry loop above owns failure; a main-frame failure here only means the boot failed
    // for real — the renderer page itself, not the server being late.
    if (isMainFrame && !revealed && !appWin.isDestroyed() && !retrying) rendererFailed(`${desc} (${code})`);
  });
  appWin.webContents.on("did-finish-load", () => {
    // Fires for the splash too; the renderer stage is only done once the *real* app is up.
    if (appWin.isDestroyed()) return;
    const url = appWin.webContents.getURL();
    const isRenderer = process.env.VITE_DEV ? url.startsWith("http://127.0.0.1:5173") : url.includes("dist");
    if (isRenderer) revealApp();
  });
  // A paint event that never arrives (a throttled hidden window, say) must not leave the app invisible
  // forever: after five seconds the handover happens anyway, worst case a frame early.
  setTimeout(revealApp, 5000);
}

/** How long the splash stays readable even on a warm boot, so the maze gets its moment. */
const SPLASH_MIN_MS = 2600;

/** The handover: the app takes the screen, the splash closes. Nothing goes dark between the two. */
function revealApp(): void {
  if (revealed || !mainWindow || mainWindow.isDestroyed() || !readyConn) return;
  revealed = true;
  stage("renderer", "done");
  const hold = SPLASH_MIN_MS - (Date.now() - bootedAt);
  setTimeout(() => {
    if (!mainWindow || mainWindow.isDestroyed()) return;
    mainWindow.show();
    const dead = splashWindow;
    splashWindow = null;
    if (dead && !dead.isDestroyed()) dead.close();
    mainWindow.focus();
  }, Math.max(0, hold));
}

/** The renderer never came up: say so on the splash, and discard the hidden window — the splash's
 * "try again" is the way out, and it relaunches the whole process rather than half of it. */
function rendererFailed(detail: string): void {
  stage("renderer", "failed", detail);
  if (!revealed && mainWindow && !mainWindow.isDestroyed()) {
    mainWindow.destroy();
    mainWindow = null;
  }
}

/**
 * The boot: sidecar up, handshake read, health confirmed — then, and only then, the real renderer,
 * loaded hidden behind the splash and revealed when it has painted. Every stage streams to the splash;
 * every failure fails into it.
 */
async function boot(): Promise<void> {
  const { cmd, args, note } = sidecarCommand();
  const label = args.length > 0 ? `${path.basename(cmd)} -m ${args[args.length - 1]}` : path.basename(cmd);
  stage("spawn", "active", note ? `${label} — ${note}` : label);
  try {
    await startSidecar(() => undefined);
  } catch (err) {
    const reason = String(err instanceof Error ? err.message : err);
    stage("spawn", "failed", reason);
    announceFailure(reason);
    return; // the splash holds the failure; the window stays up with a way out
  }
  stage("spawn", "done");
  createAppWindow();
}

const gotLock = app.requestSingleInstanceLock();
if (!gotLock) {
  app.quit();
} else {
  app.on("second-instance", () => {
    const w = mainWindow ?? splashWindow;
    if (w) { if (w.isMinimized()) w.restore(); w.focus(); }
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

    // The splash opens now; the sidecar boots underneath it. Nothing modal stands between the user and
    // the window — a failed boot is drawn where it happened.
    createSplash();
    bootedAt = Date.now();
    void boot();
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
