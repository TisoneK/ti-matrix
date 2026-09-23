/*
 * Preload: the renderer's entire view of the machine — contextIsolation on, no node integration.
 *
 * The renderer never sees Node, Electron, or the filesystem. It sees `window.tm`, and `window.tm`
 * is five functions. The sidecar's token is spoken only inside this preload: the renderer gets a
 * ready signal and a URL, never the credential itself.
 */
import { contextBridge, ipcRenderer } from "electron";

const api = {
  // main -> renderer lifecycle
  onReady: (cb: (conn: { url: string }) => void) => {
    ipcRenderer.on("tm:ready", (_e, conn) => cb(conn));
  },
  onSidecarExit: (cb: (info: { code: number | null }) => void) => {
    ipcRenderer.on("tm:sidecar-exit", (_e, info) => cb(info));
  },
  // renderer -> main requests
  connection: (): Promise<{ url: string }> => ipcRenderer.invoke("tm:connection"),
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
  versions: () => ({ electron: process.versions.electron, chrome: process.versions.chrome }),
};

contextBridge.exposeInMainWorld("tm", api);

export type TmApi = typeof api;
