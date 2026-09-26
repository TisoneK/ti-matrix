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
## bao's Mac — where the app was rebuilt (last verified 2026-09-26)
- **Identify by:** macOS (darwin 24.6.0, x86_64), project checkout at `/Users/bao/Code/ti-matrix`
- **OS:** macOS; bash; no Windows tooling — the `.cmd`/`.ps1` launchers do not apply here
- **Runtimes:** Python 3.10.20 in the repo's `.venv/` (`python3` on PATH is 3.9.6 and too old for the
  package's `requires-python = ">=3.10"` — always use `.venv/bin/python`); Node 24.17.0, npm 11.13.0
- **Verified commands (2026-09-26):** `.venv/bin/python -m pytest tests` (engine) ·
  `.venv/bin/python -m pytest tests server/tests -q` (344 passed in 61s) · `npm --prefix app run typecheck`
  · `npm --prefix app run test` (172 renderer assertions) · `npm --prefix app run build` (Vite, green) ·
  `sh .context_ledger/core/bin/ledger-gates run pre-commit|integration|exit` — all three PASSED ·
  `node -e` / `npx esbuild` are both on PATH and usable for scratch work
- **Quirks:** no `ws` package in `app/node_modules`, so a WebSocket test harness must go through the real
  sidecar rather than a stub server; `pkill -f` on a backgrounded node/python script is needed to stop test
  servers between runs
- **The window CAN be launched and read here** (found 2026-09-23): `cd app && npm run dev:vite` in one
  shell, `VITE_DEV=1 npx electron . --remote-debugging-port=9222` in another, then drive it over CDP —
  `curl 127.0.0.1:9222/json` for the page target and `Runtime.evaluate` / `Page.captureScreenshot` for the
  DOM and a picture of the window's own content. `screencapture` on the desktop shows nothing (this session's
  WindowServer does not composite the app window), but the CDP capture renders the page regardless, which is
  what the layout checks actually need. Node 24's built-in WebSocket is enough — no dependency needed.
- **Second-instance recipe — how to inspect the app without disturbing the supervisor's own window**
  (verified 2026-09-26; this is what makes a UI pass possible while they are using the app). A dev server
  is usually already up on 5173 by the supervisor; against it, launch
  `VITE_DEV=1 npx electron . --remote-debugging-port=9333 --user-data-dir=/tmp/tm-<name>`.
  **The single-instance lock is per `--user-data-dir`** (`app/main/index.ts` calls
  `requestSingleInstanceLock()`), so a second instance without its own profile exits silently and looks
  like a broken launch. Each instance spawns its own `appserver`; `--user-data-dir` also isolates the saved
  settings and library, which is why a fresh instance starts with no runs and no saved API key.
- **CDP gotchas, found the hard way:** `Input.dispatchMouseEvent` takes CSS pixels, so call
  `Emulation.setDeviceMetricsOverride` first and re-measure element rects rather than reusing coordinates
  from an earlier screenshot. A click dispatched while Vite is applying an HMR update can be lost — if an
  expected state change does not appear, re-check that the element you targeted is still the live one
  (its `title`/`disabled`) before concluding the app is broken, and be aware that a real mouse event and a
  `button.click()` inside `Runtime.evaluate` are different experiments. Vite serves the renderer at
  `http://127.0.0.1:5173/`, so renderer edits hot-reload with no reload step (a reload is still worth it
  after structural changes).

---
## Lameck — the user's Windows desktop (last verified 2026-09-23)
- **Identify by:** Windows hostname `Lameck`; project checkout at `C:/Users/Lameck/Tisone/ti-matrix`
- **OS:** Windows with Git Bash (POSIX sh available); PowerShell for `.cmd`/`.ps1` launchers
- **Runtimes:** Python 3.11.0 (project venv at `.venv/`)
- **Package manager:** pip (editable install of this repo in the venv)
- **Verified commands:** `PYTHONUTF8=1 .venv/Scripts/python.exe -m pytest tests` — the project's test suite, green (197 passed, 2 skipped) when run from the repo root under UTF-8 mode
- **Quirks:** timezone EAT (UTC+3); a bare `python -m pytest` dies with `UnicodeEncodeError: 'charmap' codec` (cp1252) on any fixture containing non-ASCII text — always set `PYTHONUTF8=1`; sibling package clone lives at `C:/Users/Lameck/Tisone/context-ledger` — `sh ../context-ledger/core/bin/ledger-sync <cmd>` works from this repo for package-mode commands (bootstrap, harvest)
-->

---
## The user's desktop — Windows 11, user `tison` (last verified 2026-09-26)
- **Identify by:** Windows hostname `DESKTOP-2VPR9IB`, Windows 10.0.26200 x64, project checkout at
  `C:/Users/tison/Dev/ti-matrix` — a *different* machine from Lameck's despite both being the user's Windows
  desktop
- **OS:** Windows with Git Bash (POSIX `sh`, `timeout`, `curl` all present); PowerShell 7 for `.cmd`/`.ps1`
- **Runtimes:** Python 3.14.2 in the repo's `.venv/` (a **uv** venv — `uv = 0.9.26` in `pyvenv.cfg`); Python
  3.14.2 also on `PATH` at `C:\Python314`; Node v24.13.0, npm 11.12.1
- **The venv has no `pip`** — a uv-created venv omits it, so `.venv/Scripts/python.exe -m pip` fails with
  "No module named pip". Install with uv instead: `uv pip install --python .venv/Scripts/python.exe ...`
  (uv 0.9.26 is on `PATH` here). `ensurepip` *is* importable if pip is ever genuinely wanted.
- **Verified commands:** `uv pip install --python .venv/Scripts/python.exe -e ".[dev]" -e "server[dev]"`
  (the CI dependency set — the venv arrived with pytest and `ti_matrix` only, so `aiohttp` and the
  `ti-matrix-server` package had to be installed before `server/tests` could even import) ·
  `sh .context_ledger/core/bin/ledger-gates run pre-commit` → PASSED (server 38 passed, app typecheck, 162
  renderer assertions) · `.venv/Scripts/python.exe -m pytest tests -q` → 294 passed, 1 failed in 76s · `-m
  pytest server/tests -q` → 38 passed in 1.4s · `npm --prefix app run build` → green
- **`agent-browser` IS installed here** (global, 0.35.1) — so `tests/test_agent_browser.py`'s real-CLI tests
  *run* instead of skipping themselves, which is the opposite of Lameck's machine and is why two Windows-only
  defects surfaced on this box. It drives real headless Chrome from `~/.agent-browser/browsers/`.
- **Quirks:** the project's own `.venv/bin/python` path in `gates.conf` is tried first and always misses here
  (`sh: .venv/bin/python: No such file or directory`), then the `.venv/Scripts/python.exe` fallback runs — the
  first line of that gate is noise on Windows, not a failure. A network timeout on a first `uv pip install`
  needs `UV_HTTP_TIMEOUT=300`. `agent-browser` leaves a daemon plus headless Chrome alive after every session
  (its `agent-browser-win32-x64.exe` owns the browser between invocations); stray Chrome accumulates in
  `%LOCALAPPDATA%\Temp\agent-browser-chrome-*` unless a session is closed with `agent-browser close --all`.
  The sibling package clone is at `C:/Users/tison/Dev/context-ledger`.
