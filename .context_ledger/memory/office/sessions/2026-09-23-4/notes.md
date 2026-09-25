# Mara (S004) — driving the real Electron window from outside it

## The thing worth keeping: CDP against the app, not a stub

The previous session's open item B-2026-09-23-1 was that the renderer had only ever
been driven with `window.tm` stubbed, and the first real window launch immediately
found a bug the stub had hidden (unregistered library IPC). The same risk applied to
everything here, so nothing in this session was called verified until it had run in
the actual Electron window.

Electron exposes the Chrome DevTools Protocol, so the window can be driven from a
shell with no new dependency:

```bash
node_modules/.bin/electron . --remote-debugging-port=9222
curl -s http://127.0.0.1:9222/json      # the page's webSocketDebuggerUrl
```

Then `Runtime.evaluate` over that socket with `returnByValue` and `awaitPromise`
runs arbitrary expressions in the renderer — reading `document.body.innerText` for
assertions, calling `window.tm.settingsLoad()` to check what is actually on disk,
and `Page.captureScreenshot` for a picture. The driver is ~25 lines of aiohttp; it
is in this session's scratch, not the repo, because it is a technique rather than a
fixture.

Two traps:

- **A React-controlled input ignores `el.value = x`.** Use the native setter and
  dispatch the event React listens for, or the component's state never changes:
  ```js
  const set = Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, "value").set;
  set.call(textarea, "the goal"); textarea.dispatchEvent(new Event("input", { bubbles: true }));
  ```
- **The welcome overlay is up on a fresh profile** and swallows the run. Click
  `skip →` first, or the Run click lands on nothing and the status stays `idle` —
  which looks exactly like the bug you are trying to fix.

## What the window found that the tests could not

Making `builtin` the shipped default passed every suite and still did nothing on
this machine, because **the broken default was already persisted**. `settings.json`
under `~/Library/Application Support/Ti Matrix/` still held `qwen2.5:7b`, and the
hydration effect overwrites the defaults with it on every launch. A default change
only ever helps a fresh install; the person with an empty map is by definition the
one who has already launched the app. That is what `migrate()` in `core/settings.ts`
is for, and it rewrites exactly the one pair the app wrote on its own behalf.

This was invisible to every test because tests start from no settings file.

## Order of work that fit

Reproduce over the real WS first (drive a goal at the sidecar with a script, see
`proposer_error: 404` in two events), *then* read the UI. The panels were never the
problem and half an hour of reading them would have been wasted. The sidecar was
healthy in every run of this session — "sidecar gone" was the renderer's word for a
socket with no retry, and the empty panels were a model that did not exist.
