/*
 * The world surface for worlds that are not a grid.
 *
 * A maze is drawn because it can be: the run's own sentences describe squares and openings. The other three
 * worlds answer in prose — a directory listing, a vault report, a page — and prose has structure, so the
 * surface is a set of cards built from the same parsers the map's knowledge is built from. What it is not
 * is a raw event dump: every card here is a *belief* (this path exists, this backlog row is open), with the
 * run's own reading behind it.
 *
 * It sits where the map sits, on purpose. The world is the hero of the run view whatever the world is; a
 * world with no drawing is not a world with no picture.
 */

import { useMemo } from "react";
import { EngineEventFrame } from "../core/types";
import { readFiles, treeOf, Node, FilesKnowledge } from "../core/worlds/files";
import { readLedger, LedgerKnowledge } from "../core/worlds/ledger";
import { readBrowser, BrowserKnowledge } from "../core/worlds/browser";
import { Empty, PaneBody, PaneHead } from "../ui/atoms";

export interface Row {
  left: string;
  right?: string;
  tone?: "ok" | "fail" | "dim";
  indent?: number;
}

export interface Card {
  title: string;
  hint?: string;
  rows: Row[];
  empty?: string;
}

export function WorldSurface({ world, events }: { world: string; events: EngineEventFrame[] }) {
  const cards = useMemo(() => cardsFor(world, events), [world, events]);

  return (
    <>
      <PaneHead title="World" sub={`${world} — read as it is observed, never in advance`} />
      <PaneBody scroll pad>
        {cards.length === 0 ? (
          <Empty title="Nothing read yet">
            This world answers in prose. Each reading the run takes becomes a card here — a directory, a
            vault report, a page — as soon as it is taken.
          </Empty>
        ) : (
          <div style={{ display: "grid", gap: 12, gridTemplateColumns: "repeat(auto-fit, minmax(300px, 1fr))" }}>
            {cards.map((card) => (
              <section key={card.title} className="card">
                <h4>{card.title}</h4>
                {card.hint ? <p className="dim" style={{ fontSize: 10.5, marginBottom: 6 }}>{card.hint}</p> : null}
                {card.rows.length === 0 ? (
                  <p className="dim" style={{ fontSize: 11.5 }}>{card.empty ?? "nothing yet"}</p>
                ) : (
                  <ul>
                    {card.rows.map((row, i) => (
                      <li key={`${row.left}-${i}`} className={row.tone ?? ""} style={{ paddingLeft: (row.indent ?? 0) * 12 }}>
                        <span className="nowrap" title={row.left}>{row.left}</span>
                        {row.right ? <em>{row.right}</em> : null}
                      </li>
                    ))}
                  </ul>
                )}
              </section>
            ))}
          </div>
        )}
      </PaneBody>
    </>
  );
}

/* ── the three prose worlds, each as its own set of cards ───────────────── */

function cardsFor(world: string, events: EngineEventFrame[]): Card[] {
  if (world === "files") return fileCards(readFiles(events));
  if (world === "ledger") return ledgerCards(readLedger(events));
  if (world === "browser") return browserCards(readBrowser(events));
  return [];
}

const bytes = (n: number): string => (n < 1024 ? `${n} B` : n < 1024 * 1024 ? `${(n / 1024).toFixed(1)} KB` : `${(n / (1024 * 1024)).toFixed(1)} MB`);

