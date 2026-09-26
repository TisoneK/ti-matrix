/*
 * The fold: a run's raw events, turned into the turns of the search loop a person can read.
 *
 * One iteration of `StateEngine._steps` emits a fixed little sentence:
 *
 *     state ─► candidates ─► (confirmation | needs_confirmation)* ─► probe* ─► evaluation*
 *           ─► selected ─► state ─► (done)?        or        ─► backtrack        or ─► stopped
 *
 * so a `Decision` is exactly one of those iterations, and this file is the only place that knows the
 * grammar. Every panel downstream works on decisions; the raw events stay behind them.
 *
 * The fold is pure and total: give it the first N events and it gives the decisions in those events, in
 * order. That is what makes the scrubber a one-line operation instead of a re-simulation.
 */

import { Candidate, Decision, DecisionKind, EngineEventFrame, Flag } from "./types";
import { pct } from "./format";

/** Below this, a move the engine still made is a guess — it went without much conviction. */
export const GUESS_BELOW = 0.5;

/**
 * The maze cell a move label lands on: `step(cell=1,3, direction=east)` names its origin and its
 * heading, and the destination is one delta away. This is the map's end of the shared cursor — without
 * it, hovering a ledger row could light the tree but never the map. Null for moves that are not steps.
 */
export function cellOf(move: string | null): string | null {
  if (!move) return null;
  const m = /cell=\s*(\d+)\s*,\s*(\d+)/.exec(move);
  const dir = /direction=\s*(north|south|east|west)/.exec(move);
  if (!m || !dir) return null;
  const d = dir[1] === "north" ? [0, -1] : dir[1] === "south" ? [0, 1] : dir[1] === "east" ? [1, 0] : [-1, 0];
  return `${Number(m[1]) + d[0]},${Number(m[2]) + d[1]}`;
}

interface StateInfo {
  depth: number;
  progress: number;
  facts: string[];
  modelCalls: number;
}

const numeric = (value: unknown, fallback: number): number =>
  typeof value === "number" && Number.isFinite(value) ? value : fallback;

const text = (value: unknown, fallback = ""): string => (value === undefined || value === null ? fallback : String(value));

function factsOf(event: EngineEventFrame, fallback: string[]): string[] {
  return Array.isArray(event["fact_list"]) ? (event["fact_list"] as unknown[]).map(String) : fallback;
}

function readState(event: EngineEventFrame, previous: StateInfo): StateInfo {
  return {
    depth: numeric(event["depth"], previous.depth),
    progress: numeric(event["progress"], previous.progress),
    facts: factsOf(event, previous.facts),
    modelCalls: numeric(event["model_calls"], previous.modelCalls),
  };
}

/** The moves a `candidates` event proposed, in the order the model offered them. */
function candidatesOf(event: EngineEventFrame): Candidate[] {
  const moves = Array.isArray(event["moves"]) ? (event["moves"] as Record<string, unknown>[]) : [];
  return moves.map((m) => ({
    fp: text(m["fp"]),
    label: text(m["label"]),
    tool: text(m["tool"]),
    why: text(m["why"]),
  }));
}

function headlineFor(kind: DecisionKind, move: string | null, reason: string | undefined, confidence: number): string {
  switch (kind) {
    case "move":
      return `took ${move ?? "a move"} · believed ${pct(confidence)}`;
    case "backtrack":
      return "nothing here beat standing still — retreated";
    case "done":
      return "the goal was reached, and the world confirmed it";
    case "needs-action":
      return "the goal needs an action this engine may not perform";
    case "stopped":
      return `the run stopped: ${reason ?? "no reason given"}`;
  }
}

/** One search iteration, being assembled. */
interface Iteration {
  from: number;
  options: Candidate[];
  /** How many actions the proposer chose from, when it could say. */
  available?: number;
  refused: string[];
  kind: DecisionKind | null;
  chosenFp: string | null;
  reason: string | undefined;
  answer: string | null;
  partialAnswer: string | null;
  answerBasis: string | null;
  settled: boolean;
  predictedResult: string;
}

/**
 * Every iteration in the log, with what the agent believed and why.
 *
 * `events` is expected to be a prefix of a run's log — pass the whole thing for the finished run, or
 * `events.slice(0, cursor + 1)` for the run as it stood at any point on the scrubber.
 */
