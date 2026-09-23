/* Exercises the world parsers against the exact observation strings the adapters write.
 *
 * There is no test runner in this package, and adding one for four parsers would be a dependency for a
 * hundred lines of assertions — so this file is plain code: `npm run test:parsers` bundles it with the
 * esbuild that already ships inside Vite and runs it on node. A failure throws, which is a non-zero exit.
 */
import { EngineEventFrame } from "./protocol";
import { readFiles, treeOf } from "./lib/files";
import { readLedger } from "./lib/ledger";
import { readBrowser } from "./lib/browser";
import { applyProbe, emptyKnowledge } from "./lib/maze";
import { layoutTree, readTree } from "./lib/tree";

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
const ledger = readLedger([
  probe("brief()", true, "Context Ledger at /p/.context_ledger — protocol core 2.0.4 The office is calm. (memory: 34 files; 2 closed office record(s) in history/)"),
  probe("open_tasks()", true, "Current task: Ship the UI — Working  session: S15 Backlog — High (2): - B-3: fix the thing - B-4: other thing Backlog — Low (1): - B-9: someday Parking lot (not a queue): Findings 1"),
  probe("decisions(limit=8)", true, '2 decision(s) in force — respected, not relitigated: - ADR-7: Use a beam (2026-09-18) — accepted - ADR-2: Old call (2026-09-01) — proposed Full text of one: read_decision {"number": "<n>"}'),
  probe("recent_sessions(limit=5)", true, "The last 1 session(s) here: - 2026-09-19 — Session 15     Agent: Codebuff     Model: gpt-5     Outcome: done"),
  probe("friction(log=inefficiencies, limit=6)", true, "1 open inefficiencies entry (showing 1): - 2026-09-20 — bao     Problem: slow     Workaround / fix: cache it     Prevent next time: measure"),
  probe("search_memory(text=flaky, scope=memory)", true, "1 line(s) in scope 'memory' contain 'flaky': memory/office/tasks/backlog.md:41: the flaky test (closed offices under history/ are outside this scope — use scope='history')"),
  probe("list_memory(scope=memory)", true, "2 file(s) in scope 'memory': - memory/user/identity.md (120 B) - memory/user/preferences.md (812 B)"),
  probe("read_memory(path=memory/user/identity.md)", true, "memory/user/identity.md: hello"),
  probe("append_note(text=x)", false, "append_note would change the ledger, and this environment only reads (a host writes, from the run's own events)"),
]);
eq("ledger vault", ledger.vault, "/p/.context_ledger");
eq("ledger core", ledger.core, "2.0.4");
eq("ledger scale", ledger.scale, "2 closed in history · 34 memory files");
eq("ledger current", ledger.current, { task: "Ship the UI", status: "Working", session: "S15" });
eq("ledger backlog sections", ledger.backlog.map((b) => b.section), ["High", "Low"]);
eq("ledger backlog rows", ledger.backlog[0].rows, [{ ident: "B-3", summary: "fix the thing" }, { ident: "B-4", summary: "other thing" }]);
eq("ledger backlog total", ledger.backlog[0].total, 2);
eq("ledger parking", ledger.parking, "Findings 1");
eq("ledger decisions", ledger.decisions, [
  { number: "7", title: "Use a beam", date: "2026-09-18", status: "accepted" },
  { number: "2", title: "Old call", date: "2026-09-01", status: "proposed" },
]);
eq("ledger session heading", ledger.sessions[0].heading, "2026-09-19 — Session 15");
eq("ledger session fields", ledger.sessions[0].fields, [["Agent", "Codebuff"], ["Model", "gpt-5"], ["Outcome", "done"]]);
eq("ledger friction log", ledger.friction[0].log, "inefficiencies");
eq("ledger friction fields", ledger.friction[0].entries[0].fields.length, 3);
eq("ledger search hits", ledger.searches[0].hits, [{ rel: "memory/office/tasks/backlog.md", line: 41, text: "the flaky test" }]);
eq("ledger memory files", ledger.memory[0].files, [{ rel: "memory/user/identity.md", bytes: 120 }, { rel: "memory/user/preferences.md", bytes: 812 }]);
eq("ledger read", ledger.reads[0].rel, "memory/user/identity.md");
eq("ledger refused write", ledger.refusedWrites.length, 1);
eq("ledger seen", [...ledger.seen].sort(), ["brief", "decisions", "friction", "list_memory", "open_tasks", "read_memory", "recent_sessions", "search_memory"]);

const unboot = readLedger([probe("brief()", false, "no bootstrapped Context Ledger at /p/.context_ledger — this needs `.context_ledger/memory/office/` to exist")]);
eq("ledger unbootstrapped", Boolean(unboot.unbootstrapped), true);

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

