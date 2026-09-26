# Current Task (overwrite each session)

Holds exactly one task — the one being worked on right now. Set it at
session start (protocol Step 3), clear it at session end (Step 15). If
you find a stale in-progress entry here, a prior session died mid-task —
its roster row (if left behind) says who was here; check the session
entry and backlog before starting.

- **Session:** 2026-09-25 — Sable / claude-sonnet-5 (S006)
- **Task:** implement model balance / token-usage tracking (staged), then run the shipped worlds end to end and fix what surfaces.
- **Status:** in-progress — stage 1 shipped and pushed (`eeafb8e`, `f3cacec`, `3f3d89d`, `151606e`): `OpenAICompatModel` tracks token usage and DeepSeek balance; the sidecar's `settled` frame and the app's top rail surface a run's usage; `files_cli`/`ledger_cli`/`browser/cli` can now actually run `--model builtin` (B-2026-09-24-3, fixed) and print a usage/balance note. Found and fixed along the way: `ledger_cli` crashed on every invocation (`a.ask` referenced an argument `_args()` never defines). All four shipped worlds (maze, files, chess, browser) verified running end to end with the builtin reasoner — no crashes; chess and browser stop honestly on `budget`/`no_moves` since builtin has no synthesizer to phrase a final answer, which is by design, not a bug.
- **Next up:** pausing here to report to the user before deciding what "fixing where possible" covers next — a real hosted-model run (DeepSeek), more builtin-path edge cases, or the two known open items surfaced along the way (B-2026-09-23-5's small-model weakness, B-2026-09-23-2's thin prose-world panels) are all live candidates.
