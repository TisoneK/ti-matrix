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

*(none yet)*
