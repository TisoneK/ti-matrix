/*
 * The narration mapping, pinned kind by kind: what the run's position becomes on screen.
 */
import { EngineEventFrame } from "../protocol";
import { narrate } from "./narrate";

let pass = 0;
const failures: string[] = [];
const eq = (name: string, got: unknown, want: unknown): void => {
  if (JSON.stringify(got) === JSON.stringify(want)) { pass += 1; return; }
  failures.push(name);
  console.error(`FAIL: ${name}\n  got:  ${JSON.stringify(got)}\n  want: ${JSON.stringify(want)}`);
};
const ok = (name: string, cond: boolean): void => {
  if (cond) { pass += 1; return; }
  failures.push(name);
  console.error(`FAIL: ${name}`);
};

const ev = (kind: string, data: Record<string, unknown> = {}): EngineEventFrame =>
  ({ seq: 1, t_ms: 0, kind, ...data });

/* ── a model call in flight — the case that used to read as silence ─────── */

const think = narrate([ev("thinking", { phase: "propose" })], 4200);
eq("thinking/propose names the phase and the seconds of silence", think?.text, "choosing what to try next");
eq("and counts itself as thinking", think?.thinking, true);
eq("and carries the elapsed quiet", think?.quietFor, 4);

const thinkEval = narrate([ev("thinking", { phase: "evaluate" })], 1200);
eq("thinking/evaluate names the weighing", thinkEval?.text, "weighing what it found");
const thinkRetry = narrate([ev("thinking", { phase: "evaluate", attempt: 2 })], 0);
eq("a retry says it is one", thinkRetry?.text, "weighing what it found — retrying the scoring call with a shorter view");
eq("a retry counts as thinking too", thinkRetry?.thinking, true);

/* ── the data events, one sentence each ──────────────────────────────────── */

const cand = narrate([ev("candidates", { moves: [{ label: "find_files(path=Tisone)" }, { label: "list_dir(path=.)" }, { label: "stat_path(path=Tisone)" }, { label: "read_file(path=x)" }] })], 0);
eq("candidates name the tools, capped at three with an ellipsis",
   cand?.text, "4 candidates proposed — find_files, list_dir, stat_path…");

const candAvail = narrate([ev("candidates", { moves: [{ label: "step()" }], available: 35 })], 0);
eq("candidates name the space they were chosen from", candAvail?.text, "choosing among 35 possible moves (1 proposed — step)");

const candSolo = narrate([ev("candidates", { moves: [{ label: "list_dir(path=.)" }] })], 0);
eq("one candidate reads as one", candSolo?.text, "1 candidate proposed — list_dir");

const probeOk = narrate([ev("probe", { ok: true, move: "list_dir(path=/x)", ms: 240 })], 0);
eq("a probe says what was read and how long it took", probeOk?.text, "read — list_dir took 240ms");
const probeBad = narrate([ev("probe", { ok: false, move: "read_file(path=/x)", ms: 1200 })], 0);
eq("a refused probe says so", probeBad?.text, "refused — read_file took 1.2s");

const evalEv = narrate([ev("evaluation", { progress: 0.5 })], 0);
eq("an evaluation reports the best score", evalEv?.text, "scored: best candidate at 50%");
const evalDone = narrate([ev("evaluation", { progress: 1, done: true })], 0);
eq("a done claim is named as one", evalDone?.text, "a candidate claims the goal is settled — 100%");

const sel = narrate([ev("selected", { move: "read_file(path=/x)", progress: 0.9 })], 0);
eq("a selection carries the tool and the belief", sel?.text, "took read_file — belief 90%");

const st = narrate([ev("state", { depth: 2 })], 0);
eq("a state names its depth", st?.text, "state 2 reached");
eq("the root is not a depth", narrate([ev("state", { depth: 0 })], 0)?.text, "at the start");

eq("a backtrack is the honest sentence", narrate([ev("backtrack")], 0)?.text, "nothing beat where it stood — backing up");
eq("a confirmation is narrated", narrate([ev("confirmation", { move: "write(x)", granted: true })], 0)?.text,
   "asked about write — granted");
eq("a needs_confirmation is narrated", narrate([ev("needs_confirmation", { move: "write(x)" })], 0)?.text,
   "write changes something — it needs a decision");

eq("a settled run says so", narrate([ev("done")], 0)?.text, "settled");
eq("a stopped run says so", narrate([ev("stopped")], 0)?.text, "stopped");

/* ── the honest fallthrough ─────────────────────────────────────────────── */

const empty = narrate([], 0);
eq("no events, no narration", empty, null);

const unknown = narrate([ev("hologram")], 0);
eq("an unknown kind still gets a heartbeat", unknown?.text, "working");
eq("and says what it came from", unknown?.from, "hologram");

/* ── report ─────────────────────────────────────────────────────────────── */

console.log(`\n${pass} passed, ${failures.length} failed`);
if (failures.length > 0) throw new Error(`${failures.length} narration assertion(s) failed`);
