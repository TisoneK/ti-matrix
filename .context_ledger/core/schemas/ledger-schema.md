# The `.context_ledger/` Schema — Single Source of Truth

This file defines every file in a project's `.context_ledger/` directory: where
it lives, who owns it, how it may be written, and which *scope* its facts
belong to. When any other document (a README, an edition, a template
comment) disagrees with this schema, **this schema wins** — and the
disagreement is a flaw to log.

A machine-readable mirror lives beside this file as
`ledger.schema.json`. The markdown is authoritative; the JSON is
generated from it by hand and must be updated in the same commit as any
schema change.

---

## The two zones

```text
{project}/
├── AGENTS.md              # generated digest for agent discovery (see Translation layer)
├── CLAUDE.md              # pointer so Claude Code (auto-loads CLAUDE.md) reaches the protocol
└── .context_ledger/
    ├── README.md          # zone map — copied from core/templates at bootstrap/update
    ├── kickoff.md         # front door — generated at bootstrap, project-owned
    ├── .gitattributes     # LF policy for core + memory (Windows CRLF guard)
    ├── core/              # ZONE 1 — package-owned, READ-ONLY, version-stamped
    ├── memory/            # ZONE 2 — project-owned, writable, never synced; holds the LIVE office + durable files
    ├── history/           # closed offices (frozen verbatim) + permanent accomplishments records — NOT read at session start
    └── archive/           # cold storage of closed offices (zipped) — NOT read at session start
```

`history/` and `archive/` hold closed offices produced by `ledger-history`
(see **Office lifecycle** below). They are never in the session-start
reading order — only the live office in `memory/office/` is.

| Zone | Owner | Agents may write? | How it changes |
|---|---|---|---|
| `core/` | The protocol package | **Never.** Not one byte. | Only via `ledger-sync update` (whole-tree, version-stamped) |
| `memory/` | The project | Yes — per each file's write mode below | Normal session work, committed with the project |

The zone rule is the entire sync model: **core is replaced as a unit,
memory is never touched by sync.** There is no per-file structural/data
classification anymore (the old `SYNC.md` basename rule is retired). If
you are editing a path that starts with `.context_ledger/core/`, stop — you are
either syncing (use `ledger-sync`) or making a protocol change, which
belongs in the package repo, not in a project.

Two root files sit outside both zones:

- **`.context_ledger/README.md`** — the zone map. Package-owned *content*
  (refreshed from `core/templates/ledger-README.md` on core updates)
  but deliberately kept at the root so a fresh agent's first `ls` +
  `cat` explains the layout.
- **`.context_ledger/kickoff.md`** — the front door. Project-owned **data**:
  generated once at bootstrap from `core/templates/kickoff.md`, its
  facts kept current by sessions. Core updates never overwrite it; if
  its template changes materially (see `core/CHANGELOG.md`), the next
  session **regenerates** it from the new template and refills the
  facts from memory.

---

## Zone 1 — `core/` (read-only reference)

```text
core/
├── VERSION              # semver of this core tree, e.g. 0.2.0
├── CHANGELOG.md         # one entry per release + migration notes
├── MANIFEST.sha256      # checksums of every core file — integrity check
├── bin/
│   ├── ledger-sync     # POSIX-sh: status / verify / update / migrate / rollback / bootstrap
│   ├── ledger-sync.ps1   # PowerShell port (Windows): status / verify / update / rollback / lock
│   ├── ledger-collab       # POSIX-sh: atomic collaboration events + status + check
│   ├── ledger-collab.ps1   # PowerShell port (Windows): emit + status + check
│   ├── ledger-collab-check # POSIX integration-readiness validator
│   ├── ledger-collab-check.ps1 # PowerShell integration-readiness validator
│   ├── ledger-gates        # POSIX lifecycle gates + checkpoint
│   ├── ledger-gates.ps1    # PowerShell lifecycle gates + checkpoint
│   ├── ledger-mem          # POSIX: check (registry dup keys) + lint (.context_ledger leak) + prune (log compaction — report or --apply)
│   ├── ledger-mem.ps1      # PowerShell port: same hygiene checks
│   ├── ledger-history      # POSIX: office lifecycle — freeze the live office verbatim,
│   │                        #   number it at close, rotate memory/office→history→archive→gc
│   ├── ledger-history.ps1  # PowerShell port: office rotation
│   ├── ledger-state        # POSIX: regenerates memory/office/STATE.md, the session digest
│   ├── ledger-state.ps1    # PowerShell port: same digest generation
│   └── context-*.cmd        # cmd.exe launchers, one per .ps1 port: each
│                            #   runs it with -ExecutionPolicy Bypass -- no
│                            #   Windows Set-ExecutionPolicy setup needed
├── rules/
│   ├── ai-engineering-protocol-local.md   # LOCAL agents' edition — always-relevant core + a Playbooks index
│   ├── ai-engineering-protocol.md         # CLOUD/SANDBOX agents' edition — same shape
│   └── playbooks/        # task-shaped guidance, loaded only per kickoff.md's Phase 4 table:
│       ├── code-review.md, functional-testing.md, ux-review.md,
│       │   performance-review.md, security-review.md
│       │   (Common Pitfalls stays inline in each edition -- no pitfalls.md here)
├── roles/               # mission overlays: reviewer, security-auditor, docs-agent, feature-engineer
├── schemas/
│   ├── ledger-schema.md         # this file
│   ├── ledger.schema.json       # machine-readable mirror
│   └── collab-event.schema.json # collaboration event document (v1)
└── templates/
    ├── AGENTS.md            # root discovery digest (translation layer)
    ├── ledger-README.md    # becomes .context_ledger/README.md
    ├── kickoff.md           # becomes .context_ledger/kickoff.md (filled at bootstrap)
    └── memory/              # the memory/ stub tree copied at bootstrap
```

