/* The non-maze world parsers, against the exact observation strings the adapters write.
 *
 * There is no test runner in this package, and adding one for three parsers would be a dependency for a
 * hundred lines of assertions — so this file is plain code: `npm run test` bundles it with the esbuild that
 * already ships inside Vite and runs it on node. A failure throws, which is a non-zero exit.
 */
import { EngineEventFrame } from "../protocol";
import { readFiles, treeOf } from "./worlds/files";
import { readBrowser } from "./worlds/browser";

let pass = 0;
const failures: string[] = [];
const eq = (what: string, got: unknown, want: unknown) => {
  if (JSON.stringify(got) === JSON.stringify(want)) { pass++; return; }
  failures.push(`${what}\n    got  ${JSON.stringify(got)}\n    want ${JSON.stringify(want)}`);
};

let seq = 0;
const probe = (move: string, ok: boolean, excerpt: string): EngineEventFrame =>
  ({ seq: ++seq, t_ms: seq * 10, kind: "probe", move, ok, excerpt, chars: excerpt.length, ms: 1, predicted: false, fp: "f" });

/* ── files ─────────────────────────────────────────────────────────────── */
const files = readFiles([
  probe("list_dir(path=/home/u/code)", true, "Contents of /home/u/code — 3 entries: 📁 sub · 📄 a.txt (11 B) · 📄 b.md (2048 B)"),
  probe("list_dir(path=/home/u/code)", true, "Contents of /home/u/code — 9 entries: 📄 a.txt (11 B) … (+7 more)"),
  probe("stat_path(path=/home/u/code/a.txt)", true, "/home/u/code/a.txt — file, 11 bytes, modified 2026-09-23 14:05"),
  probe("find_files(path=/home/u/code, contains=.py)", true, "2 file(s) under /home/u/code with '.py' in the name: /home/u/code/deep.py · /home/u/code/sub/deep.py"),
  probe("find_files(path=/home/u/code, contains=.zz)", true, "no file under /home/u/code has '.zz' in its name (12 paths searched)"),
  probe("read_file(path=/home/u/code/a.txt)", true, "hello there general kenobi"),
  probe("read_file(path=/etc/passwd)", false, "refused: '/etc/passwd' is not a path inside /home/u/code"),
  probe("read_file(path=/home/u/code/dir)", false, "not a file: /home/u/code/dir"),
  probe("list_dir(path=/home/u/code/ghost)", false, "not a directory: /home/u/code/ghost"),
]);
eq("files.root", files.root, "/home/u/code");
eq("files latest listing wins", files.listings.length, 1);
eq("files.listing total", files.listings[0].total, 9);
eq("files.listing entries", files.listings[0].entries, [{ dir: false, name: "a.txt", bytes: 11 }]);
eq("files listing more", files.listings[0].more, 7);
eq("files stat", files.stats[0], { path: "/home/u/code/a.txt", kind: "file", bytes: 11, modified: "2026-09-23 14:05", seq: 3 });
eq("files find hits", files.finds[1].total, 0);
eq("files find searched", files.finds[1].searched, 12);
eq("files refusal", files.refusals[0], { asked: "/etc/passwd", root: "/home/u/code", seq: 7 });
eq("files failure tool", files.failures.map((f) => f.tool), ["read_file", "list_dir"]);
eq("files reads", files.reads.map((r) => r.path), ["/home/u/code/a.txt"]);

const tree = treeOf(files)!;
eq("tree root name", tree.name, "code");
eq("tree has sub dir", tree.children.some((c) => c.name === "sub" && c.dir), true);
eq("tree deep.py nested under sub", tree.children.find((c) => c.name === "sub")!.children.some((c) => c.name === "deep.py"), true);
eq("tree a.txt read", tree.children.find((c) => c.name === "a.txt")!.read, true);

/* ── ledger ────────────────────────────────────────────────────────────── */
/* The Context Ledger world's parser was removed with the world itself — it was one project's
   engineering protocol, not something a stranger opening the app could recognise. The adapter and
   `ledger_cli` still ship; only the app no longer offers it. */

/* ── browser ───────────────────────────────────────────────────────────── */
const browser = readBrowser([
  probe("goto(url=https://example.com/)", true, "loaded https://example.com/ — Example Domain"),
  probe("links(limit=60)", true, "this page has no links"),
  probe("links(limit=60)", true, "- A link — https://a.test/ - B — https://b.test/x"),
  probe("find(selector=button.buy)", true, "2 match(es); the first is <button#buy-btn> at 120x40 (166.5,88) — Buy now"),
  probe("find(selector=#nope)", false, "CdpError: nothing on this page matches '#nope'"),
  probe("wait_for(selector=#results, timeout_ms=200)", true, "'#results' appeared after waiting: 12 results"),
  probe("evaluate(expression=document.title)", true, "document.title -> Example"),
  probe("screenshot(full_page=False)", true, "saved a screenshot of https://example.com/ to /tmp/tm/a-b.png (1280x720) — for a person to look at, since this is a picture and not text"),
  probe("click(selector=#buy)", true, "clicked <button> Show the price"),
  probe("type(selector=#q, text=hello)", true, "typed 5 character(s) into #q and pressed Enter"),
  probe("title_and_url()", true, "The price page — https://shop.test/price"),
]);
eq("browser page", browser.page, { title: "The price page", url: "https://shop.test/price" });
eq("browser links", browser.links, [{ text: "A link", href: "https://a.test/" }, { text: "B", href: "https://b.test/x" }]);
eq("browser found", browser.found[0].count, 2);
eq("browser found id", browser.found[0].id, "buy-btn");
eq("browser found at", browser.found[0].at, "166.5,88");
eq("browser waits", browser.waits[0], { selector: "#results", text: "12 results" });
eq("browser evals", browser.evals[0], { expr: "document.title", value: "Example" });
eq("browser shots", browser.shots[0].size, "1280x720");
eq("browser errors", browser.errors.length, 1);
// evaluate is a write action in this adapter, so it is grouped with the clicks, not with the reads.
eq("browser trail kinds", browser.trail.map((t) => t.kind),
   ["navigate", "read", "read", "read", "read", "wait", "interact", "read", "interact", "interact", "read"]);

console.log(`\n${pass} passed, ${failures.length} failed`);
if (failures.length) throw new Error("world parser checks failed:\n" + failures.map((f) => "  ✗ " + f).join("\n"));
