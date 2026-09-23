/* The renderer's own core, checked against hand-built runs.
 *
 * Same bargain as the world parsers: no test runner, just esbuild and node (`npm run test`). Everything
 * under `core/` is a pure function of `(events, cursor)`, so every case here is a small event log and the
 * answer it must produce — including the answers at earlier cursors, because that is what the scrubber is.
 */
import { EngineEventFrame } from "../protocol";
import { foldDecisions } from "./decisions";
import { boundsOf, cellKey, readKnowledge, statsOf } from "./knowledge";
import { layoutTree, pathTo, readTree, siblingContext } from "./tree";
import { readTrust, flagCounts } from "./trust";
import { artifactOf, newRunId, summarise } from "./library";

let pass = 0;
const failures: string[] = [];
const eq = (what: string, got: unknown, want: unknown) => {
  if (JSON.stringify(got) === JSON.stringify(want)) { pass++; return; }
  failures.push(`${what}\n    got  ${JSON.stringify(got)}\n    want ${JSON.stringify(want)}`);
};

let seq = 0;
const ev = (kind: string, data: Record<string, unknown> = {}): EngineEventFrame =>
  ({ seq: ++seq, t_ms: seq * 10, kind, ...data });

const move = (fp: string, label: string): Record<string, unknown> => ({ fp, label, tool: "step", why: `because ${fp}` });
const probeEv = (fp: string, move: string, ok: boolean, excerpt: string): EngineEventFrame =>
  ev("probe", { fp, move, ok, excerpt, chars: excerpt.length, ms: 3, predicted: false });
const evalEv = (fp: string, move: string, progress: number, done = false, reason = ""): EngineEventFrame =>
  ev("evaluation", { fp, move, progress, done, reason });

/* ── a run of the maze, event by event ────────────────────────────────────
 * The world, in the adapter's own string format:
 *
 *     #####
 *     #S..#     S at 1,1 · the exit at 3,3 · every other '.' is a square the run can stand on
 *     #.#.#
 *     #..E#
 *     #####
 *
 * A `step` moves one square in that drawing, so a corridor is as walkable as a room and a description
 * lists the non-wall neighbours. Every sentence below is exactly what `maze.py` writes for this map —
 * which is the point of the fixture: the parser is only ever given these sentences, never the map.
 *
 * Five decisions: read the entry, try north (refused, and the model valued it — a surprise), then walk
 * 1,2 → 1,3 → 2,3 → 3,3 and settle. */