Integrity: `sh .context_ledger/core/bin/ledger-sync verify` checks every core
file against `MANIFEST.sha256` (on Windows:
`.context_ledger/core/bin/ledger-sync.cmd verify` — the launcher shares
the same manifest). A failed verify means core was
hand-edited or corrupted — restore it (`ledger-sync rollback` or
`git checkout` of the last good commit) and log a flaw. Never "fix"
core in place inside a project.

---

## Zone 2 — `memory/` (the project's living memory)

Memory has two layers. The **live office** — `memory/office/` — holds
everything session-produced: the team roster, the session registry, session
notes and summaries, tasks, plans, flaw and inefficiency logs, reviews.
Only one office is ever live, so its paths are stable; when it fills up it
is frozen **verbatim** into `history/` and the next office opens from empty
skeletons (see **Office lifecycle** below). The **durable files** at the
memory root — `workflows/`, `collaboration/`, `system/`, `user/`,
`overrides/`, `core.lock`, `secrets/` — orient a session (standing rules,
tool config, machine/model registries, the human's facts, the coordination
trail) and never rotate.

File inventory, write modes, and scopes. **Write modes:**

- **append-only** — entries are only added at the bottom; corrections
  are appended, never edited in. Sanctioned exceptions, all of them
  **compaction** (see "Append-only logs: compaction, not hoarding"
  below): byte-identical duplicate entries may be removed, leaving a
  one-line note in place; explicitly closed entries (`RESOLVED` /
  `superseded` / fixed) move **verbatim** into the log's companion
  `archive.md`; and 3+ entries describing the same recurring thing roll
  up into one `Recurring` entry with the instances moved verbatim into
  the archive. Every moved line survives unchanged in the archive and in
  git history — compaction relocates, it never rewrites.
- **live queue** — open, **actionable** work only, capped (default ~20
  rows). New items are added as rows in their priority table (High /
  Medium / Low — see "The backlog" below); a row is deleted when its
  item is finished or no longer relevant. Never delete a row whose item
  is still open (git history keeps every removed row, so nothing is
  lost). The only live-queue file is `office/tasks/backlog.md`;
  completion records live in `office/agents/sessions.md` and the
  commits, not in the backlog. Items that are *not* actionable —
  findings, open questions, deferred or someday ideas — are not queue
  rows; they live in `office/tasks/parking-lot.md` (a knowledge base,
  not a queue). `ledger-mem check` warns when the backlog passes its cap;
  `ledger-mem closeout` still sweeps checked-off `- [x]` tombstones from
  legacy checkbox-format backlogs.
- **overwrite** — current-state only; replace the content, history
  lives in the append-only logs.
- **update-in-place** — structured records with one entry per key,
  updated where they stand (a row, a block, a bullet); never wholesale
  replaced. **This is the opposite of append-only: you correct an entry by
  editing it, not by appending a second one.** The prior value survives in
  git history, so editing loses nothing. Appending a duplicate for a key
  that already exists is the failure mode (two rows, conflicting counts);
  `ledger-mem check` flags it. Keys: `ai-models.md` = (Agent, Model),
  `environments.md` = the "Identify by:" line.
- **generated** — created from a `core/templates/` file at bootstrap,
  then maintained as data (facts updated in place; regenerated only
  when the template materially changes).
- **local-only** — never tracked by git, never travels.

**The live office** (`memory/office/…`) — everything session-produced, frozen verbatim at close:

