/*
 * The Context Ledger world — a project's memory, read as an environment.
 *
 * Each action answers with a small report, and the engine keeps a whitespace-collapsed. 320-character
 * excerpt of it, so these parsers are written to work on one run-on line: they key off the labels the
 * adapter writes (`Backlog — High (3):`, `- ADR-7: … (2026-09-18) — accepted`, `memory/x.md:12: text`)
 * rather than off line breaks, because by the time it reaches the renderer there are none.
 *
 * Whatever does not parse is not thrown away: every section keeps the raw excerpt it came from.
 */

import { EngineEventFrame } from "../protocol";
import { Probe, probesOf } from "./probe";

export interface Decision {
  number: string;
  title: string;
  date: string;
  status: string;
}

export interface MemoryFile {
  rel: string;
  bytes: number;
}

export interface Hit {
  rel: string;
  line: number;
  text: string;
}

export interface FrictionEntry {
  head: string;
  fields: [string, string][];
}

export interface LedgerKnowledge {
  vault: string | null;
  core: string | null;
  digest: string | null;
  scale: string | null;
  current: { task: string; status: string; session?: string } | null;
  backlog: { section: string; total: number; rows: { ident: string; summary: string }[] }[];
  parking: string | null;
  decisions: Decision[];
  decisionDetail: { ref: string; fields: [string, string][] } | null;
  sessions: { heading: string; fields: [string, string][] }[];
  friction: { log: string; entries: FrictionEntry[] }[];
  searches: { scope: string; needle: string; total: number; hits: Hit[] }[];
  memory: { scope: string; files: MemoryFile[] }[];
  reads: { rel: string; text: string }[];
  refusedWrites: string[];
  unbootstrapped: string | null;
  probes: Probe[];
  /** Which of the ledger's reports the run has asked for. */
  seen: Set<string>;
}

const READ_TOOLS = new Set([
  "brief", "open_tasks", "decisions", "read_decision", "recent_sessions",
  "friction", "search_memory", "list_memory", "read_memory",
]);

const escapeRe = (s: string): string => s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");

/** `- **Key:** value` and `    Key: value` both arrive as `Key: value` once whitespace is collapsed. */
function pairs(text: string, keys: string[]): [string, string][] {
  if (keys.length === 0) return [];
  const alternation = keys.map(escapeRe).join("|");
  const re = new RegExp(`(?:^|\\s)(?:\\*\\*)?(${alternation})(?:\\*\\*)?:\\s*(.*?)(?=\\s(?:\\*\\*)?(?:${alternation})(?:\\*\\*)?:|$)`, "g");
  return [...text.matchAll(re)].map((m) => [m[1], m[2].trim()]);
}

const SESSION_KEYS = ["Agent", "Model", "Platform", "Core", "Task", "Outcome", "Open items"];
const FRICTION_KEYS = ["Problem", "Workaround / fix", "Prevent next time"];

const ADR = /(?:^|\s)-?\s*ADR-(\d+): (.*?) \((\d{4}-\d{2}-\d{2})\) — (.*?)(?=\s-\sADR-\d+:| Full text of one:|$)/g;
const BACKLOG_SECTION = /Backlog — (High|Medium|Low) \((\d+)\):/g;
const BACKLOG_ROW = /-\s(B-[\w-]+): (.*?)(?=\s-\sB-|\sBacklog — |\sParking lot|$)/g;
const CURRENT = /Current task: (.*?) — (.*?)(?=\s+session:|$|\sBacklog)/;
const SESSION = /session: (.*?)(?=\sBacklog|$)/;
const PARKING = /Parking lot \(not a queue\): (.*?)(?=$)/;
const SCALE = /\(memory: (\d+) files?; (\d+) closed office record\(s\) in history\/\)/;
const HIT = /([^\s]+\.(?:md|json|txt|conf|lock|yml|yaml)):(\d+): (.*?)(?=\s[^\s]+\.(?:md|json|txt|conf|lock|yml|yaml):\d+:|$)/g;
const MEMFILE = /-\s(\S+) \((\d+) B\)/g;
const SEARCH_HEAD = /(\d+) line\(s\) in scope ('[^']*'|"[^"]*") contain ('[^']*'|"[^"]*")/;
const MEMLIST_HEAD = /(\d+) file\(s\) in scope ('[^']*'|"[^"]*")/;
const FRICTION_HEAD = /(\d+) open (\w+) entr(?:y|ies)/;

