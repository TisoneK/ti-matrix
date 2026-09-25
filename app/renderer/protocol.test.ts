/* The socket that keeps itself open — and the budget that follows whoever is deciding.
 *
 * Same bargain as the rest of the renderer's tests: esbuild and node, no runner. `WebSocket` and
 * `setTimeout` are both stubbed here, so a backoff of six seconds is asserted in microseconds and the
 * reconnect ladder is exercised without a real socket or a real wait.
 *
 * What is being held down: a dropped socket used to end the window. `onclose` set `crashed`, nothing
 * ever tried again, and the only way back was reloading the page — which is why the app could sit on
 * "the sidecar is not running" while a perfectly healthy engine was listening on the port it had just
 * been told about.
 */
import { Sidecar, Status } from "./protocol";
import { BUILTIN, budgetFor, isBuiltin, modelSummary, BUDGET, BUILTIN_BUDGET } from "./core/models";

let pass = 0;
const failures: string[] = [];
const eq = (what: string, got: unknown, want: unknown) => {
  if (JSON.stringify(got) === JSON.stringify(want)) { pass++; return; }
  failures.push(`${what}\n    got  ${JSON.stringify(got)}\n    want ${JSON.stringify(want)}`);
};
const ok = (what: string, got: boolean) => eq(what, got, true);

/* ── a fake socket and a fake clock ─────────────────────────────────────── */

class FakeSocket {
  static live: FakeSocket[] = [];
  onopen: (() => void) | null = null;
  onclose: (() => void) | null = null;
  onerror: (() => void) | null = null;
  onmessage: ((m: { data: string }) => void) | null = null;
  closed = false;
  constructor(public url: string) { FakeSocket.live.push(this); }
  close(): void { this.closed = true; this.onclose?.(); }
  /** The socket dying on its own — a sidecar that exited, a laptop that slept. */
  drop(): void { this.onerror?.(); this.onclose?.(); }
}

const timers: { at: number; fn: () => void }[] = [];
let now = 0;
const runTimers = (): void => {
  // Fire everything due, in order, including timers scheduled by the ones we fire.
  for (let guard = 0; guard < 100 && timers.length > 0; guard++) {
    timers.sort((a, b) => a.at - b.at);
    const next = timers.shift();
    if (!next) break;
    now = next.at;
    next.fn();
  }
};

const g = globalThis as unknown as Record<string, unknown>;
g["WebSocket"] = FakeSocket as unknown;
g["setTimeout"] = ((fn: () => void, ms: number) => {
  const handle = { at: now + ms, fn };
  timers.push(handle);
  return handle as unknown;
}) as unknown;
g["clearTimeout"] = ((handle: unknown) => {
  const i = timers.indexOf(handle as { at: number; fn: () => void });
  if (i >= 0) timers.splice(i, 1);
}) as unknown;

const fresh = (): { sidecar: Sidecar; seen: Status[] } => {
  FakeSocket.live = [];
  timers.length = 0;
  now = 0;
  const sidecar = new Sidecar("ws://127.0.0.1:1/ws?token=x");
  const seen: Status[] = [];
  sidecar.onStatus((s) => seen.push(s));
  return { sidecar, seen };
};

/* ── the reconnect ladder ───────────────────────────────────────────────── */

{
  const { sidecar, seen } = fresh();
  sidecar.connect();
  FakeSocket.live[0].onopen?.();
  eq("an opened socket is ready", seen, ["ready"]);

  FakeSocket.live[0].drop();
  eq("a socket that drops says so, and does not claim a crash yet", seen, ["ready", "reconnecting"]);
  eq("the retry is scheduled, not immediate", FakeSocket.live.length, 1);

  runTimers();
  ok("a new socket was opened by the retry", FakeSocket.live.length === 2);
  FakeSocket.live[1].onopen?.();
  eq("the reconnected socket is ready again", seen, ["ready", "reconnecting", "ready"]);
}

{
  // A sidecar that is genuinely gone: every attempt fails, and the app eventually says so rather than
  // retrying forever behind a status that claims it is coming back.
  const { sidecar, seen } = fresh();
  sidecar.connect();
  for (let i = 0; i < Sidecar.ATTEMPTS + 2; i++) {
    FakeSocket.live[FakeSocket.live.length - 1].drop();
    runTimers();
  }
  eq("it gives up as crashed, once", seen[seen.length - 1], "crashed");
  ok("it stopped opening sockets", FakeSocket.live.length <= Sidecar.ATTEMPTS + 1);
}

{
  // The backoff actually backs off: each wait is longer than the last, capped.
  const { sidecar } = fresh();
  sidecar.connect();
  const waits: number[] = [];
  for (let i = 0; i < 5; i++) {
    const before = now;
    FakeSocket.live[FakeSocket.live.length - 1].drop();
    runTimers();
    waits.push(now - before);
  }
  eq("the backoff doubles from 400ms and caps at 6s", waits, [400, 800, 1600, 3200, 6000]);
}

{
  // A person pressing the button does not wait out the ladder.
  const { sidecar, seen } = fresh();
  sidecar.connect();
  FakeSocket.live[0].drop();
  sidecar.reconnect();
  ok("reconnect() opens a socket immediately", FakeSocket.live.length >= 2);
  eq("and says it is connecting, not reconnecting", seen[seen.length - 1], "connecting");
}

{
  // Deliberate teardown is final — an unmounting component must not leave a retry running.
  const { sidecar, seen } = fresh();
  sidecar.connect();
  const before = seen.length;
  sidecar.close();
  runTimers();
  eq("close() schedules nothing", FakeSocket.live.length, 1);
  eq("and reports no reconnect", seen.slice(before).filter((s) => s === "reconnecting").length, 0);
}

{
  // A socket we already replaced closing late must not knock the live one over.
  const { sidecar, seen } = fresh();
  sidecar.connect();
  const stale = FakeSocket.live[0];
  sidecar.reconnect();
  FakeSocket.live[FakeSocket.live.length - 1].onopen?.();
  const after = seen.length;
  stale.onclose?.();
  runTimers();
  eq("a stale socket's close is ignored", seen.slice(after), []);
}

/* ── the seats, and the budget that belongs to each ─────────────────────── */

eq("builtin is recognised however it is typed",
   [isBuiltin("builtin"), isBuiltin(" BuiltIn "), isBuiltin("qwen2.5:7b"), isBuiltin("")],
   [true, true, false, false]);

eq("the rules are not described as a provider", modelSummary({ model: BUILTIN }), "built-in rules · no model");
eq("an endpoint still names its provider",
   modelSummary({ model: "deepseek-chat", base_url: "https://api.deepseek.com/v1" }),
   "deepseek-chat · DeepSeek");

eq("the rules get their own, larger budget", budgetFor(BUILTIN), BUILTIN_BUDGET);
eq("a model gets the engine's own defaults", budgetFor("gpt-4o-mini"), BUDGET.defaults);
ok("and the rules' budget is the bigger of the two", BUILTIN_BUDGET.max_depth > BUDGET.defaults.max_depth);

/* ── report ─────────────────────────────────────────────────────────────── */

console.log(`\n${pass} passed, ${failures.length} failed`);
if (failures.length) throw new Error("socket checks failed:\n" + failures.map((f) => "  ✗ " + f).join("\n"));