| Path (under `.context_ledger/memory/office/`) | Mode | Scope | Holds |
|---|---|---|---|
| `STATE.md` | generated | project | **Read this first.** A single at-a-glance digest — standing params, core version/drift, the roster condensed to one line per person, the current task, the backlog's High-priority rows, and for each durable log just its entry count + last-added date (not its content). Regenerated by `ledger-state generate` at check-in and at exit; never hand-edited. It replaces opening the individual files below for the common case — each of its lines points back at the real file for when a task actually needs more than the summary |
| `agents/sessions.md` | append-only (current office) | project | One entry per session: agent, model, platform, task, commits, outcome. Bounded by the office itself: the door-triggered close (see Office lifecycle) keeps it at `office_size` entries or fewer |
| `agents/roster.md` | update-in-place (current office) | project | Team roster — the "who's in the office *now*" board. Every session (solo included) adds its row at check-in — at the entrance, before the deep read, not after analysis — and pushes it; the push claims the codename (the earlier commit keeps a colliding number; the later worker fixes their own row to the next free codename). Columns: Name; codename `S<NNN>`; model; Doing (what you're on); **Status** — one short word, `Working` at check-in, edited in place to `Done` or `Blocked` as the work moves; **Status detail** — the one line the next worker needs (for `Working`: the stage or step reached; for `Done`: the outcome and extent, "Shipped: …"; for `Blocked`: what you're waiting on and from whom). Clock out (remove the row) when actually leaving — a finished session that stays live shows `Done` + its shipped outcome. Who was on duty *when* lives in `agents/sessions.md` + this file's git history. Name and codename each unique in the office; `ledger-mem check` enforces that and warns on an empty Status cell. Identity is *claimed* at check-in (fresh name + codename you pick), never *inferred* from a model/harness-string match — model strings are shared across sessions, so duplicate model values are normal. Never reset or trimmed: the whole office is frozen verbatim at close |
| `tasks/current.md` | overwrite | project | The one task in progress — a lock only in single-agent mode |
| `tasks/backlog.md` | live queue (priority-grouped tables; add/delete rows; capped ~20) | project | Actionable work only — one row per item in its priority table (High/Medium/Low, ID + Summary); a finished item's row is deleted, its completion record is the session entry + commit; past the cap, prune the lowest-value row first. Non-actionable items go to `parking-lot.md`, not here. Office-scoped: at close, only items with an active owner or a clear next step are re-seeded into the next office |
| `tasks/parking-lot.md` | live queue (grouped by kind; add/delete rows; uncapped) | project | The knowledge base, not a queue — research findings, open/advisory questions, deferred work, someday ideas, grouped by kind with stable `P-` IDs. No cap, no priority, no urgency. An item becomes a `backlog.md` row only when it turns actionable (promote: cut here, add there); at close it is not re-seeded wholesale — promote what's now work, record the rest in the permanent record |
| `plans/decisions.md` | append-only (compactable) | project | ADR-style decisions — respected, not relitigated. Decisions still in force are re-seeded into the next office and recorded in the office's permanent record. Superseded ADRs move verbatim to `plans/archive.md` |
| `flaws/log.md` | append-only (compactable) | project→package | Friction with the protocol/`.context_ledger/` system itself; flows upstream. A clean session appends nothing; closed entries move verbatim to `flaws/archive.md`; 3+ entries on the same recurring trap roll up into one `Recurring` entry |
| `flaws/README.md` | generated | project | The flaws-vs-inefficiencies split rule (pointer to this schema) |
| `inefficiencies/log.md` | append-only (compactable) | project | Friction with the project's code, env, deps — real friction only (a clean session appends nothing). Closed entries move verbatim to `inefficiencies/archive.md`; 3+ entries on the same recurring thing roll up into one `Recurring` entry |
| `reviews/YYYY-MM-DD-*.md` | new file per session | project | Session reports (deliverables — commit as `docs(review):`) |
| `reviews/README.md` | generated | project | Naming + report structure (pointer to this schema) |
| `sessions/README.md` | generated | project | Session-scoped memory rules, disposable principle, promotion rule |
| `sessions/SUMMARY.md` | update-in-place (entries are removable) | project | Compressed session history — one line per session, prunable. The permanent record is `agents/sessions.md` |
| `sessions/YYYY-MM-DD-N/notes.md` | append-only while active; deletable after promotion | project | Per-session detailed notes — research, exploration, dead ends. Disposable; durable facts must be promoted first |

**Durable files** (at the `memory/` root) — orient a session, never rotate:

| Path (under `.context_ledger/memory/`) | Mode | Scope | Holds |
|---|---|---|---|
| `collaboration/README.md` | generated | project | Peer collaboration rules and event contract |
| `collaboration/events/<event-id>.json` | immutable new file | project | Coordination events — notes (informal), claims, proposals, assessments, agreements, corrections, handoffs, releases. JSON documents validated by `core/schemas/collab-event.schema.json`. Every session writes the light path (claim → release), solo included; solo `session` is the roster codename, `issue` a task slug. Legacy `<event-id>.md` frontmatter files (pre-0.22.0) stay readable, never rewritten |
| `workflows/active.md` | overwrite | project (see scoping!) | Standing session parameters + core version in force |
| `workflows/gates.conf` | update-in-place | project | Explicit lifecycle commands and hybrid discovery mode |
| `workflows/history.conf` | update-in-place | project | Office rotation knobs: `office_size`, `history_keep`, `archive_keep` |
| `system/environments.md` | update-in-place | **machine** | One block per machine/sandbox, keyed by an "Identify by" line |
| `system/ai-models.md` | update-in-place | **agent** | Registry + evidence-based observations per agent/model |
| `user/identity.md` | update-in-place | user | Who the user is |
| `user/preferences.md` | update-in-place | user | Standing preferences, each bullet with provenance |
| `overrides/rules.md` | update-in-place | project | Project-local protocol adjustments (see Overrides) |
| `core.lock` | overwrite (by `ledger-sync`) | project | Last-known-good core version + when it was verified |
| `secrets/<slug>` | local-only | machine | One secret per file; line 1 = value. Self-gitignored |
| `secrets/README.md`, `secrets/.gitignore` | generated | project | The secrets hard rules; the self-ignore |

