/*
 * The five marks a decision can carry, and what each one claims.
 *
 * A flag is not a severity and not a colour — it is a specific, checkable statement about the run, which
 * is why each has a shape of its own: at a glance, in a list of forty rows, "it went somewhere it had
 * already decided against" must not look like "it went somewhere on a hunch".
 */

import { Flag } from "./types";

export interface FlagSpec {
  id: Flag;
  /** The word shown in legends and tooltips. */
  label: string;
  /** What it asserts — the test that put it there. */
  claim: string;
  /** The mark's SVG path, drawn in a 10×10 box. Shapes, not just hues. */
  path: string;
  filled: boolean;
}

export const FLAGS: Record<Flag, FlagSpec> = {
  confirmed: {
    id: "confirmed",
    label: "confirmed",
    claim: "The belief held — the move it committed to scored better than standing still.",
    path: "M5 0.6 A4.4 4.4 0 1 0 5 9.4 A4.4 4.4 0 1 0 5 0.6 Z",
    filled: true,
  },
  surprise: {
    id: "surprise",
    label: "surprise",
    claim: "The world disagreed — a move the model proposed was refused rather than performed.",
    path: "M5 0.6 L9.4 5 L5 9.4 L0.6 5 Z",
    filled: true,
  },
  guess: {
    id: "guess",
    label: "low confidence",
    claim: "It moved on a hunch — the evaluator's own score for the move was under half.",
    path: "M5 0.6 L9.4 5 L5 9.4 L0.6 5 Z",
    filled: false,
  },
  backtrack: {
    id: "backtrack",
    label: "backtrack",
    claim: "It gave a branch up and retreated to an ancestor to try something else.",
    path: "M0.6 0.6 L0.6 9.4 M0.6 0.6 L5.4 5 L0.6 9.4",
    filled: false,
  },
  forced: {
    id: "forced",
    label: "forced stop",
    claim: "The run ended because a limit or the world ran out — not because the goal was met.",
    path: "M0.8 0.8 L9.2 0.8 L9.2 9.2 L0.8 9.2 Z",
    filled: false,
  },
};

/** A stable order for legends and filter chips: the good news first, the interesting news next. */
export const FLAG_ORDER: Flag[] = ["confirmed", "surprise", "guess", "backtrack", "forced"];

export const flagSpec = (flag: Flag): FlagSpec => FLAGS[flag];
