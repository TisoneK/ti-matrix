/*
 * How the run ended: an answer, or the honest account of not having one.
 *
 * A `settled` frame carries `answer` when the run reached something it could verify, or `reason` when it
 * stopped without settling — the two are never both, and the heading says which one this is. `summary` is
 * the same digest `python -m ti_matrix.adapters.run_log` prints, and `record` is the full run.
 */

import { useState } from "react";
import { Panel } from "../ui/Panel";

export interface Settled {
  answer?: string | null;
  reason?: string | null;
  summary?: string | null;
  learned?: string | null;
  record?: string | null;
  error?: string;
  events?: number;
}

export function Outcome({ settled }: { settled: Settled }) {
  const [open, setOpen] = useState(false);
  const error = typeof settled.error === "string" ? settled.error : "";
  const answer = settled.answer || "";
  const heading = error ? "error" : answer ? "settled" : "stopped";
  const body = error || answer || settled.reason || "the run ended without an answer";

  return (
    <Panel title={heading} className={`outcome${error ? " is-error" : ""}`}
           meta={settled.events !== undefined ? `${settled.events} events` : undefined}>
      {heading !== "settled" && !error ? (
        <p className="kicker">nothing was verified — this is what the run can honestly say</p>
      ) : null}
      <pre className="answer">{body}</pre>
      {settled.summary ? <details className="record" open={open} onToggle={(e) => setOpen((e.target as HTMLDetailsElement).open)}>
        <summary>the run in one paragraph</summary>
        <pre>{settled.summary}</pre>
      </details> : null}
      {settled.learned ? <details className="record">
        <summary>what it learned</summary>
        <pre>{settled.learned}</pre>
      </details> : null}
      {settled.record ? <details className="record">
        <summary>the full record</summary>
        <pre>{settled.record}</pre>
      </details> : null}
    </Panel>
  );
}
