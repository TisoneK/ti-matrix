/*
 * The live trace: the search as something happening, not something recorded.
 *
 * Everything else that shows a run shows it *after* the fact — the tree is the shape it left behind, the
 * ledger the list of what it did. This is the instrument's live face: the candidates the run is weighing
 * swing around a slow radar, each one dropping out or pulling ahead as the world answers, while the feed
 * beside them prints every turn the moment it lands. One decision's fan is the radar; the run's whole
 * history is the feed.
 *
 * It is a fold over the same `Decision[]` every other panel reads — no new events, no engine change.
 */

import { useMemo } from "react";
import { Decision } from "../core/types";
import { finalAnswerOf, openFan } from "../core/decisions";
import { Empty, PaneBody, PaneHead } from "../ui/atoms";
import { CandidateRadar } from "./CandidateRadar";

/** The fan to draw: the one being weighed right now, else the most recent one that had candidates. */
export function fanOf(decisions: Decision[], cursor: number): Decision | null {
  const open = openFan(decisions, cursor);
  if (open) return open;
  for (let i = Math.min(cursor, decisions.length - 1); i >= 0; i -= 1) {
    if (decisions[i]?.options.length) return decisions[i];
  }
  return null;
}

/** Every turn, newest first, with the tone its own flags earn. Shared with the console's ticker. */
export function feedLines(decisions: Decision[]) {
  return decisions.map((d) => ({
    key: d.index,
    tMs: d.tMs,
    text: d.headline,
    tone: d.flags.includes("surprise") ? "flag"
      : d.kind === "done" ? "win"
        : d.kind === "backtrack" ? "retreat" : "",
  })).reverse();
}

export function LiveTrace({ decisions, cursor, live }: {
  decisions: Decision[];
  cursor: number;
  /** While the run streams, proposed candidates are still open — they pulse rather than sit idle. */
  live?: boolean;
}) {
  const fan = useMemo(() => fanOf(decisions, cursor), [decisions, cursor]);
  const answer = useMemo(() => finalAnswerOf(decisions), [decisions]);
  const lines = useMemo(() => feedLines(decisions).slice(0, 80), [decisions]);

  return (
    <>
      <section className="pane" aria-label="candidate states">
        <PaneHead title="Candidate states"
                  sub={fan ? `${fan.options.length} weighed · step ${fan.index + 1} of ${decisions.length}`
                    : "nothing proposed yet"} />
        <PaneBody className="trace-body">
          {fan ? (
            <CandidateRadar decision={fan} live={!!live} />
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

/** A turn's own timestamp, as the run recorded it — seconds with a tenth, not a wall clock. */
export function formatMs(ms: number): string {
  if (!Number.isFinite(ms) || ms < 0) return "—";
  return `${(ms / 1000).toFixed(1)}s`;
}
