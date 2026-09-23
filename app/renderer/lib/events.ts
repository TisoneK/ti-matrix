/*
 * Turning the engine's events into the one line each of them deserves.
 *
 * The engine's event kinds and their payload keys are the contract (`ti_matrix/search.py`, `EngineEvent`);
 * this file reads those keys and invents none. Anything unrecognised still renders — a run must never go
 * quiet because the UI met a kind it had not been taught.
 */

import { EngineEventFrame } from "../protocol";
import { formatElapsed, pct } from "./format";

export interface MoveOption {
  label: string;
  why: string;
}

export interface EventView {
  badge: string;
  tone: "plain" | "ok" | "fail";
  detail: string;
  moves?: MoveOption[];
  meta?: string;
}

export type Group = "probes" | "moves" | "notes";

export const FILTERS: { id: Group | "all"; label: string }[] = [
  { id: "all", label: "all" },
  { id: "probes", label: "probes" },
  { id: "moves", label: "moves" },
  { id: "notes", label: "notes" },
];

const MOVES: ReadonlySet<string> = new Set(["candidates", "selected", "evaluation", "backtrack"]);

export function groupOf(kind: string): Group {
  if (kind === "probe") return "probes";
  return MOVES.has(kind) ? "moves" : "notes";
}

export function describeEvent(e: EngineEventFrame): EventView {
  const str = (k: string): string => (e[k] === undefined || e[k] === null ? "" : String(e[k]));
  const kind = e.kind;

  switch (kind) {
    case "candidates": {
      const moves = (e["moves"] as MoveOption[] | undefined) ?? [];
      return { badge: "candidates", tone: "plain", detail: `${moves.length} move${moves.length === 1 ? "" : "s"} proposed`,
               moves: moves.map((m) => ({ label: m.label, why: m.why })) };
    }
    case "probe": {
      const ok = Boolean(e["ok"]);
      const predicted = e["predicted"] ? " (predicted)" : "";
      return {
        badge: ok ? "probe" : "probe failed",
        tone: ok ? "ok" : "fail",
        detail: `${str("move")}${predicted}`,
        moves: [{ label: str("excerpt"), why: "" }],
        meta: e["ms"] === undefined ? undefined : formatElapsed(Number(e["ms"])),
      };
    }
    case "evaluation":
      return { badge: "evaluation", tone: "plain", detail: `${str("move")} → progress ${pct(e["progress"])}` };
    case "selected":
      return { badge: "selected", tone: "plain", detail: `taking ${str("move")} · progress ${pct(e["progress"])}` };
    case "backtrack":
      return { badge: "backtrack", tone: "plain", detail: `retreating to depth ${str("to_depth")}` };
    case "state": {
      const facts = Number(e["facts"] ?? 0);
      const failed = Number(e["failed"] ?? 0);
      return {
        badge: "state",
        tone: "plain",
        detail: `depth ${str("depth")} · progress ${pct(e["progress"])} · ${facts} fact${facts === 1 ? "" : "s"} known · ${failed} ruled out`,
      };
    }
    case "confirmation":
      return {
        badge: "confirmation",
        tone: Boolean(e["granted"]) ? "ok" : "fail",
        detail: `${str("move")} — ${e["granted"] ? "granted" : "refused"}: ${str("why")}`,
      };
    case "needs_confirmation":
      return {
        badge: "needs confirmation",
        tone: "fail",
        detail: `${str("move")} — nobody granted it${str("confirmer_said") ? `: ${str("confirmer_said")}` : ""}`,
      };
    case "done":
      return { badge: "done", tone: "ok", detail: str("answer") || "the run settled", meta: `${str("model_calls")} model calls` };
    case "stopped": {
      const answer = str("partial_answer");
      const head = `stopped: ${str("reason") || "no reason given"} — the goal was not settled`;
      return { badge: "stopped", tone: "fail", detail: answer ? `${head}\n${answer}` : head };
    }
    default:
      return { badge: kind || "event", tone: "plain", detail: "" };
  }
}
