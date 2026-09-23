/*
 * The run's own confidence, over time.
 *
 * Each move the engine commits to carries the evaluator's score for it — the model's own belief about how
 * good that outcome was. Plotted across the run, those scores are the only honest answer to "was this run
 * getting steadier or shakier?", which is otherwise a feeling you have while watching and cannot check.
 *
 * Only decisions that actually moved are points on the curve. A backtrack and a forced stop are marked in
 * the ledger and are not zeros here: a run that gave up a branch was not "unconfident", it was corrected.
 */

import { Decision, Flag } from "./types";

export interface TrustPoint {
  index: number;
  tMs: number;
  confidence: number;
  flags: Flag[];
}

export interface TrustCurve {
  points: TrustPoint[];
  mean: number;
  min: number;
  max: number;
  /** Last third minus first third: positive means the run steadied as it went. */
  drift: number;
  /** A phrase for the panel header, so the curve does not have to be read to be understood. */
  trend: "steadying" | "slipping" | "level" | "too short to say";
}

export function readTrust(decisions: Decision[]): TrustCurve {
  const points = decisions
    .filter((d) => d.kind === "move" || d.kind === "done")
    .map((d) => ({ index: d.index, tMs: d.tMs, confidence: d.confidence, flags: d.flags }));

  if (points.length === 0) {
    return { points, mean: 0, min: 0, max: 0, drift: 0, trend: "too short to say" };
  }

  const values = points.map((p) => p.confidence);
  const mean = values.reduce((a, b) => a + b, 0) / values.length;
  const third = Math.max(1, Math.floor(points.length / 3));
  const head = values.slice(0, third);
  const tail = values.slice(-third);
  const drift = avg(tail) - avg(head);

  return {
    points,
    mean,
    min: Math.min(...values),
    max: Math.max(...values),
    drift,
    trend: points.length < 4 ? "too short to say" : drift > 0.08 ? "steadying" : drift < -0.08 ? "slipping" : "level",
  };
}

const avg = (xs: number[]): number => (xs.length === 0 ? 0 : xs.reduce((a, b) => a + b, 0) / xs.length);

/** The curve as an SVG path in a `w`×`h` box. Confidence is the y axis, time the x — no axes, no fuss. */
export function curvePath(curve: TrustCurve, w: number, h: number, pad = 2): string {
  if (curve.points.length === 0) return "";
  if (curve.points.length === 1) {
    const y = h - pad - curve.points[0].confidence * (h - pad * 2);
    return `M${pad} ${y} L${w - pad} ${y}`;
  }
  const step = (w - pad * 2) / (curve.points.length - 1);
  return curve.points
    .map((p, i) => `${i === 0 ? "M" : "L"}${(pad + i * step).toFixed(2)} ${(h - pad - p.confidence * (h - pad * 2)).toFixed(2)}`)
    .join(" ");
}

/** How many of each flag the run carries — the legend's counts, and the library's sort keys. */
export function flagCounts(decisions: Decision[]): Record<Flag, number> {
  const counts: Record<Flag, number> = { confirmed: 0, surprise: 0, guess: 0, backtrack: 0, forced: 0 };
  for (const d of decisions) for (const f of d.flags) counts[f] += 1;
  return counts;
}
