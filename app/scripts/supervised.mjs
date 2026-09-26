/*
 * Run one command so that it cannot outlive the thing that started it.
 *
 * `npm run dev` supervises vite and electron and takes both down when it stops — but only while it is
 * alive to run its handlers. Kill the supervisor itself (a closed console window, an ended agent session,
 * a `taskkill /F`) and its children are orphaned, because neither Node nor Windows ties a child's lifetime
 * to its parent. What is left behind is not inert: vite keeps `--strictPort` 5173, so the next
 * `npm run dev` refuses to start, and electron keeps the single-instance lock, so a relaunch exits without
 * drawing a window. Both read to a person as "the app broke", not "something is still running".
 *
 * So this is the tie. It runs the command, and it watches the supervisor the command was started for: when
 * that pid is gone, the command's whole tree is killed and this exits. It does not need the supervisor's
 * cooperation, which is the point — the failure it covers is the supervisor no longer being there.
 *
 *   node supervised.mjs <supervisor-pid> <command> [args…]
 *
 * No new dependencies: child_process, process, and one taskkill on Windows.
 */
import { spawn, spawnSync } from "node:child_process";
import process from "node:process";

const [supervisorPid, cmd, ...args] = process.argv.slice(2);
if (!supervisorPid || !cmd) {
  console.error("[supervised] usage: node supervised.mjs <supervisor-pid> <command> [args…]");
  process.exit(2);
}
const watched = Number(supervisorPid);

/** Whether a pid exists. Signal 0 asks without signalling; EPERM still means it is there. */
const alive = (pid) => {
  try {
    process.kill(pid, 0);
    return true;
  } catch (err) {
    return err.code === "EPERM";
  }
};

/** Kill a child and everything it started. On Windows that means the tree, explicitly. */
const reap = (child) => {
  if (!child || child.exitCode !== null) return;
  try {
    if (process.platform === "win32") {
      // Waited for, not fired and forgotten: exiting on the next tick would leave the killer as the only
      // thing still running, which is the same bug one level down.
      spawnSync("taskkill", ["/pid", String(child.pid), "/T", "/F"], { stdio: "ignore" });
    } else {
      child.kill("SIGTERM");
    }
  } catch {
    /* already gone is the state we wanted */
  }
};

const line = process.platform === "win32" ? [cmd, ...args].join(" ") : cmd;
const child = spawn(line, process.platform === "win32" ? [] : args, {
  shell: process.platform === "win32",
  stdio: "inherit",   // the command's own output goes straight where ours would have gone
  windowsHide: true,
});

child.on("exit", (code, signal) => {
  if (signal) process.kill(process.pid, signal);
  else process.exit(code ?? 0);
});
child.on("error", (err) => {
  console.error(`[supervised] could not run ${cmd}: ${err.message}`);
  process.exit(1);
});

// Our own signals mean "stop", and the command is not allowed to disagree.
for (const sig of ["SIGINT", "SIGTERM"]) process.on(sig, () => { reap(child); process.exit(0); });

// The watch. A second is short enough that nothing is left sitting for long, and long enough to cost
// nothing; a dev server is not a latency-sensitive thing to stop.
const timer = setInterval(() => {
  if (alive(watched)) return;
  clearInterval(timer);
  console.error(`[supervised] ${watched} is gone — stopping ${cmd} with it.`);
  reap(child);
  process.exit(0);
}, 1000);
timer.unref?.();
