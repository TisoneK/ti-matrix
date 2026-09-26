/*
 * The renderer's half of TM1 — the same protocol module the sidecar speaks, in TypeScript.
 *
 * The shapes mirror `server/appserver/protocol.py`; the engine event payloads are
 * `EngineEvent.to_dict()` verbatim, so this file maps exactly what the engine emits and nothing else.
 *
 * The `runs*` channels are not TM1 — they never reach the sidecar. They are the preload's route to the
 * main process's filesystem, which is the only way a run can outlive the window that watched it.
 */

import { ArtifactMeta, RunArtifact } from "./core/types";

export interface WorldField {
  name: string;
  label: string;
  default: string | number | boolean;
  placeholder?: string;
  kind?: "checkbox";
}

export interface WorldInfo {
  name: string;
  title: string;
  note: string;
  fields: WorldField[];
}

export interface EngineEventFrame {
  seq: number;
  t_ms: number;
  kind: string;
  [key: string]: unknown;
}

/** Token totals across every call a hosted run's model made — `null` for `builtin` (no model, nothing
 * spent) and for an endpoint that never sent a `usage` object back. */
export interface Usage {
  calls: number;
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
}

export type Frame =
  | { type: "event"; [key: string]: unknown }
  | { type: "confirm-request"; id: string; action: { tool: string; args: Record<string, unknown>; label: string }; reason: string }
  | { type: "settled"; answer: string | null; reason: string | null; events: number; summary: string | null; record: string | null; learned: string | null; usage: Usage | null }
  | { type: "error"; message: string }
  | { type: "worlds"; worlds: WorldInfo[] };

export type Status = "connecting" | "ready" | "running" | "reconnecting" | "crashed";

/** Where a run's files live, handed over when the run begins. */
export interface RunStartInfo {
  id: string;
  dir: string;
  /** The run log the sidecar appends to — `ti_matrix.adapters.run_log` reads it back. */
  recordPath: string | null;
}

/** The window controls the rail draws itself, wherever the OS does not draw them. */
export interface TmWindow {
  minimize: () => Promise<void>;
  toggleMaximize: () => Promise<void>;
  close: () => Promise<void>;
  state: () => Promise<WindowState>;
  onState: (cb: (state: WindowState) => void) => void;
}

export interface WindowState {
  maximized: boolean;
  fullScreen: boolean;
}

/** What the preload exposes as `window.tm` — the renderer's whole view of the machine. */
export interface TmApi {
  connection: () => Promise<{ url: string }>;
  /** `process.platform` — "darwin" keeps its traffic lights, everyone else gets the rail's own buttons. */
  platform?: string;
  window?: TmWindow;
  onReady: (cb: (conn: { url: string }) => void) => void;
  onSidecarExit: (cb: (info: { code: number | null }) => void) => void;
  pickDirectory: () => Promise<string | null>;
  userDataPath: () => Promise<string>;
  versions?: () => { electron: string; chrome: string };
  /** The session library. Absent in a plain browser tab, and `core/library.ts` copes with that. */
  runsBegin?: (id: string, world: string, goal: string, config: Record<string, unknown>) => Promise<RunStartInfo | null>;
  runsSave?: (artifact: RunArtifact, meta: ArtifactMeta) => Promise<boolean>;
  runsList?: () => Promise<ArtifactMeta[]>;
  runsLoad?: (id: string) => Promise<RunArtifact | null>;
  runsDelete?: (id: string) => Promise<boolean>;
  runsDir?: () => Promise<string>;
  /** The file holding what previous runs in this world established. Absent in a plain browser tab. */
  memoryPath?: (world: string) => Promise<string | null>;
  /** Settings that outlive the window. Absent in a plain browser tab; `core/settings.ts` copes. */
  settingsLoad?: () => Promise<unknown>;
  settingsSave?: (value: unknown) => Promise<boolean>;
  /** Spawn a fresh engine under this same window — the way back from a sidecar that died. */
  sidecarRestart?: () => Promise<{ ok: boolean; error?: string }>;
}

export class Sidecar {
  /** How many times a socket that dropped on its own is reopened before the app calls it crashed. */
  static readonly ATTEMPTS = 8;

  private ws: WebSocket | null = null;
  private attempt = 0;
  private closed = false;
  private timer: ReturnType<typeof setTimeout> | null = null;
  private handlers: ((frame: Frame) => void)[] = [];
  private watchers: ((status: Status) => void)[] = [];
  private current: Status = "connecting";
  worlds: WorldInfo[] = [];

