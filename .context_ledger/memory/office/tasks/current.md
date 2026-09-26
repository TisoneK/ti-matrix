# Current Task (overwrite each session)

Holds exactly one task — the one being worked on right now. Set it at
session start (protocol Step 3), clear it at session end (Step 15). If
you find a stale in-progress entry here, a prior session died mid-task —
its roster row (if left behind) says who was here; check the session
entry and backlog before starting.

**Cleared 2026-09-26 by Rosalind (S008).** The entry that was here belonged to Sable (S006), whose session
ended without a clock-out — it ran out of session tokens mid-write (last commit `3532cf7` at 00:36:37, its
orphaned files written at 00:40–00:41, no `claim`, no `release`). The task is closed rather than dropped:
stage 1 of the token/balance tracking shipped and was verified against a live account, the four worlds were
run end to end, and the one piece that was in flight when it stopped — the run's-last-word answer card — is
now on `main` in `7f36124`, adopted and fixed. What remains of it is the backlog rows it already pointed
at (notably B-2026-09-26-3, which its own live run surfaced). Nothing is unowned. The two protocol rules
this case needed — who may clear a stale roster row, and that an arriving session adopts abandoned work
rather than only preserving it — are now in `memory/overrides/rules.md`, and the failure signature is in
`flaws/log.md`. Full account: Session 8 in `agents/sessions.md`.

*(free — the slot is empty)*
