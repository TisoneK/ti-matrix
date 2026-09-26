/*
 * The ledger: every decision the run made, with what it believed and where the belief came from.
 *
 * A row is one turn of the search loop, not one event — "it had these options, the world answered this, it
 * believed that, it did this" is the unit a person reasons about, and the machine's own event stream is a
 * level too fine to read while anything is happening. The evidence column is the world's answer verbatim:
 * that is the whole point of the panel, since a belief whose source is not visible is just an assertion.
 *
 * Rows past the cursor stay in place and go quiet rather than disappearing — the run's future is part of
 * the picture, and clicking any row scrubs to it.
 */

import { useMemo, useState } from "react";
import { Decision, Flag } from "../core/types";
import { pct, splitTruncation } from "../core/format";
import { FLAG_ORDER, flagSpec, leadFlag } from "../core/flags";
import { TrustCurve, flagCounts } from "../core/trust";
import { Confidence, Empty, Flags, FlagMark, PaneBody, PaneHead, Sparkline } from "../ui/atoms";
import { Chip } from "../ui/controls";

const KIND_LABEL: Record<Decision["kind"], string> = {
  move: "took a move",
  backtrack: "retreated",
  done: "settled",
  stopped: "stopped",
  "needs-action": "blocked",
};

export function LogPanel({ decisions, trust, cursor, bookmarks, onSeek, onBookmark, onHover, peek }: {
  decisions: Decision[];
  trust: TrustCurve;
  cursor: number;
  bookmarks: number[];
  onSeek: (index: number) => void;
  onBookmark: (index: number) => void;
  /** The shared cursor: rows answer it, and hovering a row moves it. */
  onHover?: (index: number | null) => void;
  peek?: number | null;
}) {
  const [only, setOnly] = useState<Flag | null>(null);
  const counts = useMemo(() => flagCounts(decisions), [decisions]);
  const rows = useMemo(
    () => (only === null ? decisions : decisions.filter((d) => d.flags.includes(only))),
    [decisions, only],
  );

  return (
    <div className="ledger">
      <PaneHead title="Decisions" sub={`${decisions.length} decision${decisions.length === 1 ? "" : "s"}`}>
        {FLAG_ORDER.filter((f) => counts[f] > 0).map((f) => (
          <Chip key={f} label={`${flagSpec(f).label} ${counts[f]}`} pressed={only === f} swatch={undefined}
                onClick={() => setOnly((cur) => (cur === f ? null : f))}
                title={flagSpec(f).claim} />
        ))}
      </PaneHead>

      <div className="trust" title="The evaluator's own score for each move the run committed to, 0–100%: how much of the goal it judged known once that move was added. The model's confidence, not a probability.">
        <Sparkline curve={trust} />
        <div>
          <div className="pane-sub">
            belief in its own moves — mean {Math.round(trust.mean * 100)}% · {trust.trend}
          </div>
          {trust.points.length > 1 ? (
            <div className="dim" style={{ fontSize: 10.5 }}>
              each point is a move the run committed to, from {Math.round(trust.min * 100)}% to {Math.round(trust.max * 100)}%
            </div>
          ) : null}
        </div>
      </div>

      <PaneBody scroll className="rows">
        {decisions.length === 0 ? (
          <Empty eyebrow="the ledger" title="No decisions yet">
            Each turn of the search appears here as it happens: the options it had, the score it gave them,
            and the world's answer to the one it took.
          </Empty>
        ) : rows.length === 0 ? (
          <Empty eyebrow="filtered" title={`Nothing marked “${only ? flagSpec(only).label : ""}”`}>
            Clear the filter to see the whole run.
          </Empty>
        ) : (
          rows.map((d) => (
            <Row key={d.index} decision={d} current={d.index === cursor} future={d.index > cursor}
                 booked={bookmarks.includes(d.index)} onSeek={onSeek} onBookmark={onBookmark}
                 onHover={onHover} peek={peek === d.index} />
          ))
        )}
      </PaneBody>

      <div className="legend" role="list" aria-label="what the marks mean">
        {FLAG_ORDER.map((f) => (
          <span className="legend-item" key={f} role="listitem" title={flagSpec(f).claim}>
            <FlagMark flag={f} />
            {flagSpec(f).label}
            {counts[f] > 0 ? <span className="n">{counts[f]}</span> : null}
          </span>
        ))}
      </div>
    </div>
  );
}

