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
npm run dev:vite            # in one shell
npm run dev:electron        # in another (TI_MATRIX_PYTHON overrides the venv python)

# packaging
python -m pip install -e . -e server[dev]
cd server && sh scripts/build-sidecar.sh    # bundle -> app/release/sidecar
cd ../app && npm run dist                   # unsigned installers per platform
```

CI (`.github/workflows/ci.yml`): the engine's suite and the sidecar's suite on 3.10–3.13 × three
OSes, both wheels, the sidecar bundle smoked per OS, and unsigned app artifacts. Codesigning,
notarization and auto-update are later milestones.
