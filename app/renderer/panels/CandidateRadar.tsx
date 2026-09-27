/*
 * The candidate radar: one decision's fan drawn as satellites around a scanning centre.
 *
 * A ranged scanner is the honest shape for this engine. `StateEngine` is, by its own docstring, "a beam of
 * one with backtracking": exactly one state is ever live, and what it is doing at any moment is weighing a
 * set of candidate moves out at a distance — not walking a maze of states. So the picture is a centre
 * (where the run stands) and its candidates around it, each one dropping out or being taken.
 *
 * A candidate's phase is read straight off the candidate itself — proposed (`ok` unknown), probed
 * (`ok` known), weighed (`progress` known), taken (`chosen`) — so there is no second state to keep in
 * sync and the radar cannot disagree with the tree or the ledger about the same option.
 *
 * Shared by both faces of the run: the live trace's pane and the ops console's orbit are this component,
 * at different sizes, because they are the same fact.
 */

import { Candidate, Decision } from "../core/types";
import { pct } from "../core/format";

const CENTER = 210;
const RINGS = [66, 128, 188];
/** Candidates sit on the middle ring, the way a contact does on a scope. */
const R_NODES = 132;
/** Past this the rest fold into a count — a ring of fourteen labels is a smudge, not a readout. */
const MAX_NODES = 8;

export type NodeState = "idle" | "live" | "won" | "dropped";

export function stateOf(c: Candidate, live: boolean): NodeState {
  if (c.chosen) return "won";
  if (c.ok === false) return "dropped";           // the world refused it — ruled out for good
  if (c.progress !== undefined) return "dropped";  // weighed and not taken
  return live ? "live" : "idle";                   // proposed, still open
}

const labelOf = (c: Candidate): string => {
  const raw = (c.label || c.tool || "candidate").replace(/\s+/g, " ").trim();
  return raw.length > 22 ? `${raw.slice(0, 21)}…` : raw;
};

function whyOf(c: Candidate, state: NodeState): string {
  if (state === "won") return `${c.label} — taken${c.progress === undefined ? "" : ` · believed ${pct(c.progress)}`}`;
  if (c.ok === false) return `${c.label} — the world refused this`;
  if (c.progress !== undefined) return `${c.label} — weighed ${pct(c.progress)}, not taken`;
  return `${c.label} — proposed, still open`;
}

export function CandidateRadar({ decision, live }: { decision: Decision; live: boolean }) {
  const options = decision.options.slice(0, MAX_NODES);
  const extra = decision.options.length - options.length;
  const winner = decision.options.find((o) => o.chosen);
  const best = decision.options
    .filter((o) => o.ok !== false)
    .sort((a, b) => (b.progress ?? -1) - (a.progress ?? -1))[0];
  const belief = winner?.progress ?? best?.progress;
  const settled = decision.kind === "done";

  // A fixed number of ticks at a fixed 15°: a scale, not a measurement. It exists so the sweep has
  // something to cross — a scope with a bare face reads as a spinner rather than as an instrument.
  const ticks = [];
  for (let a = 0; a < 360; a += 15) {
    const rad = (a * Math.PI) / 180;
    const long = a % 45 === 0;
    const r1 = RINGS[2];
    const r2 = long ? RINGS[2] - 11 : RINGS[2] - 6;
    ticks.push(
      <line key={a} className="tick"
            x1={CENTER + r1 * Math.cos(rad)} y1={CENTER + r1 * Math.sin(rad)}
            x2={CENTER + r2 * Math.cos(rad)} y2={CENTER + r2 * Math.sin(rad)} />,
    );
  }

  return (
    <div className="radarwrap">
      <svg className="radar" viewBox="0 0 420 420" role="img"
           aria-label={`candidate states: ${decision.options.length} considered, ${decision.options.filter((o) => o.chosen).length} taken`}>
        <defs>
          <linearGradient id="trace-sweep" x1="0" y1="0" x2="1" y2="0">
            <stop offset="0%" stopColor="#5fe3ff" stopOpacity="0" />
            <stop offset="100%" stopColor="#5fe3ff" stopOpacity="0.3" />
          </linearGradient>
        </defs>

        {RINGS.map((r) => <circle key={r} className="ring" cx={CENTER} cy={CENTER} r={r} />)}
        <g>{ticks}</g>
        <g className="sweep">
          <path d={`M${CENTER},${CENTER} L${CENTER},${CENTER - RINGS[2]} A${RINGS[2]},${RINGS[2]} 0 0,1 ${CENTER + 45},${CENTER - RINGS[2] + 10} Z`}
                fill="url(#trace-sweep)" />
        </g>

        <text className="center-readout" x={CENTER} y={CENTER - 10}>belief</text>
        <text className={`center-readout big ${settled ? "settled" : ""}`} x={CENTER} y={CENTER + 13}>
          {belief === undefined ? "—" : pct(belief)}
        </text>

        {options.map((c, i) => {
          const a = (-90 + i * (360 / options.length)) * (Math.PI / 180);
          const x = CENTER + R_NODES * Math.cos(a);
          const y = CENTER + R_NODES * Math.sin(a);
          const state = stateOf(c, live);
          const spoke = state === "live" ? "live" : state === "won" ? "won" : "";
          return (
            <g key={c.fp || i} className={`node ${state}`}>
              <title>{whyOf(c, state)}</title>
              <path className={`path-line ${spoke}`} d={`M${CENTER},${CENTER} L${x},${y}`} />
              {state === "live" ? <circle className="ping" cx={x} cy={y} r="10" /> : null}
              <circle className="core" cx={x} cy={y} r="9" />
              <text x={x} y={y - 15} textAnchor="middle">{labelOf(c)}</text>
            </g>
          );
        })}

        {extra > 0 ? (
          <text className="center-readout" x={CENTER} y={CENTER + RINGS[2] + 22}>
            +{extra} more candidate{extra === 1 ? "" : "s"}
          </text>
        ) : null}
      </svg>
    </div>
  );
}