const rawRun: EngineEventFrame[] = [
  ev("state", { depth: 0, goal: "find the exit", trail: [], progress: 0, facts: 0, failed: 0, fact_list: [], failed_fps: [] }),
  ev("candidates", { moves: [move("g1", "grid()"), move("e1", "entry()"), move("l1", "look(cell=9,9)")] }),
  probeEv("g1", "grid()", true, "a 5x5 grid holding 9 cells; a run enters at 1,1 and looks for the exit"),
  probeEv("e1", "entry()", true, "cell 1,1 — open: south, east"),
  probeEv("l1", "look(cell=9,9)", false, "not a cell of this maze: '9,9' — cells are written as <x,y>"),
  evalEv("g1", "grid()", 0.2),
  evalEv("e1", "entry()", 0.8),
  evalEv("l1", "look(cell=9,9)", 0.0),
  ev("selected", { fp: "e1", move: "entry()", progress: 0.8 }),
  ev("state", { depth: 1, trail: ["entry()"], progress: 0.35, facts: 1, failed: 1, fact_list: ["cell 1,1 — open: south, east"], failed_fps: ["l1"] }),
  ev("candidates", { moves: [move("s1", "step(cell=1,1, direction=north)"), move("s2", "step(cell=1,1, direction=south)")] }),
  probeEv("s1", "step(cell=1,1, direction=north)", false, "a wall blocks north from 1,1"),
  probeEv("s2", "step(cell=1,1, direction=south)", true, "from 1,1 south: cell 1,2 — open: north, south"),
  evalEv("s1", "step(cell=1,1, direction=north)", 0.6),
  evalEv("s2", "step(cell=1,1, direction=south)", 0.55),
  ev("selected", { fp: "s2", move: "step(cell=1,1, direction=south)", progress: 0.55 }),
  ev("state", { depth: 2, trail: ["entry()", "step(cell=1,1, direction=south)"], progress: 0.55, facts: 2, failed: 2, fact_list: ["cell 1,1 — open: south, east", "cell 1,2 — open: north, south"], failed_fps: ["s1", "l1"] }),
  ev("candidates", { moves: [move("s3", "step(cell=1,2, direction=south)")] }),
  probeEv("s3", "step(cell=1,2, direction=south)", true, "from 1,2 south: cell 1,3 — open: north, east"),
  evalEv("s3", "step(cell=1,2, direction=south)", 0.6),
  ev("selected", { fp: "s3", move: "step(cell=1,2, direction=south)", progress: 0.6 }),
  ev("state", { depth: 3, trail: ["entry()", "step(cell=1,1, direction=south)", "step(cell=1,2, direction=south)"], progress: 0.6, facts: 3, failed: 2, fact_list: ["cell 1,3 — open: north, east"], failed_fps: ["s1", "l1"] }),
  ev("candidates", { moves: [move("s4", "step(cell=1,3, direction=east)")] }),
  probeEv("s4", "step(cell=1,3, direction=east)", true, "from 1,3 east: cell 2,3 — open: east, west"),
  evalEv("s4", "step(cell=1,3, direction=east)", 0.7),
  ev("selected", { fp: "s4", move: "step(cell=1,3, direction=east)", progress: 0.7 }),
  ev("state", { depth: 4, trail: ["entry()", "step(cell=1,1, direction=south)", "step(cell=1,2, direction=south)", "step(cell=1,3, direction=east)"], progress: 0.7, facts: 4, failed: 2, fact_list: ["cell 2,3 — open: east, west"], failed_fps: ["s1", "l1"] }),
  ev("candidates", { moves: [move("s5", "step(cell=2,3, direction=east)")] }),
  probeEv("s5", "step(cell=2,3, direction=east)", true, "from 2,3 east: cell 3,3 — open: north, west · THIS IS THE EXIT"),
  evalEv("s5", "step(cell=2,3, direction=east)", 1.0, true, "the exit"),
  ev("selected", { fp: "s5", move: "step(cell=2,3, direction=east)", progress: 1.0 }),
  ev("state", { depth: 5, trail: ["entry()", "step(cell=1,1, direction=south)", "step(cell=1,2, direction=south)", "step(cell=1,3, direction=east)", "step(cell=2,3, direction=east)"], progress: 1.0, facts: 5, failed: 2, fact_list: ["the exit is at 3,3"], failed_fps: ["s1", "l1"] }),
  ev("done", { answer: "the exit is at 3,3", trail: ["entry()", "step(cell=1,1, direction=south)", "step(cell=1,2, direction=south)", "step(cell=1,3, direction=east)", "step(cell=2,3, direction=east)"], model_calls: 6 }),
];

/**
 * The engine stamps its own tree ids (`StateEngine.run`): a `state` event carries `node` and `parent`, a
 * `backtrack` names the node it returns to, and every other event carries `at` — the node being stood on.
 * This reproduces that stamping so the tree is tested against the contract rather than a guess at it.
 */
function stamped(events: EngineEventFrame[]): EngineEventFrame[] {
  let current: string | null = null;
  let pending: string | null = null;
  let counter = 0;
  return events.map((e) => {
    if (e.kind === "state") {
      const node = `n${counter++}`;
      current = node;
      const parent = pending;
      pending = null;
      return { ...e, node, parent };
    }
    if (e.kind === "selected") { pending = current; return { ...e, at: current }; }
    return { ...e, at: current };
  });
}

const run: EngineEventFrame[] = stamped(rawRun);

/* ── decisions ─────────────────────────────────────────────────────────── */
const decisions = foldDecisions(run);
eq("one decision per search iteration", decisions.length, 5);
eq("the iteration kinds", decisions.map((d) => d.kind), ["move", "move", "move", "move", "done"]);
eq("each decision keeps its own event span", decisions.map((d) => [d.from, d.to]),
   [[1, 9], [10, 16], [17, 21], [22, 26], [27, 32]]);
eq("decisions cover the log without gaps",
   decisions.every((d, i) => i === 0 || d.from > decisions[i - 1].to), true);
eq("the first decision took the entry probe", decisions[0].move, "entry()");
eq("confidence is the evaluator's own score", decisions.map((d) => d.confidence), [0.8, 0.55, 0.6, 0.7, 1]);
eq("a decision knows what it believed before", decisions[1].priorProgress, 0.35);
eq("the evidence is the world's answer, not a summary", decisions[4].evidence,
   "from 2,3 east: cell 3,3 — open: north, west · THIS IS THE EXIT");
eq("options carry what the world did with each", decisions[1].options.map((o) => [o.label, o.ok, o.progress]),
   [["step(cell=1,1, direction=north)", false, 0.6], ["step(cell=1,1, direction=south)", true, 0.55]]);
