# Environments (update in place)

Machines and sandboxes agents have run on, and what it takes to work on
this project from each. One block per environment; update the matching
block (and its "last verified" date) every time you run on it again.

## Rules

1. **Match before you add.** At session start, check whether the machine
   you're on already has a block (use its "Identify by" line). Update the
   match; add a new block only for a genuinely new environment.
2. **Record what you verified, not what you assume.** A command belongs
   under "Verified commands" only after it ran successfully on this
   environment, this project.
3. **Agents never delete blocks.** An environment the project no longer
   uses may be pruned by the user; if you can't verify a block, leave it
   alone — its last-verified date already says how stale it is.
4. **Machine facts only.** Secret values go in `secrets/`; user
   preferences in `user/`; project-wide decisions in `plans/`.

---
## bao's Mac — where the app was rebuilt (last verified 2026-09-23)
- **Identify by:** macOS (darwin 24.6.0, x86_64), project checkout at `/Users/bao/Code/ti-matrix`
- **OS:** macOS; bash; no Windows tooling — the `.cmd`/`.ps1` launchers do not apply here
- **Runtimes:** Python 3.10.20 in the repo's `.venv/` (`python3` on PATH is 3.9.6 and too old for the
  package's `requires-python = ">=3.10"` — always use `.venv/bin/python`); Node 24.17.0, npm 11.13.0
- **Verified commands:** `.venv/bin/python -m pytest tests` (engine, 207 passed) ·
  `cd server && ../.venv/bin/python -m pytest tests` (sidecar, 34 passed) ·
  `cd app && npm run typecheck && npm run test && npm run build` (129 renderer assertions, Vite build) ·
  `node -e` / `npx esbuild` are both on PATH and usable for scratch work
- **Quirks:** no `ws` package in `app/node_modules`, so a WebSocket test harness must go through the real
  sidecar rather than a stub server; `pkill -f` on a backgrounded node/python script is needed to stop test
  servers between runs
- **The window CAN be launched and read here** (found later, 2026-09-23): `cd app && npm run dev:vite` in one
  shell, `VITE_DEV=1 npx electron . --remote-debugging-port=9222` in another, then drive it over CDP —
  `curl 127.0.0.1:9222/json` for the page target and `Runtime.evaluate` / `Page.captureScreenshot` for the
  DOM and a picture of the window's own content. `screencapture` on the desktop shows nothing (this session's
  WindowServer does not composite the app window), but the CDP capture renders the page regardless, which is
  what the layout checks actually need. Node 24's built-in WebSocket is enough — no dependency needed.

---
## Lameck — the user's Windows desktop (last verified 2026-09-23)
- **Identify by:** Windows hostname `Lameck`; project checkout at `C:/Users/Lameck/Tisone/ti-matrix`
- **OS:** Windows with Git Bash (POSIX sh available); PowerShell for `.cmd`/`.ps1` launchers
- **Runtimes:** Python 3.11.0 (project venv at `.venv/`)
- **Package manager:** pip (editable install of this repo in the venv)
- **Verified commands:** `PYTHONUTF8=1 .venv/Scripts/python.exe -m pytest tests` — the project's test suite, green (197 passed, 2 skipped) when run from the repo root under UTF-8 mode
- **Quirks:** timezone EAT (UTC+3); a bare `python -m pytest` dies with `UnicodeEncodeError: 'charmap' codec` (cp1252) on any fixture containing non-ASCII text — always set `PYTHONUTF8=1`; sibling package clone lives at `C:/Users/Lameck/Tisone/context-ledger` — `sh ../context-ledger/core/bin/ledger-sync <cmd>` works from this repo for package-mode commands (bootstrap, harvest)
-->
