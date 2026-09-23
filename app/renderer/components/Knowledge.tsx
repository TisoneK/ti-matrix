/*
 * What the run has established, and what it has ruled out.
 *
 * Facts are the engine's product: each one is a real observation, kept verbatim, and the list is what the
 * final answer will be built from. Dead ends are the other half of the same ledger — the moves this run
 * tried and will not try again.
 */

import { EngineEventFrame } from "../protocol";
import { Vitals, newestFirst } from "../lib/vitals";
import { Panel } from "../ui/Panel";

export function Knowledge({ vitals, running }: { vitals: Vitals; running: boolean }) {
  const facts = newestFirst(vitals.facts);
  const deadEnds = [...new Set(vitals.deadEnds)].reverse();

  return (
    <>
      <Panel title="what this run has established" grow={false}
             meta={`${facts.length} fact${facts.length === 1 ? "" : "s"}`
               + (vitals.ruledOut > 0 ? ` · ${vitals.ruledOut} moves ruled out` : "")}>
        {facts.length === 0 ? (
          <p className="hint">
            {running
              ? "Nothing yet — a fact is an answer the world actually gave, and the first one lands with the first probe."
              : "Nothing yet. Facts are what a run keeps: the exact text the world handed back, never a summary."}
          </p>
        ) : (
          <ol className="facts">
            {facts.map((fact, i) => (
              <li key={`${facts.length - i}`} className={i === 0 && running ? "fresh" : undefined}>
                <span className="fact-n">F{facts.length - i}</span>
                <span className="fact-text">{fact}</span>
              </li>
            ))}
          </ol>
        )}
      </Panel>

      {deadEnds.length > 0 ? (
        <Panel title="ruled out" meta={`${deadEnds.length}`}>
          <ul className="plain-list dead-ends">
            {deadEnds.map((move, i) => (
              <li key={i}><code>{move}</code></li>
            ))}
          </ul>
          <p className="hint">
            A probe that failed is remembered by its fingerprint, so the same move is not proposed twice.
          </p>
        </Panel>
      ) : null}
    </>
  );
}