  constructor(private url: string) {}

  /** A socket that dies is not a silent thing: whoever draws the status hears about it. */
  get status(): Status {
    return this.current;
  }

  private setStatus(next: Status): void {
    if (next === this.current) return;
    this.current = next;
    for (const w of this.watchers) w(next);
  }

  onStatus(watcher: (status: Status) => void): () => void {
    this.watchers.push(watcher);
    return () => { this.watchers = this.watchers.filter((w) => w !== watcher); };
  }

  /**
   * Open the socket, and keep it open.
   *
   * A dropped socket used to be the end of the window: `onclose` set `crashed` and nothing ever tried
   * again, so a sidecar that blinked — or a laptop that slept — left the app reading "the sidecar is not
   * running — restart the app" with no way back except reloading the page. Now a close that nobody asked
   * for schedules another attempt, backing off 400ms → 6s so a sidecar that is genuinely gone is not
   * hammered, and the status says `reconnecting` while that is true rather than claiming a crash the
   * app has not established yet. Only `close()` — or giving up after ATTEMPTS — is final.
   *
   * What this does NOT do is resume a run. The sidecar cancels a run in flight when its socket goes
   * (see `ws_handler`), so a reconnect gets a live, empty engine back; the events already on screen stay
   * on screen, and the run they belonged to is over. Saying otherwise would be a lie the UI cannot keep.
   */
  connect(): void {
    this.closed = false;
    this.open();
  }

  private open(): void {
    let socket: WebSocket;
    try {
      socket = new WebSocket(this.url);
    } catch {
      this.retry();
      return;
    }
    this.ws = socket;
    socket.onopen = () => {
      this.attempt = 0;
      this.setStatus("ready");
    };
    socket.onmessage = (m) => {
      let frame: Frame | null = null;
      try { frame = JSON.parse(m.data as string) as Frame; } catch { return; }
      if (!frame) return;
      if (frame.type === "worlds") this.worlds = frame.worlds;
      for (const h of this.handlers) h(frame);
    };
    // onerror always precedes onclose for a failed socket, so the retry is scheduled in one place only.
    socket.onerror = () => { /* the close that follows is what we act on */ };
    socket.onclose = () => {
      if (socket !== this.ws) return; // a socket we already replaced; its close is not news
      this.ws = null;
      if (this.closed) return;
      this.retry();
    };
  }

  private retry(): void {
    if (this.closed) return;
    if (this.attempt >= Sidecar.ATTEMPTS) {
      this.setStatus("crashed");
      return;
    }
    this.setStatus("reconnecting");
    const wait = Math.min(6000, 400 * 2 ** this.attempt);
    this.attempt += 1;
    this.timer = setTimeout(() => { if (!this.closed) this.open(); }, wait);
  }

  /** Try again right now, from a button — the backoff starts over, because a person asked. */
  reconnect(): void {
    if (this.timer !== null) { clearTimeout(this.timer); this.timer = null; }
    this.attempt = 0;
    this.closed = false;
    if (this.ws) { const dead = this.ws; this.ws = null; dead.close(); }
    this.setStatus("connecting");
    this.open();
  }

  /** Deliberate teardown: no retry follows this one. */
  close(): void {
    this.closed = true;
    if (this.timer !== null) { clearTimeout(this.timer); this.timer = null; }
    const dead = this.ws;
    this.ws = null;
    if (dead) dead.close();
  }

  onFrame(handler: (frame: Frame) => void): () => void {
    this.handlers.push(handler);
    return () => { this.handlers = this.handlers.filter((h) => h !== handler); };
  }

  goal(text: string, world: string, config: Record<string, unknown>,
       options: { record?: string | null; remember?: string | null;
                  budget?: Record<string, number> } = {}): void {
    this.send({
      type: "goal", text, world, config,
      ...(options.record ? { record: options.record } : {}),
      // `remember` turns on the engine's own memory: it loads this world's record before the run and
      // saves it after, which is what makes `recall` and `LearningProposer` exist for that run.
      ...(options.remember ? { remember: options.remember } : {}),
      ...(options.budget ? { budget: options.budget } : {}),
    });
  }

  confirm(id: string, granted: boolean): void {
    this.send({ type: "confirm-response", id, granted });
  }

  stop(): void {
    this.send({ type: "stop" });
  }

  private send(frame: Record<string, unknown>): void {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) this.ws.send(JSON.stringify(frame));
  }
}
