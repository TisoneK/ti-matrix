# Session 3 notes — how the rebuild was driven and checked

Session-scoped detail behind the entry in `agents/sessions.md`. The durable facts were promoted to
`plans/decisions.md` (the architecture), `tasks/backlog.md` (what is still open),
`tasks/parking-lot.md` (what the engine and the maze taught us), `system/environments.md` (this machine)
and `reviews/2026-09-23-review-2.md` (the findings). What follows is the how, so it does not have to be
worked out again.

## The problem: no window to look at

A GUI Electron window could not be launched in this session, and a screenshot is the only way to judge
layout. Reading the JSX found none of the eleven defects — every one was visible on screen within seconds.

## The harness (worked; the recipe)

Serve the built renderer, stub only the preload, and let the page talk to a **real sidecar**:

1. `cd app && npm run build` (the harness serves `app/dist`).
2. A small node script that (a) spawns the real sidecar (`server/` + `.venv/bin/python -m appserver`),
   reads the `TM1 <port> <token>` handshake from its stdout, and (b) serves `app/dist` statically plus
   `harness.html`. The page gets `window.tm` from an injected script — `connection()` returns the real
   `ws://` URL from an HTTP endpoint, and `runsBegin/Save/List/Load/Delete` are backed by a directory
   under `/tmp`. Then `await import("/assets/" + js)` mounts the app.
3. Two traps: the built app's stylesheet lives in `assets/*.css` and **index.html is not loaded by the
   harness** — inject a `<link rel="stylesheet">` yourself, or the whole window renders unstyled and looks
   like a broken app. And the harness must be restarted after each `npm run build`, since the hashed
   bundle filename changes.
4. `pkill -f harness` / `pkill -f stub-model` to stop things; both leak otherwise.

`Window.tm` being the only stub is the point: the WebSocket, the frames, the folds, the artifact save and
the library listing all run as shipped. The only thing not exercised is Electron's own `userData` path.

## The model

A scripted OpenAI-compatible endpoint on `127.0.0.1:8123` that answers in the two shapes the engine parses
(`{"moves": [...]}` for a propose prompt, `{"evals": [...]}` for an evaluate prompt), reading only what a
real model would see — the state render's `KNOWN FACTS` and `MOVES SO FAR`. Enough of one to play the
maze (propose a step into the nearest unexplored opening) and, later, to walk a directory. Each run took
~100ms, so a full run + screenshot cycle was a few seconds.

It also produced the session's most useful accident: with the wrong endpoint configured, the app surfaced
the provider's 404 verbatim in a ledger row with a `forced stop` flag — the error path, checked for free.

## Order of work that made it fit in one session

The folds first (pure, testable, no React), the panels second. Because the panels are drawings of a
projection, the four of them could be written and rewritten without any of them breaking another — and
`npm run test` covered the thinking while the browser covered the drawing.

## What a next session should do first

Launch the real window (`npm run dev:vite` + `npm run dev:electron`) and look at it. That is
`B-2026-09-23-1`, and it is the one thing the harness cannot stand in for.
