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
  pickDirectory: (): Promise<string | null> => ipcRenderer.invoke("tm:pick-directory"),
  userDataPath: (): Promise<string> => ipcRenderer.invoke("tm:user-data"),
  versions: () => ({ electron: process.versions.electron, chrome: process.versions.chrome }),
};

contextBridge.exposeInMainWorld("tm", api);

export type TmApi = typeof api;
