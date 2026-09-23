/*
 * One cursor, four projections.
 *
 * This is the hinge the whole window turns on. A run is a list of events; a cursor is a decision index;
 * and every panel is a pure function of the two:
 *
 *     events ─┬─► decisions (the ledger)
 *             ├─► knowledge (the map, at the cursor)
 *             ├─► tree      (the search, at the cursor)
 *             └─► trust     (the curve, up to the cursor)
 *
 * Because it is pure, playback is free: dragging the scrubber back re-derives the map and the tree as they
 * were, rather than replaying a recording. Because it is one function, compare mode is free too — the two
 * runs are two calls with two cursors.
 *
 * Cost is O(events) per call. Runs here are hundreds of events, and the fold is arithmetic over them, so a
 * scrub re-derives in well under a frame; caching would be more machinery than it saves.
 */

import { Decision, EngineEventFrame } from "./types";
import { foldDecisions } from "./decisions";
import { MazeKnowledge, readKnowledge } from "./knowledge";
import { readTree, SearchTree } from "./tree";
import { readTrust, TrustCurve } from "./trust";

export interface Projection {
  /** Every decision in the log so far — the ledger's rows, and the scrubber's range. */
  decisions: Decision[];
  /** The decision the cursor is on, when there is one. */
  at: Decision | null;
  /** What the run believed when that decision finished. */
  knowledge: MazeKnowledge;
  tree: SearchTree;
  /** The confidence curve as it stood at the cursor — not as the run ended. */
  trust: TrustCurve;
  /** The last event the cursor has passed. */
  eventIndex: number;
  /**
   * The run's own progress at the cursor — the state's accumulated score, not the last decision's
   * belief. They mean different things: how far the run has come, versus how good the move just made
   * looked, and a header that conflates them reads as a bug in the run.
   */
  progress: number;
}

export function project(events: EngineEventFrame[], cursor: number): Projection {
  const decisions = foldDecisions(events);
  const index = decisions.length === 0 ? -1 : Math.max(0, Math.min(cursor, decisions.length - 1));
  const at = index === -1 ? null : decisions[index];
  const upto = at === null ? 0 : at.to + 1;
  return {
    decisions,
    at,
    knowledge: readKnowledge(events, upto),
    tree: readTree(events, upto, decisions.slice(0, Math.max(0, index + 1))),
    trust: readTrust(index === -1 ? [] : decisions.slice(0, index + 1)),
    eventIndex: upto - 1,
    progress: progressAt(events, upto),
  };
}

/** The progress the newest state inside the cursor reported. */
function progressAt(events: EngineEventFrame[], upto: number): number {
  for (let i = Math.min(upto, events.length) - 1; i >= 0; i -= 1) {
    if (events[i].kind === "state") return Number(events[i]["progress"] ?? 0);
  }
  return 0;
}
