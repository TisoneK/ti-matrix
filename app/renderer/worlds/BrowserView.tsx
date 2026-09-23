/*
 * The browser world: where the run is, what it did there, and what it found.
 *
 * A run in this world is a sequence of actions against a real page, and the actions that change the page
 * (a click, a keystroke, a script) are exactly the ones that needed a person's yes — so they are marked
 * here, next to the reads that needed nothing from anyone.
 */

import { useMemo } from "react";
import { EngineEventFrame } from "../protocol";
import { BrowserKnowledge, readBrowser } from "../lib/browser";
import { shortPath, splitTruncation } from "../lib/format";
import { Panel, Empty } from "../ui/Panel";

const KIND_LABEL: Record<string, string> = {
  navigate: "went to",
  read: "read",
  interact: "changed",
  wait: "waited",
};

export function BrowserView({ events }: { events: EngineEventFrame[] }) {
  const k: BrowserKnowledge = useMemo(() => readBrowser(events), [events]);

  if (k.probes.length === 0) {
    return (
      <Panel title="the page the run is on">
        <Empty>Nothing yet — the browser panel fills in as the run navigates and reads.</Empty>
      </Panel>
    );
  }

  return (
    <>
      <Panel title="the page the run is on"
             meta={k.page ? undefined : "the run has not asked for a title or URL yet"}>
        {k.page ? (
          <div className="browser-bar">
            <span className="dot" /><span className="dot" /><span className="dot" />
            <code className="url" title={k.page.url}>{shortPath(k.page.url, 72)}</code>
            {k.page.title ? <span className="page-title">{k.page.title}</span> : null}
          </div>
        ) : (
          <p className="hint">
            Only <code>goto</code> and <code>title_and_url</code> name the page in their answer; every other
            reading leaves the location implicit.
          </p>
        )}
      </Panel>

      <Panel title="what the run did" meta={`${k.trail.length} actions`}>
        <ul className="trail">
          {k.trail.map((step) => (
            <li key={step.seq} className={`trail-step k-${step.kind}${step.ok ? "" : " failed"}`}>
              <span className="tag-mini">{KIND_LABEL[step.kind] ?? step.kind}</span>
              <code className="tool">{step.tool}</code>
              <span className="detail">{splitTruncation(step.detail).body || "—"}</span>
            </li>
          ))}
        </ul>
      </Panel>

      {k.links.length > 0 ? (
        <Panel title="links on the page" meta={`${k.links.length}`}>
          <ul className="plain-list links">
            {k.links.map((l, i) => (
              <li key={i}>
                <span className="strong">{l.text}</span>
                <code className="dim" title={l.href}>{shortPath(l.href, 60)}</code>
              </li>
            ))}
          </ul>
        </Panel>
      ) : null}

      {k.found.length > 0 || k.waits.length > 0 || k.evals.length > 0 ? (
        <Panel title="elements and values">
          <ul className="plain-list">
            {k.found.map((f, i) => (
              <li key={`f${i}`}>
                <span className="tag-mini">{f.count} match(es)</span>
                <code>&lt;{f.tag}{f.id ? `#${f.id}` : ""}&gt;</code>
                <span className="dim">{f.size} at {f.at} · {f.text}</span>
              </li>
            ))}
            {k.waits.map((w, i) => (
              <li key={`w${i}`}>
                <span className="tag-mini">appeared</span>
                <code>{w.selector}</code><span className="dim">{w.text}</span>
              </li>
            ))}
            {k.evals.map((e, i) => (
              <li key={`e${i}`}>
                <span className="tag-mini">evaluated</span>
                <code>{e.expr}</code><span className="dim"> → {e.value}</span>
              </li>
            ))}
          </ul>
        </Panel>
      ) : null}

      {k.shots.length > 0 ? (
        <Panel title="screenshots">
          <ul className="plain-list">
            {k.shots.map((s, i) => (
              <li key={i}>
                <span className="tag-mini">{s.size}</span>
                <code title={s.path}>{shortPath(s.path, 52)}</code>
                <span className="dim">of {shortPath(s.url, 32)}</span>
              </li>
            ))}
          </ul>
          <p className="hint">A screenshot is a file on disk for a person to open — the engine reads text, not pictures.</p>
        </Panel>
      ) : null}

      {k.texts.length > 0 ? (
        <Panel title="text read from the page">
          {k.texts.map((t, i) => (
            <pre className="file-text" key={i}>{splitTruncation(t).body}</pre>
          ))}
        </Panel>
      ) : null}

      {k.errors.length > 0 ? (
        <Panel title="what the page refused" meta={`${k.errors.length}`}>
          <ul className="plain-list">
            {k.errors.map((e, i) => <li key={i} className="bad">{e}</li>)}
          </ul>
        </Panel>
      ) : null}
    </>
  );
}
