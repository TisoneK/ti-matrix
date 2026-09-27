/*
 * The live trace: the search as something happening, not something recorded.
 *
 * Everything else that shows a run shows it *after* the fact — the tree is the shape it left behind, the
 * ledger the list of what it did. This is the instrument's live face: the candidates the run is weighing
 * swing around a slow radar, each one dropping out or pulling ahead as the world answers, while the feed
 * beside them prints every turn the moment it lands. One decision's fan is the radar; the run's whole
 * history is the feed.
 *
 * It is a fold over the same `Decision[]` every other panel reads — no new events, no engine change. A
 * candidate's three phases are already carried by the candidate itself: proposed (nothing probed), probed
 * (`ok` known), scored (`progress` known) and chosen (`chosen`). The radar just draws those four facts at
 * angles instead of in lanes.
 */

import { useMemo } from "react";
import { Candidate, Decision } from "../core/types";
import { finalAnswerOf, openFan } from "../core/decisions";
import { pct } from "../core/format";
import { Empty, PaneBody, PaneHead } from "../ui/atoms";

/** How many candidates the radar will draw before it folds the rest into a count. */
const MAX_NODES = 8;

/** The fan to draw: the one being weighed right now, else the most recent one that had candidates. */
function fanOf(decisions: Decision[], cursor: number): Decision | null {
  const open = openFan(decisions, cursor);
  if (open) return open;
  for (let i = Math.min(cursor, decisions.length - 1); i >= 0; i -= 1) {
    if (decisions[i]?.options.length) return decisions[i];
  }
  return null;
}

/**
 * What a candidate is, at a glance. Read straight off the candidate — there is no second state to keep in
 * sync, which is why the radar cannot disagree with the tree or the ledger about the same option.
 */
type NodeState = "idle" | "live" | "won" | "dropped";
function stateOf(c: Candidate, live: boolean): NodeState {
  if (c.chosen) return "won";
  if (c.ok === false) return "dropped";          // the world refused it — ruled out for good
  if (c.progress !== undefined) return "dropped"; // weighed and not taken
  return live ? "live" : "idle";                  // proposed, still open
}

const labelOf = (c: Candidate): string => {
  const raw = (c.label || c.tool || "candidate").replace(/\s+/g, " ").trim();
  return raw.length > 22 ? `${raw.slice(0, 21)}…` : raw;
};

const whyOf = (c: Candidate, state: NodeState): string => {
  if (state === "won") return `${c.label} — taken${c.progress === undefined ? "" : ` · believed ${pct(c.progress)}`}`;
  if (c.ok === false) return `${c.label} — the world refused this`;
  if (c.progress !== undefined) return `${c.label} — weighed ${pct(c.progress)}, not taken`;
  return `${c.label} — proposed, still open`;
};

export function LiveTrace({ decisions, cursor, live }: {
  decisions: Decision[];
  cursor: number;
  /** While the run streams, proposed candidates are still open — they pulse rather than sit idle. */
  live?: boolean;
}) {
  const fan = useMemo(() => fanOf(decisions, cursor), [decisions, cursor]);
  const answer = useMemo(() => finalAnswerOf(decisions), [decisions]);
  // Newest first: the feed is what just happened, so it reads from the top down like a print-out.
  const lines = useMemo(
    () => decisions.map((d) => ({
      key: d.index,
      tMs: d.tMs,
      text: d.headline,
      tone: d.flags.includes("surprise") ? "flag"
        : d.kind === "done" ? "win"
          : d.kind === "backtrack" ? "retreat" : "",
    })).reverse().slice(0, 80),
    [decisions]);

  return (
    <>
      <section className="pane" aria-label="candidate states">
        <PaneHead title="Candidate states"
                  sub={fan ? `${fan.options.length} weighed · step ${fan.index + 1} of ${decisions.length}`
                    : "nothing proposed yet"} />
        <PaneBody className="trace-body">
          {fan ? (
            <Radar decision={fan} live={!!live} />
          ) : (
            <Empty eyebrow="the search" title="No candidates yet">
              The instant the run proposes one it appears here — and each drops out or pulls ahead as the
              world answers.
            </Empty>
          )}
          {answer ? (
            <div className={`answer-band ${answer.verified ? "on" : "held"}`}>
              <span className="lbl">{answer.verified ? "answer" : "best from what it read"}</span>
              <span className="answer-text">{answer.text}</span>
            </div>
          ) : null}
        </PaneBody>
      </section>

      <section className="pane" aria-label="state feed">
        <PaneHead title="State feed"
                  sub={lines.length === 0 ? undefined : `${decisions.length} turn${decisions.length === 1 ? "" : "s"} · newest first`} />
        <PaneBody className="feedwrap">
          {lines.length === 0 ? (
            <Empty eyebrow="the feed" title="Nothing yet">
              Every turn the run takes lands here the moment it happens, newest first.
            </Empty>
          ) : (
            <ol className="feed">
              {lines.map((line) => (
                <li key={line.key} className={`feed-line ${line.tone}`}>
                  <span className="t">{formatMs(line.tMs)}</span>
                  <span className="body">{line.text}</span>
                </li>
              ))}
            </ol>
          )}
        </PaneBody>
      </section>
    </>
  );
}

