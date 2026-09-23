# Agent Sessions (append-only within the current office)

One entry per agent session in the **current office**, newest at the bottom.
Never edit or delete past entries — append corrections instead. This is not
append-only *forever*: when the office reaches `office_size` sessions (or a
milestone), `ledger-history close` freezes this whole office verbatim into
`.context_ledger/history/office-<NNN>/` (roster, registry, notes, logs —
nothing trimmed), writes the permanent accomplishments record
`.context_ledger/history/office-<NNN>.md`, and opens a fresh empty office
here. Closed offices in `history/` and `archive/` are never read at session
start. Before closing, note which open threads still matter — they are
re-seeded into the new office explicitly, and nothing else carries over.

<!-- TEMPLATE — copy below the last entry and FILL IN every placeholder:
---
## YYYY-MM-DD — Session N
- **Agent:** <name> | **Model:** <model id> | **Platform:** <machine/sandbox + OS> | **Role:** <engineer, or overlay from .context_ledger/core/roles/> | **Core:** <version from .context_ledger/core/VERSION>
- **Task:** <what this session set out to do>
- **Commits:** <count> (<first-sha>..<last-sha>)
- **Outcome:** <done / partial / blocked — one line>
- **Open items:** <pointers into tasks/backlog.md (actionable) or tasks/parking-lot.md (findings/questions), or "none">
- **Notes:** .context_ledger/memory/office/sessions/<date>-<N>/notes.md  (or "none")
- **Report:** .context_ledger/memory/office/reviews/YYYY-MM-DD-review.md
-->

---
## 2026-09-23 — Session 1 (bootstrap + the desktop app's skeleton)
- **Agent:** Buffy | **Model:** unknown | **Platform:** Lameck — Windows, Git Bash | **Role:** engineer | **Core:** 2.0.4
- **Task:** bootstrap `.context_ledger/` from the package clone (`sh ../context-ledger/core/bin/ledger-sync bootstrap .`) and fill the memory skeleton; then build the desktop-app skeleton per the approved plan — `server/` (the `ti-matrix-server` sidecar: TM1 protocol, event streaming, WS confirmer, world registry, seeded scenario generator, 33 tests) and `app/` (Electron main with sidecar lifecycle, minimal preload, React run-inspector with the confirmer dialog; typecheck + Vite build + subprocess smoke green) — and the CI matrix (pytest 3.10–3.13 × 3 OS, both wheels, PyInstaller sidecar, electron-builder artifacts)
- **Commits:** 3, pushed (48190e7 project surface — server/, app/, CI, .gitignore; e16237d ledger bootstrap; 2fa0699 merge with four remote commits that arrived mid-push, .gitignore conflict resolved, both suites re-verified after)
- **Outcome:** done and pushed — the `ti_matrix` wheel untouched (197 passed, 2 skipped before the merge; 204 passed, 2 skipped after integrating the remote's engine changes), sidecar suite 33 passed, app typecheck green
- **Open items:** `npm run dev:electron` not yet run against a live window (needs the user at the keyboard); PyInstaller bundle not yet built locally; codesigning/notarization and auto-update deliberately deferred; ledger write-back checkbox exists but is only exercised by unit tests
- **Notes:** none
- **Report:** none
---
## 2026-09-23 — Session 3 (the app UI, rebuilt from the ground up)
- **Agent:** Nadia | **Model:** deepseek-flash | **Platform:** bao's Mac — macOS (darwin 24.6.0), Node 24.17.0, Python 3.10.20 (.venv) | **Role:** engineer | **Core:** 2.0.4
- **Task:** discard the renderer and rebuild it as a visualization-first run inspector — a fog-of-war map drawn only from what a run observed, the search tree, a ledger of every decision with the belief behind it, playback (scrub/step/speed/bookmarks over one cursor), comparison of two runs, a persisted session library, and config demoted to a collapsible drawer
- **Commits:** 1 product commit (`7348350` — the renderer rebuild, the new `tm.runs*` IPC in `app/main` + `app/preload`, the docs) plus ledger commits (`bb09e33` check-in, `888895a` peer merge, `c260f95` STATE, and the closing memory commit)
- **Outcome:** done and pushed — typecheck green, 129 renderer assertions, engine 207 passed, sidecar 34 passed, Vite build green; a real run driven end to end in a browser harness against the real sidecar (102 events, 14 decisions, 6 retreats) and 11 defects found on screen and fixed (two pane-nesting layout bugs, two accessibility bugs, the map legend, the missing way back from a rewound finished run, a knowledge-precedence bug where an inferred wall erased a known corridor). **Follow-up, same session:** the rail became the window's title bar (macOS keeps its traffic lights; every other platform gets the rail's own controls over new `tm:window-*` channels) — and launching the real Electron window to check it found that the library IPC handlers had never been registered, a bug the stubbed harness had hidden. Fixed and verified in the real window; `main` fast-forwarded to this branch per the standing push policy. **Third pass, same session:** two real runs against the DeepSeek API through the app's own window (6 decisions/3m29s, then 10/6m37s after the fix below), which exposed that the window never sent a run budget — the goal frame always accepted one — so every real run stopped at the engine's default depth of six with nothing on screen to change it; the budget is now four fields in the config drawer and the second run passed the old ceiling. Both runs are saved in the library with real numbers
- **Open items:** B-2026-09-23-1 (no real Electron window was launched — the renderer was driven with `window.tm` stubbed), B-2026-09-23-2 (the prose worlds' panels are thinner than the views they replaced), B-2026-09-23-3 (no run against a real LLM yet)
- **Collaboration:** light path with the peer on the board (Wren, S002, idle on `main`): session `S003`, issue `ui-rebuild`, a `note` and a `claim` at start, a `release` citing `7348350` at close (events under `memory/collaboration/events/`). No agreement was needed — the scopes never overlapped.
- **Notes:** .context_ledger/memory/office/sessions/2026-09-23-3/notes.md — the browser-harness recipe that made the visual checks possible without a window, and the order of work that fit it in one session
- **Report:** .context_ledger/memory/office/reviews/2026-09-23-review-2.md
