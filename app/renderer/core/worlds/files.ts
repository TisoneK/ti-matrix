/*
 * The files world, as a tree.
 *
 * `RootedFiles` resolves every path under its root before the adapter sees it, so the paths in these
 * observations are absolute and symlink-free. The adapter answers in one line:
 *
 *   Contents of /a/b — 3 entries: 📁 sub · 📄 x.txt (11 B) · 📄 y.md (2 KB)
 *   /a/b/x.txt — file, 11 bytes, modified 2026-09-23 14:05
 *   2 file(s) under /a with '.py' in the name: /a/deep.py · /a/sub/deep.py
 *   not a directory: /a/nope        (also: not a file: …, does not exist: …)
 *   refused: '/etc/passwd' is not a path inside /home/you/code
 *
 * One catch worth remembering: the engine stores every observation whitespace-collapsed and cut to 320
 * characters, so what arrives here is a single line and the tail may be missing. Parse what is there, and
 * keep the raw text alongside it for the rest.
 */

import { Probe, probesOf } from "./probe";
import { EngineEventFrame } from "../../protocol";

export interface DirEntry {
  name: string;
  dir: boolean;
  bytes?: number;
}

export interface Listing {
  path: string;
  total: number;
  entries: DirEntry[];
  more: number;
  seq: number;
}

export interface FileRead {
  path: string;
  text: string;
  seq: number;
}

export interface StatFact {
  path: string;
  kind: "dir" | "file";
  bytes: number;
  modified: string;
  seq: number;
}

export interface FindResult {
  root: string;
  needle: string;
  paths: string[];
  total: number;
  searched?: number;
  seq: number;
}

export interface FilesKnowledge {
  root: string | null;
  listings: Listing[];
  reads: FileRead[];
  stats: StatFact[];
  finds: FindResult[];
  refusals: { asked: string; root: string; seq: number }[];
  failures: { tool: string; path: string; why: string; seq: number }[];
  /** Every probe this world answered, for the raw record under the tree. */
  probes: Probe[];
}

const LISTING = /^Contents of (.*?) — (\d+) entries?: (.*)$/;
const LISTED_ITEM = /^(📄|📁)\s+(.*?)(?:\s+\((\d+) B\))?$/;
const MORE = /… \(\+(\d+) more\)$/;
const STAT = /^(.*?) — (dir|file), (\d+) bytes, modified (\d{4}-\d{2}-\d{2} \d{2}:\d{2})$/;
const FOUND = /^(\d+) file\(s\) under (.*?) with (.*?) in the name: (.*)$/;
const FOUND_NONE = /^no file under (.*?) has (.*?) in its name \((\d+) paths searched\)$/;
const REFUSED = /^refused: (.*?) is not a path inside (.*)$/;
const NOT_A_DIR = /^not a directory: (.*)$/;
const NOT_A_FILE = /^not a file: (.*)$/;
const NO_SUCH = /^does not exist: (.*)$/;

