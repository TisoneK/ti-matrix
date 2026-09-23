# Session-Scoped Memory

Session history lives here: self-contained, disposable, and separable
from knowledge that must outlive the session. The three layers:

| Layer | Location | Lifetime | Purpose |
|---|---|---|---|
| **Session detail** | `<date>-N/notes.md` | Disposable | Research, dead ends, exploration, reasoning |
| **Session summary** | `SUMMARY.md` | Prunable (current office) | Compressed continuity (~1 line per session) |
| **Office registry** | `../agents/sessions.md` | Current office; frozen verbatim at close | Formal registry for the live office — one entry proves the session happened |

## Office lifecycle (three-zone rotation)

Session history lives inside the **office** — the live, unnumbered directory
`memory/office/`, the only zone read at session start. When the office fills
up (at `office_size` sessions, or a milestone), `ledger-history close`
freezes it **verbatim** — roster, registry, notes, logs, nothing condensed
or trimmed — and numbers it at that moment:

```
memory/office/ (live)  ->  history/office-<NNN>/ (frozen, readable)  ->  archive/office-<NNN>.tar.gz (cold)  ->  gc
```

Alongside the frozen directory, close writes the **permanent accomplishments
record** `history/office-<NNN>.md` — what the office achieved, which
decisions stay in force, which open threads were re-seeded. That record
stays in `history/` forever, even after the tarball is garbage-collected.

`.context_ledger/history/` and `.context_ledger/archive/` are **never read at
session start**. The next office opens from empty skeletons: nothing carries
over implicitly — anything that still matters is re-seeded into the new
office's files explicitly at close, and recorded in the permanent record.
This is what bounds session history: `memory/office/` only ever holds the
live office. See `ledger-history status`.

## Core Principle: Session Data Is Disposable

> **Permanent context must never depend exclusively on an individual
> session.** If Session 47 discovers an architectural decision worth
> keeping, that decision gets promoted out of the notes into its proper
> file (the office's `plans/decisions.md`, `tasks/backlog.md` for
> actionable work or `tasks/parking-lot.md` for a finding/question that
> isn't work yet, `inefficiencies/log.md`, `flaws/log.md` — or, for facts that must
> outlive this office entirely, the durable memory at the `memory/`
> root: `user/preferences.md`, `system/`, `overrides/rules.md`).
> Deleting Session 47's notes afterwards cannot damage the project's
> institutional knowledge — the facts were promoted first.

This gives a clean lifecycle:

```
New information
      ↓
Session notes
      ↓
Session summary (SUMMARY.md)
      ↓
Is it durable?
   ↙       ↘
 YES       NO
  ↓         ↓
Promote    Session
to its     only
file
  ↓
Survives session deletion
```

## Directory layout

```text
sessions/
├── README.md                      # this file
├── SUMMARY.md                     # compressed history — entries are removable
└── YYYY-MM-DD-N/                  # one directory per session with detail (optional)
    └── notes.md                   # append-only while active; deletable after promotion
```

Sessions directories are **optional** — a trivial session (typo fix,
one-line config change) that produces nothing worth keeping beyond its
summary line creates no directory here. `SUMMARY.md` always gets an
entry for every session, even trivial ones.

## Promotion Rule

At session end, before closing:

> **Does anything in these notes need to survive beyond this session?**

- **NO** — the notes stay here. A future agent can retrieve them
  selectively if the detail is needed.
- **YES** — distill the durable facts and promote them to their proper
  file (an architectural insight → `plans/decisions.md`, a discovered
  constraint → `inefficiencies/log.md`, a new backlog item →
  `tasks/backlog.md`, a user preference → the memory root's
  `user/preferences.md`, a protocol friction → `flaws/log.md`). After
  promotion, the directory may be deleted if its raw history is no
  longer useful.

**The litmus test:** *"Would this fact still matter after the session
closes, to an agent that never reads these notes?"* If yes, it does not
belong only here — promote it.

## Cleanup & Garbage Collection

- **Session directories** can be deleted when no longer useful. The
  permanent record in `agents/sessions.md` proves the session happened;
  promoted facts live in their proper files.
- **SUMMARY.md entries** can be removed for older sessions — compress
  the key facts into the durable logs first. Never let `SUMMARY.md`
  become another giant history file. A removed summary line MUST have a
  corresponding permanent entry in `agents/sessions.md`.
- **Keep all recent entries** (~last 10 sessions) in `SUMMARY.md` for
  continuity; prune selectively beyond that.
- **Never delete** the permanent `agents/sessions.md` entry or promoted
  durable knowledge.
- **At office close nothing here is deleted at all** — the whole office
  (this directory included) is frozen verbatim into `history/`, and the
  open threads are re-seeded into the new office from the permanent
  record.

<!-- The templates for SUMMARY.md and notes.md live in this directory.
In a running project, copy the template comments from
.context_ledger/core/templates/memory/office/sessions/. -->