Entry formats: every writable file carries its entry template in an HTML
comment at the top (seeded from `core/templates/memory/`). **Read the
template before writing; never invent formats.** If a file's in-repo
template comment and this schema's mode column disagree, this schema
wins.

### The backlog: a capped work queue

`office/tasks/backlog.md` is a **queue of actionable work, not a
knowledge base**. The test for a row is: *can an agent start on this and
finish it?* If not — it's a finding, an open question, an advisory
"should we…?", a deferred or someday idea — it belongs in
`office/tasks/parking-lot.md` (next section), not here. The failure mode
this rule prevents is the well-documented backlog that is an unworkable
queue: rows accumulate research narrative and status qualifiers, nothing
is ever deleted because deleting feels like losing the record, and the
file becomes a knowledge base pretending to be a to-do list.

The file is arranged exactly like this:

    ## Open Items

    ### High Priority

    | ID | Summary |
    |----|---------|
    | B-2026-08-15-12 | Three-tier classification: tier decides whether the feature boots |

    ### Medium Priority

    | ID | Summary |
    |----|---------|
    | B-2026-08-17-9 | OUTPUT tokens: cap file_read injection + uniform choke-point cap |

    ### Low Priority

    | ID | Summary |
    |----|---------|
    | B-2026-07-31-10 | Non-coding capability roadmap |

- **Actionable rows only.** One row per item, in its priority table.
  The Summary says what to *do*, in a line — not everything known about
  it. Deep context lives in the linked issue, PR, ADR, or parking-lot
  finding the row points at; packing it into the cell is the document
  mindset creeping back in. Keep status qualifiers short ("partial",
  "blocked on X"); a row that needs a paragraph of justification to
  belong is usually a parking-lot item.
- **ID every row:** `B-<added YYYY-MM-DD>-<n>`, n = that date's next
  sequence in the file. Stable IDs are what make cross-references and
  workstream clustering possible. Legacy checkbox-format items keep
  their line until next touched; re-row them with an ID then.
- **Finished = delete the row. Stale = delete the row.** The backlog
  holds open work only; the completion record is the session entry +
  commit. There are no checkboxes in the file, so there is nothing to
  "check off" — a row that remains is open work. When an item stops
  mattering, delete it; if it still carries information, move it to the
  parking lot first. Git history keeps every removed row, so deleting
  loses nothing. (`ledger-mem closeout` still sweeps checked-off
  `- [x]` tombstones from pre-1.0.5 checkbox-format backlogs.)
- **The queue is capped (default ~20 rows).** The cap is a working-set
  limit, not a quota to fill: `backlog_cap` in
  `memory/workflows/history.conf` (default 20), and `ledger-mem check`
  warns past it. When you'd add a row that pushes the file past the
  cap, prune one first: the lowest-value open row goes to the parking
  lot (deferred, still valuable) or is deleted (no longer relevant).
  Never prune a row you can't justify dropping, and never let the cap
  become an excuse to hoard — a queue you can hold in your head beats a
  comprehensive one you can't.
- **Priority is the table an item sits in (High / Medium / Low), and it
  is dynamic.** Only the top of the queue really matters — the handful
  of High rows (roughly the top 3–5) are the work a session starts on;
  the rest is context. A row that has sat in Low across many sessions is
  a parking-lot candidate, not a permanent resident. When unsure between
  two tables, pick the lower one; promoting later is cheap, and a
  backlog where everything is High says nothing.