eq("the chosen option is marked", decisions[1].options.map((o) => Boolean(o.chosen)), [false, true]);

// Flags: the entry probe beat standing still (confirmed); the valued north step was refused (surprise);
// the zero-valued look(9,9) that failed is not a surprise, because nothing was expected of it.
eq("flags of the first decision", decisions[0].flags, ["confirmed"]);
eq("flags of the decision that hit the wall", decisions[1].flags, ["confirmed", "surprise"]);
eq("a step that worked and helped is merely confirmed", decisions[2].flags, ["confirmed"]);
eq("a settle is confirmed", decisions[4].flags, ["confirmed"]);
eq("the run's flag tally", flagCounts(decisions), { confirmed: 5, surprise: 1, guess: 0, backtrack: 0, forced: 0 });

// The fold is prefix-total: the same decisions, minus the ones that had not happened yet.
const early = foldDecisions(run.slice(0, decisions[1].to + 1));
eq("a prefix folds to the decisions inside it", early.map((d) => d.kind), ["move", "move"]);
eq("a prefix keeps the earlier decisions identical", early[1].confidence, decisions[1].confidence);

/* ── what the run believed about the world ─────────────────────────────── */
const knowledge = readKnowledge(run);
eq("the grid's own size is read from the world", knowledge.grid, { width: 5, height: 5, floors: 9 });
eq("the entry cell is known", knowledge.start, cellKey(1, 1));
eq("the exit is known once seen", knowledge.exit, cellKey(3, 3));
eq("where the run ended up", knowledge.current, cellKey(3, 3));
eq("cells entered, in order", knowledge.entered,
   [cellKey(1, 2), cellKey(1, 3), cellKey(2, 3), cellKey(3, 3)]);
eq("corridors walked", knowledge.steps,
   [[cellKey(1, 1), cellKey(1, 2)], [cellKey(1, 2), cellKey(1, 3)], [cellKey(1, 3), cellKey(2, 3)], [cellKey(2, 3), cellKey(3, 3)]]);
eq("the live path follows the engine's own trail", knowledge.livePath,
   [cellKey(1, 1), cellKey(1, 2), cellKey(1, 3), cellKey(2, 3), cellKey(3, 3)]);
eq("nothing was abandoned on a run that never retreated", knowledge.abandoned, []);
eq("a refused step leaves a wall on the map", knowledge.walls.has(cellKey(1, 0)), true);
eq("a described cell opens the corridors out of it",
   knowledge.floor.has(cellKey(1, 2)) && knowledge.floor.has(cellKey(2, 1)), true);
eq("a cell it is standing on is floor, not wall", knowledge.walls.has(cellKey(1, 2)), false);
eq("an opening it never walked is still known floor", knowledge.floor.has(cellKey(2, 1)), true);
eq("the run walked each cell once", statsOf(knowledge).revisits, 0);
eq("coverage is against the world's own floor count",
   Math.round((statsOf(knowledge).coverage ?? 0) * 100), 56);

// The same events, read at an earlier cursor — this is what the scrubber shows when it is dragged back.
const afterSouth = run.findIndex((e) => e.kind === "state" && e["depth"] === 2) + 1;
const midway = readKnowledge(run, afterSouth);
eq("at an earlier cursor the exit is not yet known", midway.exit, null);
eq("at an earlier cursor the run stands at 1,2", midway.current, cellKey(1, 2));
eq("at an earlier cursor the map is smaller", midway.cells.size < knowledge.cells.size, true);

const empty = readKnowledge([]);
eq("an empty log has no bounds to draw", boundsOf(empty), null);
const bounds = boundsOf(knowledge)!;
eq("bounds use the world's dimensions once it was read", [bounds.minX, bounds.maxX, bounds.minY, bounds.maxY], [-1, 5, -1, 5]);

// Precedence: whichever way the sentences arrive, an inference about a cell's neighbours must not erase
// a corridor another square said was open. A hand-written world can disagree with itself; the map may not.
const conflicting = readKnowledge([
  probeEv("a", "entry()", true, "cell 1,1 — open: south, east"),
  probeEv("b", "step(cell=1,1, direction=south)", true, "from 1,1 south: cell 1,2 — open: north"),
  probeEv("c", "step(cell=1,2, direction=north)", true, "from 1,2 north: cell 1,1 — open: south"),
  probeEv("d", "look(cell=3,1)", true, "cell 3,1 — open: north"),
]);
eq("an inference never walls off a corridor another square opened",
   [conflicting.floor.has(cellKey(2, 1)), conflicting.walls.has(cellKey(2, 1))], [true, false]);
eq("but a refusal still marks a wall", conflicting.walls.has(cellKey(3, 2)), true);

