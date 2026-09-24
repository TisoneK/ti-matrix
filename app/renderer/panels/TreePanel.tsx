/*
 * The tree: the search as a shape, not a list.
 *
 * Every node is a state the run actually stood on, and the engine's own `trail` says exactly which state
 * is whose parent — so this is the search, not a picture of one. What the picture is *for* is the two
 * questions a log cannot answer at a glance: how wide did it go before it committed, and which parts of
 * it did it give up.
 *
 * Three things make it usable on a long run. Cold branches fold into the node they branched from (and can
 * be unfolded by hand, or the rule turned off entirely). Hovering a node names the choice it faced — the
 * options the model offered, and which one it took. Clicking a node drives the shared cursor to the
 * moment that state existed, so the map and the ledger follow the tree rather than the tree being a
 * separate record.
 */

import { useMemo, useState } from "react";
import { SearchTree, layoutTree, pathTo, siblingContext, ROOT } from "../core/tree";
import { Decision } from "../core/types";
import { Chip } from "../ui/controls";
import { Empty, PaneBody, PaneHead } from "../ui/atoms";

const COL = 46;
const ROW = 44;
const NODE = 7;

export function TreePanel({ tree, decisions, cursor, onSeek, onHover, peek }: {
  tree: SearchTree;
  decisions: Decision[];
  cursor: number;
  onSeek: (decision: number) => void;
  /** The shared cursor: nodes answer it, and hovering a node moves it. */
  onHover?: (index: number | null) => void;
  peek?: number | null;
}) {
  const [foldDead, setFoldDead] = useState(true);
  const [collapsed, setCollapsed] = useState<Set<string>>(() => new Set());
  const [hover, setHover] = useState<string | null>(null);

  const view = useMemo(() => layoutTree(tree, { collapsed, foldDead }, { xGap: COL, yGap: ROW }), [tree, collapsed, foldDead]);
  const attached = useMemo(
    () => new Set(decisions.slice(0, cursor + 1).map((d) => d.index)),
    [decisions, cursor],
  );

  const toggleFold = (id: string) => setCollapsed((prev) => {
    const next = new Set(prev);
    if (next.has(id)) next.delete(id); else next.add(id);
    return next;
  });

  const width = Math.max(240, view.width + COL);
  const height = Math.max(120, view.height + ROW);
  const hidden = view.folds.reduce((sum, f) => sum + f.hidden, 0);
  // How many candidates this run probed and did not take. A search that weighed sixty options and a
  // walk that weighed none read identically before this — both were "N states".
  const weighed = decisions.reduce((n, d) => n + d.options.filter((o) => !o.chosen).length, 0);

  return (
    <>
      <PaneHead title="Search tree"
                sub={`${tree.states} state${tree.states === 1 ? "" : "s"} · ${tree.backtracks} retreat${tree.backtracks === 1 ? "" : "s"}`
                  + (weighed > 0 ? ` · ${weighed} weighed and passed over` : "")
                  + (hidden > 0 ? ` · ${hidden} folded` : "")}>
        <Chip label="fold cold branches" pressed={foldDead} onClick={() => setFoldDead((v) => !v)}
              title="fold a branch the run has already given up" />
      </PaneHead>

      <PaneBody>
        {tree.states === 0 ? (
          <Empty title="No states yet">
            Every state the run stands on becomes a node here, with the branch it gave up drawn cold.
          </Empty>
        ) : (
          <div className="treewrap">
            <svg width={width} height={height} viewBox={`-${COL / 2} -${ROW / 2} ${width + COL / 2} ${height + ROW / 2}`}
                 role="img" aria-label={`the search: ${tree.states} states, ${tree.backtracks} retreats`}>
              {view.edges.map((edge) => (
                <path
                  key={`${edge.from.id}->${edge.to.id}`}
                  className={`node-edge ${edge.to.id === hover ? "live" : ""} ${edge.dead ? "cold" : edge.live ? "live" : ""}`}
                  d={`M${edge.from.x} ${edge.from.y + NODE} C${edge.from.x} ${edge.from.y + ROW * 0.6}, ${edge.to.x} ${edge.to.y - ROW * 0.6}, ${edge.to.x} ${edge.to.y - NODE}`}
                />
              ))}

              {/* The roads not taken. Every candidate in a fan is probed against the real world and
                  scored; one is applied and becomes a node. The rest were folded into
                  `Decision.options` from the start and the tree never drew them, so a branch point
                  looked exactly like a corridor.

                  They are stubs, not nodes, and that is the honest shape: each was probed exactly
                  once and has no subtree. Drawing them as branches would invent a search that never
                  happened. They hang off the node they were weighed at and end in an open marker. */}
              {view.visible.map((node) => {
                if (node.decision === null) return null;
                const passed = (decisions[node.decision]?.options ?? []).filter((o) => !o.chosen);
                if (passed.length === 0) return null;
                return (
                  <g key={`stubs-${node.id}`} className={node.dead ? "stubs cold" : "stubs"}>
                    {passed.map((option, i) => {
                      // Fan them to the right of the trunk, so the applied edge stays the vertical one.
                      const spread = (i - (passed.length - 1) / 2) * 0.34;
                      const dx = Math.sin(spread + 0.9) * COL * 0.62;
                      const dy = Math.cos(spread + 0.9) * ROW * 0.42;
                      const refused = option.ok === false;
                      return (
                        <g key={option.fp} className={`stub ${refused ? "refused" : ""}`}>
                          <title>
                            {`${option.label} — ${refused ? "the world refused this"
                              : option.progress === undefined ? "not scored"
                                : `scored ${Math.round(option.progress * 100)}%`}`}
                            {option.excerpt ? `\n${option.excerpt.slice(0, 160)}` : ""}
                          </title>
                          <path className="stub-edge"
                                d={`M${node.x} ${node.y} L${node.x + dx} ${node.y + dy}`} />
                          <circle className="stub-dot" cx={node.x + dx} cy={node.y + dy} r={2.6} />
                        </g>
                      );
                    })}
                  </g>
                );
              })}

              {view.visible.map((node) => {
                const fold = view.folds.find((f) => f.from === node.id);
                const isCurrent = node.id === tree.current;
                const settled = decisions[node.decision ?? -1]?.kind === "done";
                const cls = `node-dot ${node.dead ? "cold" : isCurrent ? "live" : settled ? "settled" : "alive"}`;
                const clickable = node.decision !== null;
                const here = node.decision !== null && node.decision === cursor;
                const seen = node.decision !== null && node.decision === peek;
                return (
                  <g key={node.id}
                     onMouseEnter={() => { setHover(node.id); if (node.decision !== null) onHover?.(node.decision); }}
                     onMouseLeave={() => { setHover((h) => (h === node.id ? null : h)); onHover?.(null); }}>
                    <title>{nodeTitle(node.id, node.depth, node.progress, node.dead, node.current, siblingContext(tree, decisions, node.id))}</title>
                    <circle
                      className="node-hit"
                      cx={node.x} cy={node.y} r={NODE + 6}
                      tabIndex={clickable ? 0 : -1}
                      role={clickable ? "button" : undefined}
                      aria-label={clickable ? `jump to step ${node.decision! + 1}: ${node.last || "entry"}` : undefined}
                      onClick={() => clickable && onSeek(node.decision!)}
                      onKeyDown={(e) => {
                        if (!clickable) return;
                        if (e.key === "Enter" || e.key === " ") { e.preventDefault(); onSeek(node.decision!); }
                      }}
                    />
                    {fold ? (
                      <rect className="fold-chip" x={node.x - 13} y={node.y - NODE - 1} width={26} height={NODE * 2 + 2} rx={3}
                            onClick={() => toggleFold(node.id)} />
                    ) : (
                      <circle className={cls} cx={node.x} cy={node.y} r={NODE} />
                    )}
                    {fold ? <text className="fold-text" x={node.x} y={node.y + 3} textAnchor="middle">+{fold.hidden}</text> : null}
                    {here ? <circle className="node-selected" cx={node.x} cy={node.y} r={NODE + 4} /> : null}
                    {seen && !here ? <circle className="node-peek" cx={node.x} cy={node.y} r={NODE + 3} /> : null}
                    {node.children.length === 0 || node.id === ROOT ? (
                      <text className="node-label" x={node.x} y={node.y + NODE + 11} textAnchor="middle">
                        {node.depth === 0 ? "entry" : shortMove(node.last)}
                      </text>
                    ) : null}
                  </g>
                );
              })}
            </svg>
          </div>
        )}
      </PaneBody>

      {hover ? (
        <div className="inspector">
          <NodeInspector tree={tree} decisions={decisions} id={hover} attached={attached} />
        </div>
      ) : null}
    </>
  );
}

