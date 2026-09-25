/*
 * One probe, taken apart.
 *
 * Every world view is built from the same raw material: the probe events a run produced. The engine labels
 * an action as `tool(k=v, k=v)` (`Action.label()` in `ti_matrix/protocols.py`) and the world answers with a
 * sentence — so a view parses the label for what was asked and the excerpt for what came back.
 */

import { EngineEventFrame } from "../../protocol";

export interface Probe {
  seq: number;
  tMs: number;
  /** The action as the engine labelled it, verbatim: `read_file(path=/a/b.txt)`. */
  move: string;
  tool: string;
  args: Record<string, string>;
  ok: boolean;
  predicted: boolean;
  /** The world's answer, whitespace-collapsed — the same text the engine's own facts carry. */
  excerpt: string;
}

const LABEL = /^\s*([A-Za-z_][\w-]*)\s*\((.*)\)\s*$/;

function parseArgs(inner: string): Record<string, string> {
  const args: Record<string, string> = {};
  if (!inner.trim()) return args;
  // Values may contain commas and equals signs (a path, a phrase, a CSS selector), so a new argument
  // starts only where a bare `name=` follows a comma — never inside a value.
  for (const part of inner.split(/,\s*(?=[A-Za-z_][\w-]*=)/)) {
    const eq = part.indexOf("=");
    if (eq === -1) continue;
    args[part.slice(0, eq).trim()] = part.slice(eq + 1).trim();
  }
  return args;
}

export function probesOf(events: EngineEventFrame[]): Probe[] {
  const out: Probe[] = [];
  for (const e of events) {
    if (e.kind !== "probe") continue;
    const move = String(e["move"] ?? "");
    const label = LABEL.exec(move);
    out.push({
      seq: e.seq,
      tMs: e.t_ms,
      move,
      tool: label ? label[1] : move.split("(")[0],
      args: label ? parseArgs(label[2]) : {},
      ok: Boolean(e["ok"]),
      predicted: Boolean(e["predicted"]),
      excerpt: String(e["excerpt"] ?? ""),
    });
  }
  return out;
}

/** Any event kind, filtered — the views mostly want probes, but a few want the run's own milestones. */
export function kindsOf<T extends string>(events: EngineEventFrame[], kinds: readonly T[]): EngineEventFrame[] {
  const wanted = new Set<string>(kinds);
  return events.filter((e) => wanted.has(e.kind));
}
