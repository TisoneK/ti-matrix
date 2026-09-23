# CLAUDE.md — read this first, every session

<!-- Installed at bootstrap from .context_ledger/core/templates/CLAUDE.md.
Claude Code auto-loads THIS file, not AGENTS.md, so the same weak-agent-
floor rules AGENTS.md carries (check in; close a full office; no leaked
secrets; no mixed commit surfaces; don't stop without pushing) are
stated here too, not only routed onward — the two floors should agree
even though only one of them loads automatically here. Keep everything
else short — update kickoff.md and the vendored core, not this pointer
(core 2.0.0 trimmed this file to a pointer; core 2.0.2 put the check-in
line back after it caused a real collision; core 2.0.3 put the rest of
this list back on the same reasoning — see CHANGELOG). -->

This repo runs the `.context_ledger/` engineering protocol.

**Before reading anything else here — including the rest of this
file — check in:** add your row to
[`.context_ledger/memory/office/agents/roster.md`](.context_ledger/memory/office/agents/roster.md)
(a real name — never "Claude" — plus codename `S<NNN>`, model, Status
`Working`), then commit and push it. Reading or analyzing first is how
two sessions collide before either ever sees the other on the board.

**Before that push, check `.context_ledger/memory/office/agents/sessions.md`:**
if it already holds more than `office_size` sessions (default 20), the
office is full — close it first (`sh .context_ledger/core/bin/ledger-history close`,
dry run then `--confirm`) and sign the fresh board instead.

**Then** read
[`.context_ledger/kickoff.md`](.context_ledger/kickoff.md) and follow it,
in order — its Phase 2 covers both of the above with full mechanics,
then routes you onward. Do not start work from memory of this file alone.

Never write under `.context_ledger/core/`. No secret values in any
tracked file, ever — only in `.context_ledger/memory/secrets/`. Stage and
commit project code and `.context_ledger/` memory separately, never both
with `git add -A`. And the session is not done until it's committed
**and pushed** — a user reminder to push is a logged protocol failure.
