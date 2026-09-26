# Protocol Overrides (update in place — project-owned)

Project-local adjustments to the protocol. Sessions read this file
right after loading their edition; where an override and the edition
conflict, **the override wins** — except the two rules nothing can
override: secret handling and append-only guarantees.

Overrides are standing, project-shaped deltas — not session
instructions (those die with the session) and not user preferences
(those live in `../user/preferences.md`). Core updates never touch
this file: customizations here survive every core version bump.

Because they survive core bumps, an override can quietly keep a project
diverged from a core that was later fixed — or diverged from a core that
is *still* broken everywhere else. So tag every override by kind:

- **`[core-defect]`** — core is wrong/broken here and this bullet is a
  local patch. `ledger-sync harvest` collects these into the package so
  the fix ships in a future core and the next project bootstrapped from
  it never rediscovers the workaround.
- **`[project-local]`** — core is fine; this project just works
  differently (git-flow, house style). Never harvested; stays local.

<!-- TEMPLATE — one bullet per override, tagged by kind, with provenance:
- **[core-defect]** <what core says> → <what THIS project does instead> —
  <why + which core version is broken> (set by <user/agent>, YYYY-MM-DD)
- **[project-local]** <what core says> → <what THIS project does instead> —
  <why this project differs> (set by <user/agent>, YYYY-MM-DD)

Examples:
- **[core-defect]** ledger-sync verify hashes with `sha256sum` → use
  `certutil -hashfile <file> SHA256`; `sha256sum` isn't on stock Windows
  PATH — core assumes POSIX coreutils (set by agent, 2026-07-20)
- **[project-local]** Push to main after each commit → push to the
  `develop` branch; main is release-only — repo uses git-flow (set by
  user, 2026-07-14)
-->

**[core-defect]** The schema does not say who may clear a roster row whose session has gone without
clocking out, and by definition it cannot be that session. This project has hit the gap twice in one day
(Wren/S002 on 2026-09-23, unnoticed for three days; Sable/S006 on 2026-09-26, after running out of session
tokens mid-write) — so, until the package states a rule: **any arriving session may remove a stale row,
and it must clear it by evidence, in a commit that records the evidence.**

Evidence means at least one of: the supervisor says the session is gone; a `release` event citing a
product commit, with no later activity from that codename; or a check-in that is older than the office's
own most recent session entry with nothing committed since. Absent the supervisor, cite what you used in
the commit message and in your own session entry. Nothing is lost by removing a row — the roster's git
history, the session's own entry in `agents/sessions.md`, and its commits are the durable record — but the
*reason* dies with the office unless it also goes in `flaws/log.md`, which is durable. (set by agent
Rosalind/S008 on the supervisor's statement, 2026-09-26)

**[core-defect]** A dirty working tree whose owner has abandoned it → the arriving session **adopts** the
work rather than only preserving it: read it, decide whether it is finished, keep what is right, fix what
is red, and say in the session entry that it was adopted and from whom. Phase 1's "never stash or discard
someone else's work" is right and must not change, but taken alone it deadlocks with "every change is
committed and pushed" the moment the owner is gone: the tree cannot be committed (someone else's half-done
work), cannot be reverted (destructive), and cannot be pushed. Adoption is the resolution, and the adopting
session owns the fix. The signal that an owner is gone rather than thinking: compare the newest commit's
timestamp against the dirty files' mtimes — a tree written *after* the last commit, with no `claim` event
and no `release` for that codename, is an abrupt stop, which is what token exhaustion looks like. (set by
agent Rosalind/S008, 2026-09-26)

*(none yet beyond the two above)*
