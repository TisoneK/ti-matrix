/*
 * The raw record: every event, in the order the engine emitted it.
 *
 * This is the machinery's own view — `EngineEvent.to_dict()` verbatim, the same shape `run_log` reads off
 * disk — so it is worth having and worth folding away: what a run established is on the panels above.
 */

import { useEffect, useMemo, useRef, useState } from "react";
import { EngineEventFrame } from "../protocol";
import { FILTERS, Group, describeEvent, groupOf } from "../lib/events";
import { formatElapsed } from "../lib/format";
import { Chip } from "../ui/Controls";
import { Panel } from "../ui/Panel";

function EventRow({ e }: { e: EngineEventFrame }) {
  const view = describeEvent(e);
  return (
    <article className={`ev k-${e.kind} t-${view.tone}`}>
      <div className="meta">
        <span>#{e.seq}</span>
        <span>{formatElapsed(e.t_ms)}</span>
        <span className="badge">{view.badge}</span>
        <span className="spacer" />
        {view.meta ? <span>{view.meta}</span> : null}
      </div>
      {view.detail ? <div className="text">{view.detail}</div> : null}
      {view.moves?.map((m, i) => (
        <div className="text move" key={i}>
          <span className="strong">{m.label}</span>
          {m.why ? <span className="why">— {m.why}</span> : null}
        </div>
      ))}
    </article>
  );
}

export function EventStream({ events, running, collapsedByDefault }: {
  events: EngineEventFrame[];
  running: boolean;
  collapsedByDefault?: boolean;
}) {
  const [open, setOpen] = useState(!collapsedByDefault);
  const [filter, setFilter] = useState<Group | "all">("all");
  const [follow, setFollow] = useState(true);
  const scroller = useRef<HTMLDivElement | null>(null);

  const counts = useMemo(() => {
    const c: Record<string, number> = { all: events.length, probes: 0, moves: 0, notes: 0 };
    for (const e of events) c[groupOf(e.kind)] += 1;
    return c;
  }, [events]);

  const shown = useMemo(
    () => (filter === "all" ? events : events.filter((e) => groupOf(e.kind) === filter)),
    [events, filter],
  );

  useEffect(() => {
    if (!follow || !open) return;
    const el = scroller.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [shown.length, follow, open]);

  return (
    <Panel title="the raw record" grow={open}
           meta={running ? "thinking…" : `${events.length} events`}
           actions={
             <div className="tools">
               {open ? FILTERS.map((f) => (
                 <Chip key={f.id} on={filter === f.id} onClick={() => setFilter(f.id)}>
                   {f.label}{counts[f.id] ? ` ${counts[f.id]}` : ""}
                 </Chip>
               )) : null}
               {open ? (
                 <Chip on={follow} onClick={() => setFollow((v) => !v)} title="keep the newest event in view">follow</Chip>
               ) : null}
               <Chip on={open} onClick={() => setOpen((v) => !v)}>
                 {open ? "fold away" : "show the raw log"}
               </Chip>
             </div>
           }>
      {open ? (
        <div className="stream-scroll" ref={scroller} aria-live="polite" aria-busy={running}>
          <div className="stream">
            {shown.length === 0 ? (
              <p className="empty">
                {events.length === 0 ? "Nothing yet — set a goal and press Run." : "Nothing of this kind yet."}
              </p>
            ) : (
              shown.map((e) => <EventRow key={`${e.seq}-${e.kind}`} e={e} />)
            )}
          </div>
        </div>
      ) : null}
    </Panel>
  );
}
