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