/** `step(cell=1,3, direction=east)` is a mouthful on a 7px node; the last line of it is not. */
function shortMove(label: string): string {
  const dir = /direction=([a-z]+)/.exec(label);
  if (dir) return dir[1].slice(0, 4);
  const tool = /^(\w+)/.exec(label.trim());
  return (tool?.[1] ?? label).slice(0, 7);
}

function nodeTitle(id: string, depth: number, progress: number, dead: boolean, current: boolean, why: ReturnType<typeof siblingContext>): string {
  const lines = [`depth ${depth} · believed ${Math.round(progress * 100)}%`];
  if (current) lines.push("the run is standing here");
  else if (dead) lines.push("given up");
  if (why.siblings.length > 1) {
    lines.push(`chosen over ${why.siblings.filter((s) => !s.chosen).length}:` +
      why.siblings.filter((s) => !s.chosen).map((s) => ` ${s.label} (${Math.round(s.progress * 100)}%)`).join(" ·"));
  }
  return lines.join("\n");
}

/** The node, in words: where it sits, and the choice it faced. */
function NodeInspector({ tree, decisions, id, attached }: {
  tree: SearchTree;
  decisions: Decision[];
  id: string;
  attached: Set<number>;
}) {
  const node = tree.nodes.get(id);
  if (!node) return null;
  const { chosen, siblings } = siblingContext(tree, decisions, id);
  const trail = pathTo(tree, id).slice(1).map((n) => shortMove(n.last)).join(" → ");
  const history = attached.has(node.decision ?? -1);

  return (
    <div className="inspector-grid">
      <div>
        <h4>State · depth {node.depth}</h4>
        <p className="mono nowrap">{node.id === ROOT ? "(the entry state)" : node.id}</p>
        <p style={{ marginTop: 4 }}>
          {trail ? `reached by ${trail}` : "the state the run began in"}
          {node.dead ? " · given up" : node.current ? " · standing here" : ""}
        </p>
      </div>
      <div>
        <h4>Believed</h4>
        <p className="mono">{Math.round(node.progress * 100)}% · {node.facts} fact{node.facts === 1 ? "" : "s"} known</p>
        {!history && node.decision !== null ? <p className="dim">not reached yet at this step</p> : null}
      </div>
      <div>
        <h4>Why this branch</h4>
        {siblings.length === 0 ? (
          <p>Nothing was chosen from here.</p>
        ) : (
          <table className="options-table">
            <tbody>
              {siblings.map((s) => (
                <tr key={s.label} className={`${s.chosen ? "chosen" : ""} ${s.ok ? "" : "failed"}`}>
                  <td>{s.chosen ? s.label : s.label.replace(/^\w+\(|\)$/g, (m) => (m.length > 1 ? "" : m))}</td>
                  <td className="score">{Math.round(s.progress * 100)}%{s.done ? " · exit" : ""}{s.ok ? "" : " · refused"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        {chosen?.refused.length ? <p className="dim">also refused: {chosen.refused.join(", ")}</p> : null}
      </div>
    </div>
  );
}
