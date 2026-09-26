# Current Task (overwrite each session)

Holds exactly one task — the one being worked on right now. Set it at
session start (protocol Step 3), clear it at session end (Step 15). If
you find a stale in-progress entry here, a prior session died mid-task —
its roster row (if left behind) says who was here; check the session
entry and backlog before starting.

- **Session:** 2026-09-25 — Marlowe / claude-sonnet-5 (S005)
- **Task:** shipped step 1 of B-2026-09-24-2 — the moving-world staleness contract. `AgentState` gains a fact clock (`fact_times`), staleness surfaces in `to_dict()`, the engine's honest-stop events, and `RunMemory.recall()`. Purely additive/diagnostic — no re-probing, no new stop reason.
- **Status:** done and pushed (`6cb8e73`) — pre-commit, integration and exit gates all green (321 tests, typecheck, app build)
- **Next up:** step 2 (re-check the one fact a decision rests on, at the moment of acting) is the natural follow-on, per the brief's build order — not started. See B-2026-09-24-2 for the full open-questions list.
