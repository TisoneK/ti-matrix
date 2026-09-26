/*
 * Preload: the renderer's entire view of the machine — contextIsolation on, no node integration.
 *
 * The renderer never sees Node, Electron, or the filesystem. It sees `window.tm`, and `window.tm`
 * is five functions. The sidecar's token is spoken only inside this preload: the renderer gets a
 * ready signal and a URL, never the credential itself.
 */
import { contextBridge, ipcRenderer } from "electron";

export interface BootStageReport { id: "spawn" | "handshake" | "health" | "renderer"; status: "active" | "done" | "failed"; detail?: string }

const api = {
  // main -> renderer lifecycle
  onReady: (cb: (conn: { url: string }) => void) => {
    ipcRenderer.on("tm:ready", (_e, conn) => cb(conn));
  },
  onSidecarExit: (cb: (info: { code: number | null }) => void) => {
    ipcRenderer.on("tm:sidecar-exit", (_e, info) => cb(info));
  },
  // The boot, narrated: one report per stage as main clears or fails it. The splash is the audience.
  onBootStage: (cb: (stage: BootStageReport) => void) => {
    ipcRenderer.on("tm:boot-stage", (_e, report) => cb(report));
  },
  // renderer -> main requests
  connection: (): Promise<{ url: string }> => ipcRenderer.invoke("tm:connection"),
  // Stages reported before this page finished loading, so a splash that arrives late still shows them.
  bootLog: (): Promise<BootStageReport[]> => ipcRenderer.invoke("tm:boot-log"),
  // The splash's "try again": a fresh process, because a half-started sidecar may hold the port.
  relaunch: (): Promise<void> => ipcRenderer.invoke("tm:relaunch"),
  // The window's "try again": a new engine under the same window, so a dead sidecar does not cost the
  // run on screen, the library, or the config someone just typed.
  sidecarRestart: (): Promise<{ ok: boolean; error?: string }> => ipcRenderer.invoke("tm:sidecar-restart"),
  // The window's own chrome. The rail is the title bar, so these are the buttons it draws — on macOS the
  // OS keeps its traffic lights instead and the rail leaves room for them.
  platform: process.platform,
  window: {
    minimize: (): Promise<void> => ipcRenderer.invoke("tm:window-minimize"),
    toggleMaximize: (): Promise<void> => ipcRenderer.invoke("tm:window-toggle-maximize"),
    close: (): Promise<void> => ipcRenderer.invoke("tm:window-close"),
    state: (): Promise<{ maximized: boolean; fullScreen: boolean }> => ipcRenderer.invoke("tm:window-state"),
    onState: (cb: (state: { maximized: boolean; fullScreen: boolean }) => void) => {
      ipcRenderer.on("tm:window-state", (_e, state) => cb(state));
    },
  },
  pickDirectory: (): Promise<string | null> => ipcRenderer.invoke("tm:pick-directory"),
  userDataPath: (): Promise<string> => ipcRenderer.invoke("tm:user-data"),
  // The session library. The renderer has no filesystem of its own; these five calls are all of it, and
  // each one is answered by a handler that validates the id before it touches a path.
  runsBegin: (id: string, world: string, goal: string, config: unknown) =>
    ipcRenderer.invoke("tm:run-begin", id, world, goal, config),
  runsSave: (artifact: unknown, meta: unknown) => ipcRenderer.invoke("tm:run-save", artifact, meta),
  runsList: () => ipcRenderer.invoke("tm:runs-list"),
  runsLoad: (id: string) => ipcRenderer.invoke("tm:run-load", id),
  runsDelete: (id: string) => ipcRenderer.invoke("tm:run-delete", id),
  runsDir: (): Promise<string> => ipcRenderer.invoke("tm:runs-dir"),
  // Where a world's accumulated experience is kept, so a run can carry what earlier ones learned.
  memoryPath: (world: string): Promise<string | null> => ipcRenderer.invoke("tm:memory-path", world),
  // Settings that outlive the window. The value of an API key is not a setting and never travels here:
  // the renderer sends the env-var *name* and the run-time key only ever goes through the goal config.
  settingsLoad: (): Promise<unknown> => ipcRenderer.invoke("tm:settings-load"),
  settingsSave: (value: unknown): Promise<boolean> => ipcRenderer.invoke("tm:settings-save", value),
  // The key at rest, kept behind its own three channels so it never shares a call with the settings
  // above. Encryption happens in main (`safeStorage`); nothing decrypted is written anywhere.
  keyLoad: (): Promise<{ base_url: string; key: string } | null> => ipcRenderer.invoke("tm:key-load"),
  keySave: (value: { base_url: string; api_key: string }): Promise<boolean> =>
    ipcRenderer.invoke("tm:key-save", value),
  keyClear: (): Promise<boolean> => ipcRenderer.invoke("tm:key-clear"),
  versions: () => ({ electron: process.versions.electron, chrome: process.versions.chrome }),
};

contextBridge.exposeInMainWorld("tm", api);

export type TmApi = typeof api;