export function foldDecisions(events: EngineEventFrame[]): Decision[] {
  const decisions: Decision[] = [];
  // The states the run has stood on, by depth. A backtrack restores an ancestor, and the decision after
  // it has to be measured against that ancestor's progress rather than the abandoned branch's.
  const byDepth = new Map<number, StateInfo>();
  let current: StateInfo = { depth: -1, progress: 0, facts: [], modelCalls: 0 };

  let i = 0;
  while (i < events.length) {
    const head = events[i];

    if (head.kind === "state") {
      current = readState(head, current);
      byDepth.set(current.depth, current);
      i += 1;
      continue;
    }
    if (head.kind !== "candidates" && head.kind !== "stopped" && head.kind !== "done") {
      i += 1; // an event the iteration grammar has no slot for; the inspector still shows it raw
      continue;
    }

    // ── a terminal event with no fan in front of it — the budget check runs before the proposer ──
    if (head.kind === "done" || head.kind === "stopped") {
      const kind: DecisionKind = head.kind === "done" ? "done"
        : head["reason"] === "needs_action" ? "needs-action" : "stopped";
      const reason = head["reason"] === undefined ? undefined : String(head["reason"]);
      const predicted = head["predicted"] as Record<string, unknown> | undefined;
      current = { ...current, modelCalls: numeric(head["model_calls"], current.modelCalls) };
      decisions.push({
        index: decisions.length,
        kind,
        depth: Math.max(0, current.depth),
        from: i,
        to: i,
        move: kind === "needs-action" ? text(head["needs"]) || null : null,
        cell: null,
        confidence: kind === "done" ? 1 : 0,
        priorProgress: current.progress,
        evidence: kind === "needs-action" ? text(predicted?.["result"]) : "",
        partialAnswer: text(head["partial_answer"]) || null,
        answerBasis: text(head["answer_basis"]) || null,
        headline: headlineFor(kind, text(head["needs"]) || null, reason, 0),
        flags: [kind === "done" ? "confirmed" : "forced"],
        options: [],
        available: undefined,
        refused: [],
        facts: current.facts,
        modelCalls: current.modelCalls,
        tMs: head.t_ms,
        reason,
        answer: head["answer"] === undefined ? null : text(head["answer"]),
        settled: kind === "done",
      });
      i += 1;
      continue;
    }

    // ── an iteration begins ──────────────────────────────────────────────────
    const it: Iteration = {
      from: i,
      options: candidatesOf(head),
      // How many actions the proposer was choosing from, when it could say. Absent for a world where
      // the question has no answer — a filesystem admits any path.
      available: typeof head["available"] === "number" ? (head["available"] as number) : undefined,
      refused: [],
      kind: null,
      chosenFp: null,
      reason: undefined,
      answer: null,
      partialAnswer: null,
      answerBasis: null,
      settled: false,
      predictedResult: "",
    };
    const priorProgress = current.progress;
    i += 1;

    while (i < events.length) {
      const e = events[i];

      if (e.kind === "confirmation" || e.kind === "needs_confirmation") {
        // A decision was made about an action that changes the world; refused actions are recorded, not
        // dropped, because "it wanted to and was not allowed" is the most interesting row a run can have.
        if (!e["granted"]) it.refused.push(text(e["move"], text(e["fp"])));
        i += 1;
        continue;
      }
      if (e.kind === "probe") {
        const option = it.options.find((o) => o.fp === text(e["fp"]));
        if (option) {
          option.ok = Boolean(e["ok"]);
          option.excerpt = text(e["excerpt"]);
          option.ms = numeric(e["ms"], 0);
          option.predicted = Boolean(e["predicted"]);
          if (!option.ok && option.predicted) it.predictedResult = text(e["excerpt"]);
        }
        i += 1;
        continue;
      }
      if (e.kind === "evaluation") {
        const option = it.options.find((o) => o.fp === text(e["fp"]));
        if (option) {
          option.progress = numeric(e["progress"], 0);
          option.done = Boolean(e["done"]);
          option.reason = text(e["reason"]);
        }
        i += 1;
        continue;
      }
      if (e.kind === "selected") {
        it.kind = "move";
        it.chosenFp = text(e["fp"]);
        i += 1;
        continue;
      }
      if (e.kind === "backtrack") {
        it.kind = "backtrack";
        i += 1;
        break;
      }
      if (e.kind === "stopped") {
        // A stop lands at the end of an iteration far more often than in front of one: the engine folds
        // the last move, then reports why it is not taking another. The synthesizer's answer rides on
        // this event, so it has to be captured here — reading only the no-fan path above is what left
        // every real stopped run's last word on the floor.
        it.kind = "stopped";
        it.reason = text(e["reason"], "stopped");
        it.partialAnswer = text(e["partial_answer"]) || null;
        it.answerBasis = text(e["answer_basis"]) || null;
        i += 1;
        break;
      }
      if (e.kind === "done") {
        it.kind = "done";
        it.answer = text(e["answer"]);
        it.settled = true;
        i += 1;
        break;
      }
      if (e.kind === "state") {
        // The state a selection produced. Absorbing it here keeps the iteration whole — "took this step,
        // and here is what the run then knew" — instead of splitting it into two rows.
        current = readState(e, current);
        byDepth.set(current.depth, current);
        i += 1;
        continue;
      }
      break; // the next iteration's `candidates` — not ours to consume
    }

    // The log ran out mid-iteration: the run is live, standing between proposing and deciding. Report the
    // turn rather than dropping it, so the map shows where it is and the ledger shows it thinking.
    if (it.kind === null) it.kind = "move";

    const chosen = it.chosenFp === null ? undefined : it.options.find((o) => o.fp === it.chosenFp);
    if (chosen) chosen.chosen = true;

    let depth = current.depth;
    if (it.kind === "backtrack") {
      const toDepth = numeric(events[i - 1]?.["to_depth"], 0);
      current = byDepth.get(toDepth) ?? { ...current, depth: toDepth };
      depth = current.depth;
    }

    // A settle is measured by the same yardstick as any other move — the evaluator's score for the step
    // that settled it — and only falls back to certainty for a run that settled without proposing.
    const confidence = chosen !== undefined ? numeric(chosen.progress, 0)
      : it.kind === "done" ? 1
        : 0;
    decisions.push({
      index: decisions.length,
      kind: it.kind,
      depth: Math.max(1, depth + (it.kind === "backtrack" ? 1 : 0)),
      from: it.from,
      to: Math.max(it.from, i - 1),
      move: chosen?.label ?? null,
      cell: cellOf(chosen?.label ?? null),
      confidence,
      priorProgress,
      evidence: chosen ? text(chosen.excerpt) : "",
      headline: headlineFor(it.kind, chosen?.label ?? null, it.reason, confidence),
      flags: flagsFor(it.kind, it.options, chosen, confidence, priorProgress),
      options: it.options,
      available: it.available,
      refused: it.refused,
      facts: current.facts,
      modelCalls: current.modelCalls,
      tMs: events[Math.max(it.from, i - 1)].t_ms,
      reason: it.reason,
      answer: it.answer,
      partialAnswer: it.partialAnswer,
      answerBasis: it.answerBasis,
      settled: it.settled,
    });
  }

  return decisions;
}