const unquote = (s: string): string => s.replace(/^['"]|['"]$/g, "");

export function readLedger(events: EngineEventFrame[]): LedgerKnowledge {
  const k: LedgerKnowledge = {
    vault: null, core: null, digest: null, scale: null, current: null, backlog: [], parking: null,
    decisions: [], decisionDetail: null, sessions: [], friction: [], searches: [], memory: [], reads: [],
    refusedWrites: [], unbootstrapped: null, probes: [], seen: new Set(),
  };
  const probes = probesOf(events).filter((p) => READ_TOOLS.has(p.tool) || LEDGER_WRITES.has(p.tool));
  k.probes = probes;

  for (const p of probes) {
    if (LEDGER_WRITES.has(p.tool) && !p.ok && /would change the ledger/.test(p.excerpt)) {
      k.refusedWrites.push(p.move);
      continue;
    }
    if (p.excerpt.includes("no bootstrapped Context Ledger")) {
      k.unbootstrapped = p.excerpt;
      continue;
    }
    if (!p.ok) continue;
    k.seen.add(p.tool);
    const text = p.excerpt;

    switch (p.tool) {
      case "brief": {
        const head = /^Context Ledger at (.*?) — protocol core (.*?)(?= |$)/.exec(text);
        if (head) { k.vault = head[1]; k.core = head[2]; }
        const scale = SCALE.exec(text);
        if (scale) k.scale = `${scale[2]} closed in history · ${scale[1]} memory files`;
        const body = text
          .replace(/^Context Ledger at .*?(?=\s|$)/, "")
          .replace(SCALE, "")
          .replace(/^.*?\(STATE\.md has not been generated — reading the files directly\)\s*/, "")
          .trim();
        k.digest = body || null;
        break;
      }
      case "open_tasks": {
        const cur = CURRENT.exec(text);
        if (cur) {
          const session = SESSION.exec(text);
          k.current = { task: cur[1].trim(), status: cur[2].trim(), session: session?.[1]?.trim() };
        }
        const sections = [...text.matchAll(BACKLOG_SECTION)];
        sections.forEach((s, i) => {
          const from = (s.index ?? 0) + s[0].length;
          const to = i + 1 < sections.length ? sections[i + 1].index ?? text.length : text.length;
          const chunk = text.slice(from, to);
          const rows = [...chunk.matchAll(BACKLOG_ROW)].map((r) => ({ ident: r[1], summary: r[2].trim() }));
          k.backlog.push({ section: s[1], total: Number(s[2]), rows });
        });
        const parked = PARKING.exec(text);
        if (parked) k.parking = parked[1].trim();
        break;
      }
      case "decisions":
        for (const d of text.matchAll(ADR)) {
          const entry: Decision = { number: d[1], title: d[2].trim(), date: d[3], status: d[4].trim() };
          if (!k.decisions.some((x) => x.number === entry.number)) k.decisions.push(entry);
        }
        break;
      case "read_decision": {
        const head = /ADR-(\d+): (.*?) \((\d{4}-\d{2}-\d{2})\)/.exec(text);
        k.decisionDetail = {
          ref: head ? `ADR-${head[1]}: ${head[2].trim()} (${head[3]})` : text.split(" ").slice(0, 6).join(" "),
          fields: pairs(text, ["Status", "Context", "Decision", "Consequences"]),
        };
        break;
      }
      case "recent_sessions": {
        const body = text.replace(/^The last \d+ session\(s\) here:\s*/, "");
        // Entries are `- …` items, but the collapse ate the newlines: the first one is at the start of the
        // string, so the boundary has to allow for that or the first session is dropped.
        for (const chunk of body.split(/(?:^|\s)-\s(?=\d{4}-\d{2}-\d{2}|[A-Z])/).slice(1)) {
          const fields = pairs(chunk, SESSION_KEYS);
          const heading = fields.length > 0 ? chunk.slice(0, chunk.indexOf(fields[0][0])).trim() : chunk.trim();
          if (heading || fields.length > 0) k.sessions.push({ heading: heading || "(no heading)", fields });
        }
        break;
      }
      case "friction": {
        const head = FRICTION_HEAD.exec(text);
        const log = head ? head[2] : "friction";
        const body = text.replace(FRICTION_HEAD, "").replace(/^[^:]*:\s*/, "");
        const entries: FrictionEntry[] = [];
        for (const chunk of body.split(/(?:^|\s)-\s(?=\d{4}-\d{2}-\d{2})/).slice(1)) {
          const fields = pairs(chunk, FRICTION_KEYS);
          const heading = fields.length > 0 ? chunk.slice(0, chunk.indexOf(fields[0][0])).trim() : chunk.trim();
          entries.push({ head: heading.replace(/\s+$/, ""), fields });
        }
        if (entries.length === 0 && /^no open/.test(text)) entries.push({ head: text, fields: [] });
        if (!k.friction.some((f) => f.log === log)) k.friction.push({ log, entries });
        break;
      }
      case "search_memory": {
        const head = SEARCH_HEAD.exec(text);
        if (!head) break;
        // The adapter signs off with a note about the history scope; it is about the search, not a hit.
        const body = text.replace(/\s*\(closed offices under history\/ are outside this scope[^)]*\)\s*$/, "");
        const hits = [...body.matchAll(HIT)].map((h) => ({ rel: h[1], line: Number(h[2]), text: h[3].trim() }));
        k.searches.push({
          scope: unquote(head[2]),
          needle: unquote(head[3]),
          total: Number(head[1]),
          hits,
        });
        break;
      }
      case "list_memory": {
        const head = MEMLIST_HEAD.exec(text);
        const files = [...text.matchAll(MEMFILE)].map((m) => ({ rel: m[1], bytes: Number(m[2]) }));
        k.memory.push({ scope: head ? unquote(head[2]) : "memory", files });
        break;
      }
      case "read_memory": {
        const rel = p.args["path"] ?? text.split(":")[0];
        if (!k.reads.some((r) => r.rel === rel)) k.reads.push({ rel, text });
        break;
      }
      default:
        break;
    }
  }
  return k;
}

const LEDGER_WRITES = new Set(["add_backlog_row", "log_inefficiency", "record_decision", "append_note"]);

export const LEDGER_SECTIONS = [
  { id: "tasks", label: "tasks" },
  { id: "decisions", label: "decisions" },
  { id: "sessions", label: "sessions" },
  { id: "friction", label: "friction" },
  { id: "memory", label: "memory" },
] as const;

export type LedgerSection = typeof LEDGER_SECTIONS[number]["id"];