function fileCards(k: FilesKnowledge): Card[] {
  const cards: Card[] = [];
  const tree = treeOf(k);

  if (tree) {
    const rows: Row[] = [];
    const walk = (node: Node, depth: number): void => {
      rows.push({
        left: `${node.name}${node.dir ? "/" : ""}`,
        right: node.dir ? "dir" : node.bytes === undefined ? "file" : bytes(node.bytes),
        indent: depth,
        tone: node.read ? "ok" : undefined,
      });
      for (const child of node.children) walk(child, depth + 1);
    };
    walk(tree, 0);
    cards.push({
      title: `Known under ${tree.name}`,
      hint: k.root ? `rooted at ${k.root}` : undefined,
      rows,
      empty: "no path read yet",
    });
  }

  cards.push({
    title: "Readings",
    hint: "each one is a real file read, in the order they happened",
    rows: k.reads.map((r) => ({ left: r.path, right: `${r.text.length} chars`, tone: "ok" as const })),
    empty: "nothing read in full",
  });

  cards.push({
    title: "Searches",
    rows: k.finds.map((f) => ({
      left: `${f.needle} under ${f.root}`,
      right: f.searched === undefined ? `${f.total} found` : `${f.total} of ${f.searched} paths`,
      tone: f.total > 0 ? ("ok" as const) : undefined,
    })),
    empty: "no search run",
  });

  const refusals: Row[] = [
    ...k.refusals.map((r) => ({ left: r.asked, right: `outside ${r.root}`, tone: "fail" as const })),
    ...k.failures.map((f) => ({ left: `${f.tool} ${f.path}`.trim(), right: f.why, tone: "fail" as const })),
  ];
  cards.push({ title: "Refused", rows: refusals, empty: "nothing was refused" });
  return cards;
}

function ledgerCards(k: LedgerKnowledge): Card[] {
  const cards: Card[] = [];
  cards.push({
    title: "The vault",
    rows: [
      ...(k.vault ? [{ left: k.vault, right: "root" }] : []),
      ...(k.core ? [{ left: `protocol core ${k.core}`, right: "version" }] : []),
      ...(k.scale ? [{ left: k.scale, right: "scale" }] : []),
      ...(k.current ? [{ left: k.current.task, right: `${k.current.status}${k.current.session ? ` · ${k.current.session}` : ""}` }] : []),
    ],
    empty: k.unbootstrapped ? "no vault here" : "nothing read yet",
  });

  cards.push({
    title: "Backlog",
    rows: k.backlog.flatMap((section) =>
      section.rows.map((row, i) => ({
        left: `${row.ident} ${row.summary}`,
        right: i === 0 ? `${section.section} · of ${section.total}` : undefined,
      }))),
    empty: "no backlog read",
  });

  cards.push({
    title: "Decisions in force",
    rows: k.decisions.map((d) => ({ left: `ADR-${d.number}: ${d.title}`, right: `${d.date} · ${d.status}`, tone: d.status === "accepted" ? ("ok" as const) : undefined })),
    empty: "none read",
  });

  cards.push({
    title: "Memory",
    rows: k.memory.flatMap((group) => group.files.map((f) => ({ left: f.rel, right: bytes(f.bytes) }))),
    empty: "no file listed",
  });

  cards.push({
    title: "Search results",
    rows: k.searches.flatMap((s) => s.hits.map((h) => ({ left: `${h.rel}:${h.line}`, right: h.text }))),
    empty: "nothing searched",
  });

  if (k.refusedWrites.length > 0) {
    cards.push({ title: "Refused writes", rows: k.refusedWrites.map((w) => ({ left: w, right: "read-only world", tone: "fail" as const })) });
  }
  return cards;
}

function browserCards(k: BrowserKnowledge): Card[] {
  const cards: Card[] = [];
  cards.push({
    title: "Page",
    rows: k.page ? [{ left: k.page.title || "(untitled)", right: k.page.url }] : [],
    empty: "the run never said where it was",
  });
  cards.push({
    title: "Links it found",
    rows: k.links.map((l) => ({ left: l.text || "(no text)", right: l.href })),
    empty: "no links read",
  });
  cards.push({
    title: "Elements",
    rows: k.found.map((f) => ({ left: `${f.tag}${f.id ? `#${f.id}` : ""}`, right: `${f.count} match${f.count === 1 ? "" : "es"} · ${f.size} · at ${f.at}` })),
    empty: "no element looked up",
  });
  cards.push({
    title: "What it did",
    rows: k.trail.map((t) => ({ left: t.detail || t.move, right: t.kind, tone: t.ok ? undefined : ("fail" as const) })),
    empty: "nothing yet",
  });
  if (k.errors.length > 0) {
    cards.push({ title: "Failed", rows: k.errors.map((e) => ({ left: e, tone: "fail" as const })) });
  }
  return cards;
}