- **Workstream view — derived, never stored.** When the backlog is
  large (near or past the cap) or the user asks for a planning pass,
  render the workstreams: numbered clusters of items attacking the same
  problem ("Code Block / Code Display (3 items → 1 effort)"), each
  listing its item IDs, a one-line rationale, dedupe/partial notes
  ("treat as the same effort; dedupe when picked up"), and an ordering
  suggestion when one exists ("ship measurement first — you can't
  optimize what you can't measure"). Close with a summary table:

  | Workstream | Items | Estimated Effort |
  |------------|-------|------------------|
  | Token efficiency | 6 | Large |

  …plus a leverage note: which workstreams touch the most surface
  (e.g., "affects every agent turn") and what is currently blocking
  (e.g., the one item blocking the exit gate). Count the mapping
  ("70 items → ~12 workstreams"). Workstreams are an analysis of the
  rows, never a second copy of them — an item has one home (its
  priority-table row), so finishing it stays a single delete.

### The parking lot: the knowledge base, not a queue

`office/tasks/parking-lot.md` is where everything the backlog must stay
clean of actually goes: research findings, open and advisory questions,
consciously deferred work, and loose someday ideas. It exists so the
backlog can be a queue. The distinction is one question — *is this
actionable now?* — and the two files are the two answers.

- **Grouped by kind, not by priority.** Four sections — Findings, Open
  questions, Deferred work, Someday — because these items are not
  competing for the top of a queue, so ranking them is meaningless.
- **Uncapped, no urgency.** Nothing here blocks a gate or a session. The
  whole point is that it is out of the working set, so it can grow
  without hurting anything; the backlog's cap is what keeps *this* file
  honest by giving overflow a home instead of a permanent queue row.
- **ID every row:** `P-<added YYYY-MM-DD>-<n>`, n = that date's next
  sequence in the file — the same shape as backlog IDs, a separate
  namespace.
- **Promote, don't duplicate.** When a parked item becomes actionable —
  it now has a clear next step and someone to take it — it becomes a
  backlog row: cut it here, add a one-line actionable row there (a fresh
  `B-` ID, pointing back at the `P-` ID for context if useful). An item
  that turns out wrong or moot is simply deleted; history remembers it.
- **Not re-seeded wholesale at close.** The parking lot is office-scoped
  like the backlog, but the closing session does not copy it forward.
  It promotes what is now actionable into the new backlog and records
  the rest in the permanent record (`history/office-<NNN>.md`, "Open
  threads"). A cold idea earns its way into the next office by becoming
  work, not by being carried.

### Append-only logs: compaction, not hoarding

`agents/sessions.md`, `plans/decisions.md`, `flaws/log.md`, and
`inefficiencies/log.md` are append-only — corrections are appended,
never edited in — but append-only is not a license to hoard. Four
mechanisms keep every one of them small enough that the session-start
read stays cheap:

- **Clean sessions append nothing.** A session that hit no friction adds
  no block to `flaws/log.md` or `inefficiencies/log.md` — "none this
  session" entries are noise, not history. The session's honesty lives
  in its `agents/sessions.md` entry; only real friction earns a block.
- **Closed entries move verbatim to the archive.** Once an entry is
  explicitly marked `RESOLVED` / `superseded` / fixed, it is cold
  history: cut it unchanged into the log's companion archive
  (`flaws/archive.md`, `inefficiencies/archive.md`, `plans/archive.md`).
  Startup reads only the active log; the archive stays in git,
  grep-able. `ledger-mem prune --apply` performs this move mechanically
  (`ledger-mem prune`, no flag, only reports it — the manual cut-and-paste
  is still there for anyone who prefers it) — and only an explicit closed
  marker makes an entry eligible either way; age alone never does. The
  marker is the entry's **own** `**Status:**` line carrying one of those
  words — prose elsewhere in the entry is never the marker (an accepted
  ADR *describing* the compaction rule mentions "superseded" without
  being closed), and a file's `<!-- -->` template comment is never a
  candidate (its placeholder Status lines carry the words literally).
  Both `prune` and `prune --apply` follow exactly this scoping. An
  unresolved flaw stays in the active log: it is a live trap the next
  agent must see.
- **Repeats roll up.** When a log holds 3+ entries describing the same
  recurring thing (same failing tool, same root cause, same protocol
  trap), append ONE consolidated `Recurring` entry — the pattern, how
  many times, the current workaround — and move the individual entries
  verbatim into the archive. The live log keeps the pattern, not the
  repeats. This move stays manual even under `--apply`: composing the
  one consolidated entry needs an agent's judgment, not a mechanical cut.
- **The office bounds the session registry.** `agents/sessions.md` needs
  none of the above within a healthy office: the door-triggered close
  (see Office lifecycle) freezes it at `office_size` entries or fewer,
  and `sessions/SUMMARY.md` prunes at ~40 lines as before.
- **A cap nudges before a log grows unbounded.** `flaws_cap` and
  `inefficiencies_cap` in `workflows/history.conf` (default 15 each) are
  hygiene nudges, not hard limits — `ledger-mem check` warns past them,
  pointing at `prune`/`prune --apply`; an unresolved entry is never
  pruned regardless of count. `ledger-gates run exit` also calls
  `ledger-mem prune` (report mode) so the nudge surfaces at the natural
  moment, not only when someone thinks to run it by hand.

`ledger-mem prune` reports each log's size, the archive-eligible
entries (`--list` names them), and roll-up candidates. `ledger-mem prune
--apply` performs the archive-eligible moves (only those — never the
roll-up) mechanically, creating the companion `archive.md` with a header
if it doesn't exist yet; every moved line survives unchanged in the
archive and in git history. Compaction relocates; it never rewrites or
deletes context.

### Reading order (session start)

The check-in short-circuits this order: read `agents/roster.md` and the
last `agents/sessions.md` entry (the two files signing needs), add your
row, push, run `ledger-state generate` — then continue from the top. The
deep read follows the check-in; it never precedes it.

`.context_ledger/README.md` → `kickoff.md` → **`memory/office/STATE.md`**
— one digest standing in for the eight files it summarizes (standing
params, roster, current task, backlog High rows, and flaws/inefficiencies/
decisions entry counts). Open the individual file behind a `STATE.md` line
only when your task actually needs more than the summary gives — a live
peer row you don't recognize → `agents/roster.md` in full; a task that
touches backlog work → `tasks/backlog.md`; a task shaped by protocol
friction, project friction, or a standing decision → the matching log.
Always still read in full, regardless of `STATE.md`: `memory/overrides/rules.md`
(project-local rule changes) → `memory/workflows/gates.conf` (gate
commands) → `memory/collaboration/README.md` and active event files when
collaboration is enabled → `memory/system/` → `memory/user/` → note what's
in `memory/secrets/` (never print values). `memory/office/sessions/SUMMARY.md`
(skim last 10 entries) is worth a look for continuity beyond what
`STATE.md`'s current-task line gives. The `history/` and `archive/` zones
are never in this order — deliberate lookback only.

This is also how the protocol editions in `core/rules/` scale to the task
instead of being read in full every session — see `kickoff.md` Phase 4's
routing table: the always-relevant core sections (Binding Rules, Gate
Protocol, Git Workflow, Quality Gates) are a fixed, small read; the
task-shaped playbooks (`core/rules/playbooks/*`) are loaded only when the
task's shape calls for them.


---

## Office lifecycle

Session history lives in discrete **offices** so it never grows unbounded
and a new office is never misdirected by a previous one's leftovers. The
live office is the unnumbered directory `memory/office/` — the team roster
(`agents/roster.md`), the session registry (`agents/sessions.md`), the
session notes and summaries (`sessions/`), tasks (`tasks/`), plans
(`plans/`), the flaw and inefficiency logs (`flaws/`, `inefficiencies/`),
and reviews (`reviews/`). Only one office is ever live, so its paths are
stable. **Durable files never rotate:** `user/`, `system/`,
`workflows/`, `overrides/`, `collaboration/` (including the event trail),
`core.lock`, and `secrets/` stay at the memory root across offices.

The **roster** is the team board for the current office: **every session
(solo included) checks in** — picks a human name, adds a row (Name,
codename `S<NNN>`, model, what they're doing, a `Working`/`Done`/`Blocked`
**Status**, and a one-line **Status detail**: how far the work has got,
what shipped, or what's blocking), and pushes it at the door,
before the deep read and any product work. The Status cells are the
at-a-glance coordination signal — each worker edits their own row's
cells in place as the work moves, so the next live worker sees what is
finished, what is in flight at which stage, and what is blocked without
asking. Clocking out removes the row in the closing memory commit, so the board shows who is in the office *now*. Who was on
duty *when* is the duty log's job: append-only `agents/sessions.md`
entries plus the roster file's own git history (check-in commit opens a
shift, clock-out closes it). Each agent presents itself by that name in
events and to the supervisor, and
name + codename are each unique in the office. `ledger-mem check` flags a
duplicate and warns when a session entry was logged while a row still
claimed the office (a forgotten clock-out). The roster is never reset or
trimmed — the whole office is frozen with it intact at close.

An office moves through three zones, and only the live one is read at session
start:

| Zone | Holds | Read at start? | Format |
|---|---|---|---|
| `memory/office/` | the current live office | yes | working files |
| `history/` | permanent records (all offices) + recently closed offices | no | `office-<NNN>.md` (permanent) + `office-<NNN>/` (frozen, verbatim) |
| `archive/` | older closed offices | no | `office-<NNN>.tar.gz` (cold) |

`ledger-history` rotates them: `close` freezes the live office directory
**verbatim** — no condensing, no resetting, the roster keeps every shift —
into `history/office-<NNN>/`, numbering it **at that moment** (the next
number is derived from the records; there is no state file), writes the
**permanent accomplishments record** `history/office-<NNN>.md` (what the
office achieved, decisions still in force, open threads re-seeded), and
opens a fresh empty office from templates (default `office_size` = 20
sessions, or a milestone). When `history/` holds more than `history_keep`
(default 3) frozen directories, the oldest is zipped into `archive/` and
removed — its record stays in `history/` forever. `gc` deletes `archive/`
tarballs over `archive_keep` (default 12), oldest-first, git-recoverable.
Config lives in `memory/workflows/history.conf`.

**No implicit carryover:** a new office starts from empty skeletons.
Anything from a closing office that still matters is re-seeded into the
new office's files explicitly by the closing session, and recorded in the
permanent record — the same promotion rule as session notes, applied at
the office boundary. This is what lets a closed office be archived and
eventually deleted without losing institutional knowledge: the permanent
record plus the durable files remember what matters.

**Re-seed work, not knowledge.** The backlog re-seeds **only items with
an active owner or a clear next step** — the queue's whole purpose is
that a fresh session can act on what's in it, and a row that can't be
acted on is a knowledge-base entry wearing a queue's clothes. Findings,
open questions, and deferred or someday items are not re-seeded at all:
they are recorded in the permanent record (and promoted to the new
backlog later, when they become actionable). Decisions and open log
threads follow the same test — carry what the next office must *do* or
*respect*, not what it might *want to remember*.

**Re-seed content, not record numbers.** A re-seeded backlog row,
decision, or log entry must stand alone: it never cites the closed
office's session numbers or codenames ("as fixed in S014", "see Session
12") — those point into the frozen copy, which the new office never
reads. Describe the work and its state in plain words; the permanent
record (`history/office-<NNN>.md`, "Open threads") is the bridge between
the two offices. The new office's own numbering starts clean — codenames
from `S001`, session entries from `Session 1`, ADRs and backlog IDs from
1.

**The door trigger — a full office closes at check-in.** Closing at
`office_size` is not optional tidy-up the next session might get to:
the worker whose check-in read finds `agents/sessions.md` past
`office_size` (default 20 — the codename they would claim is past S020)
runs the close right after their check-in push, before the deep read and
any analysis, re-seeds the open threads, and signs the fresh office's
board. `ledger-history status` and `ledger-gates checkpoint` warn when a
close is due, but the warning is a backstop — the trigger fires at the
door because an over-full registry is exactly how a fresh session gets
misdirected by stale numbers.

---

## Peer collaboration

Collaboration is opt-in for a shared `session` + `issue` identity. Peers
are one team with one goal, not rivals. Each agent uses an isolated product
git worktree/branch; product edits never happen in the same checkout. Live
coordination is published on the shared `collab/<session-id>/coordination`
ref as immutable, one-file-per-event records under
`memory/collaboration/events/`, not in a shared append-only file. This
makes simultaneous notes, claims, proposals, assessments, agreements,
corrections, handoffs, and releases mergeable.

The everyday event is a **note** — the informal office channel (a heads-up,
a hand-off in plain words, a peer review). A note needs only a body, never
gates the integration check, and never has to be "resolved"; optional
`--to` addresses a peer and `--re` points at an event, path, or commit. The
common lifecycle is a note plus `claim → release`. The formal
`proposal → assessment → agreement` ceremony is the escalation for a
genuine conflict (same paths, incompatible changes) only.

A claim makes scope visible but is not a lock. A `release`/`handoff` closes
a claim when it cites the claim's event ID **or** shares its session+issue
and overlaps its paths — so a release citing only its commit SHA still
closes the claim. Overlapping *active* claims require peers to compare the
two changes and agree who takes it, via an explicit agreement selecting the
best-supported option and one implementation owner. A correction names the
evidence, likely cause, candidate repairs, and suggested owner; peers agree
on the repair and owner before it is applied. There is no timestamp or
agent-ID tie-breaker. If evidence remains tied, pause the conflicting work
and ask the user. Use `.context_ledger/core/bin/ledger-collab` (or the `.ps1` port
on Windows) to emit events and inspect status; run `ledger-collab check`
before integration. Event commits remain separate from product commits.

`office/tasks/current.md` remains the single-agent lock when collaboration is not
enabled — but "no collaboration declared" no longer means "alone": the
roster's live rows are the occupancy evidence. A live row you didn't
write means a peer is in the office — declare or join a shared
session/issue and coordinate before editing. In collaboration mode
`tasks/current.md` is not a lock and must not be used to
block a peer; use the collaboration event trail instead.

---

## Fact scoping — the contamination rules

`.context_ledger/` memory serves **every** agent that will ever work on the
project: local and cloud, strong and weak, on any machine. The single
biggest failure mode observed in the field is *scope contamination*:
one agent records a fact that is true only for its own type, machine,
or model — and the next agent of a different kind reads it as binding.
(A local agent on a cloud-bootstrapped repo starts doing PAT dances and
re-cloning; a cloud agent trusts a macOS-only command.)

Every fact you write into memory belongs to exactly one scope. Record
it so the scope is explicit:

| Scope | Definition | Where it lives | How it's keyed |
|---|---|---|---|
| **project** | True for this repo regardless of who works on it (repo URL, default branch, decisions, backlog) | most of `memory/` | nothing — unqualified facts are project facts |
| **agent-type** | True only for local OR only for cloud/sandbox agents (edition, credential flow, clone steps) | **never as a single value** — always recorded keyed "by agent type", naming both branches | explicit `local: … / cloud: …` |
| **machine** | True only on one machine/sandbox (paths, installed tools, verified commands) | `memory/system/environments.md` blocks | the block's "Identify by" line — apply a block only if it matches where you are |
| **agent/model** | True only for one agent or model (capabilities, blind spots) | `memory/system/ai-models.md` | the registry row |
| **user** | About the person (identity, preferences) | `memory/user/` | provenance markers |

Binding consequences:

1. **Edition choice is a function of your agent type at session start —
   never of memory.** `workflows/active.md` records the protocol "by
   agent type", naming BOTH editions. If you ever find a single edition
   recorded there, that's the *previous* agent's type leaking; follow
   your own type and fix the record.
2. **A machine-scoped block applies only where its "Identify by"
   matches.** Never run another environment's verified commands as if
   they were yours; add or update your own block.
3. **Credential flows are agent-type facts.** PAT steps exist only in
   the cloud edition; a local agent that finds PAT instructions in
   memory ignores them and logs a flaw.
4. **When writing, ask: "would this sentence be wrong for an agent of
   the other type, on another machine?"** If yes, key it to its scope
   or don't write it.

---

## Overrides — project-local protocol adjustments

`memory/overrides/rules.md` is the one sanctioned place a project bends
the protocol without forking core. Sessions read it right after loading
their edition; where an override and the edition conflict, **the
override wins** — with two exceptions that nothing can override:
secret-handling rules and the append-only guarantee.

Overrides are for standing, project-shaped deltas ("this repo squashes
to a release branch, not main", "reports go in docs/reports/ for
legacy reasons"). They are *not* a scratchpad for session instructions
(those die with the session) or user preferences (those go in
`user/preferences.md`). Each override carries provenance and a date,
like a preference. Core updates never touch this file — that's the
point: customizations survive every core version bump.

---

## Translation layer — how weaker agents consume this system

Not every agent reads a 900-line edition reliably. The system degrades
gracefully through three tiers, all generated from core — never
hand-maintained per project:

1. **`AGENTS.md` at the project root** (from `core/templates/AGENTS.md`,
   generated at bootstrap; optionally copied as `CLAUDE.md` and
   `.github/copilot-instructions.md` for tools that auto-load those
   paths). **Mostly a router, but not only one** — under 40 lines: what
   this repo uses, "read `.context_ledger/kickoff.md` and follow it,"
   and the one rule that can't be missed (never write under
   `.context_ledger/core/`). It does **not** restate the roster's
   format, gate commands, or collaboration mechanics — those live in
   exactly one place each (kickoff's phases, the edition, this schema).
   **It does restate one behavior directly: check in before reading
   further or analyzing anything.** This is the floor — the one file
   some sessions on this repo will ever read in full — and core 2.0.0
   learned the hard way that "go read kickoff.md" is not itself a
   substitute for stating the single highest-cost rule where the
   weakest reader will actually see it: a session that reads this file
   and stops, or reads it front-to-back before acting, still checks in
   before doing anything else.
2. **`.context_ledger/kickoff.md`** — the front door: numbered phases that
   route by agent type, check in, point at `memory/office/STATE.md` for
   orientation, and — the routing table that keeps this tier cheap for
   the common case — decide which parts of the edition a task's shape
   actually needs (see "Reading order" above).
3. **The edition in `core/rules/`** — Binding Rules, Gate Protocol, Git
   Workflow, Quality Gates, and a Playbooks index are always read (a
   deliberately small file); `core/rules/playbooks/*` (code review,
   functional testing, UX/UI review, performance review, security review,
   common pitfalls) are read only when kickoff's Phase 4 table says the
   task calls for them.

Each tier links down to the next; no tier contradicts another because
all three are rendered from the same core version. A weak agent
following only tier 1 does less, but nothing *wrong* — it cannot
clobber core (rule stated in tier 1), cannot miss the entry point, and
cannot pick the wrong edition (the kickoff routes by type).

---

## Sync, change detection, and fallback

- **Startup check:** the kickoff's entry steps run
  `sh .context_ledger/core/bin/ledger-sync status` — compares the vendored
  core's `VERSION` against the best reachable source (an explicit path,
  a sibling package clone, or the package remote). Unreachable source =
  skip and note; **never fail a session over sync.**
- **Safe auto-update:** same-MAJOR updates (`1.0.x → 1.0.y`, minor
  bumps included) may be applied without asking; a MAJOR bump requires
  the user (there may be migration steps in `CHANGELOG.md`). Updating
  core never rewrites durable memory — the one deliberate exception is
  the office-layout migration (a legacy flat layout is grouped into
  `memory/office/`), which runs once and only moves files.
- **core.lock:** after any successful `verify`, `ledger-sync` records
  the version + date in `memory/core.lock`. That is the
  **last-known-good** marker.
- **Fallback:** if a session cannot parse or trust the current core
  (failed verify, half-applied update), roll back to the locked
  version — `ledger-sync rollback` restores `core/` from the project's
  own git history — then log the incident in `memory/office/flaws/log.md` and
  continue on the restored version. The session proceeds; the flaw
  flows upstream.
