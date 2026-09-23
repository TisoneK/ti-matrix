# The desktop app (`app/`) and its sidecar (`server/`)

Three artifacts live in this repo, shipped independently. Changing one must never touch the others —
that is the whole point of the layout, and `tests/test_boundary.py` polices the most important wall.

| Artifact | Where | What it is |
|---|---|---|
| `ti-matrix` | `ti_matrix/` | the pip package: the engine, stdlib-only, zero dependencies |
| `ti-matrix-server` | `server/` | the sidecar: the engine behind a loopback WebSocket, speaks TM1 |
| `Ti Matrix` (app) | `app/` | the Electron + React desktop shell; bundles the sidecar |

## The seam

```
Electron main ──spawn──► sidecar (PyInstaller one-dir, or `python -m appserver` in dev)
      │ stdout:  TM1 <port> <token>          ← one line, the handshake
      │ HTTP:    /healthz                    ← main polls until 200
      ▼
renderer ◄── ws://127.0.0.1:<port>/ws?token=<token> ──► sidecar
      frames: goal / event / confirm-request / confirm-response / settled / error / stop
```

The protocol is versioned (`TM1`, `server/appserver/protocol.py`) and shared as the only contract
between the two bundles. Event payloads are `EngineEvent.to_dict()` verbatim — what the app shows
live is byte-compatible with `python -m ti_matrix.adapters.run_log FILE` on disk.

The engine never knows it is behind a server. Worlds are built from `server/appserver/worlds.py`;
the confirmer is `server/appserver/confirm_ws.py`, which turns the engine's ask into a
`confirm-request` frame and the app's Allow/Deny button into the answer. A dropped socket is a
refusal — the safe default, exactly like `--ask` at a terminal.

## The window

The renderer is a **run inspector**: the visualization is the product, and everything else is pushed to
one side of it. Three views, one run:

- **Run** — the map (what the run believes about the world, filled in as it observes it), the search tree
  (the states it stood on, with cold branches folded away), and the ledger (every decision with the
  belief behind it and the world's answer underneath). A transport under all of it scrubs, plays, steps
  and bookmarks the run.
- **Library** — every finished run, kept as an artifact: sortable by seed, model, steps, retreats,
  surprises, mean belief and duration.
- **Compare** — two saved runs under one cursor, overlaid on one grid when they read the same world.
  Two models, same seed, is the comparison worth making.

The whole thing hangs off one idea: a run is an event log, a cursor is a decision index, and every panel
is a pure function of the two (`renderer/core/project.ts`). Playback is therefore free — dragging the
scrubber back re-derives the map and the tree as they were, rather than replaying a recording — and
comparison is the same function called twice.

```
renderer/
  protocol.ts      the renderer's half of TM1, plus the `window.tm` channels the preload offers
  core/            pure functions only: events in, belief out. No React, no DOM, fully tested
    decisions.ts     the fold: raw events → one row per turn of the search loop
    knowledge.ts     the fold: the world's own sentences → the map, cell by cell
    tree.ts          the fold: the engine's node ids → the shape of the search
    trust.ts         the fold: the evaluator's scores → the confidence curve
    project.ts       (events, cursor) → all four at once
  hooks/           the sidecar session, and the transport's state machine
  shell/           the rail, the command bar, the config drawer, the transport, the confirmer
  panels/          Map, Tree, Log, Library, Compare, WorldSurface
  ui/              the primitives — buttons, chips, marks, the confidence bar, the sparkline
```

The window has no OS chrome above the app: **the top rail is the title bar.** It already carries what a
title bar carries — the name, the state, the way in — so a second strip would spend screen a run never gets
back. macOS keeps its traffic lights and the rail leaves them their corner (`titleBarStyle: "hiddenInset"`);
everywhere else the frame is gone and the rail draws its own minimize/maximize/close over the same
`tm.window-*` channels. The rail therefore takes the drag region, and everything clickable inside it opts
out — plus a double-click on its empty space maximizes, the way every title bar does.

The renderer has no filesystem: context isolation, no node integration. `window.tm` is the only way out,
and the session library is the one thing it needs — `app/main/index.ts` owns `<userData>/runs/<id>/`,
holding `run.json` (the artifact), `meta.json` (the library row) and `events.jsonl` (the engine's own run
log, written by the sidecar as the run streams, so the CLIs can read it back).

The config drawer also carries **what a run may spend** — steps, options per step, model calls, retreats —
seeded with the engine's own defaults. Against a real endpoint the defaults are the thing that ends a run:
a live model spends 20–45 seconds per decision, so depth six runs out long before the exit does.

## Endless scenarios

The maze world takes a **seed**: blank means a brand-new procedural maze every run (recursive
backtracker, BFS farthest-exit, guaranteed solvable — `server/appserver/scenarios.py`); the same
integer seed rebuilds the same world, so runs are repeatable and comparable. Width and height are
yours to set.

## Working on it

```bash
# sidecar, from server/
PYTHONUTF8=1 ../.venv/Scripts/python.exe -m pytest tests   # its own suite, real sockets

# app, from app/
npm install
npm run typecheck           # both tsconfigs, no emit
npm run test                # the renderer's own checks: the folds, against hand-built runs
npm run dev:vite            # in one shell
npm run dev:electron        # in another (TI_MATRIX_PYTHON overrides the venv python)

# packaging
python -m pip install -e . -e server[dev]
cd server && sh scripts/build-sidecar.sh    # bundle -> app/release/sidecar
cd ../app && npm run dist                   # unsigned installers per platform
```

`npm run test` needs no runner: `renderer/test.ts` imports the check files under `core/` and esbuild —
which already ships inside Vite — bundles and runs them on node. A failure throws, which is the exit code.

CI (`.github/workflows/ci.yml`): the engine's suite and the sidecar's suite on 3.10–3.13 × three
OSes, both wheels, the sidecar bundle smoked per OS, and unsigned app artifacts. Codesigning,
notarization and auto-update are later milestones.
