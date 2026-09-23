# Environments (update in place)

Machines and sandboxes agents have run on, and what it takes to work on
this project from each. One block per environment; update the matching
block (and its "last verified" date) every time you run on it again.

## Rules

1. **Match before you add.** At session start, check whether the machine
   you're on already has a block (use its "Identify by" line). Update the
   match; add a new block only for a genuinely new environment.
2. **Record what you verified, not what you assume.** A command belongs
   under "Verified commands" only after it ran successfully on this
   environment, this project.
3. **Agents never delete blocks.** An environment the project no longer
   uses may be pruned by the user; if you can't verify a block, leave it
   alone — its last-verified date already says how stale it is.
4. **Machine facts only.** Secret values go in `secrets/`; user
   preferences in `user/`; project-wide decisions in `plans/`.

---
## Lameck — the user's Windows desktop (last verified 2026-09-23)
- **Identify by:** Windows hostname `Lameck`; project checkout at `C:/Users/Lameck/Tisone/ti-matrix`
- **OS:** Windows with Git Bash (POSIX sh available); PowerShell for `.cmd`/`.ps1` launchers
- **Runtimes:** Python 3.11.0 (project venv at `.venv/`)
- **Package manager:** pip (editable install of this repo in the venv)
- **Verified commands:** `PYTHONUTF8=1 .venv/Scripts/python.exe -m pytest tests` — the project's test suite, green (197 passed, 2 skipped) when run from the repo root under UTF-8 mode
- **Quirks:** timezone EAT (UTC+3); a bare `python -m pytest` dies with `UnicodeEncodeError: 'charmap' codec` (cp1252) on any fixture containing non-ASCII text — always set `PYTHONUTF8=1`; sibling package clone lives at `C:/Users/Lameck/Tisone/context-ledger` — `sh ../context-ledger/core/bin/ledger-sync <cmd>` works from this repo for package-mode commands (bootstrap, harvest)
-->