const unquote = (s: string): string => s.replace(/^['"]|['"]$/g, "");

export function readFiles(events: EngineEventFrame[]): FilesKnowledge {
  const k: FilesKnowledge = {
    root: null, listings: [], reads: [], stats: [], finds: [], refusals: [], failures: [], probes: [],
  };
  const probes = probesOf(events);
  k.probes = probes.filter((p) => FILE_TOOLS.has(p.tool));
  const seenListing = new Set<string>();
  const seenStat = new Set<string>();

  for (const p of k.probes) {
    const path = p.args["path"] ?? "";
    if (!p.ok) {
      const refused = REFUSED.exec(p.excerpt);
      if (refused) {
        k.refusals.push({ asked: unquote(refused[1]), root: refused[2], seq: p.seq });
        k.root = k.root ?? refused[2];
        continue;
      }
      const why = NOT_A_DIR.exec(p.excerpt) ?? NOT_A_FILE.exec(p.excerpt) ?? NO_SUCH.exec(p.excerpt);
      if (why) k.failures.push({ tool: p.tool, path: why[1], why: p.excerpt.split(":")[0], seq: p.seq });
      continue;
    }

    if (p.tool === "list_dir") {
      const m = LISTING.exec(p.excerpt);
      if (!m) continue;
      const body = m[3];
      const more = MORE.exec(body);
      const items = (more ? body.slice(0, more.index) : body)
        .split(" · ")
        .map((s) => LISTED_ITEM.exec(s.trim()))
        .filter((x): x is RegExpExecArray => x !== null)
        .map((x) => ({ dir: x[1] === "📁", name: x[2], bytes: x[3] ? Number(x[3]) : undefined }));
      if (seenListing.has(m[1])) k.listings = k.listings.filter((l) => l.path !== m[1]);
      seenListing.add(m[1]);
      k.listings.push({ path: m[1], total: Number(m[2]), entries: items, more: more ? Number(more[1]) : 0, seq: p.seq });
    } else if (p.tool === "read_file") {
      if (!k.reads.some((r) => r.path === path)) k.reads.push({ path, text: p.excerpt, seq: p.seq });
    } else if (p.tool === "stat_path") {
      const m = STAT.exec(p.excerpt);
      if (!m || seenStat.has(m[1])) continue;
      seenStat.add(m[1]);
      k.stats.push({ path: m[1], kind: m[2] as "dir" | "file", bytes: Number(m[3]), modified: m[4], seq: p.seq });
    } else if (p.tool === "find_files") {
      const hits = FOUND.exec(p.excerpt);
      if (hits) {
        k.finds.push({ root: hits[2], needle: unquote(hits[3]), paths: hits[4].split(" · "), total: Number(hits[1]), seq: p.seq });
        continue;
      }
      const none = FOUND_NONE.exec(p.excerpt);
      if (none) k.finds.push({ root: none[1], needle: unquote(none[2]), paths: [], total: 0, searched: Number(none[3]), seq: p.seq });
    }
  }
  return k;
}

const FILE_TOOLS = new Set(["list_dir", "read_file", "stat_path", "find_files"]);

/* ── the tree ────────────────────────────────────────────────────────────── */

export interface Node {
  name: string;
  path: string;
  dir: boolean;
  bytes?: number;
  /** Set when the run listed this directory: its children are known, not guessed. */
  children: Node[];
  listed: boolean;
  read: boolean;
  stated?: StatFact;
}

const parentOf = (path: string): string => {
  const cut = path.replace(/\/+$/, "").lastIndexOf("/");
  return cut <= 0 ? "/" : path.slice(0, cut);
};

/** The directories above a path, so a file can be placed even if its parent was never listed. */
function ancestorsOf(path: string): string[] {
  const out: string[] = [];
  let cur = parentOf(path);
  while (cur && cur !== "/" && !out.includes(cur)) {
    out.push(cur);
    const next = parentOf(cur);
    if (next === cur) break;
    cur = next;
  }
  return out;
}

/**
 * A tree of what the run has actually looked at. Directories come from listings; files come from listings,
 * reads, stats and finds — a file the run read but never listed still appears, under its real parent.
 */
export function treeOf(k: FilesKnowledge): Node | null {
  const nodes = new Map<string, Node>();
  const ensure = (path: string, dir: boolean, extra?: Partial<Node>): Node => {
    let node = nodes.get(path);
    if (!node) {
      node = { name: path.split("/").pop() || path, path, dir, children: [], listed: false, read: false, ...extra };
      nodes.set(path, node);
    }
    if (extra?.listed) node.listed = true;
    if (extra?.read) node.read = true;
    if (extra?.bytes !== undefined && node.bytes === undefined) node.bytes = extra.bytes;
    return node;
  };

  const attach = (node: Node): void => {
    const parent = nodes.get(parentOf(node.path));
    if (parent && parent !== node) {
      if (!parent.children.some((c) => c.path === node.path)) parent.children.push(node);
    }
  };

  for (const listing of k.listings) {
    ensure(listing.path, true, { listed: true });
    for (const entry of listing.entries) {
      const child = ensure(`${listing.path}/${entry.name}`, entry.dir, { bytes: entry.bytes });
      attach(child);
    }
  }
  for (const read of k.reads) ensure(read.path, false, { read: true });
  for (const stat of k.stats) {
    const node = ensure(stat.path, stat.kind === "dir", { bytes: stat.bytes });
    node.stated = stat;
  }
  for (const find of k.finds) for (const path of find.paths) ensure(path, false);

  // Files whose parent was never listed need their own placeholder directories to hang from.
  for (const node of [...nodes.values()]) {
    for (const ancestor of ancestorsOf(node.path)) ensure(ancestor, true);
  }
  for (const node of [...nodes.values()]) attach(node);

  const root = k.root ? nodes.get(k.root) : undefined;
  if (root) return root;

  const all = [...nodes.values()];
  const roots = all.filter((n) => !nodes.has(parentOf(n.path)) || parentOf(n.path) === n.path);
  if (roots.length === 0) return null;
  if (roots.length === 1) return roots[0];
  return { name: "(everything the run touched)", path: "", dir: true, children: roots, listed: false, read: false };
}
