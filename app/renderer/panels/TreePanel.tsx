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

// Room for a node that says something, plus the lane of passed-over candidates that hangs beside it —
// these were sized for a 7px dot, and the picture was exactly that: anonymous circles with the move's name
// on the few leaves that happened to get one.
const COL = 136;
const ROW = 62;
// Wide enough for the tool names this app actually has — `find_files`, `stat_path`, `read_file` — because a
// plate that reads `find_fi` looks like a bug rather than an abbreviation.
const NODE_W = 108;
const NODE_H = 28;

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
      {/* The aggregate "it looked at 38 of 38 it could have" used to be here and forced the head to wrap its
          button onto a second, ragged line. It is the sum of a number every row already carries ("weighed 4
          of 35"), so the head keeps the two facts that exist nowhere else. */}
      <PaneHead title="Search tree"
                sub={`${tree.states} state${tree.states === 1 ? "" : "s"} · ${tree.backtracks} retreat${tree.backtracks === 1 ? "" : "s"}`
                  + (weighed > 0 ? ` · ${weighed} passed over` : "")
                  + (hidden > 0 ? ` · ${hidden} folded` : "")}>
        <Chip label="fold cold branches" pressed={foldDead} onClick={() => setFoldDead((v) => !v)}
              title="fold a branch the run has already given up" />
      </PaneHead>

      <PaneBody>
        {tree.states === 0 ? (
          <Empty eyebrow="the search" title="No states yet">
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
                  d={`M${edge.from.x} ${edge.from.y + NODE_H / 2} C${edge.from.x} ${edge.from.y + ROW * 0.55}, ${edge.to.x} ${edge.to.y - ROW * 0.55}, ${edge.to.x} ${edge.to.y - NODE_H / 2}`}
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
                      // A lane out of the node's right edge, one per candidate, stacked so their names
                      // can be read. These were 2.6px dots on a fan: the shape was honest and the
                      // information was invisible — which option was weighed, and what it scored,
                      // existed only in a tooltip.
                      const refused = option.ok === false;
                      const lane = 23;
                      const x0 = node.x + NODE_W / 2;
                      const x1 = x0 + 14;
                      const y = node.y + (i - (passed.length - 1) / 2) * lane;
                      return (
                        <g key={option.fp} className={`stub ${refused ? "refused" : ""}`}>
                          <title>
                            {`${option.label} — ${refused ? "the world refused this"
                              : option.progress === undefined ? "not scored"
                                : `scored ${Math.round(option.progress * 100)}%`}`}
                            {option.excerpt ? `\n${option.excerpt.slice(0, 160)}` : ""}
                          </title>
                          <path className="stub-edge" d={`M${x0} ${node.y} L${x1} ${y}`} />
                          <rect className="stub-plate" x={x1} y={y - 9} width={112} height={18} rx={4} />
                          <text className="stub-move" x={x1 + 6} y={y + 3.5}>{shortMove(option.label)}</text>
                          <text className="stub-score" x={x1 + 106} y={y + 3.5} textAnchor="end">
                            {refused ? "refused" : option.progress === undefined ? "—" : `${Math.round(option.progress * 100)}%`}
                          </text>
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
                // The branch's state decides the plate's treatment; the same class goes on the label and
                // the belief bar so a cold branch recedes as one object rather than three faded pieces.
                const state = node.dead ? "cold" : isCurrent ? "live" : settled ? "settled" : "alive";
                const clickable = node.decision !== null;
                const here = node.decision !== null && node.decision === cursor;
                const seen = node.decision !== null && node.decision === peek;
                const move = node.depth === 0 ? "entry" : shortMove(node.last);
                return (
                  <g key={node.id} className="node-group"
                     onMouseEnter={() => { setHover(node.id); if (node.decision !== null) onHover?.(node.decision); }}
                     onMouseLeave={() => { setHover((h) => (h === node.id ? null : h)); onHover?.(null); }}>
                    <title>{nodeTitle(node.id, node.depth, node.progress, node.dead, node.current, siblingContext(tree, decisions, node.id))}</title>
                    {here ? <rect className="node-selected" x={node.x - NODE_W / 2 - 3} y={node.y - NODE_H / 2 - 3} width={NODE_W + 6} height={NODE_H + 6} rx={9} /> : null}
                    {seen && !here ? <rect className="node-peek" x={node.x - NODE_W / 2 - 2} y={node.y - NODE_H / 2 - 2} width={NODE_W + 4} height={NODE_H + 4} rx={8} /> : null}
                    {fold ? (
                      <g className="node-fold" onClick={() => toggleFold(node.id)}>
                        <rect className="fold-chip" x={node.x - NODE_W / 2} y={node.y - NODE_H / 2} width={NODE_W} height={NODE_H} rx={6} />
                        <text className="fold-text" x={node.x} y={node.y + 3.5} textAnchor="middle">+{fold.hidden} folded</text>
                      </g>
                    ) : (
                      <>
                        <rect className={`node-body ${state}`} x={node.x - NODE_W / 2} y={node.y - NODE_H / 2} width={NODE_W} height={NODE_H} rx={6} />
                        {/* The move it made, on every node rather than only on the leaves: a diagram whose
                            boxes have no names makes the reader cross-reference the ledger for the one thing
                            the diagram exists to show. */}
                        <text className={`node-move ${state}`} x={node.x} y={node.y + 1} textAnchor="middle">{move}</text>
                        {/* What it believed here, drawn rather than printed — the bar's length is the number
                            — with the number itself small in the corner for the exact value. */}
                        <rect className="node-belief-track" x={node.x - NODE_W / 2 + 7} y={node.y + NODE_H / 2 - 6} width={NODE_W - 14} height={2.5} rx={1.25} />
                        <rect className={`node-belief ${state}`} x={node.x - NODE_W / 2 + 7} y={node.y + NODE_H / 2 - 6} width={Math.max(1, (NODE_W - 14) * node.progress)} height={2.5} rx={1.25} />
                        <text className="node-score" x={node.x + NODE_W / 2 - 4} y={node.y - NODE_H / 2 + 2} textAnchor="end">
                          {Math.round(node.progress * 100)}
                        </text>
                      </>
                    )}
                    <rect
                      className="node-hit"
                      x={node.x - NODE_W / 2} y={node.y - NODE_H / 2} width={NODE_W} height={NODE_H} rx={6}
                      tabIndex={clickable ? 0 : -1}
                      role={clickable ? "button" : undefined}
                      aria-label={clickable ? `jump to step ${node.decision! + 1}: ${node.last || "entry"}` : undefined}
                      onClick={() => clickable && onSeek(node.decision!)}
                      onKeyDown={(e) => {
                        if (!clickable) return;
                        if (e.key === "Enter" || e.key === " ") { e.preventDefault(); onSeek(node.decision!); }
                      }}
                    />
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

/** `step(cell=1,3, direction=east)` is a mouthful on a node; the last line of it is not. */
function shortMove(label: string): string {
  const dir = /direction=([a-z]+)/.exec(label);
  if (dir) return dir[1].slice(0, 4);
  const tool = /^(\w+)/.exec(label.trim());
  return (tool?.[1] ?? label).slice(0, 11);
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
