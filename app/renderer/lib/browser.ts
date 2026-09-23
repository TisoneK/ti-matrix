/*
 * The browser world — a real Chrome behind DevTools, driven one action at a time.
 *
 * The adapter only names the page in some of its answers (`loaded <url> — <title>`,
 * `<title> — <url>`, `went back to <url>`), so the URL is tracked from whichever of those arrived last;
 * a run that only ever reads text never says where it is, and the view says so rather than guessing.
 */

import { EngineEventFrame } from "../protocol";
import { Probe, probesOf } from "./probe";

export type ActKind = "navigate" | "read" | "interact" | "wait";

export interface TrailStep {
  seq: number;
  tMs: number;
  kind: ActKind;
  tool: string;
  move: string;
  detail: string;
  ok: boolean;
}

export interface BrowserKnowledge {
  page: { url: string; title: string } | null;
  trail: TrailStep[];
  links: { text: string; href: string }[];
  found: { count: number; tag: string; id: string; size: string; at: string; text: string }[];
  waits: { selector: string; text: string }[];
  evals: { expr: string; value: string }[];
  shots: { url: string; path: string; size: string }[];
  texts: string[];
  errors: string[];
  probes: Probe[];
}

const READS = new Set(["goto", "page_text", "html", "links", "find", "title_and_url", "wait_for", "screenshot", "scroll", "back", "forward"]);
const INTERACTS = new Set(["click", "type", "press", "evaluate", "new_tab", "close_tab"]);

const LOADED = /^loaded (\S+) — (.*)$/;
const WENT = /^went (?:back|forward) to (\S+)/;
const TAB_AT = /^opened a new tab at (\S+)/;
const TAB_WAS = /^closed the tab that was on (\S+)/;
const SHOT = /^saved a screenshot of (\S+) to (.*?) \((\d+x\d+)\)/;
const FOUND = /^(\d+) match\(es\); the first is <([a-z0-9-]+)(?:#([^>]*))?> at (\d+x\d+) \((\d+(?:\.\d+)?),(\d+(?:\.\d+)?)\) — (.*)$/;
const NO_MATCH = /^nothing on this page matches (.*)$/;
const WAITED = /^(.*?) appeared after waiting: (.*)$/;
const EVALED = /^(.*?) -> (.*)$/;
const CLICKED = /^clicked <([a-z0-9-]+)>(.*)$/;
const TYPED = /^typed (\d+) character\(s\) into (.*?)( and pressed Enter)?$/;
const LINK = /- (.*?) — (\S+?)(?=\s-\s|$)/g;

const unquote = (s: string): string => s.replace(/^['"]|['"]$/g, "");

function kindOf(tool: string): ActKind {
  if (tool === "goto" || tool === "back" || tool === "forward" || tool === "new_tab" || tool === "close_tab") return "navigate";
  if (tool === "wait_for") return "wait";
  if (INTERACTS.has(tool)) return "interact";
  return "read";
}

export function readBrowser(events: EngineEventFrame[]): BrowserKnowledge {
  const k: BrowserKnowledge = {
    page: null, trail: [], links: [], found: [], waits: [], evals: [], shots: [], texts: [], errors: [], probes: [],
  };
  const probes = probesOf(events);
  k.probes = probes.filter((p) => READS.has(p.tool) || INTERACTS.has(p.tool));

  for (const p of k.probes) {
    const kind = kindOf(p.tool);
    let detail = p.excerpt;

    if (p.ok) {
      const loaded = LOADED.exec(p.excerpt);
      if (loaded) {
        k.page = { url: loaded[1], title: loaded[2] };
        detail = loaded[2];
      }
      const went = WENT.exec(p.excerpt);
      if (went) { k.page = { url: went[1], title: k.page?.title ?? "" }; detail = went[1]; }
      const tab = TAB_AT.exec(p.excerpt) ?? TAB_WAS.exec(p.excerpt);
      if (tab) { k.page = { url: tab[1], title: k.page?.title ?? "" }; detail = tab[1]; }

      if (p.tool === "title_and_url") {
        const sep = p.excerpt.lastIndexOf(" — ");
        if (sep > 0) {
          k.page = { title: p.excerpt.slice(0, sep), url: p.excerpt.slice(sep + 3) };
          detail = k.page.title;
        }
      }

      if (p.tool === "links") {
        const links = p.excerpt === "this page has no links"
          ? []
          : [...p.excerpt.matchAll(LINK)].map((m) => ({ text: m[1].trim(), href: m[2] }));
        k.links = links;
        detail = links.length === 0 ? "no links on this page" : `${links.length} link${links.length === 1 ? "" : "s"}`;
      }

      if (p.tool === "find") {
        const m = FOUND.exec(p.excerpt);
        if (m) {
          k.found.push({ count: Number(m[1]), tag: m[2], id: m[3] ?? "", size: m[4], at: `${m[5]},${m[6]}`, text: m[7] });
          detail = `${m[1]} match(es)`;
        }
      }

      if (p.tool === "wait_for") {
        const m = WAITED.exec(p.excerpt);
        if (m) {
          k.waits.push({ selector: unquote(m[1]), text: m[2] });
          detail = `${unquote(m[1])} appeared`;
        }
      }

      if (p.tool === "evaluate") {
        const m = EVALED.exec(p.excerpt);
        if (m) {
          k.evals.push({ expr: m[1], value: m[2] });
          detail = m[2];
        }
      }

      if (p.tool === "screenshot") {
        const m = SHOT.exec(p.excerpt);
        if (m) {
          k.shots.push({ url: m[1], path: m[2], size: m[3] });
          detail = m[3];
        }
      }

      if (p.tool === "click") {
        const m = CLICKED.exec(p.excerpt);
        if (m) detail = `<${m[1]}>${m[2]}`;
      }
      if (p.tool === "type") {
        const m = TYPED.exec(p.excerpt);
        if (m) detail = `${m[2]}${m[3] ?? ""}`;
      }

      if ((p.tool === "page_text" || p.tool === "html") && p.excerpt) k.texts.push(p.excerpt);
    } else {
      const noMatch = NO_MATCH.exec(p.excerpt);
      k.errors.push(noMatch ? `${p.tool}: ${p.excerpt}` : `${p.tool}: ${p.excerpt}`);
    }

    k.trail.push({ seq: p.seq, tMs: p.tMs, kind, tool: p.tool, move: p.move, detail, ok: p.ok });
  }

  // A read that happens after a navigation describes the page we landed on, so the newest text is "this page".
  if (k.page && k.page.title === "" && k.texts.length > 0) k.page.title = "(title not asked for)";
  return k;
}