/**
 * The fan, at angles. A ranged scanner is the honest shape for this engine: exactly one state is live at a
 * time, and what it is doing is weighing a set of candidates out at a distance — not walking a maze of
 * them. The sweep is a clock, not a claim; the spokes are the candidates, and their colour is their state.
 */
function Radar({ decision, live }: { decision: Decision; live: boolean }) {
  const options = decision.options.slice(0, MAX_NODES);
  const extra = decision.options.length - options.length;
  const winner = decision.options.find((o) => o.chosen);
  const best = decision.options
    .filter((o) => o.ok !== false)
    .sort((a, b) => (b.progress ?? -1) - (a.progress ?? -1))[0];
  const belief = winner?.progress ?? best?.progress;
  const settled = decision.kind === "done";

  return (
    <div className="radarwrap">
      <svg className="radar" viewBox="0 0 400 400" role="img"
           aria-label={`candidate states: ${decision.options.length} considered, ${decision.options.filter((o) => o.chosen).length} taken`}>
        <defs>
          <linearGradient id="trace-sweep" x1="0" y1="0" x2="1" y2="0">
            <stop offset="0%" stopColor="#5fe3ff" stopOpacity="0" />
            <stop offset="100%" stopColor="#5fe3ff" stopOpacity="0.3" />
          </linearGradient>
        </defs>
        <circle className="ring" cx="200" cy="200" r="60" />
        <circle className="ring" cx="200" cy="200" r="120" />
        <circle className="ring" cx="200" cy="200" r="176" />
        <g className="sweep">
          <path d="M200,200 L200,24 A176,176 0 0,1 244,32 Z" fill="url(#trace-sweep)" />
        </g>

        <text className="center-readout" x="200" y="192">belief</text>
        <text className={`center-readout big ${settled ? "settled" : ""}`} x="200" y="215">
          {belief === undefined ? "—" : pct(belief)}
        </text>

        {options.map((c, i) => {
          const a = (-90 + i * (360 / options.length)) * (Math.PI / 180);
          const x = 200 + 150 * Math.cos(a);
          const y = 200 + 150 * Math.sin(a);
          const state = stateOf(c, live);
          const spoke = state === "live" ? "live" : state === "won" ? "won" : "";
          return (
            <g key={c.fp || i} className={`node ${state}`}>
              <title>{whyOf(c, state)}</title>
              <path className={`path-line ${spoke}`} d={`M200,200 L${x},${y}`} />
              {state === "live" ? <circle className="ping" cx={x} cy={y} r="10" /> : null}
              <circle className="core" cx={x} cy={y} r="9" />
              <text x={x} y={y - 15} textAnchor="middle">{labelOf(c)}</text>
            </g>
          );
        })}

        {extra > 0 ? (
          <text className="center-readout" x="200" y="374">+{extra} more candidate{extra === 1 ? "" : "s"}</text>
        ) : null}
      </svg>
    </div>
  );
}

/** A turn's own timestamp, as the run recorded it — seconds with a tenth, not a wall clock. */
function formatMs(ms: number): string {
  if (!Number.isFinite(ms) || ms < 0) return "—";
  return `${(ms / 1000).toFixed(1)}s`;
}