/* ── the tree ──────────────────────────────────────────────────────────── */
const tree = readTree(run, run.length, decisions);
eq("every state is a node", tree.states, 6);
eq("the root is the node the run began on", tree.roots, ["n0"]);
eq("the deepest node is where the run stopped", tree.nodes.get(tree.current!)!.depth, 5);
eq("every node can explain how it came to exist", [...tree.nodes.values()].filter((n) => n.decision !== null).length, 6);
eq("nodes carry the ids the engine gave them", [...tree.nodes.keys()].sort(), ["n0", "n1", "n2", "n3", "n4", "n5"]);
eq("the engine said who the parent was", tree.nodes.get("n3")!.parent, "n2");
eq("the run is on the last node it stood on", tree.current, "n5");
eq("the path to the deepest node is its trail, entry first",
   pathTo(tree, tree.current).map((n) => n.depth), [0, 1, 2, 3, 4, 5]);
eq("a trail entry is the move, not the observation", tree.nodes.get(tree.current!)!.last,
   "step(cell=2,3, direction=east)");
eq("the live line is still live", [...tree.nodes.values()].every((n) => !n.dead), true);

const laid = layoutTree(tree, { collapsed: new Set(), foldDead: true });
eq("the layout places every node when nothing is folded", laid.visible.length, 6);
eq("the layout draws one edge per non-root node", laid.edges.length, 5);
eq("siblings sit in different columns", laid.visible.filter((n) => n.depth === 2).length, 1);

const why = siblingContext(tree, decisions, "n1");
// A node answers "why this branch?": the options of the decision that created it, and which one it took.
eq("a node can say who its siblings were", why.siblings.map((s) => s.label),
   ["grid()", "entry()", "look(cell=9,9)"]);
eq("and which of them it took", why.siblings.map((s) => s.chosen), [false, true, false]);
eq("a sibling the world refused is marked refused", siblingContext(tree, decisions, "n2").siblings.map((s) => s.ok), [false, true]);
eq("the decision a node is, is the one that made it", why.chosen?.index, 0);

/* ── a run that retreated ────────────────────────────────────────────────
 * Two steps down a corridor that only went one way, a wall, a retreat all the way back, then east to the
 * exit. Enough of a branch for there to be something to fold. */
const retreat: EngineEventFrame[] = [
  ev("state", { depth: 0, trail: [], progress: 0, facts: 0, fact_list: [] }),
  ev("candidates", { moves: [move("a", "step(cell=1,1, direction=south)")] }),
  probeEv("a", "step(cell=1,1, direction=south)", true, "from 1,1 south: cell 1,2 — open: north, south"),
  evalEv("a", "step(cell=1,1, direction=south)", 0.4),
  ev("selected", { fp: "a", move: "step(cell=1,1, direction=south)", progress: 0.4 }),
  ev("state", { depth: 1, trail: ["step(cell=1,1, direction=south)"], progress: 0.4, facts: 1, fact_list: ["cell 1,2 — open: north, south"] }),
  ev("candidates", { moves: [move("b", "step(cell=1,2, direction=south)")] }),
  probeEv("b", "step(cell=1,2, direction=south)", true, "from 1,2 south: cell 1,3 — open: north, south"),
  evalEv("b", "step(cell=1,2, direction=south)", 0.5),
  ev("selected", { fp: "b", move: "step(cell=1,2, direction=south)", progress: 0.5 }),
  ev("state", { depth: 2, trail: ["step(cell=1,1, direction=south)", "step(cell=1,2, direction=south)"], progress: 0.5, facts: 2, fact_list: ["cell 1,3 — open: north"] }),
  ev("candidates", { moves: [move("d", "step(cell=1,3, direction=south)")] }),
  probeEv("d", "step(cell=1,3, direction=south)", false, "a wall blocks south from 1,3"),
  evalEv("d", "step(cell=1,3, direction=south)", 0.0),
  ev("backtrack", { to_depth: 0 }),
  ev("candidates", { moves: [move("c", "step(cell=1,1, direction=east)")] }),
  probeEv("c", "step(cell=1,1, direction=east)", true, "from 1,1 east: cell 2,1 — open: west · THIS IS THE EXIT"),
  evalEv("c", "step(cell=1,1, direction=east)", 0.9, true),
  ev("selected", { fp: "c", move: "step(cell=1,1, direction=east)", progress: 0.9 }),
  ev("state", { depth: 1, trail: ["step(cell=1,1, direction=east)"], progress: 0.9, facts: 3, fact_list: ["the exit is at 2,1"] }),
  ev("done", { answer: "2,1", trail: ["step(cell=1,1, direction=east)"], model_calls: 3 }),
];
const retreatDecisions = foldDecisions(retreat);
const retreatTree = readTree(retreat, retreat.length, retreatDecisions);
const retreatKnowledge = readKnowledge(retreat);

