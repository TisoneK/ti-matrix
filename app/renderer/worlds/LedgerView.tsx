/*
 * The Context Ledger world: the project's own memory, section by section.
 *
 * The chips are the ledger's reports, and only the ones this run actually asked for are offered — a run
 * that read decisions and nothing else gets decisions, not five empty panels.
 */

import { useMemo, useState } from "react";
import { EngineEventFrame } from "../protocol";
import { LEDGER_SECTIONS, LedgerSection, readLedger } from "../lib/ledger";
import { formatBytes, shortPath, splitTruncation } from "../lib/format";
import { Panel, Empty } from "../ui/Panel";
import { Chip } from "../ui/Controls";

export function LedgerView({ events }: { events: EngineEventFrame[] }) {
  const k = useMemo(() => readLedger(events), [events]);
  const [section, setSection] = useState<LedgerSection>("tasks");

  const available = LEDGER_SECTIONS.filter((s) => {
    switch (s.id) {
      case "tasks": return k.current !== null || k.backlog.length > 0;
      case "decisions": return k.decisions.length > 0 || k.decisionDetail !== null;
      case "sessions": return k.sessions.length > 0;
      case "friction": return k.friction.length > 0;
      case "memory": return k.memory.length > 0 || k.reads.length > 0 || k.searches.length > 0;
      default: return false;
    }
  });

  if (k.probes.length === 0) {
    return (
      <Panel title="the project's memory">
        <Empty>Nothing read yet — the ledger fills in as the run asks it things.</Empty>
      </Panel>
    );
  }

  if (k.unbootstrapped) {
    return (
      <Panel title="the project's memory">
        <p className="bad">{k.unbootstrapped}</p>
        <p className="hint">Point this world at a project that has a bootstrapped <code>.context_ledger/</code>.</p>
      </Panel>
    );
  }

  const active = available.some((s) => s.id === section) ? section : available[0]?.id ?? "tasks";

  return (
    <>
      <Panel title="the project's memory" meta={k.vault ? shortPath(k.vault, 40) : undefined}
             actions={<div className="tools">
               {available.map((s) => (
                 <Chip key={s.id} on={s.id === active} onClick={() => setSection(s.id)}>{s.label}</Chip>
               ))}
             </div>}>
        {k.core || k.scale ? (
          <div className="ledger-head">
            {k.core ? <span className="tag-mini">core {k.core}</span> : null}
            {k.scale ? <span className="dim">{k.scale}</span> : null}
          </div>
        ) : null}

        {active === "tasks" ? (
          <>
            {k.current ? (
              <div className="card">
                <div className="card-head"><span className="tag-mini on">in flight</span>{k.current.status}</div>
                <p className="card-title">{k.current.task}</p>
                {k.current.session ? <p className="dim">session {k.current.session}</p> : null}
              </div>
            ) : null}
            {k.backlog.map((group) => (
              <div className="group" key={group.section}>
                <h3>{group.section} <span className="dim">{group.rows.length} of {group.total}</span></h3>
                <ul className="plain-list">
                  {group.rows.map((r) => (
                    <li key={r.ident}><code>{r.ident}</code> {r.summary}</li>
                  ))}
                </ul>
              </div>
            ))}
            {k.parking ? <p className="dim">parking lot (not a queue): {k.parking}</p> : null}
          </>
        ) : null}

        {active === "decisions" ? (
          <>
            {k.decisions.length > 0 ? (
              <ul className="plain-list decisions">
                {k.decisions.map((d) => (
                  <li key={d.number}>
                    <span className="tag-mini">ADR-{d.number}</span>
                    <span className="strong">{d.title}</span>
                    <span className="dim">{d.date} · {d.status}</span>
                  </li>
                ))}
              </ul>
            ) : null}
            {k.decisionDetail ? (
              <div className="card">
                <div className="card-head"><span className="tag-mini on">read in full</span></div>
                <p className="card-title">{k.decisionDetail.ref}</p>
                <dl className="kv">
                  {k.decisionDetail.fields.map(([key, value], i) => (
                    <div className="kv-row" key={i}><dt>{key}</dt><dd>{value}</dd></div>
                  ))}
                </dl>
              </div>
            ) : null}
          </>
        ) : null}

        {active === "sessions" ? (
          <ul className="plain-list sessions">
            {k.sessions.map((s, i) => (
              <li key={i}>
                <span className="strong">{s.heading}</span>
                {s.fields.length > 0 ? (
                  <span className="dim"> · {s.fields.map(([key, value]) => `${key}: ${value}`).join(" · ")}</span>
                ) : null}
              </li>
            ))}
          </ul>
        ) : null}

        {active === "friction" ? (
          k.friction.map((log) => (
            <div className="group" key={log.log}>
              <h3>{log.log}</h3>
              {log.entries.map((e, i) => (
                <div className="card" key={i}>
                  <div className="card-head"><span className="tag-mini">{e.head}</span></div>
                  {e.fields.map(([key, value], j) => (
                    <p className="friction-line" key={j}><b>{key}:</b> {value}</p>
                  ))}
                </div>
              ))}
            </div>
          ))
        ) : null}

        {active === "memory" ? (
          <>
            {k.searches.map((s, i) => (
              <div className="group" key={i}>
                <h3>search <code>{s.needle}</code> <span className="dim">in {s.scope} · {s.total} line(s)</span></h3>
                <ul className="plain-list hits">
                  {s.hits.map((h, j) => (
                    <li key={j}>
                      <code className="dim">{h.rel}:{h.line}</code> {splitTruncation(h.text).body}
                    </li>
                  ))}
                </ul>
              </div>
            ))}
            {k.memory.map((m, i) => (
              <div className="group" key={`m${i}`}>
                <h3>{m.scope} <span className="dim">{m.files.length} file(s)</span></h3>
                <ul className="plain-list">
                  {m.files.map((f) => (
                    <li key={f.rel}><code>{f.rel}</code> <span className="dim">{formatBytes(f.bytes)}</span></li>
                  ))}
                </ul>
              </div>
            ))}
            {k.reads.map((r) => (
              <div className="group" key={r.rel}>
                <h3><code>{r.rel}</code></h3>
                <pre className="file-text">{splitTruncation(r.text).body}</pre>
              </div>
            ))}
          </>
        ) : null}
      </Panel>

      {k.refusedWrites.length > 0 ? (
        <Panel title="changes the engine asked for" meta="this environment only reads">
          <ul className="plain-list">
            {k.refusedWrites.map((move, i) => <li key={i}><code>{move}</code></li>)}
          </ul>
        </Panel>
      ) : null}
    </>
  );
}