export interface FinalAnswer {
  text: string;
  /** A settled `done` answer is verified against the world; a stopped run's is the best a synthesizer
   * could make of the facts actually established — real, but never checked against the world itself. */
  verified: boolean;
  /** The engine's own note on where an unverified answer came from. Null for a settled one. */
  basis: string | null;
}

/**
 * The run's own last word, when it said one.
 *
 * A settled run's `answer` (kind `"done"`) is the one the engine itself verified. A run that stopped
 * without settling carries `partial_answer` instead — a synthesizer's best reading of the facts,
 * labelled unverified rather than hidden, the way the engine itself reports it. `null` when neither
 * exists: the run is still going, stopped with nothing to answer from, or hit a world with no
 * synthesizer wired in front of it (`builtin`).
 */
export function finalAnswerOf(decisions: Decision[]): FinalAnswer | null {
  const last = decisions[decisions.length - 1];
  if (!last) return null;
  if (last.kind === "done" && last.answer) return { text: last.answer, verified: true, basis: null };
  if (last.kind === "stopped" && last.partialAnswer) {
    return { text: last.partialAnswer, verified: false, basis: last.answerBasis ?? null };
  }
  return null;
}

/**
 * The flags a decision earns — each a distinct claim about the run, each with its own test. More than one
 * can apply to the same decision, which is information rather than a conflict.
 *
 * `confirmed`  the belief held: the move it committed to scored better than standing still.
 * `surprise`   the world disagreed with an expectation: a move the evaluator valued was refused by the
 *              world, or a move the model predicted failed its own prediction. A move the model expected
 *              nothing of that failed is not a surprise — that is how a probe is supposed to work.
 * `guess`      it moved without conviction — the evaluator's own score for the move was low.
 * `backtrack`  it gave up a branch and retreated to an ancestor.
 * `forced`     the run ended because a limit or the world ran out, not because the goal was met.
 */
export function flagsFor(
  kind: DecisionKind,
  options: Candidate[],
  chosen: Candidate | undefined,
  confidence: number,
  priorProgress: number,
): Flag[] {
  if (kind === "done") return ["confirmed"];

  const flags: Flag[] = [];
  if (kind === "backtrack") flags.push("backtrack");
  if (kind === "stopped" || kind === "needs-action") flags.push("forced");

  if (kind === "move") {
    if (chosen?.ok === true && confidence > priorProgress) flags.push("confirmed");
    if (confidence < GUESS_BELOW) flags.push("guess");
  }

  const expectedSomething = options.some((o) => o.ok === false && (o.progress ?? 0) > 0);
  const betrayedItsOwnPrediction = options.some((o) => o.ok === false && o.predicted === true);
  if (expectedSomething || betrayedItsOwnPrediction) flags.push("surprise");

  return flags;
}
