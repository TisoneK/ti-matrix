# history/ — closed offices (readable) + permanent records

This zone holds two things:

1. **Permanent accomplishments records** — `office-<NNN>.md`, one per office
   ever closed, written by `ledger-history close`. Small, human-readable,
   and **never deleted**: even after an office's frozen directory is zipped
   into `../archive/` and eventually garbage-collected, its record stays
   here, so no office is ever forgotten — what it achieved, which decisions
   stayed in force, which open threads were re-seeded. This is the shelf
   you scan for the project's whole history.
2. **Recently closed offices** — `office-<NNN>/`, the frozen office
   directory itself (roster, session registry, notes, tasks, plans, flaw
   and inefficiency logs, reviews — preserved verbatim, nothing condensed
   or trimmed). The most recent `history_keep` (default 3) offices stay
   readable here; when the next office closes, the oldest directory is
   zipped into `../archive/` and removed (its record stays).

**Not read at session start.** Agents read the live office in
`.context_ledger/memory/office/`. This zone is for deliberate lookback —
"what did office 004 accomplish?", "who was on the team back then?"

An office's lifecycle:

```
memory/office/ (live)  ->  history/office-<NNN>/ (frozen, readable)  ->  archive/office-<NNN>.tar.gz (cold)  ->  gc
        |                            |
        `-- close writes history/office-<NNN>.md, the permanent record (stays forever)
```

Nothing durable lives only in a frozen office — the closing session
re-seeded still-open threads into the new office and recorded decisions
still in force in the permanent record. Legacy installs may also hold
`group-<NNN>.md` files here (the pre-1.0.0 condensed format) — read-only
history, left in place.
