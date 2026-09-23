/*
 * The files world: the tree the run has actually walked, and the text of what it read.
 *
 * Nothing here is a filesystem browser — the app never touches the disk. Every node is a path some probe
 * named, and a file's text is the excerpt the engine kept of that observation.
 */

import { useMemo, useState } from "react";
import { EngineEventFrame } from "../protocol";
import { FilesKnowledge, Node, readFiles, treeOf } from "../lib/files";
import { formatBytes, shortPath, splitTruncation } from "../lib/format";
import { Panel, Empty } from "../ui/Panel";

function Tree({ node, depth, selected, onSelect }: {
  node: Node;
  depth: number;
  selected: string | null;
  onSelect: (path: string) => void;
}) {
  const [open, setOpen] = useState(true);
  const hasChildren = node.children.length > 0;
  const tone = [
    "tree-node",
    node.dir ? "dir" : "file",
    node.read ? "read" : "",
    node.path === selected ? "on" : "",
  ].filter(Boolean).join(" ");

  return (
    <li>
      <div className={tone} style={{ paddingLeft: 6 + depth * 12 }}>
        <button type="button" className="twist" aria-expanded={hasChildren ? open : undefined}
                onClick={() => hasChildren && setOpen((v) => !v)}>
          {hasChildren ? (open ? "▾" : "▸") : "·"}
        </button>
        <button type="button" className="tree-label" onClick={() => onSelect(node.path)}
                title={node.path}>
          <span className={node.dir ? "ico-dir" : "ico-file"}>{node.dir ? "▸" : "◦"}</span>
          {node.name}
        </button>
        <span className="tree-meta">
          {node.bytes !== undefined ? formatBytes(node.bytes) : null}
        </span>
      </div>
      {hasChildren && open ? (
        <ul>
          {node.children.map((c) => (
            <Tree key={c.path} node={c} depth={depth + 1} selected={selected} onSelect={onSelect} />
          ))}
        </ul>
      ) : null}
    </li>
  );
}

export function FilesView({ events }: { events: EngineEventFrame[] }) {
  const knowledge: FilesKnowledge = useMemo(() => readFiles(events), [events]);
  const tree = useMemo(() => treeOf(knowledge), [knowledge]);
  const [picked, setPicked] = useState<string | null>(null);

  const byPath = useMemo(() => new Map(knowledge.reads.map((r) => [r.path, r])), [knowledge]);
  const statsByPath = useMemo(() => new Map(knowledge.stats.map((s) => [s.path, s])), [knowledge]);
  const listingsByPath = useMemo(() => new Map(knowledge.listings.map((l) => [l.path, l])), [knowledge]);

  const active = picked ?? knowledge.reads[knowledge.reads.length - 1]?.path ?? null;
  const read = active ? byPath.get(active) : undefined;
  const stat = active ? statsByPath.get(active) : undefined;
  const listing = active ? listingsByPath.get(active) : undefined;

  if (!tree) {
    return (
      <Panel title="the tree the run has walked">
        <Empty>Nothing read yet — the tree fills in as the run lists and reads.</Empty>
      </Panel>
    );
  }

  return (
    <>
      <Panel title="the tree the run has walked" meta={`${knowledge.listings.length} listed · ${knowledge.reads.length} read`}>
        <div className="split">
          <div className="split-left">
            <ul className="tree">
              <Tree node={tree} depth={0} selected={active} onSelect={setPicked} />
            </ul>
          </div>
          <div className="split-right">
            {active ? (
              <>
                <div className="pane-head">
                  <code title={active}>{shortPath(active, 60)}</code>
                  {stat ? <span className="tag-mini">{stat.kind} · {formatBytes(stat.bytes)} · {stat.modified}</span> : null}
                </div>
                {read ? (
                  <pre className="file-text">{splitTruncation(read.text).body}</pre>
                ) : listing ? (
                  <ul className="plain-list">
                    {listing.entries.map((e, i) => (
                      <li key={i}>
                        <span className={e.dir ? "ico-dir" : "ico-file"}>{e.dir ? "▸" : "◦"}</span>
                        {e.name}
                        {e.bytes !== undefined ? <span className="dim"> {formatBytes(e.bytes)}</span> : null}
                      </li>
                    ))}
                    {listing.more > 0 ? <li className="dim">… and {listing.more} more</li> : null}
                  </ul>
                ) : (
                  <Empty>This path was named but never listed or read.</Empty>
                )}
                {read && splitTruncation(read.text).truncated ? (
                  <p className="hint">The engine keeps an excerpt of every observation; the file on disk is longer.</p>
                ) : null}
              </>
            ) : (
              <Empty>Pick a path from the tree.</Empty>
            )}
          </div>
        </div>
      </Panel>

      {knowledge.finds.length > 0 ? (
        <Panel title="searches">
          {knowledge.finds.map((f, i) => (
            <div className="find" key={i}>
              <div className="find-head">
                <span className="tag-mini">{f.total} hit{f.total === 1 ? "" : "s"}</span>
                <code>{f.needle}</code>
                <span className="dim">under {shortPath(f.root, 40)}</span>
              </div>
              {f.paths.length > 0 ? (
                <ul className="plain-list">
                  {f.paths.map((p, j) => <li key={j}><code>{shortPath(p, 56)}</code></li>)}
                  {f.total > f.paths.length ? <li className="dim">… {f.total - f.paths.length} not shown</li> : null}
                </ul>
              ) : (
                <p className="hint">{f.searched !== undefined ? `${f.searched} paths searched, none matched.` : "nothing matched."}</p>
              )}
            </div>
          ))}
        </Panel>
      ) : null}

      {knowledge.failures.length + knowledge.refusals.length > 0 ? (
        <Panel title="refused and not found" meta={`${knowledge.refusals.length + knowledge.failures.length}`}>
          <ul className="plain-list">
            {knowledge.refusals.map((r, i) => (
              <li key={`r${i}`} className="bad">
                <span className="tag-mini bad">refused</span>
                <code>{shortPath(r.asked, 44)}</code> is outside the root <code>{shortPath(r.root, 30)}</code>
              </li>
            ))}
            {knowledge.failures.map((f, i) => (
              <li key={`f${i}`}>
                <span className="tag-mini">{f.tool}</span>
                <code>{shortPath(f.path, 44)}</code> <span className="dim">{f.why}</span>
              </li>
            ))}
          </ul>
        </Panel>
      ) : null}
    </>
  );
}
