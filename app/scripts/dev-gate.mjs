/*
 * The gate for the two-shell path (`npm run dev:vite` in one shell, `npm run dev:electron` in another).
 *
 * The rule this enforces is the one the first real launch broke: the Electron window must not come up
 * before something is actually serving :5173 — "the shell is running" is not "the server is listening".
 * With the gate, a second shell launched too early waits (with a message) instead of showing a blank
 * window; launched with no Vite at all, it fails in three words instead of twenty seconds of silence.
 *
 * Exits 0 the moment the port answers. No dependencies — Node's own `net` is the whole probe.
 */
import net from "node:net";

const PORT = 5173;
const TIMEOUT_MS = 30_000;

// Both loopbacks — vite may bind IPv4 or IPv6 depending on the machine.
const HOSTS = ["127.0.0.1", "::1"];
const answers = (port) => Promise.all(HOSTS.map((host) => new Promise((resolve) => {
  const socket = net.connect({ port, host });
  socket.once("connect", () => { socket.destroy(); resolve(true); });
  socket.once("error", () => { socket.destroy(); resolve(false); });
  socket.setTimeout(1200, () => { socket.destroy(); resolve(false); });
})).then((hit) => hit.some(Boolean)));

const started = Date.now();
let said = false;
for (;;) {
  if (await answers(PORT)) process.exit(0);
  if (Date.now() - started > TIMEOUT_MS) {
    console.error(`\ndev:electron: nothing is serving :${PORT}. Start the dev server first — npm run dev (one command), or npm run dev:vite in another shell.\n`);
    process.exit(1);
  }
  if (!said) { console.error("dev:electron: waiting for the vite server on :5173…"); said = true; }
  await new Promise((r) => setTimeout(r, 400));
}
