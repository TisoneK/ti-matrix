/*
 * The library: runs that outlive the window that watched them.
 *
 * A single run watched once is an anecdote. Twenty runs, sorted by how many surprises they hit and how
 * long they took, is evidence — and it is the only way to answer "is this model actually getting worse at
 * the maze" or "does the seed matter more than the model". So every finished run is saved, listed with the
 * numbers that make runs comparable, and reloadable into the same three panels.
 *
 * The table is sortable by clicking a column header, because the questions people ask of a run list are
 * all "which one was worst at X".
 */

import { useMemo, useState } from "react";
import { ArtifactMeta } from "../core/types";
import { Badge, Empty, PaneHead } from "../ui/atoms";
import { Button } from "../ui/controls";

type SortKey = "startedAt" | "durationMs" | "decisions" | "surprises" | "backtracks" | "meanConfidence" | "world" | "model" | "seed";

const COLUMNS: { key: SortKey; label: string; numeric?: boolean }[] = [
  { key: "startedAt", label: "when" },
  { key: "world", label: "world" },
  { key: "seed", label: "seed" },
  { key: "model", label: "model" },
  { key: "decisions", label: "steps", numeric: true },
  { key: "backtracks", label: "retreats", numeric: true },
  { key: "surprises", label: "surprises", numeric: true },
  { key: "meanConfidence", label: "mean belief", numeric: true },
  { key: "durationMs", label: "took", numeric: true },
];

export function LibraryPanel({ metas, loading, onOpen, onDelete, onCompare, selected, onSelect, onRefresh, persisted }: {
  metas: ArtifactMeta[];
  loading: boolean;
  /** By id: the panel never touches a store, it only says which run the viewer pointed at. */
  onOpen: (id: string) => void;
  onDelete: (id: string) => void;
  onCompare: (ids: [string, string]) => void;
  selected: string[];
  onSelect: (id: string) => void;
  onRefresh: () => void;
  persisted: boolean;
}) {
  const [sort, setSort] = useState<{ key: SortKey; dir: 1 | -1 }>({ key: "startedAt", dir: -1 });

  const rows = useMemo(() => {
    const copy = [...metas];
    copy.sort((a, b) => {
      const x = a[sort.key];
      const y = b[sort.key];
      if (typeof x === "number" && typeof y === "number") return (x - y) * sort.dir;
      return String(x ?? "").localeCompare(String(y ?? "")) * sort.dir;
    });
    return copy;
  }, [metas, sort]);

  const toggleSort = (key: SortKey) => setSort((s) => ({ key, dir: s.key === key ? (s.dir === 1 ? -1 : 1) : key === "startedAt" ? -1 : 1 }));

  return (
    <section className="pane" aria-label="the session library">
      <PaneHead title="Library" sub={persisted ? `${metas.length} run${metas.length === 1 ? "" : "s"} saved` : "not saved to disk — no shell around this window"}>
        {selected.length === 2 ? (
          <Button variant="primary" size="sm" onClick={() => onCompare(selected as [string, string])}>
            Compare these two
          </Button>
        ) : selected.length === 1 ? (
          <span className="pane-sub">pick one more to compare</span>
        ) : (
          <span className="pane-sub">select two to compare</span>
        )}
        <Button size="sm" onClick={onRefresh} disabled={loading}>{loading ? "reading…" : "refresh"}</Button>
      </PaneHead>

      <div className="library">
        {metas.length === 0 ? (
          <Empty title={loading ? "Reading the library…" : "No runs saved yet"}>
            Finish a run and it lands here: the events verbatim, the world it was driven against, the model
            that proposed for it, and how it ended. Nothing is kept until a run is over.
          </Empty>
        ) : (
          <table className="lib-table">
            <thead>
              <tr>
                <th style={{ width: 28 }}><span className="sr">pick</span></th>
                <th>run</th>
                {COLUMNS.map((c) => (
                  <th key={c.key} style={c.numeric ? { textAlign: "right" } : undefined}>
                    <button type="button" onClick={() => toggleSort(c.key)}
                            title={`sort by ${c.label}`}>
                      {c.label}{sort.key === c.key ? <span className="arrow"> {sort.dir === 1 ? "↑" : "↓"}</span> : null}
                    </button>
                  </th>
                ))}
                <th><span className="sr">actions</span></th>
              </tr>
            </thead>
            <tbody>
              {rows.map((m) => (
                <tr key={m.id} aria-selected={selected.includes(m.id)}>
                  <td>
                    <input type="checkbox" checked={selected.includes(m.id)} onChange={() => onSelect(m.id)}
                           aria-label={`select ${m.name} for comparison`} />
                  </td>
                  <td>
                    <div className="name nowrap" title={m.goal}>{m.goal || m.name}</div>
                    <div className="dim" style={{ fontSize: 10.5 }}>
                      {m.settled ? <Badge tone="ok">settled</Badge>
                        : <Badge tone={m.reason === "error" ? "fail" : "warn"}>{m.reason ?? "unsettled"}</Badge>}
                    </div>
                  </td>
                  <td className="mono dim">{when(m.startedAt)}</td>
                  <td>{m.world}</td>
                  <td className="mono">{m.seed ?? "—"}</td>
                  <td className="mono nowrap">{m.model || "—"}</td>
                  <td className="num">{m.decisions}</td>
                  <td className="num">{m.backtracks}</td>
                  <td className="num" style={{ color: m.surprises > 0 ? "var(--red)" : undefined }}>{m.surprises}</td>
                  <td className="num">{Math.round(m.meanConfidence * 100)}%</td>
                  <td className="num dim">{took(m.durationMs)}</td>
                  <td>
                    <div className="lib-actions">
                      <Button size="sm" onClick={() => onOpen(m.id)}>open</Button>
                      <Button size="sm" variant="danger" onClick={() => onDelete(m.id)} title="delete this run from disk">delete</Button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </section>
  );
}

const when = (iso: string): string => {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "—";
  return `${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")} ${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
};

const took = (ms: number): string => {
  if (ms < 1000) return `${Math.round(ms)}ms`;
  const s = Math.round(ms / 1000);
  return s < 60 ? `${s}s` : `${Math.floor(s / 60)}m${String(s % 60).padStart(2, "0")}`;
};
