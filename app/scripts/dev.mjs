/*
 * One command, both halves of dev mode: `npm run dev`.
 *
 * Dev used to mean two shells and an ordering rule — Vite first, Electron second — and the first person
 * to try it launched Electron alone and stared at a blank window. This script is the rule, enforced:
 * Vite starts first, we wait until it is actually listening (not merely spawned), and only then does
 * Electron come up with VITE_DEV set. When the Electron window closes, Vite goes down with it, so there
 * is no orphan server squatting on 5173 after you are done. Ctrl+C takes both down.
 *
 * Both children go through `supervised.mjs`, which is what makes that promise survive *this* script being
 * killed. Taking them down from here only works while there is a here to run the handler: close the
 * console window, end the agent session, or `taskkill /F` this process and its children are orphaned,
 * because Node and Windows both leave a child running when its parent dies. Vite then holds `--strictPort`
 * 5173 so the next `npm run dev` refuses to start, and Electron holds the single-instance lock so a
 * relaunch exits without drawing a window. The supervisor hands its own pid to each wrapper, and the
 * wrapper reaps the tree when that pid is gone.
 *
 * No new dependencies: this is what Node already ships with — child_process, net, signals.
 */
import { spawn } from "node:child_process";
import path from "node:path";
import net from "node:net";
import process from "node:process";

const ROOT = new URL("..", import.meta.url).pathname.replace(/^\/([A-Za-z]:)/, "$1");
const PORT = 5173;
const SUPERVISED = path.join(ROOT, "scripts", "supervised.mjs");

const run = (cmd, args, opts = {}) => {
  // One command string with the shell, not args + shell: Node deprecates the latter (DEP0190), and on
  // Windows the shell is what finds `npx` anyway.
  const line = process.platform === "win32" ? [cmd, ...args].join(" ") : cmd;
  const argv = process.platform === "win32" ? [] : args;
  const child = spawn(line, argv, { cwd: ROOT, shell: process.platform === "win32", ...opts });
  child.stdout?.on("data", (d) => process.stdout.write(d));
  child.stderr?.on("data", (d) => process.stderr.write(d));
  return child;
};

/** The shell on Windows splits the command line itself, so anything with a space in it must be quoted. */
const quoteIfNeeded = (s) => (process.platform === "win32" && /\s/.test(s) ? `"${s}"` : s);

/** The same command, with a wrapper that outlives this script and cleans up after it. */
const supervised = (cmd, args) => run(quoteIfNeeded(process.execPath), [
  quoteIfNeeded(SUPERVISED), String(process.pid), cmd, ...args,
]);

/** Resolves the moment something answers on the port — "spawned" is not "serving". */
function waitListening(port, timeoutMs = 30_000) {
  // Both loopbacks: vite may bind IPv4 (127.0.0.1) or IPv6 (::1) depending on the machine, and the
  // gate must not stare past a server that answered on the other stack.
  const hosts = ["127.0.0.1", "::1"];
  const answersOnce = (host) => new Promise((resolve) => {
    const socket = net.connect({ port, host });
    socket.once("connect", () => { socket.destroy(); resolve(true); });
    socket.once("error", () => { socket.destroy(); resolve(false); });
    socket.setTimeout(1200, () => { socket.destroy(); resolve(false); });
  });
  return new Promise((resolve, reject) => {
    const started = Date.now();
    const tryOnce = async () => {
      for (const host of hosts) {
        if (await answersOnce(host)) { resolve(); return; }
      }
      if (Date.now() - started > timeoutMs) reject(new Error(`nothing answered on ${port} within ${timeoutMs / 1000}s`));
      else setTimeout(tryOnce, 250);
    };
    tryOnce();
  });
}

let vite = null;
let electron = null;
let stopping = false;

const stop = (code) => {
  if (stopping) return;
  stopping = true;
  for (const child of [electron, vite]) {
    if (!child || child.exitCode !== null || child.killed) continue;
    if (process.platform === "win32") spawn("taskkill", ["/pid", String(child.pid), "/T", "/F"]);
    else child.kill();
  }
  process.exit(code);
};

for (const sig of ["SIGINT", "SIGTERM"]) {
  process.on(sig, () => stop(0));
}

console.log(`[dev] checking :${PORT}…`);
if (await waitListening(PORT, 1200).then(() => true).catch(() => false)) {
  console.error(`[dev] :${PORT} is already in use — another vite (or yesterday's one) owns it.\n` +
    `      Kill it first (or just use it): refusing to start a second server on the same port.`);
  process.exit(1);
}

console.log(`[dev] vite starting on :${PORT}…`);
vite = supervised("npx", ["vite", "--port", String(PORT), "--strictPort"]);
// A vite that dies (bad flag, crash, Ctrl+C in its output) must end this script — otherwise the gate
// below would happily wait out its timeout, or worse, connect to some *other* process that later took
// the port, and start Electron against a server nobody owns.
vite.on("exit", (code) => {
  if (!stopping) {
    console.error(`[dev] vite exited (code ${code ?? "signal"}) — stopping.`);
    stop(code ?? 1);
  }
});

try {
  await waitListening(PORT);
} catch (err) {
  console.error(`[dev] ${err.message} — is something else on :${PORT}?`);
  stop(1);
}
console.log(`[dev] vite is serving — starting electron…`);

electron = supervised("npx", ["cross-env", "VITE_DEV=1", "electron", "."]);
electron.on("exit", (code) => stop(code ?? 0));
