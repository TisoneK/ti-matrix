# .context_ledger/ — Agent Memory + Vendored Protocol

<!-- CORE-OWNED — refreshed from core/templates/ledger-README.md on
core updates. Project-specific notes belong in memory/ files, never here. -->

This directory makes any AI agent — any model, any machine, local or
cloud — a continuing member of this project instead of a stranger. It
is committed to git and travels with the repo. It has **two zones**:

```text
.context_ledger/
├── README.md     # this file — the zone map
├── kickoff.md    # THE FRONT DOOR — read this first, every session
├── core/         # the protocol, vendored — package-owned, READ-ONLY
│   ├── VERSION           # core semver in force here
│   ├── rules/            # the protocol editions (local + cloud)
│   ├── roles/            # mission overlays
│   ├── schemas/          # ledger-schema.md — the single source of truth on formats
│   ├── templates/        # what memory files are generated from
│   └── bin/              # ledger-sync + ledger-collab (+ .ps1): sync, peer coordination, and integration checks
├── memory/       # this project's living memory — project-owned, writable
│   ├── office/                 # THE live office — one at a time, never numbered;
│   │                           #   frozen verbatim into history/ when it fills up
│   │   ├── agents/sessions.md      # append-only session registry
│   │   ├── agents/roster.md        # the "who's in the office now" board — sign here FIRST, before the deep read
│   │   ├── tasks/current.md        # task in progress (single-agent lock only)
│   │   ├── tasks/backlog.md        # capped work QUEUE — actionable items only (delete the row when done; overflow → parking lot)
│   │   ├── tasks/parking-lot.md    # knowledge BASE — findings, questions, deferred/someday (uncapped, not a queue; promote to backlog when actionable)
│   │   ├── plans/decisions.md      # append-only ADRs
│   │   ├── flaws/log.md            # protocol friction — flows upstream to the package
│   │   ├── inefficiencies/log.md   # project friction
│   │   ├── reviews/                # session reports
│   │   └── sessions/               # per-session notes (optional)
│   │       ├── SUMMARY.md              # compressed history — entries are removable
│   │       └── YYYY-MM-DD-N/notes.md   # session-scoped detail
│   ├── collaboration/          # durable — opt-in peer coordination, never rotates
│   │   ├── README.md            # worktree + event contract
│   │   └── events/               # immutable one-file-per-event records
│   ├── workflows/
│   │   ├── active.md             # standing session parameters
│   │   ├── gates.conf             # explicit lifecycle commands + hybrid discovery mode
│   │   └── history.conf           # office rotation knobs (office_size, keeps)
│   ├── system/                 # durable — machines + agent/model registry
│   ├── user/                   # durable — identity + preferences
│   ├── overrides/rules.md      # durable — project-local protocol adjustments
│   ├── core.lock                # last-known-good core version (ledger-sync writes it)
│   └── secrets/                 # LOCAL-ONLY — self-gitignored, never travels
├── history/      # closed offices + permanent records — NOT read at session start
│   ├── office-001.md             # permanent accomplishments record (never deleted)
│   └── office-001/               # the frozen office, verbatim (kept history_keep, then zipped)
└── archive/      # cold storage of closed offices — NOT read at session start
    └── office-001.tar.gz         # the zipped frozen office; its record stays in history/
```

## The three rules that matter most

1. **Never write under `core/`.** It is a versioned, checksummed copy
   of the protocol package — updated only as a whole tree by
   `core/bin/ledger-sync`. Protocol improvements go to the package
   repo via `memory/office/flaws/log.md`, not into this copy.
2. **`memory/` is this project's data.** Write it per each file's mode —
   append-only logs stay append-only, `chore(ledger):` commit prefix,
   no secret values in tracked files, ever. The full spec:
   `core/schemas/ledger-schema.md`.
3. **Sessions start at `kickoff.md`** (one level up from memory —
   `.context_ledger/kickoff.md`). It routes you by agent type to your edition
   in `core/rules/`. Memory never chooses your edition — your agent
   type does. Check in at the roster before the deep read — signing is
   the first write of a session, not a wrap-up formality; the push
   claims your codename. For concurrent work, use isolated branches/worktrees and
   `memory/collaboration/events/`; overlapping changes require a peer
   agreement before implementation.
