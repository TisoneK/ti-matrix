# Current Task (overwrite each session)

Holds exactly one task — the one being worked on right now. Set it at
session start (protocol Step 3), clear it at session end (Step 15). If
you find a stale in-progress entry here, a prior session died mid-task —
its roster row (if left behind) says who was here; check the session
entry and backlog before starting.

**The slot is free as of 2026-09-26.** The entry that was here belonged to Sable (S006), whose session ended
without a clock-out — it ran out of session tokens mid-write (last commit `3532cf7` at 00:36:37, its
orphaned files written at 00:40–00:41, no `claim`, no `release`). The supervisor *informed* this session of
that fact; clocking S006 out and clearing this slot were Rosalind's (S008) own decisions on that
information plus the trail, and are recorded as such.

**Not a certification that S006's session is finished — it is not.** What was adopted is what I could see:
the run's-last-word answer card, now on `main` in `7f36124`, adopted and fixed. What I found only when the
supervisor pushed back on the word "finished" is a third, adjacent piece that is plainly open:
`server/appserver/events.py::stream_run` reports `answer` from a `done` event alone, so a stopped run's
`partial_answer` never reaches `on_done` → `settled.answer` and `RunArtifact.outcome.answer` are empty for
exactly the case Sable's synthesizer work (6061180) exists to serve. The answer is drawn on screen (the
renderer refolds the events) and absent from the run's own durable record — two surfaces disagreeing about
whether a run answered. `answer_of`/`reason_of` in `server/appserver/main.py` are dead code and carry the
same `done`-only bug. Not fixed: it is sidecar behaviour, outside the surface this session claimed, and it
changes what a finished run reports.

Read the correction in Session 8 of `agents/sessions.md` before treating anything above as settled. The two
protocol rules this case needed — who may clear a stale roster row, and that an arriving session adopts
abandoned work rather than only preserving it — are in `memory/overrides/rules.md`, and the failure
signature is in `flaws/log.md`.

*(free — the slot is empty)*
