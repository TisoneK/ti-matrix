/*
 * What the run is doing right now, said in one line.
 *
 * The engine narrates everything it does into events, and the panels show the parts that have already
 * happened — but the model's own calls are the longest stretches in a run (15-45 seconds each) and they
 * produce no data, only time. What the window showed during them was a lamp and a clock, so the run's
 * richest work looked like nothing happening. This reads the tail of the event log and turns the
 * *position in the loop* into a sentence, with the elapsed silence ticking beside it — so the waiting
 * is legible as waiting on the model, not as the app being stuck.
 *
 * The engine's vocabulary is kept, not humanised (propose, evaluate, candidates, probes): the reader
 * of this window is the engine's builder.
 */

import { EngineEventFrame } from "../protocol";

export interface Narration {
  /** The sentence: where the run is in its loop. */
  text: string;
  /** Seconds since the last event — ticks up while the model thinks. */
  quietFor: number;
  /** True while the current stretch is inside a model call (the long, honest silences). */
  thinking: boolean;
  /** The event kind the sentence came from — so a test pins the mapping kind by kind. */
  from: string;
}

/** `read_file(path=…, contains=…)` -> `read_file` — the tool is the identity, the args are noise. */
const shortMove = (move: unknown): string => {
  const s = String(move ?? "");
  const i = s.indexOf("(");
  return i > 0 ? s.slice(0, i) : s;
};

const msText = (ms: number): string => (ms < 1000 ? `${ms}ms` : `${(ms / 1000).toFixed(1)}s`);

export function narrate(events: EngineEventFrame[], nowMs: number): Narration | null {
  const last = events[events.length - 1];
  if (!last) return null;
  const quietFor = Math.max(0, Math.round((nowMs - last.t_ms) / 1000));
  const base = { quietFor };

  switch (last.kind) {
    case "thinking": {
      // A model call is in flight. `attempt: 2` is the engine's retry of a scoring call that came
      // back empty — worth naming, because it is the engine spending a second chance, not stalling.
      const attempt = Number(last.attempt ?? 1);
      const evaluating = String(last.phase ?? "") === "evaluate";
      return {
        ...base, thinking: true, from: "thinking",
        text: evaluating
          ? (attempt > 1 ? "weighing what it found — retrying the scoring call with a shorter view"
                         : "weighing what it found")
          : "choosing what to try next",
      };
    }
    case "candidates": {
      const moves = Array.isArray(last.moves) ? (last.moves as { label?: unknown }[]) : [];
      const tools = [...new Set(moves.map((m) => shortMove(m?.label)))].slice(0, 3);
      const listing = tools.length > 0
        ? ` — ${tools.join(", ")}${tools.length < moves.length ? "…" : ""}`
        : "";
      const available = Number(last.available ?? -1);
      const n = moves.length;
      return {
        ...base, thinking: false, from: "candidates",
        text: available >= 0
          ? `choosing among ${available} possible moves (${n} proposed${listing})`
          : `${n} candidate${n === 1 ? "" : "s"} proposed${listing}`,
      };
    }
    case "probe": {
      const ok = Boolean(last.ok);
      return {
        ...base, thinking: false, from: "probe",
        text: `${ok ? "read" : "refused"} — ${shortMove(last.move)} took ${msText(Number(last.ms ?? 0))}`,
      };
    }
    case "evaluation": {
      const pct = Math.round(Number(last.progress ?? 0) * 100);
      return {
        ...base, thinking: false, from: "evaluation",
        text: last.done ? `a candidate claims the goal is settled — ${pct}%`
                        : `scored: best candidate at ${pct}%`,
      };
    }
    case "selected": {
      const pct = Math.round(Number(last.progress ?? 0) * 100);
      return { ...base, thinking: false, from: "selected", text: `took ${shortMove(last.move)} — belief ${pct}%` };
    }
    case "state": {
      const depth = Number(last.depth ?? 0);
      return { ...base, thinking: false, from: "state", text: depth === 0 ? "at the start" : `state ${depth} reached` };
    }
    case "backtrack":
      return { ...base, thinking: false, from: "backtrack", text: "nothing beat where it stood — backing up" };
    case "confirmation":
      return {
        ...base, thinking: false, from: "confirmation",
        text: `asked about ${shortMove(last.move)} — ${last.granted ? "granted" : "refused"}`,
      };
    case "needs_confirmation":
      return { ...base, thinking: false, from: "needs_confirmation", text: `${shortMove(last.move)} changes something — it needs a decision` };
    case "done":
      return { ...base, thinking: false, from: "done", text: "settled" };
    case "stopped":
      return { ...base, thinking: false, from: "stopped", text: "stopped" };
    default:
      // An unknown kind still gets a heartbeat rather than an empty line — the run is doing *something*.
      return { ...base, thinking: false, from: String(last.kind ?? "unknown"), text: "working" };
  }
}