/* ── maze ──────────────────────────────────────────────────────────────── */
// A world that keeps its own story straight: 1,1 opens south; the run walks to 1,3, finds the south wall
// there, tries a cell it has not entered, tries a cell that is not in the maze, then steps east to the exit.
const maze = emptyKnowledge();
applyProbe(maze, "entry()", true, "cell 1,1 — open: south, east");
applyProbe(maze, "grid()", true, "a 5x5 grid holding 4 cells; a run enters at 1,1 and looks for the exit");
applyProbe(maze, "step(cell=1,1, direction=south)", true, "from 1,1 south: cell 1,2 — open: north, south");
applyProbe(maze, "step(cell=1,2, direction=south)", true, "from 1,2 south: cell 1,3 — open: north, south");
applyProbe(maze, "step(cell=1,3, direction=south)", false, "a wall blocks south from 1,3");
applyProbe(maze, "look(cell=2,1)", false, "2,1 has not been entered — a run learns a cell by stepping into it, and this one has only been here: 1,1, 1,2, 1,3");
applyProbe(maze, "look(cell=0,0)", false, "not a cell of this maze: '0,0' — cells are written as <x,y>");
applyProbe(maze, "step(cell=1,3, direction=east)", true, "from 1,3 east: cell 2,3 — open: west · THIS IS THE EXIT");
eq("maze grid", maze.grid, { width: 5, height: 5, floors: 4 });
eq("maze start", maze.start, "1,1");
eq("maze exit", maze.exit, "2,3");
eq("maze current", maze.current, "2,3");
eq("maze wall below the dead end", maze.cells.get("1,4")!.wall, true);
eq("maze a cell named but not entered is floor, not wall", maze.cells.get("2,1")!.wall, false);
eq("maze a cell off the map is a wall", maze.cells.get("0,0")!.wall, true);
eq("maze 1,2 keeps the openings the world reported", [...maze.cells.get("1,2")!.open].sort(), ["north", "south"]);
eq("maze exit cell flagged", maze.cells.get("2,3")!.exit, true);
eq("maze stepped-into cell opens back", [...maze.cells.get("2,3")!.open].sort(), ["west"]);
eq("maze corridors walked", maze.steps, [["1,1", "1,2"], ["1,2", "1,3"], ["1,3", "2,3"]]);
eq("maze cells entered in order", maze.entered, ["1,2", "1,3", "2,3"]);
eq("maze a corridor is not counted twice", (() => {
  applyProbe(maze, "step(cell=1,1, direction=south)", true, "from 1,1 south: cell 1,2 — open: north, south");
  return maze.steps.length;
})(), 3);

/* ── the search tree ───────────────────────────────────────────────────── */
const state = (trail: string[], progress: number): EngineEventFrame =>
  ({ seq: ++seq, t_ms: seq * 10, kind: "state", trail, progress, facts: trail.length, depth: trail.length });
let treeEvents: EngineEventFrame[] = [
  state([], 0),
  state(["step(a)"], 0.2),
  state(["step(a)", "step(b)"], 0.4),
  { seq: ++seq, t_ms: 0, kind: "backtrack", to_depth: 1 },
  state(["step(a)", "step(c)"], 0.9),
];
const searchTree = readTree(treeEvents);
eq("tree states counted", searchTree.states, 4);
eq("tree root is the empty trail", [...searchTree.nodes.keys()][0], "(start)");
eq("tree children of the root", searchTree.nodes.get("(start)")!.children, ["step(a)"]);
eq("tree children of step(a)", searchTree.nodes.get("step(a)")!.children, ["step(a) → step(b)", "step(a) → step(c)"]);
eq("tree abandoned branch is dead", searchTree.nodes.get("step(a) → step(b)")!.dead, true);
eq("tree live branch is not", searchTree.nodes.get("step(a) → step(c)")!.dead, false);
eq("tree current is the newest state", searchTree.current, "step(a) → step(c)");
eq("tree records the backtrack", searchTree.backtracks, 1);
eq("tree max depth", searchTree.maxDepth, 2);
const laid = layoutTree(searchTree);
eq("layout places every node", laid.placed.length, 4);
eq("layout draws one edge per non-root node", laid.edges.length, 3);
eq("layout ranks by depth", laid.placed.map((p) => p.node.depth).sort(), [0, 1, 2, 2]);
eq("layout spreads siblings", laid.placed.find((p) => p.node.id === "step(a) → step(b)")!.x
   !== laid.placed.find((p) => p.node.id === "step(a) → step(c)")!.x, true);

console.log(`\n${pass} passed, ${failures.length} failed`);
if (failures.length) throw new Error("parser checks failed:\n" + failures.map((f) => "  ✗ " + f).join("\n"));