function Row({ decision, current, future, booked, onSeek, onBookmark, onHover, peek }: {
  decision: Decision;
  current: boolean;
  future: boolean;
  booked: boolean;
  onSeek: (index: number) => void;
  onBookmark: (index: number) => void;
  onHover?: (index: number | null) => void;
  peek: boolean;
}) {
  const confidence = decision.confidence;
  // The candidates this decision weighed and did not take. They were probed against the real world and
  // scored like the winner; the only thing that makes them different is that one move gets applied.
  const passedOver = decision.options.filter((o) => !o.chosen);
  // The strongest flag becomes the row's tone: the gutter tells the run's story before any word is read.
  const tone = leadFlag(decision.flags);
  return (
    <div
      className={`row ${future ? "cold" : ""} ${tone ? `tone-${tone}` : ""} ${peek ? "peek" : ""}`}
      role="button"
      tabIndex={0}
      aria-current={current}
      aria-label={`step ${decision.index + 1}: ${decision.headline}`}
      onClick={() => onSeek(decision.index)}
      onMouseEnter={() => onHover?.(decision.index)}
      onMouseLeave={() => onHover?.(null)}
      onFocus={() => onHover?.(decision.index)}
      onBlur={() => onHover?.(null)}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") { e.preventDefault(); onSeek(decision.index); }
      }}
    >
      <span className="row-step">{decision.index + 1}</span>

      <span className="row-main">
        <span className="row-head">
          {KIND_LABEL[decision.kind]}
          {decision.move ? <> <span className="move">{decision.move}</span></> : null}
          {decision.kind === "stopped" && decision.reason ? <span className="dim"> · {decision.reason}</span> : null}
        </span>
        {decision.evidence ? (
          // The world cuts a long read off and leaves "… (truncated)"; `splitTruncation` has existed to
          // catch that and nothing called it, so the ledger showed a fragment as though it were the whole
          // answer. In an app whose question is whether to believe the run, "it only saw this much" is
          // not a detail — it is the difference between a fact and a sample.
          <span className="row-evidence">
            {splitTruncation(decision.evidence).body}
            {splitTruncation(decision.evidence).truncated ? (
              <em className="cut" title="the world returned more than the run was shown — it decided on this much">
                cut off here
              </em>
            ) : null}
          </span>
        ) : decision.refused.length > 0 ? (
          <span className="row-evidence">refused: {decision.refused.join(", ")}</span>
        ) : null}

        {/* What else was on the table. Every candidate in a fan is probed against the real world and
            scored, and only one is applied — `foldDecisions` has always kept the rest in `options`, with
            the world's answer and the evaluator's number on each, and nothing in the app rendered it.
            "It went east" and "it went east at 41% over north at 38%, and the world refused west" are
            different claims, and only the second is a decision you can check. */}
        {passedOver.length > 0 ? (
          <span className="row-alts">
            {/* "4 of 35" is the number that makes this a decision rather than a list. Shown only
                when the proposer could say — a filesystem has no denominator, and inventing one
                would be worse than the silence. */}
            <span className="alts-label">
              {decision.available !== undefined
                ? `weighed ${decision.options.length} of ${decision.available}`
                : "passed over"}
            </span>
            {passedOver.map((o) => (
              <span key={o.fp} className={`alt ${o.ok === false ? "refused" : ""}`}
                    title={o.ok === false ? `the world refused this: ${o.excerpt ?? ""}` : o.excerpt ?? o.why}>
                {o.label}
                <b>{o.ok === false ? "refused" : o.progress === undefined ? "—" : pct(o.progress)}</b>
              </span>
            ))}
          </span>
        ) : null}
      </span>

      <span className="row-side">
        <Flags flags={decision.flags} order={FLAG_ORDER} />
        {decision.kind === "move" || decision.kind === "done"
          ? <Confidence value={confidence} />
          : <span className="conf-num dim">—</span>}
        <button
          type="button"
          className={`row-bookmark ${booked ? "on" : ""}`}
          aria-pressed={booked}
          aria-label={booked ? `remove the bookmark on step ${decision.index + 1}` : `bookmark step ${decision.index + 1}`}
          title={booked ? "remove this bookmark" : "bookmark this step"}
          onClick={(e) => { e.stopPropagation(); onBookmark(decision.index); }}
        >
          {booked ? "★" : "☆"}
        </button>
      </span>
    </div>
  );
}
