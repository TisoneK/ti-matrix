/*
 * The search, drawn. This is the thing the engine actually is — a beam that widens, picks a branch,
 * and gives one up when nothing came of it — so the window shows it rather than only narrating it.
 */

import { useMemo } from "react";
import { EngineEventFrame } from "../protocol";
import { layoutTree, readTree } from "../lib/tree";
import { pct } from "../lib/format";
import { Bar } from "../ui/Display";
import { Panel } from "../ui/Panel";

const PAD = 18;
const shorten = (s: string, n = 22): string => (s.length > n ? `${s.slice(0, n - 1)}…` : s);

export function SearchTree({ events }: { events: EngineEventFrame[] }) {
  const tree = useMemo(() => readTree(events), [events]);
  const layout = useMemo(() => layoutTree(tree), [tree]);

  if (tree.states === 0) {
    return (
      <Panel title="the search">
        <p className="hint">
          Nothing searched yet. Every state the engine reaches is drawn here, with the branch it took and
          the ones it gave up.
        </p>
      </Panel>
    );
  }

  return (
    <Panel title="the search"
           meta={`${tree.states} states · depth ${tree.maxDepth}${tree.backtracks ? ` · ${tree.backtracks} backtrack${tree.backtracks === 1 ? "" : "s"}` : ""}`}>
      <div className="tree-head">
        <span className="dim">progress</span>
        <Bar value={tree.progress} tone={tree.progress >= 1 ? "ok" : undefined} />
        <span className="mono-dim">{pct(tree.progress)}</span>
      </div>
      <div className="tree-scroll">
        <svg width={layout.width + PAD * 2} height={layout.height + PAD * 2} role="img"
             aria-label={`search tree: ${tree.states} states, greatest depth ${tree.maxDepth}`}>
          <g transform={`translate(${PAD}, ${PAD - 6})`}>
            {layout.edges.map((e, i) => (
              <line key={i} className={`st-edge${e.dead ? " dead" : ""}`}
                    x1={e.from.x} y1={e.from.y} x2={e.to.x} y2={e.to.y} />
            ))}
            {layout.placed.map((p) => (
              <g key={p.node.id} className={`st-node${p.node.current ? " current" : ""}${p.node.dead ? " dead" : ""}`}>
                <circle cx={p.x} cy={p.y} r={p.node.current ? 6 : 4} />
                {p.node.last && (p.node.current || p.node.children.length === 0) ? (
                  <text x={p.x + 10} y={p.y + 4}>{shorten(p.node.last)}</text>
                ) : null}
                <title>{`depth ${p.node.depth} · progress ${pct(p.node.progress)} · ${p.node.facts} facts`}</title>
              </g>
            ))}
          </g>
        </svg>
      </div>
    </Panel>
  );
}