eq("a retreat is its own decision", retreatDecisions.map((d) => d.kind), ["move", "move", "backtrack", "done"]);
eq("the retreat is flagged as one", retreatDecisions[2].flags, ["backtrack"]);
eq("the abandoned branch goes cold", retreatTree.nodes.get("step(cell=1,1, direction=south)")!.dead, true);
eq("everything below it goes cold with it",
   retreatTree.nodes.get("step(cell=1,1, direction=south) → step(cell=1,2, direction=south)")!.dead, true);
eq("the branch taken instead is live", retreatTree.nodes.get("step(cell=1,1, direction=east)")!.current, true);
eq("a retreat is counted", retreatTree.backtracks, 1);
eq("the map keeps the cells it walked into and left", retreatKnowledge.abandoned, [cellKey(1, 2), cellKey(1, 3)]);
eq("the live path is the branch it kept", retreatKnowledge.livePath, [cellKey(1, 1), cellKey(2, 1)]);

const foldedView = layoutTree(retreatTree, { collapsed: new Set(), foldDead: true });
eq("a cold branch folds into the node it branched from",
   foldedView.visible.some((n) => n.id === "step(cell=1,1, direction=south) → step(cell=1,2, direction=south)"), false);
eq("the node it folded into is still drawn, holding the count", foldedView.visible.some((n) => n.id === "step(cell=1,1, direction=south)"), true);
eq("the fold says how much is inside it", foldedView.folds[0].hidden, 1);
eq("the fold knows it was all abandoned", foldedView.folds[0].dead, 1);
const unfolded = layoutTree(retreatTree, { collapsed: new Set(), foldDead: false });
eq("and unfolding brings it back", unfolded.visible.length, 4);
eq("folding is what made the difference", foldedView.visible.length, 3);
const handFolded = layoutTree(retreatTree, {
  collapsed: new Set(["step(cell=1,1, direction=south)"]), foldDead: false,
});
eq("folding by hand works with the automatic rule off", handFolded.visible.length, 3);
eq("a hand fold of a leaf does nothing, because there is nothing under it",
   layoutTree(retreatTree, { collapsed: new Set(["step(cell=1,1, direction=east)"]), foldDead: false }).visible.length, 4);

/* ── the trust curve ───────────────────────────────────────────────────── */
const trust = readTrust(retreatDecisions);
eq("the curve is over the moves, not the events", trust.points.map((p) => p.confidence), [0.4, 0.5, 0.9]);
eq("the curve averages", Math.round(trust.mean * 100), 60);
eq("a short run says so", trust.trend, "too short to say");
eq("the curve averages the committed moves", Math.round(readTrust(decisions).mean * 100), 73);
eq("a run that ends better than it started reads as steadying", readTrust(decisions).trend, "steadying");
const longTrust = readTrust([...decisions, ...decisions]);
eq("a steady run reads as steady", longTrust.trend === "level" || longTrust.trend === "steadying", true);

/* ── the library ───────────────────────────────────────────────────────── */
const artifact = artifactOf({
  id: newRunId(new Date("2026-09-23T18:15:00")),
  world: "maze",
  goal: "find the exit",
  config: { model: "qwen2.5:7b", base_url: "http://localhost:11434/v1", seed: "7", width: 11 },
  events: run,
  outcome: { settled: true, answer: "the exit is at 2,2", reason: null, summary: "settled", record: null },
  startedAt: "2026-09-23T18:15:00.000Z",
  endedAt: "2026-09-23T18:15:04.000Z",
  bookmarks: [1],
});
eq("a run id sorts by time", artifact.id.startsWith("20260923-181500-"), true);
eq("the name is derived, not asked for", artifact.name, "maze · seed 7 · qwen2.5:7b");
eq("the seed is promoted out of the config", artifact.seed, "7");

const meta = summarise(artifact);
eq("the summary counts the decisions", meta.decisions, 5);
eq("the summary counts the surprises", meta.surprises, 1);
eq("the summary counts the backtracks", meta.backtracks, 0);
eq("the summary keeps the outcome", [meta.settled, meta.reason], [true, null]);
eq("the summary measures the run", meta.durationMs, 4000);

console.log(`\n${pass} passed, ${failures.length} failed`);
if (failures.length) throw new Error("core checks failed:\n" + failures.map((f) => "  ✗ " + f).join("\n"));
