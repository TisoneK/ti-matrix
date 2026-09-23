/*
 * The renderer's half of TM1 — the same protocol module the sidecar speaks, in TypeScript.
 *
 * The shapes mirror `server/appserver/protocol.py`; the engine event payloads are
 * `EngineEvent.to_dict()` verbatim, so this file maps exactly what the engine emits and nothing else.
 */

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

export type Frame =
  | { type: "event"; [key: string]: unknown }
  | { type: "confirm-request"; id: string; action: { tool: string; args: Record<string, unknown>; label: string }; reason: string }
  | { type: "settled"; answer: string | null; reason: string | null; events: number; summary: string | null; record: string | null; learned: string | null }
  | { type: "error"; message: string }
  | { type: "worlds"; worlds: WorldInfo[] };

export type Status = "connecting" | "ready" | "running" | "crashed";

export class Sidecar {
  private ws: WebSocket | null = null;
  private handlers: ((frame: Frame) => void)[] = [];
  status: Status = "connecting";
  worlds: WorldInfo[] = [];

  constructor(private url: string) {}

  connect(): void {
    this.ws = new WebSocket(this.url);
    this.ws.onopen = () => { this.status = "ready"; };
    this.ws.onmessage = (m) => {
      let frame: Frame | null = null;
      try { frame = JSON.parse(m.data as string) as Frame; } catch { return; }
      if (!frame) return;
      if (frame.type === "worlds") this.worlds = frame.worlds;
      for (const h of this.handlers) h(frame);
    };
    this.ws.onclose = () => { this.status = "crashed"; };
    this.ws.onerror = () => { this.status = "crashed"; };
  }

  onFrame(handler: (frame: Frame) => void): () => void {
    this.handlers.push(handler);
    return () => { this.handlers = this.handlers.filter((h) => h !== handler); };
  }

  goal(text: string, world: string, config: Record<string, unknown>): void {
    this.send({ type: "goal", text, world, config });
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
