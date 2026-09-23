# Core Changelog

One entry per released core version, newest first. An agent syncing a
project's `.context_ledger/core/` from an older version reads every entry
between the two versions — migration notes live here.

Semver: breaking changes to the `.context_ledger/` spec or the memory layout
bump MAJOR; new features (roles, pitfalls, templates, schema fields)
bump MINOR; wording and fixes bump PATCH.

---

## 2.0.4 — 2026-09-23

**Windows sessions could not pass their exit gate at all.** 2.0.3 shipped
PowerShell ports that fail to parse on a stock Windows box, and
`ledger-sync verify` treats an unparseable port as a core integrity
failure (exit 3) — so every gate that calls it failed there. Reported from
a consumer project that hit it while migrating to 2.0.3.

- **`ledger-state.ps1` did not parse on any engine.** Its `Get-Field`
  built a regex as `"...\*\*$Label:\*\*..."`; the parser reads `$Label:`
  as a scope-qualified variable reference (`$env:`-style) and rejects the
  whole file — Windows PowerShell 5.1 and pwsh 7 alike. Now `${Label}`.
- **Non-ASCII bytes in a port are a latent 5.1 parse failure.** Windows
  PowerShell 5.1 decodes a BOM-less script with the *system codepage*,
  not UTF-8, so a literal em-dash (E2 80 94) arrives as U+201D — which
  the parser reads as a string terminator and fails the rest of the file,
  while pwsh 7 parses the very same bytes fine. That asymmetry is how a
  release ships broken: the authoring host had no PowerShell to try, and
  a pwsh-only host cannot reproduce the failure. All seven ports are now
  pure ASCII; text that needs a non-ASCII character builds it from its
  code point (`[char]0x2014`, `[char]0x2026`), so a port still emits
  exactly the bytes its sh twin emits. The rule sits at the top of every
  port and is enforced (below).
- **`parse_ports` now checks every engine on PATH, not just the first.**
  It ran the ps1 half through `powershell` when present, else `pwsh` — so
  on a Windows box carrying both, a port that only pwsh could parse passed
  verification and then failed at runtime, because the `.cmd` launchers
  deliberately target 5.1 (it ships with every Windows 10+ install). A
  port must now parse under *every* engine found; `verify` prints which
  engines and versions it used, so a failure is diagnosable at a glance.
- **An engine-free encoding guard, in both editions.** `verify` fails a
  `bin/*.ps1` carrying a non-ASCII byte, with the sh and ps1 editions
  agreeing on the verdict — so the release this bug came from would have
  been caught by `verify` on the authoring machine, whatever its OS.
- **A pre-existing divergence between the ports, fixed in passing.**
  `ledger-state.ps1` wrote a plain hyphen where the sh port writes an
  em-dash in five places — the Core block's drift note among them — so
  STATE.md differed by punctuation depending on which port generated it.
  Both ports now produce byte-identical STATE.md, and a test pins it.

Package tests: 63 green, four of them new — every engine on PATH parses
every port; the sh port's encoding guard fires on a non-ASCII byte; the
shipped ports are ASCII; sh and ps1 write the same STATE.md. Verified on
Windows under both engines (5.1.26100.9444 and 7.6.6): `ledger-sync
verify` exits 0 under each, and the `.cmd` launcher path (5.1) runs the
gates again.

---

## 2.0.3 — 2026-09-19

**A supervisor audit of the whole 2.0.0 token-optimization pass, not just
the one collision 2.0.2 fixed.** The check-in regression 2.0.2 patched
was a symptom of a broader pattern in 2.0.0: content that got moved or
condensed on the assumption that routing would reliably carry weak
agents to it, and in a couple of cases content that was cut with no
replacement at all. Four fixes, found by diffing 2.0.0/2.0.1/2.0.2
directly against the last v1 release (1.2.0) rather than trusting each
release's own account of itself:

- **A shipped broken reference.** `kickoff.md`'s Phase 4 routing table
  told a session that hit a snag to read `core/rules/playbooks/pitfalls.md`
  — a file that has never existed. Common Pitfalls stayed inline in each
  edition on purpose (2.0.0's own changelog says so), but the table was
  never corrected to match, and neither 2.0.1 nor 2.0.2 — both live-tested
  bug-fix releases — caught it. Fixed in `kickoff.md` (template + this
  repo's own copy) and in `ledger-schema.md`'s directory diagram, which
  listed the same phantom file.
- **Two v1 rules were deleted outright, not deduplicated.** "`.context_ledger/`
  reflects what was true when written — if it contradicts the codebase,
  the codebase wins" and "small and current beats big and stale — session
  entries run ~10 lines, not transcripts" existed in v1's edition `### Rules`
  list and had zero equivalent anywhere in 2.0.0 through 2.0.2 (confirmed by
  grep across the whole vendored core, not just the obvious spots). The
  second one isn't hypothetical: this office's own `sessions.md` entries
  for Sessions 11–14 are dense multi-paragraph blocks, not ~10-line
  summaries — the bloat the rule existed to prevent. Both restored as
  items 11–12 of what was "The Ten Binding Rules" in both editions
  (renamed to "The Binding Rules" since the count is no longer ten and
  hard-coding it was never load-bearing).
- **The weak-agent floor only got the one line that had already caused an
  incident.** 2.0.2 restored check-in to `AGENTS.md`/`CLAUDE.md` after it
  regressed into a real collision, but left ~8 other rules 2.0.0 cut from
  the same files exposed to the identical failure mode (a session that
  reads only the floor file and never reliably chains into `kickoff.md`).
  The most consequential of those — the door-triggered close at
  `office_size` sessions (a session could now read a full, stale board and
  never find out), no-secrets-in-tracked-files, the two-surface commit
  split, and "not done until pushed" — are now restated directly in both
  floor files, same treatment 2.0.2 gave check-in: short, load-bearing,
  not the full v1 ceremony.
- **Playbook extraction quietly changed a guarantee, not just a file
  layout.** The playbook content itself was verified byte-faithful to what
  it replaced — that part of 2.0.0 was clean. But v1's edition read the
  Code Review Checklist unconditionally, every session; 2.0.0's routing
  table made it conditional on the agent correctly self-classifying its
  own task as "a new feature or a substantial review," and its default row
  for an ordinary product-code change was "(nothing more)." Changed in
  `kickoff.md`'s table and both editions' own Playbooks index:
  `code-review.md` is back to unconditional for any product-code task,
  however small; the other four stay conditional on task shape.

No file moves, no memory-layout changes — everything above is a content
restoration or a reference fix inside files 2.0.0–2.0.2 already ship.

- **Migration:** `ledger-sync update` picks this up automatically. If a
  project customized `AGENTS.md`/`CLAUDE.md` since 2.0.0, this update
  overwrites them again (regenerated, never hand-patched) — move
  project-specific text into `memory/overrides/rules.md` first if it must
  survive.

---

## 2.0.2 — 2026-09-19

**A real collision, reported directly: sessions were fighting during
initialization because check-in-before-analysis stopped happening.**
Core 2.0.0's token-optimization pass reduced `AGENTS.md` from a 158-line
digest to a ~28-line pure router ("go read `kickoff.md` and follow it")
— and in doing so dropped the one restated rule that was there on
purpose: `AGENTS.md` is the **weak-agent floor**, the one file some
sessions on this repo will ever read in full, and it used to state
"check in before any analysis" directly rather than only routing to it.
Some agents evidently don't chain reliably into a multi-file, multi-phase
routing sequence — they read the floor, or read a whole file
front-to-back before acting on any of it, and by the time a check-in
happened it was too late to prevent a collision. This is the same
failure class core 1.0.6 fixed once already (two sessions launched
together both seeing an empty board); de-duplication treated all
repetition as pure waste, but some repetition was a deliberate safety
margin against exactly this.

- `AGENTS.md` and `CLAUDE.md` (templates + this repo's own copies) each
  gain back a short, standalone "check in — before reading anything
  else, including the rest of this file" directive, placed *before* the
  "go read `kickoff.md`" pointer rather than after. Still far shorter
  than pre-2.0.0 (~40 and ~20 lines vs. 158 and 32) — this restores the
  one line that mattered, not the whole restated ceremony.
- `kickoff.md`'s Phases intro gains an explicit instruction to execute
  each phase before reading the next, with a named recovery step: if you
  already read ahead to Phase 3 or later, stop and push Phase 2's
  check-in now, before reading further.
- `ledger-schema.md`'s "Translation layer" section corrected — it had
  described tier 1 as restating *nothing*, which was no longer accurate
  even before this fix's own change (mostly a router now, but not
  purely one, and deliberately so).
- New regression test (`tests/run-tests.sh`): asserts `AGENTS.md` and
  `CLAUDE.md` state check-in-before-analysis directly, so a future
  token-optimization pass can't silently strip this again without a
  test noticing. Flaw logged with the general lesson: before removing a
  restated rule as duplication, check whether the repetition was a
  documented safety margin, not an oversight.

Tests 27 → 29.

- **Migration:** `ledger-sync update` picks this up automatically — no
  file moves. If a project customized `AGENTS.md`/`CLAUDE.md` after the
  2.0.0 update, this update overwrites them again (they are regenerated,
  never hand-patched, per the 2.0.0 migration note) — move any
  project-specific text into `memory/overrides/rules.md` first if it
  must survive. **This update is urgent** for any project mid-fleet
  running with concurrent/multi-agent sessions: 2.0.0/2.0.1 carry the
  regression described above.

---

## 2.0.1 — 2026-09-18

**A live bootstrap test of 2.0.0 (fresh scratch project, not just the unit
fixtures) found two bugs in what it shipped.** `ledger-state generate`'s
`field()`/`Get-Field` helper had no `<!-- -->` comment-skipping — unlike
every other parser in this codebase — so a key mentioned only inside a
file's own template comment (never given a real line yet, as on a fresh
bootstrap) leaked the comment's placeholder text into `STATE.md` as if it
were live data. That surfaced a second, independent bug:
`workflows/active.md`'s template nests a second `<!-- -->` inside the
outer one (an aside on the Protocol field) — invalid comment syntax that
closes the outer block early — and the real skeleton below the comment
was simply missing a `- **Target:** —` line the comment documents but
never seeds. Both fixed: `field()`/`Get-Field` now skip `<!-- -->` blocks
(single-level, matching `log_digest`/`check_roster`/`prune`); the
template's nested aside is now a plain parenthetical, and the missing
`Target` placeholder line is added. Flaw logged with the general lesson —
`<!-- -->` never nests in this codebase's parsers.

- **Migration:** none required — `ledger-sync update` picks it up; no
  file moves, no format changes for already-filled `workflows/active.md`
  files (this only affected freshly bootstrapped, still-placeholder
  ones).

---

## 2.0.0 — 2026-09-18

**The protocol stops taxing product work to pay for its own bookkeeping.**
Measured at the top of this release: a plain local-agent kickoff read
`AGENTS.md` (158 lines) + `kickoff.md` (322) + ~9 small memory files
(~550 lines) + the full edition (1159–1228 lines) — **~2,760 lines of
protocol overhead before any host-repo work**, the same tax for a
one-line fix as for a big feature. Four coordinated changes, all
backward-compatible in *behavior* but a MAJOR bump because the reading
order and the entry-point file shapes both change:

- **`AGENTS.md` / `CLAUDE.md` become pure routers.** Both used to restate
  the check-in/roster/collab/gate/commit-prefix ceremony that
  `kickoff.md` also stated, which the edition stated a third time.
  `AGENTS.md`: 158 → 28 lines. `CLAUDE.md`: 32 → 14 lines. Their only job
  now: what this repo uses, the one rule that can't wait (never write
  under `.context_ledger/core/`), and a pointer to `kickoff.md`.
- **`kickoff.md` becomes six numbered Phases with an explicit,
  task-scaled routing table**, replacing "Entry Steps" that mixed
  pointers with restated ceremony prose. Phase 2 (check in) now also
  regenerates the new `STATE.md` digest; Phase 3 (orient) reads it
  instead of ~8 separate files; **Phase 4 replaces "read your edition in
  full" with a routing table** — read the edition's always-relevant core,
  then load only the playbook(s) your task's shape actually calls for.
- **`memory/office/STATE.md` — one generated digest**, standing in for
  `workflows/active.md` + `agents/roster.md` + `tasks/current.md` +
  `tasks/backlog.md`'s High rows + entry counts from `flaws/log.md` /
  `inefficiencies/log.md` / `plans/decisions.md`. New `ledger-state`
  (sh + ps1) generates it — never hand-edited, regenerated at check-in
  and at exit. Every line points back at its source file for when a task
  needs more than the summary.
- **Both editions split: playbooks extracted, the schema is the single
  source of truth again.** `core/rules/playbooks/` now holds
  `code-review.md`, `functional-testing.md`, `ux-review.md`,
  `performance-review.md`, `security-review.md` — loaded only per
  `kickoff.md`'s Phase 4 table, not unconditionally. Each edition's
  ~190-line "`.context_ledger/` Directory" section (structure tree,
  write-mode rules, entry-template examples — duplicating
  `ledger-schema.md` almost verbatim) is now a short pointer to the
  schema. **Common Pitfalls stays inline in each edition** — it's
  cross-referenced by number from the Ten Binding Rules and the two
  editions number their pitfalls differently (PAT-specific entries
  interleave in the cloud edition), so extracting it would break those
  references. `ai-engineering-protocol-local.md`: 1159 → 958 lines.
  `ai-engineering-protocol.md`: 1228 → 1053 lines — and a session whose
  task doesn't touch `core/`, collaboration, UI, security, performance,
  or a new feature now skips the playbooks entirely on top of that.
- **Append-only compaction stops being purely advisory.**
  `ledger-mem prune --apply` (sh + ps1) mechanically moves every entry
  whose own Status/Fixed-in-package line carries a closed marker,
  verbatim, into the log's `archive.md` (created with a header if
  missing) — the 3+-repeat roll-up stays a manual edit, since composing
  the consolidated entry needs an agent's judgment. Two new
  `history.conf` keys, `flaws_cap` / `inefficiencies_cap` (default 15
  each), give `ledger-mem check` a warn-only nudge mirroring
  `backlog_cap`. `ledger-gates run exit` now calls `ledger-mem prune`
  (report mode) as an advisory nudge at the natural moment.
- Schema (md + json) updated throughout: `STATE.md` in the file
  inventory, a rewritten "Reading order (session start)" that reads
  `STATE.md` first, a rewritten "Translation layer" describing the new
  tier-1 router size, and the compaction section documenting `--apply`
  and the two new caps.

Tests 23 → 27 (new: `prune --apply`'s closed-entry move + idempotency,
`flaws_cap` default + `history.conf` override).

- **Migration:** `ledger-sync update --major` (a MAJOR bump needs the
  user's go-ahead per this repo's own rule). `AGENTS.md`, `CLAUDE.md`,
  and `kickoff.md` are **regenerated from their new templates**, never
  hand-patched — a project with local edits to any of the three loses
  them on this update; move project-specific text into
  `memory/overrides/rules.md` first if it must survive. `STATE.md` is
  created fresh (`ledger-state generate`) — nothing to migrate, it has
  no prior state. No file is renamed or moved; `core/rules/playbooks/`
  is new. Everything below the moved playbook sections in each edition
  is otherwise unchanged.

---

## 1.2.0 — 2026-09-15

**The backlog becomes a capped work queue, and what was never work moves
to a new parking lot.** A backlog row is a promise to act; for a while
the template invited every kind of note into the queue — research
findings, design questions, deferred ideas, "someday" items — and the
result was a 57-row document posing as a queue: the header said "delete
rows when done", the culture said never lose information, so nothing
left and nothing got worked. The two roles split:

- `tasks/backlog.md` (template rewritten) holds actionable work only —
  the test for a row is "can an agent start on this and finish it?" —
  capped at `backlog_cap` (default 20, `workflows/history.conf`).
  Adding a row past the cap means pruning the lowest-value open row
  first, to the parking lot or the bin. Done rows and stale rows are
  deleted, not annotated. `ledger-mem check` reports a warn-only nudge
  past the cap (both ports; the cap is read from `history.conf`, so a
  project can raise it by intent).
- `tasks/parking-lot.md` (new template) is the knowledge base:
  Findings / Open questions / Deferred work / Someday, `P-<date>-<n>`
  IDs, no cap, no urgency. A parking-lot row is not a task; when one
  grows an owner and a next step, it is promoted to the queue.
- Office close re-seeds WORK, not knowledge: the fresh backlog inherits
  only rows with an active owner or a clear next step; parking-lot
  content survives the close in the permanent record (`Open threads`),
  not in the queue. Both `ledger-history` ports' pre-close checklists,
  record templates, and post-close messages carry the rule.
- Schema (md + json), both protocol editions (startup reads, door-close
  re-seed, deep-scan, promotion routing, pitfalls, report template),
  and the AGENTS / kickoff / ledger-README / sessions / collaboration
  templates updated to match. Tests 36 → 41: at-cap silent, over-cap
  warn-only, `backlog_cap` conf override, ps1 parity, and the
  work-not-knowledge checklist line.

No existing file moves or renames; projects that never write a
parking-lot file keep working — `check` only reads `backlog.md`.

- **Migration:** none required. `ledger-sync update` to 1.2.0 seeds
  `tasks/parking-lot.md` in new offices; existing offices can add the
  file by copying the template and splitting non-actionable rows out of
  the live backlog at the next convenient session.

---

## 1.1.3 — 2026-09-14

**Harvest reaches office-era projects, and the core's own path pointers
catch up to 1.0.0.** Three stale references from before the office
architecture shipped, all confirmed against the layout:

- `ledger-sync harvest` (package-mode, the flaw back-port collector) read
  each project's `memory/flaws/log.md` and
  `memory/inefficiencies/log.md` — the **pre-office** locations. Since
  1.0.0 those logs live under `memory/office/`, and the during-sync
  migration moves the old flat trees there, so harvest collected
  *nothing* from every migrated project: fleet flaws marked `open` and
  `Upstream: candidate` entries silently stopped reaching the package.
  Harvest now reads the office paths first, falling back to the flat
  layout for a project still mid-migration (`overrides/rules.md` stays at
  the memory root in both). Package regression added (`tests/run-tests.sh`
  35 → 36): a scratch package + sibling project harvests one entry from
  each office log.
- The integrity-failure and rollback advisories in both `ledger-sync`
  ports, and the schema's rollback fallback, pointed a session at
  `memory/flaws/log.md` — the same stale path in operator-facing text;
  corrected to `memory/office/flaws/log.md`.
- The `workflows/active.md` template's Deliverable example cited
  `memory/reviews/`; corrected to `memory/office/reviews/`.

No other behavior change.

- **Migration:** none. `ledger-sync update` to 1.1.3.

---

## 1.1.2 — 2026-09-14

**`ledger-mem prune` reads the closed marker where it lives.** The
compaction advisor (1.1.0) scanned every line of a log entry for the
words `RESOLVED` / `superseded` / `fixed in package`, so it flagged the
seeded template comment (whose placeholder Status line literally reads
"superseded by ADR-M") and any accepted entry that merely *describes*
the compaction rule — prose mentioning those words. Acting on the report
would have moved live, accepted entries into the archive. The marker is
now scoped to an entry's own `**Status:**` line (plus a `**Fixed in
package:**` line, the documented correction convention), and `<!-- -->`
template comments are never segmented at all. The schema's compaction
bullet states the same scoping, so hand-compaction follows the rule the
tool reports. No other behavior change.

- **Migration:** none. `ledger-sync update` to 1.1.2.

---

## 1.1.1 — 2026-09-13

**A comment cleaned by the rule 1.1.0 just enforced.** The one-way-linkage
sweep applied to the package's own code: `ledger-sync` cited a backlog bug
ID in a source comment. That ID resolves only in this
repo's own `tasks/backlog.md`, which is never vendored into a consumer's
`core/` — so the reference was a dangling pointer for every downstream
reader, the exact defect `ledger-mem lint --tree` now hunts. The reason was
already stated in plain words; only the ID tail is removed. No behavior
change.

- **Migration:** none. `ledger-sync update` to 1.1.1; the vendored
  `core/` rehashes (MANIFEST regen), memory untouched.

---

## 1.1.0 — 2026-09-13

**At-a-glance coordination, self-closing offices, compactable logs, and a
real one-way-linkage sweep.** Four supervisor-requested changes that make
the office legible to the next worker and stop memory from growing
without bound (MINOR — all backward-compatible: legacy four-column rosters
and old-office re-seeds keep working).

- **Roster gains `Status` + `Status detail` columns** (roster template,
  schema roster spec + JSON, both editions' binding rule 1 / Step 3
  check-in / light path / Step 15 clock-out, AGENTS digest rule 5, kickoff
  Step 2): `Working` at sign-in, edited in place to `Done` (what shipped,
  e.g. "Shipped: core 1.1.0 self-hosted") or `Blocked` (the blocker), with
  a detail line for the stage reached. The board becomes the next live
  worker's at-a-glance picture of who's where. `ledger-mem check` warns
  (never fails) when a real row has an empty or missing Status cell —
  legacy rows warn too. A pre-existing 4-column roster keeps working; add
  the two cells on the next edit.
- **A full office closes itself at the door** (both editions' Step 3 door
  bullet + Step 17 lifecycle, schema Office lifecycle "door trigger",
  AGENTS digest rule 5, kickoff Step 2, `ledger-history` status + pre-close
  checklist): the worker whose check-in read finds `agents/sessions.md`
  past `office_size` (default 20 — their codename would be past S020) runs
  `ledger-history close` right after their check-in push, before the deep
  read — not skippable to "finish this task first". **Re-seeded backlog /
  decision / log entries describe the work in plain words and never cite
  the closed office's session numbers or codenames** (those live in the
  frozen `history/` copy the new office never reads); the new office's
  numbering restarts clean (codenames from S001, entries from Session 1,
  ADRs and backlog IDs from 1).
- **Append-only logs compact, they don't hoard** (schema append-only mode
  + new "compaction, not hoarding" subsection + four table rows, both
  editions' rule 4 / Rules #1 / Step 17 / Pitfall #39, flaws +
  inefficiencies log templates, AGENTS digest rule 6): a clean session
  appends nothing to the friction logs; entries marked
  `RESOLVED`/`superseded`/fixed move **verbatim** to the log's
  `archive.md` (flaws, inefficiencies, and now decisions →
  `plans/archive.md`); 3+ entries hitting the same recurring thing roll up
  into one `Recurring` entry with the instances archived. Every moved line
  survives in the archive and in git — compaction relocates, never
  rewrites. `ledger-mem prune` now reports all three signals and covers
  `plans/decisions.md`, in both ports.
- **One-way linkage is enforced and swept** (both editions' gate-lint step
  + Pitfall #44, AGENTS digest rule 8, schema.json `oneWayLinkage`):
  product code must never carry `.context_ledger` vocabulary (ADR numbers,
  bug IDs, `.context_ledger/` paths, "per ADR"). `ledger-mem lint` gains
  `--tree`, sweeping every tracked product file (excluding
  `.context_ledger/`) and reporting `file:line`, so leaks an **earlier
  session** left become visible — the staged-diff mode only ever caught new
  ones. A found leak is stripped on sight as a safe fix, then the session
  continues; never tolerated, never backlogged.

**Tool ports:** `ledger-mem` (check roster-Status warn, prune decisions +
roll-ups, lint `--tree`) and `ledger-history` (status door rule, pre-close
no-leak checklist) — PowerShell ports mirror the shell tools and share the
manifest. A ps1-only gotcha fixed along the way: the roster-Status warn
must write to `[Console]::Out`, not `Say`, because `check` captures the
function's output stream into its return value and would swallow the
warning. **Migration:** none required — update and carry on; old rosters,
old office re-seeds, and old logs all keep working, and the new rules
apply from the next session.

**Verified:** suite 34/34 (sh + ps1) on Windows and POSIX, `ledger-sync
verify` green, gates passed.

---

## 1.0.6 — 2026-09-12

**The check-in happens at the entrance, not after working.** The
protocol sequenced the roster sign-in after the startup read (memory,
edition, product code, analysis); two workers launched together then
both saw an empty office, both took the same codename, and met
mid-session as strangers fighting over the main tree
(supervisor-reported PATCH).

- **Check-in is now the first write of every session** (both editions'
  Ten Binding Rules #1 and Step 3, and the kickoff template's Step 2,
  retitled "Sign in at the door, then read `.context_ledger/`"):
  signing needs exactly two files — the roster and the last session
  entry — so read those, push your row, then do the deep read of
  memory, protocol, and product code. Presence becomes visible in
  minutes, not after analysis. The editions' ENTRY rule now names the
  check-in row as the one sanctioned edit inside Phase 1.
- **The push claims the codename, not the intention**: whoever's
  check-in commit is already on origin keeps the number; a worker who
  reads for an hour before signing does not own the codename they
  thought of at the door. On a concurrent collision the earlier commit
  keeps it, and the later worker edits **their own row only** to the
  next free codename — never drops or rewrites a peer's row.
- **The main tree is settled at the door, by conversation**: two solo
  starts that discover each other afterwards resolve it from the board
  — work already in flight keeps the main tree, the other worker takes
  an isolated branch/worktree off origin/main, and both declare the
  shared session/issue before further edits.
- **No migration, no tooling change**: docs-only wording across the
  editions, the kickoff/AGENTS/roster/ledger-README templates, and the
  schema (roster file spec, reading order, office lifecycle). Regenerate
  the project entry points on next sync: kickoff.md, root AGENTS.md,
  `.context_ledger/README.md`.

---

## 1.0.5 — 2026-09-12

**The backlog is arranged, not a checkbox list.** `tasks/backlog.md`
used to be a flat list of `- [ ]` lines where related items hid each
other and nothing showed priority; the supervisor wanted the file
itself to show the shape of the work (format PATCH).

- **The file is now priority-grouped tables** (both editions' Step 15,
  the schema's new "The backlog: arrangement + workstream view"
  section, and the `tasks/backlog.md` template): one row per open item
  in its **High / Medium / Low** table, each row `ID | Summary` with a
  stable ID `B-<added YYYY-MM-DD>-<n>` and a Summary cell that carries
  the full context plus status qualifiers ("partial", "deferred by
  owner"). Finished = delete the row; there are no checkboxes, so
  nothing can be "checked off" — a row that remains is open work.
- **Existing backlogs do not need a migration commit**: legacy
  checkbox-format items keep their line until next touched; re-row
  them with an ID then. `ledger-mem closeout`/`check` still sweep and
  flag checked-off `- [x]` tombstones, so old-format files keep their
  tooling.
- **The workstream view is derived, never stored**: when planning over
  a large backlog (or the user asks), render numbered clusters of
  related items — one-line rationale, dedupe/ordering notes, and a
  `Workstream | Items | Estimated Effort` summary table — but an item's
  only home stays its priority-table row, so finishing it remains a
  single delete.

---

## 1.0.4 — 2026-09-11

**Session reports read like they were written for a person.** The
mandated report skeleton — Executive Summary → Discovery Phase →
Baseline Health → Findings → Fixes Applied → Open Items → Recommended
Next Steps — was a form for archiving, not prose for reading; the
maintainer flagged the voice, not the mechanics (tone PATCH).

- **Step 13 (both editions) now specifies the voice, not a skeleton:**
  write for the project's owner in plain sentences a reader outside the
  session's chat understands in one pass, lead with what happened, and
  cover what happened / what you found / what you changed / what's
  still open / what to do next in whatever structure fits. Headings
  only when the report needs them; severity labels only on findings
  that carry one. A clean review is one plain line ("reviewed
  `<area>`; baseline healthy; nothing needed") — not a padded skeleton.
- **`reviews/README.md`** carries the same shape guidance instead of
  the numbered skeleton.
- **The feature-engineer overlay** keeps the feature report's substance
  (design decisions, verified vs. not verified, open items) and drops
  the form-speak.

Migration from 1.0.3: none — run `update`. (Past reports are never
edited; their shape is history.)

## 1.0.3 — 2026-09-11

**The gate can no longer be cleared by a chatty failing command.** The
1.0.1 fix closed the piped-consumer case, but the PowerShell edition
still ran the gated command inline: its stdout rode `Run-One`'s return
pipeline, so a command that prints a line and exits nonzero returned
`@(lines..., $false)`, `-not` on that array never registered the
failure, and the gate printed `FAILED (N)` and then `GATE PASSED` with
rc=0. Silent failures kept failing correctly, which is why the flaw
looked intermittent (verified open by fleet sessions across 1.0.0–1.0.2;
tooling-correctness PATCH).

- **PowerShell edition (`core/bin/ledger-gates.ps1`):** `Run-One` now
  captures the gated command's stdout, judges the verdict first (the
  re-emit loop's `Write-Host` successes would reset `$?` and mask a
  failed final stage), and re-emits each line on the host stream — the
  same capture-and-host-stream shape `Invoke-ChildScript` already used.
  The wrapper's exit code is the verdict again on Windows; the interim
  "read gate stdout, never trust rc" rule can retire once projects
  sync to 1.0.3.
- **Same-class hardening:** `Invoke-ChildScript` judged its
  `$LASTEXITCODE`-less fallback (`$?`) after the re-emit loop — a chatty
  child failing without a reliable exit code would have read as 0. The
  verdict is captured before the loop (behavior-preserving when no
  output is emitted).
- **sh edition unaffected:** the gated command runs in a real child
  shell, its exit code propagates, and its stdout never passes through
  a function return.
- **Regressions:** the package suite grows 14 → 22 tests — on both
  editions, a gated command that prints a line and exits nonzero must
  fail the gate with its output visible and the `FAILED (N)` verdict
  line asserted, never the wrapper rc alone.

## 1.0.2 — 2026-09-11

**The Windows ports are UTF-8-clean — explicit encodings everywhere.**
Windows PowerShell 5.1 reads BOM-less files — *and parses BOM-less .ps1
source* — in the system ANSI codepage (cp1252) unless UTF-8 is explicit.
The office migration rewrote `history.conf` through an unencoded
`Get-Content`, corrupting the em-dash in the template comment (found by
the maintainer after the 1.0.0 ship; reproduced byte-for-byte). The
audit closed the whole class:

- **`Migrate-OfficeLayout` reads UTF-8 explicitly** — the migrated
  config keeps every non-ASCII byte; the key rename still applies.
  Regression test asserts the em-dash bytes survive a ps1 migrate.
- **`Write-Lock` is byte-identical to the sh port** — the em-dash in the
  `core.lock` header comes from a code point (`[char]0x2014`), so the
  file stops churning when the two ports alternate on one install. The
  rule this teaches: **string literals in ps1 sources stay pure ASCII**
  — a literal in a BOM-less ps1 is itself parsed as cp1252 and
  double-encodes on write.
- **The `rename` entry-point sweep** reads and writes UTF-8 explicitly
  (it edits the generated em-dash-bearing files in place).
- **All 27 `Get-Content` call sites across the six ps1 ports** pass
  `-Encoding UTF8` explicitly; no `Set-Content` of non-ASCII content
  remains anywhere in the ports.
- **tests/run-tests.sh grows to 14 tests**: em-dash survives a ps1
  migrate, the `group_size` → `office_size` rename still applies, and a
  ps1 `verify` writes a `core.lock` byte-identical to the sh port's
  (em-dash present, no BOM). Suite green on Git Bash + Windows
  PowerShell 5.1.

Migration from 1.0.1: none — run `update`. (If your project's
`history.conf` was already mojibake'd by a 1.0.0–1.0.1 ps1 migration,
repair the comment by hand; the keys were always parsed correctly.)

## 1.0.1 — 2026-09-11

**The gate can no longer be cleared by a piped consumer.** A gated
command like `ci-check.sh 2>&1 | tee out.txt` used to pass even when
the tool under test failed: both shells report only a pipeline's last
stage, so the gate read the consumer's success (reported from a fleet
project; tooling-correctness PATCH).

- **sh edition (`core/bin/ledger-gates`):** gated commands run under
  `set -o pipefail` when the shell — or a bash on PATH — supports it,
  so any pipeline stage's failure fails the gate. On a shell without
  pipefail, a gated command containing a top-level pipeline is
  **rejected** with a fix-it message (use redirection
  `tool > file 2>&1`, or one command per gates.conf line) instead of
  silently passing. `||` fallbacks and quoted `|` are never rejected.
- **PowerShell edition (`core/bin/ledger-gates.ps1`):** gated text is
  audited with the real parser before it runs. A pipeline with two or
  more external commands — or an unresolvable one — is rejected (its
  verdict would be the last native command's exit code); a pipeline
  with at most one external stage runs, and the verdict now fails on
  the exit code OR a failed `$?` — either signal.
- **Port parse checks are part of verify:** `ledger-sync verify` now
  also refuses to bless a core whose scripts cannot run — `ParseFile`
  over every `bin/*.ps1` and `sh -n` over every sh port (each edition
  checks what its host can run; a missing engine skips that half).
  Hashing catches corruption; this catches a port that shipped broken.
- **Package test suite:** `tests/run-tests.sh` in the package repo runs
  the gate-verdict tests against both editions on scratch projects — a
  gated `failing-cmd | tee` must fail the gate everywhere. Maintainer
  discipline: run it for every `core/` change.

---

## 1.0.0 — 2026-09-11

**Office architecture — the live session group is a directory, frozen
verbatim when it closes.** The flat memory layout
(`memory/agents/`, `memory/tasks/`, `memory/plans/`, …) becomes the live
office: an unnumbered directory `memory/office/` holding everything
session-produced — team roster, session registry, session notes, tasks,
plans, flaw and inefficiency logs, reviews. Only one office is ever live,
so every path in the protocol stays static. Design:
`designs/office-architecture.md` in the package repo.

- **Close freezes the office VERBATIM** — no condensing, no resetting;
  the roster keeps every check-in/clock-out shift. The whole directory
  moves to `history/office-<NNN>/`, numbered **at close time** from the
  records (the `agents/GROUP` state file retires — the sequence is
  derived from the permanent records, which never leave). Previously
  `close` condensed registry + summaries into one file and reset the
  live roster and registry.
- **A permanent accomplishments record per office:**
  `history/office-<NNN>.md`, written by close with the auto-facts
  (number, opened/closed dates, session count, milestone) and filled in
  by the closing session — **Accomplished / Decisions still in force /
  Open threads**. It stays in `history/` forever, even after the frozen
  office is zipped into `archive/office-<NNN>.tar.gz` and eventually
  garbage-collected: no office is ever forgotten.
- **The next office starts from empty skeletons.** Nothing carries over
  implicitly — the closing session re-seeds open threads that still
  matter into the new office's backlog/flaws/decisions and lists them in
  the permanent record. A fresh office cannot be misdirected by a
  previous office's stale claims, resolved-but-unpruned log entries, or
  superseded decisions.
- **Durable files never rotate:** `workflows/`, `collaboration/`
  (events trail), `system/`, `user/`, `overrides/`, `core.lock`, and
  `secrets/` stay at the `memory/` root across offices — they orient a
  session (rules, config, registries, the human's facts) rather than
  narrate one.
- **Migration is automatic and happens during sync:** `update` (and
  `migrate`) group a legacy flat layout into `memory/office/` — the old
  layout becomes the live office, nothing is lost or rewritten;
  `memory/agents/GROUP` is removed and the `history.conf` key
  `group_size` is renamed `office_size` (the tools still read the legacy
  key). Durable files never move. Legacy `history/group-<NNN>.md`
  records stay in place as read-only history. MAJOR bump: run
  `update --major` / `migrate --major` with the user's go-ahead; commit
  the regroup as `chore(ledger): group memory into the live office
  (core 1.0.0)`.
- **The full-office nudge:** `ledger-gates checkpoint` prints a
  warn-only notice (never blocks) when the live office has reached
  `office_size` sessions — the grouping lifecycle now announces itself
  instead of relying on the agent remembering `ledger-history status`.
- **Backfill tops up a partial office:** after migration, any office
  directory missing from the install (e.g. `reviews/` if never used) is
  seeded from templates without touching existing files.
- **Tools (sh + ps1 parity, runtime-verified on Git Bash and Windows
  PowerShell 5.1):** `ledger-history` rewritten (freeze-at-close,
  stateless numbering, permanent-record stub, fresh-office seeding,
  directory roll-to-archive, gc); `ledger-mem` checks repointed to the
  office paths; `ledger-sync` migration + office backfill; `ledger-gates`
  checkpoint notice. Templates, schemas (`ledger-schema.md`,
  `ledger.schema.json`), both protocol editions, and all generated
  entry-point digests updated to the office layout.

## 0.22.0 — 2026-09-10

**Collaboration events are JSON documents — and every session writes
them, solo included.** Events move from markdown frontmatter to immutable
JSON documents (`core/schemas/collab-event.schema.json` v1): validated
document-level by a standard JSON Schema, trail-level by
`ledger-collab check` exactly as before. The light path (`claim` → work
→ `release`) becomes universal — solo sessions emit it into the same
`memory/collaboration/events/` directory on the shared branch, so an
agent arriving mid-session sees live claimed paths in any mode. Design:
`designs/collab-events-json.md` in the package repo.

- **New event format:** one `<event-id>.json` per event, written in a
  strict profile (fixed key order, one `"key": value` per line, UTF-8
  without BOM) that keeps the POSIX-sh reader dependency-free — no jq.
  The `none` sentinels become real `null`/`[]`; CSV strings become real
  arrays; a new `schema: 1` field versions the durable trail for future
  format changes.
- **Backward compatible:** readers accept legacy `<event-id>.md`
  frontmatter files (pre-0.22.0) alongside JSON, forever; writers emit
  JSON only. Event files live in the memory zone, which `ledger-sync`
  never touches, so projects need no migration. MINOR bump.
- **Solo light path:** solo `session` = the roster codename (`S<NNN>`),
  `issue` = a short task slug; `tasks/current.md` unchanged. The
  collaboration README teaches it; edition prose may follow later.
- **Fixed (Windows port):** `ledger-collab-check.ps1`'s `Claim-Closed`
  used `if (Cmd a -or Cmd b)` — a bare `-or` between command calls
  inside an `if()` does not evaluate as two boolean command results, so
  event-ID-based claim closure silently never matched in PowerShell and
  only the path-overlap fallback ever closed claims there. Split into
  named booleans; logged as a flaw.
- **Cross-platform bytes:** the sh and PowerShell writers produce
  identical strict-profile documents (PowerShell writes UTF-8 without a
  BOM via `[IO.File]::WriteAllText` — a BOM would break the sh reader);
  both platforms read both representations and each other's output.
  Runtime-verified on Git Bash and Windows PowerShell over a mixed
  sh/ps1/markdown trail: emit, status (chatter, overlaps), check pass
  and fail paths, agreement ceremony, handoff, weak-agent SHA fallback.

**`ledger-mem closeout` — the live queue gets its sweep command.**
0.21.0 reclassified `tasks/backlog.md` as open-work-only and told
sessions to delete a finished item's line, but left the rule
prose-only: agents kept checking the box (`- [x]`) instead of
deleting, and tombstones accrued exactly as under the old append-only
habit.

- **New `closeout` command** (sh + `.ps1` port): deletes finished
  `- [x]` tombstones from `tasks/backlog.md`; open (`- [ ]`) items are
  never touched, and every deleted line stays recoverable in git
  history. Dry run by default — lists the tombstones with line
  numbers; `--confirm` deletes and prints the `chore(ledger):` commit
  suggestion.
- **`ledger-mem check` now warns** (warn-only, exit stays 0) when the
  backlog still holds checked-off items, pointing at `closeout`.
- **Teaching updated:** Step 15 in both protocol editions, the
  memory-tree comments, `ledger-README.md`, `AGENTS.md` rule 6, the
  backlog template header, and the schema (`ledger.schema.json`,
  `ledger-schema.md`).
- No memory migration: existing checked-off lines are exactly what
  `closeout` removes — run it once per project after updating.

## 0.21.0 — 2026-09-09

**Backlog is a live queue — open work only.** The backlog previously
held completed items as checked-off tombstones (`- [x]`, "don't remove
the line"), so every session re-read fixed work at startup. Completion
history already has a home: `agents/sessions.md` entries, the commits
themselves, and git history (which preserves any removed line).
`designs/feature-scoped-memory.md` had already flagged checked-off
backlog items as unbounded growth.

- **`tasks/backlog.md` reclassified:** no longer in the append-only set.
  Append new items at the bottom; **delete the line** when the item is
  finished or no longer relevant. Never delete a line whose item is
  still open — a `- [ ]` line vanishing without a matching session
  entry is a dropped handoff.
- Both protocol editions updated (Rule 4 file-kinds digest, Step 15,
  memory-tree comment, what-goes-where table, memory Rules 1, Pitfall
  #22, Pitfall #39). Pitfall #39's additions-only diff check now lists
  `backlog.md` as the explicit exemption.
- Templates updated: `memory/tasks/backlog.md` header rewritten;
  `ledger-README.md` tree; `AGENTS.md` digest rule 6; collaboration
  README durable-files note. Repo-level `README.md` and `MVP.md`
  updated to match.
- No tool changes: `ledger-mem`/`ledger-gates` never mechanically
  enforced backlog append-only (the check was prose-only), so no script
  edits. Existing project ledgers keep their checked-off lines until an
  agent deletes them under the new rule — no migration needed; a
  same-major `ledger-sync update` ships the new spec.

**Identity is never inferred — a model match proves nothing.** At sync
start a fresh session inferred "Zola (S455) is ME" from her roster row's
model-ID string matching its own system prompt's model name, and moved
to treat a dirty main checkout as its own uncommitted closeout. Doubly
wrong: the `cf02f3d0-…` UUID it matched on is the ZCode harness marker
shared by every ZCode session (it appears in the S450/S452 sessions.md
entries under glm-5.3-flash), and the model suffix `qwen3.8-flash` also
matches Nia's row (S454). Model strings can never discriminate agents,
and a fresh context can never prove it is a prior session.

- **New check-in bullet + Pitfall #45 in both editions:** identity is
  *claimed* at registration (fresh name + codename `S<NNN>`), never
  *inferred* from a model/harness-string match — model IDs, version
  suffixes, and harness/session UUIDs are fingerprints shared by every
  session on that harness or model. "That row is me" is justified only
  by continuity within your own live context (the re-check-in rule) or
  the user's word; a matching row is a peer's — leave it and its dirty
  checkout (Pitfall #20) alone.
- Threaded through the kickoff check-in, the AGENTS.md digest, the
  collaboration README ("You are a new arrival until you register"), the
  roster template's Model bullet, and both schemas' roster notes
  (duplicate model values are documented as normal).
- No tool changes: `ledger-mem check` already keys roster uniqueness on
  Name + codename, never on model, so duplicate model values never trip
  it. No migration; a same-major `ledger-sync update` ships the new spec.

**Worktrees are rented, not owned — tear down the topology at closeout.**
Collaboration setup was taught everywhere (check-in/mode bullets, the
collaboration README's workspace topology, the kickoff, the digest) and
teardown nowhere: clock-out, Step 15, and the EXIT checklists covered
the roster row, `current.md`, the logs, and the PAT — never the
workspace an agent created. So worktree directories accumulated one per
agent per session, and stale `git worktree list` registrations met the
next session as unexplained, locked paths.

- **Both editions:** a teardown bullet in the collaboration Isolation
  guidance, a Step 15 clock-out sentence, and a new EXIT / end-of-session
  gates checkbox. After the final `release` and integration: remove your
  product worktree (from a clean tree — unexplained changes stop you,
  Pitfall #20) and delete your product branch (`git branch -d` refuses
  an unmerged branch; `git push origin --delete` if pushed).
  `git worktree list` must be clean of your rows before you go.
- The coordination *branch* is the deliberate exception: it is the
  session's event trail, which later agents fetch to continue the
  session — it is not deleted while the session can resume. The
  coordination *worktree* may be removed by the last agent out
  (re-added in one command next session).
- Threaded through the collaboration README ("Teardown — the topology is
  rented, not owned"), the kickoff, and the AGENTS.md digest. No tool
  changes; a same-major `ledger-sync update` ships the new spec.

## 0.20.0 — 2026-09-09

**Additive roster edits — the peer-clobber fix.** On check-in into a
board holding a live peer's row, the arriving agent (LocalMind S449)
answered to the peer's identity instead of creating its own; when
corrected, its replace-style edit anchored on the table body *containing
the peer's row* — the block swap erased the live peer from the board and
was committed and pushed without a diff review (from `flaws/log.md`,
2026-09-09, via LocalMind flaw 86eeaef6). The check-in rule said "add or
update your row" but never stated the edit discipline that makes that
safe on a shared board.

- **Roster edits are additive — your row only** (both editions, kickoff,
  AGENTS.md digest): a live row you didn't write is a colleague's
  check-in, not sample text. Never take a peer's identity (name taken →
  pick another); never let an edit's `old_string` span or include a
  peer's row — the edit tool replaces blocks, so anchoring on the table
  body erases whoever is on it.
- **Diff-review gate for roster edits:** after any roster edit, `git
  diff` must show exactly your own row changed (`+1` on check-in) —
  review the diff before committing. A two-second diff review is what
  the S449 push lacked.
- No tool changes, schema changes, or memory-layout changes — project
  agents pick the rule up from the vendored rules/kickoff/digest text at
  the next same-major `ledger-sync update`.

## 0.19.0 — 2026-09-08

**Resume after clock-out — the ghost-editor fix.** Clock-out (Step 15)
removed the roster row and Step 17 logged the session as soon as "the
main work looks done," yet Pitfall #30 holds that the session is not over
until the user says so. So when the supervisor followed up after wrap-up,
the agent resumed *after* it had already left the board: it kept editing
under the identity it just retired, never re-registered, and peers saw
edits landing from someone who was not in the office (from
`flaws/log.md`, 2026-09-08 user report).

- **Clock-out now means leaving, not wrapping up.** Vacate the board only
  when you are actually leaving; if you expect a follow-up, keep your row
  live and clock out later. Step 15 and the AGENTS.md digest say so
  explicitly and cross-reference Pitfall #30.
- **New resume rule (both editions, kickoff, digest):** if you already
  clocked out and the user brings more work, you have left and returned —
  **check back in before touching anything.** Re-add your row under the
  **same name and codename `S<N>`** (you are the same session) and push it
  as `chore(ledger): <name> (<codename>) checks back in — <task>`. Never
  edit under a retired identity while your row is gone.
- **One `sessions.md` entry per codename `S<N>`, even across a resume.**
  Extend your existing Step 17 entry (commit range, outcome, open items);
  never append a second `Session N`.
- **`ledger-mem check` gains a duplicate-session audit** (POSIX +
  PowerShell): two `Session N` entries for one codename warn (never fail)
  — a resumed session re-logged instead of extending. Merge them. The
  PowerShell port mirrors the POSIX logic but was not runtime-verified on
  Windows this release (no `pwsh` on the authoring host).

## 0.18.1 — 2026-09-08

**Cross-platform `rename` fix.** The 0.18 `rename` command's entry-point
sweep used `sed -i 's|…|…|g' file`, which only works on GNU sed (Linux,
Git Bash on Windows). On BSD/macOS sed, `-i` consumes the next argument
as a backup suffix and the filename is then parsed as a sed script — so
every sweep errored (`sed: ... invalid command code .`) and the
generated entry points (`README.md`, `kickoff.md`, `.gitattributes`,
`AGENTS.md`, `CLAUDE.md`) were left with stale `.context/` references
after the `git mv` succeeded.

- **Fix.** The sweep now rewrites through a temp file (no `-i`) using
  POSIX-only regex — and drops the GNU-only `\b` word boundary. It runs
  identically on GNU and BSD sed: Linux, macOS, and Windows Git Bash.
  `.context/` is rewritten first; bare `.context` is matched only at a
  non-word/non-slash boundary or end of line, so an existing
  `.context_ledger` is never double-renamed to `.context_ledger_ledger`.
- **Scope.** `rename` (POSIX-sh tool) only; PATCH. No spec, layout,
  memory, or behavioral change on GNU platforms — the sweep now simply
  also works on macOS. The PowerShell port was already correct.
- **Who needs it.** Anyone finishing the 0.18 `.context/` →
  `.context_ledger/` migration on macOS. If you already ran `rename`
  there, the `git mv` worked but the five entry-point files may still
  say `.context/` — re-run `rename` against this core, or fix them by
  hand. Memory files were never touched by the sweep regardless.

## 0.18.0 — 2026-09-08

**Context Ledger.** The package went public and took its real name. The
repo is `TisoneK/context-ledger` (was `TisoneK/.context` — GitHub
redirects the old URL), and every project's two-zone directory is
renamed `.context/` → **`.context_ledger/`**. The tools rename with it:
`context-sync` → **`ledger-sync`**, `context-gates` → **`ledger-gates`**,
`context-collab` → **`ledger-collab`** (+ `ledger-collab-check`),
`context-mem` → **`ledger-mem`**, `context-history` → **`ledger-history`**.
Schemas rename to match: `ledger-schema.md` + `ledger.schema.json`,
`ledger-README.md`.

- **Breaking, shipped as a 0.x MINOR — deliberately.** The directory and
  tool names are part of the spec, so this would be a MAJOR under 1.x
  discipline; while the project is pre-1.0 it ships as a MINOR. Safe
  because the 0.18 tooling detects **both** layouts: a project that
  updates without renaming keeps working, and `rename` is the explicit
  finishing step. Memory files, formats, and the two-zone model are
  unchanged — this is a rename, not a redesign.
- **Migration — three commands, existing project:** from the project
  root, with the package reachable:

  ```bash
  sh .context/core/bin/context-sync update    # same-MAJOR: applies; its self-re-exec
                                              # errors — expected, core 0.18 is in place
  sh .context/core/bin/ledger-sync migrate    # new tool: backfill + relock + verify
  sh .context/core/bin/ledger-sync rename     # git mv .context -> .context_ledger + sweep
  ```

  `rename` `git mv`s `.context/` to `.context_ledger/`, sweeps the
  generated entry points (`README.md`, `kickoff.md`, `.gitattributes`,
  root `AGENTS.md` + `CLAUDE.md`), relocks, and verifies. Requires a
  clean tree. It prints the one manual step: sweep stale `.context/`
  *instruction* references in your memory files (historical log entries
  stay as written — append-only). Commit as `chore(ledger): rename
  .context/ to .context_ledger/ (core 0.18)`.
- **Compat.** Mode detection accepts `.context/` and `.context_ledger/`,
  so `status`/`verify`/`update`/`migrate` all run in a legacy project;
  `rename` finishes the job. Package-side `harvest` reads both layouts
  too. Full recipe: `MIGRATION.md`.
- **Sources.** `update`/`migrate` look for the package clone at
  `../context-ledger` first, then legacy `../context`, then
  `../.context` — or set `LEDGER_PKG`/pass a path as before.
- **Windows.** Every `.cmd` launcher and `.ps1` port carries the new
  names; the `rename` command is ported too.
- **Public repo.** The package repo is now **public** — cloud bootstraps
  no longer need a package PAT (project PATs unchanged). The docs'
  private-repo claims were updated.

---

## 0.17.0 — 2026-09-08

**Check-in is universal — the board shows who is in the office.** The
roster was signed only inside Peer Collaboration Mode, and the solo
decision keyed on `tasks/current.md` being idle — a value that stays
"idle" on the shared branch until the first agent's wrap-up commit. So
every arriving agent saw an empty board, concluded it was alone, and ran
a solo protocol that never signs in and never claims a worktree: N
agents, N parallel solo sessions, unattributable uncommitted changes
(from `flaws/log.md`, 2026-09-08 user report).

- **Check-in moved to Step 3 of every session, solo included:** pick a
  real name, add your row to `memory/agents/roster.md`, and **push it
  immediately, before any product work** (`chore(ledger): <name>
  (<codename>) checks in — <task>`). Presence is real-time, not
  wrap-up-time; a rebase on that push is itself a signal that a peer
  checked in concurrently.
- **The board is on every read order** (both editions, kickoff Step 2,
  AGENTS.md digest, schema reading order) and drives the mode decision:
  **solo = no declared session/issue AND no live roster row you didn't
  write AND `current.md` idle.** A live row you didn't write means a peer
  is here — declare or join a session, take an isolated worktree, emit a
  `note` + `claim`; never run a solo protocol into a peer.
- **Clock-out at Step 15:** remove your row in the closing memory
  commit. The board answers "who is in the office *now*"; who was on
  duty *when* stays in the append-only duty log (`agents/sessions.md`)
  and the roster file's own git history — check-in opens the shift,
  clock-out closes it. Nothing historical is deleted by clocking out.
- **`ledger-mem check` audits board vs duty log** (POSIX + PowerShell):
  a roster row whose `Session N` is already in `agents/sessions.md`
  warns "logged itself done without clocking out". Warn-only, exit 0.
- Collaboration section now opens with "Collaboration is opt-in;
  **presence is not**"; the collaboration-light-path step 0 references
  the Step 3 check-in; dirty-tree STOP / unexpected-changes guidance in
  both editions says to check the roster and events before
  investigating — it may be a teammate's claim, not drift.

**Migration:** none — `roster.md` already exists in every 0.15.0+
project; existing empty boards behave exactly as before until the first
session checks in. Older projects: `ledger-sync migrate` installs
`roster.md`.

**The ports' self-referential help matches the `.cmd` convention.**
`ledger-sync.ps1`'s printed help (what `ledger-sync.cmd` shows with no
arguments) and `ledger-collab.ps1`'s header examples still told Windows
agents to run `pwsh -File .context_ledger/core/bin/...ps1` — which an
execution-policy-locked machine blocks. Both now show the documented
no-setup form (`ledger-sync.cmd <cmd>`). Text-only change, line counts
preserved (the sync help is sliced from the file header); manifest
regenerated.

## 0.16.0 — 2026-09-06

**Sync is one command and fill again.** Each release since 0.9.x added files
or zones that only `update`'s versioned backfill installed — and because that
backfill lived in the *old* script that runs first, migrating an old project
meant running `update` twice, guessing about CRLF, and hand-creating new
zones. This restores the old simplicity.

- **New `ledger-sync migrate` (POSIX + PowerShell + `.cmd`):** the
  one-command bring-current. It updates the core to the newest reachable
  same-MAJOR version, then **backfills every missing zone/file** (`history/`,
  `archive/`, `CLAUDE.md`, `.gitattributes`, `roster.md`, `history.conf`,
  `GROUP`, …), LF-normalizes, relocks, and verifies — then prints the single
  manual step: fill the project facts. Idempotent; safe to re-run; doubles as
  a repair command for a project missing any current file.
- **The backfill is factored out** (`backfill_project`) as the one definition
  of "what a fully-migrated project contains" — adding a new template file to
  that list is all it takes to teach migration about it. Both `update` and
  `migrate` go through it.
- **`update` now fully migrates in one run** (from this version on): after
  the core swap it re-execs the *just-installed* script's `migrate
  --backfill-only`, so the new script — which knows every new file — does the
  backfill. No more "run update twice."
- **The PowerShell `update` caught up:** it had only ever backfilled README /
  `.gitattributes` / `CLAUDE.md`, missing the `history/`, `archive/`,
  `roster.md`, `GROUP`, and `history.conf` a 0.13+ project needs. It now
  installs all of them through the shared backfill.
- **MIGRATION.md rewritten** to lead with the one-command path for any
  0.2.0+ project (with the old-script fallback), keeping the pre-0.2.0
  flat-layout `git mv` steps as a clearly-marked special case that ends in
  the same `migrate`.

**Migration to 0.16.0 itself:** from an older project, `update` once (installs
this script) then `migrate` — or just `migrate` if the vendored script already
has it. From 0.16.0 forward, one `update` (or one `migrate`) is enough.

## 0.15.0 — 2026-09-06

**Agents are named coworkers, not "peers".** Collaboration works, but agents
identified as "peer" or a bare `S427`. Now each agent picks a real name and
the team reads as people in a workplace — with the human as the supervisor.

- **New `agents/roster.md`** (update-in-place, current-group-scoped): a team
  board, one row per person — a chosen human **Name**, a **codename**
  `S<NNN>` (session number), the **model**, and one line on what they're
  doing. An agent adds its row at session start and presents itself by that
  name everywhere ("John (S427)"), in events and when reporting to the
  supervisor.
- **Name and codename are each unique within the group.** `ledger-mem
  check` now validates the roster and flags a duplicate name or codename
  (there is only one John on the team at a time) — the same update-in-place
  discipline as the other registries.
- **The roster rotates with the group.** `ledger-history close` captures
  the closed group's roster into `history/group-<NNN>.md` and resets a fresh
  empty roster for the new group.
- **Docs reframed to the workplace metaphor:** the collaboration README (new
  "Who you are — pick a name" section), both protocol editions (a step 0 in
  the light path), the AGENTS digest, and the schema now say: pick a name,
  present yourself by it, the human is the supervisor. `--agent` takes your
  name, so the chatter feed reads "John: ...".

**Migration from 0.14.x:** `update` installs `agents/roster.md` if absent.
Existing agents just start adding rows; nothing else changes. The `.ps1`
port changes (roster check + roster reset) are ASCII-clean but owe the usual
Windows runtime pass.

## 0.14.0 — 2026-09-06

**Windows verified for real: three latent port bugs fixed, `.cmd`
launchers remove the execution-policy hurdle.** 0.13.1 made the `.ps1`
ports *parse* under Windows PowerShell 5.1; this release makes them *run*.
Every port was executed end-to-end against a bootstrapped fixture project
(registry hygiene, the full three-zone history lifecycle, the
collaboration trail, the gates), which surfaced defects a parse-level fix
cannot catch.

- **`ledger-collab-check.ps1` crashed on every invocation.** It assigned
  the automatic `$args` variable (a no-op under `Set-StrictMode`) and its
  `if`-expression `@()` unwrapped to `$null`, so the argument loop died on
  `$null.Count`. The array is now built by direct assignment. 0.9.1 had
  shipped this file as "Windows-verified"; only its parse had ever been
  exercised.
- **`ledger-history.ps1 close` / `gc` crashed when run without flags.**
  `$RestArgs.Count` on a `$null` `ValueFromRemainingArguments` parameter
  is fatal under strict mode. Both such parameters now default to `@()`
  (`ledger-mem.ps1` hardened the same way).
- **`ledger-history.ps1` never archived anything.** It passed a
  `C:\...` archive path to `tar`, which GNU tar (MSYS, often first on
  PATH) parses as remote *host* `C` ("Cannot connect to C: resolve
  failed"). The roll now runs tar from inside `history/` with a relative
  `-f` path — the exact pattern the POSIX port already used — so bsdtar
  (System32 `tar.exe`) and GNU tar behave identically.
- **`ledger-collab.ps1` rejected its own documented `--re` flag.**
  PowerShell parameter prefix-matching bound `--re` to the `$Rest`
  parameter (re ⊂ Rest), consuming it and derailing binding of every
  later flag ("parameter cannot be found '-session'"). The parameter is
  renamed `$Extra`; `emit assessment --re <id>` and friends work.
- **New `context-*.cmd` launchers**, one per `.ps1` port. A `.cmd` file is
  executed by cmd.exe regardless of the PowerShell execution policy, and
  starts its port with `powershell -NoProfile -ExecutionPolicy Bypass
  -File`. The documented Windows invocation becomes e.g.
  `.context_ledger/core/bin/ledger-mem.cmd check` — no `Set-ExecutionPolicy`
  step. Windows PowerShell 5.1 is targeted deliberately: it ships with
  every Windows 10+ install, while pwsh 7 is an optional add-on. All
  docs (kickoff, both protocol editions, schema, README, QUICKSTART) now
  show the `.cmd` form.

**Migration from 0.13.x:** `update` installs the launchers with the rest
of `core/`; no memory changes and no behavior change for POSIX. Windows
agents should switch to the `.cmd` form; `pwsh -File` keeps working where
the policy allows it.

## 0.13.1 — 2026-09-06

**ASCII-clean the new PowerShell ports.** `ledger-mem.ps1` and
`ledger-history.ps1` (0.10.0–0.13.0) shipped with UTF-8 punctuation
(em-dashes, arrows) in string literals. Windows PowerShell 5.1 decodes the
`.ps1` as ANSI and fails to parse non-ASCII bytes — the same defect 0.9.1
fixed for the other ports. Both files are now ASCII-only, matching the
standing rule. POSIX ports unchanged (sh handles UTF-8). No behavior change;
manifest regenerated.

## 0.13.0 — 2026-09-06

**Session history is grouped and bounded (three-zone lifecycle).**
`agents/sessions.md` was append-only *forever* — session history grew without
bound and sat in the startup read (LocalMind's registry alone spans dozens of
sessions). This introduces session **groups** that rotate through three zones
so `memory/` only ever holds the live group.

- **New zones `history/` and `archive/`** under `.context_ledger/` (created by
  bootstrap and installed by `update` for existing projects). Neither is read
  at session start — the schema and both editions state this. `memory/`
  (live) → `history/` (closed, readable `group-<NNN>.md`) → `archive/` (cold
  `group-<NNN>.tar.gz`) → `gc`.
- **New `ledger-history` + `ledger-history.ps1`:** `status` (current group,
  session count, zone sizes, due?), `close [--milestone L] [--confirm]`
  (consolidate the live group into `history/`, start a fresh group, roll the
  oldest readable group into `archive/`), `gc [--confirm]` (delete oldest
  `archive/` tarballs over the cap, oldest-first, git-recoverable). Destructive
  steps are gated behind `--confirm` and print a dry-run plan first.
- **A "group" is the session-history subtree only** — `agents/sessions.md`,
  `sessions/SUMMARY.md`, `sessions/<date-N>/`. Durable facts (`user/`,
  `system/`, decisions, backlog, flaws, inefficiencies) and collaboration
  events never rotate; they persist in `memory/` with their own hygiene. This
  scoping is deliberate: resetting all of `memory/` per group would break the
  durable-facts spine (ADRs are respected, not relitigated).
- **No implicit carryover.** `close` prints a promotion checklist and refuses
  to execute without `--confirm`: every open thread must already live in its
  durable domain file before the group closes, so the new group starts clean —
  the spec's "no carryover" enforced at the boundary, not by wiping memory.
- **Tunable, weak-agent-safe defaults** in `memory/workflows/history.conf`:
  `group_size=20`, `history_keep=3`, `archive_keep=12`. `agents/sessions.md`
  becomes the *current group's* registry (backward-compatible — rotation only
  begins at the first `close`).

**Migration from 0.12.x:** `update` creates `history/`, `archive/`,
`history.conf`, and `agents/GROUP` if absent, and never clobbers an existing
one. Existing `agents/sessions.md` keeps growing until the first
`ledger-history close`, which starts the rotation. Archives are `.tar.gz` on
both platforms (the `.ps1` uses `tar.exe`, shipped on Windows 10+).

## 0.12.0 — 2026-09-05

**Bound the durable logs (context pruning).** The append-only durable logs
(`flaws/log.md`, `inefficiencies/log.md`) grow forever and sit in the
mandatory startup reading order, so a mature project reads mostly resolved
history every session (LocalMind: flaws 614 lines / 52 entries,
inefficiencies 1172 lines / 108 entries). The session layer already had a
cold-storage story (disposable notes, prunable SUMMARY.md); the durable
layer had none.

- **`ledger-mem prune`:** advises archiving resolved history out of the
  durable logs. It reports each log's size and how many entries are
  explicitly marked `RESOLVED` / `superseded` / fixed — the archive-eligible
  ones — and `--list` names them. It **never moves or deletes anything**;
  archiving stays a deliberate cut-and-paste into a companion `archive.md`
  (which stays in git, grep-able). Conservative by design: **only an
  explicit closed marker makes an entry eligible; age alone never does**, so
  an unresolved flaw is never archived out from under the next agent.
- **The archive convention** is documented in both editions (beside the
  SUMMARY.md prune rule), the schema, and the `flaws/` and `inefficiencies/`
  log templates: move a resolved entry verbatim into `archive.md`; startup
  reads only the active log.

**Migration from 0.11.x:** none — additive advisory + wording. Nothing is
moved automatically; run `ledger-mem prune` when a log feels heavy and
archive the entries it flags.

## 0.11.0 — 2026-09-05

**Keep `.context_ledger` vocabulary out of product code.** The protocol trains
agents to think in ADRs, bug IDs, and session numbers — and that vocabulary
leaks into product artifacts. Across the fleet, product source cites
`.context_ledger`-internal terms in docstrings and comments
(`/** ADR-34 B-8: bounded evidence entry */`, `"""ADR-11 one-time data
copy..."""`) — dangling pointers into a `.context_ledger/` that anyone cloning only
the product repo does not have.

- **`ledger-mem lint`:** a new subcommand (POSIX + PowerShell). It scans the
  **staged** product diff (everything outside `.context_ledger/`) and fails if an
  added line cites an ADR number (`ADR-N`), a bug ID (`B-YYYY-MM-DD-N`),
  `"per ADR"`, or a `.context_ledger/` path. `.context_ledger/` files are exempt — they
  legitimately use the vocabulary. (`Session N` is deliberately *not*
  flagged: apps have a legitimate "session" domain noun.)
- **The one-way-linkage rule.** Memory may reference product code; product
  code must never reference memory. Added as a pitfall in both editions, the
  `AGENTS.md` "two surfaces" rule, and a schema invariant. If the reason for
  a decision matters, state it in plain words in the docstring; the ADR link
  lives in `plans/decisions.md`, which points at the code — never the
  reverse. The pre-commit step runs `ledger-mem lint` for product commits.

**Migration from 0.10.x:** none — additive subcommand + wording. Existing
product code that already cites `.context_ledger` vocabulary will fail
`ledger-mem lint` on the next edit to those lines; rephrase the docstring to
stand alone and move the ADR link into `plans/decisions.md`.

## 0.10.0 — 2026-09-05

**Update-in-place registries stop duplicating.** `system/ai-models.md` and
`system/environments.md` are update-in-place (one entry per key), but the
append-only invariant is stated so loudly that agents apply it here too and
*append* a corrected entry instead of editing the existing one — so a
registry accumulates two rows for one key with conflicting counts (observed
in the fleet: one agent+model registered three times, sessions 8/10/30).

- **`ledger-mem` + `ledger-mem.ps1`:** a new helper. `ledger-mem check`
  flags a duplicated key in the update-in-place registries —
  `ai-models.md` keyed by (Agent, Model), `environments.md` by its
  "Identify by:" line. It is the inverse of the append-only rule: for these
  files, a *second* entry for an existing key is the defect. Different
  models for one agent are separate rows (expected), not duplicates.
- **The distinction is now stated as loudly as append-only.** Both protocol
  editions' top rules, the `AGENTS.md` digest, the `ai-models.md` header,
  and the schema now say: correct an update-in-place entry by *editing* it,
  never by appending a duplicate — the prior value is safe in git history,
  so editing loses nothing. The exit step runs `ledger-mem check`.

**Migration from 0.9.x:** none — additive helper + wording. Existing
registries that already have a duplicated key will fail `ledger-mem check`;
merge the rows/blocks into one (sessions accumulate) and the old values
remain in git history.

## 0.9.1 — 2026-09-05

**Windows verified on Windows.** 0.9.0 shipped the durable LF policy
(`.gitattributes`) and the CRLF manifest-parse fix, but the verifiers still
hashed raw on-disk bytes — so any CRLF copy of the core (a project checked
out under `core.autocrlf=true` before the `.gitattributes` existed, or files
copied outside git, where the attribute never reaches) still failed every
hash and reported CORE INTEGRITY FAILURE. Worse, the advised remediation
(`rollback`) re-restored CRLF bytes on those targets — an unfixable loop —
and on the sh side a CRLF `memory/core.lock` poisoned the version lookup so
rollback died with "no commit in history has core VERSION". This release
was written and validated on Windows (Git Bash + PowerShell 7.6 + Windows
PowerShell 5.1), closing the validation pass 0.9.0 owed.

- **`verify` hashes CR-stripped content** (both sh and PowerShell). One
  manifest stays byte-compatible across LF checkouts and CRLF copies:
  LF-only files hash identically, so `MANIFEST.sha256` values are unchanged
  and 0.9.1 verifiers validate 0.9.0 cores and vice versa. A CRLF copy now
  verifies clean instead of reporting 46 false integrity failures.
- **`update` / `bootstrap` normalize the staged copy to LF in place**
  (sh `normalize_lf`; PowerShell `Convert-ToLf`), so a core vendored or
  updated from a CRLF source is byte-identical to its manifest on disk —
  no renormalize dance needed afterward. `bootstrap` normalizes the memory
  skeleton too.
- **PowerShell `rollback` rewrites the restored core to LF**, so a rollback
  under `core.autocrlf=true` verifies afterward instead of looping.
- **`lock_version` tolerates a CRLF `core.lock`** (sh), fixing the
  rollback dead-end above.
- **PowerShell `update` parity with sh:** installs `.context_ledger/.gitattributes`
  and the root `CLAUDE.md` pointer when absent — and `update` now installs
  them on *every* run, including a no-op, so a 0.8.x project's second
  `update` (after the new core has landed) picks them up (0.9.0 taught
  only the sh script; Windows agents run the `.ps1`).
- **Gate results propagate again.** Two independent bugs silently turned
  every gate failure into a pass. PowerShell: `Run-One`'s log lines went
  through the return pipeline, so `if (-not (Run-One ...))` compared an
  array — and `-not` on a non-empty array is always `$false`. sh:
  `run_explicit` and `run_discovered` reset the caller's `_failed` counter
  (functions have no locals in sh). Gate logs now go to the host stream
  and the sh helpers use distinct failure counters. Also: a cmdlet-only
  gate command no longer inherits a stale `$LASTEXITCODE`, a thrown
  script error fails the gate instead of crashing it, and child `.ps1`
  invocations pre-seed `$LASTEXITCODE` (a child script's `exit N` does
  not reliably set it on every host, and reading it unset trips
  StrictMode).
- **PowerShell argument parsing works again.** Parameters named `$Args`
  collide with the automatic variable of the same name, so every
  `--session/--issue/--paths/...` flag was silently lost in
  `ledger-collab.ps1` (status filters matched everything) and
  `ledger-gates.ps1` (checkpoint and integration scopes no-oped).
  Renamed throughout. A missing collaboration events directory no longer
  crashes `ledger-collab-check.ps1` under StrictMode.
- **`manifest` regenerates identically on Windows.** `sha256sum` under Git
  Bash defaults to the binary-mode separator (`hash *path`), so a
  Windows-regenerated manifest churned all 46 lines vs a mac `shasum`
  regen; `cmd_manifest` now forces the text-mode separator (`-t`). The
  parsers already accept both.

**Migration from 0.9.0:** none — verify both ways, no manifest or memory
changes. Projects still on a CRLF working tree no longer need the 0.9.0
renormalize step for `verify` to pass; the `.gitattributes` LF policy
remains the durable git-level fix and is worth committing anyway.

**Upgrading a 0.8.x project on Windows:** (1) Use a git checkout of this
package as the update source — a fresh clone, or the existing clone pulled
to 0.9.1 and re-smudged (`rm -rf core && git checkout -- core`) if it
predates 0.9.0. The 0.8.x verifier hashes raw bytes, so a CRLF source (a
stale clone or a hand copy) will be refused. (2) Run the update under Git
Bash or PowerShell 7 — the 0.8.x `.ps1` cannot be parsed by Windows
PowerShell 5.1 (its UTF-8 punctuation breaks 5.1's ANSI decoding; the
0.9.1 `.ps1` files are ASCII-clean). (3) Run `update` a second time after
it lands: the first run executes the old script and swaps in 0.9.1, the
second (no-op) run is the one that installs `.context_ledger/.gitattributes` and
the root `CLAUDE.md` pointer. (4) Commit `chore(ledger): update core to
0.9.1`, and `git add --renormalize .` if the project ever committed CRLF
blobs. Once 0.9.1 is in place, `verify` passes on LF and CRLF working
trees alike, so the rollback deadlock cannot recur.

## 0.9.0 — 2026-09-05

**Collaboration that feels like coworkers.** Peer collaboration was
technically working but less effective than single-agent mode: fleet
evidence (LocalMind's 42-event trail — the only trail that ever exercised
it) showed agents paying heavy ceremony for solo work, never once
completing an `agreement`, and colliding on identical paths with no
resolution. The framing primed rivalry ("competing proposals are
expected"), the tooling reported closed claims as active forever and hung
for minutes, and Windows CRLF corrupted the integrity system. This release
turns the "courtroom" into an "office."

- **New `note` event — the office channel.** An informal heads-up to peers:
  a body is all it needs (optional `--to <peer>`, `--re <event|path|commit>`),
  it never gates `check`, and it never has to be resolved. `status` opens
  with a **Recent chatter** feed. Notes give agents the low-stakes
  back-and-forth they lacked, so peer reviews and hand-offs stop being
  smuggled into shared durable files.
- **Cooperative reframing.** The README, both protocol editions, the AGENTS
  digest, the schema, and the kickoff now frame peers as one team with one
  goal. The light path (`note` + `claim`/`release`) is the documented
  default; the `proposal → assessment → agreement` ceremony is the
  escalation for a genuine conflict (same paths, incompatible changes) only.
- **`ledger-collab` tells the truth.** A `release`/`handoff` now closes a
  claim when it cites the claim's event ID **or** simply shares its
  session+issue and overlaps its paths — so a release citing only the commit
  SHA no longer strands its claim as "active forever" (the common,
  weak-agent case).
- **`ledger-collab check` no longer hangs.** Rewritten as a single-pass
  in-memory index instead of re-globbing the events dir and forking
  `sed`+`head` per field. On a 42-event trail it went from > 3.5 minutes
  (killed) to < 0.1 s. Notes are exempt from every gate; release/handoff
  correspondence is checked by the same forgiving claim-linkage.
- **Windows / CRLF root fix.** New package-root `.gitattributes` and a
  shipped `templates/.gitattributes` (installed into `.context_ledger/` by
  `bootstrap` and `update`) force `eol=lf` on the vendored core *and* the
  memory logs — fixing the `ledger-sync verify` false-positive under
  `core.autocrlf=true`, the `sh` manifest-parse death on `\r`-suffixed
  filenames, and the phantom whole-file diffs in append-only logs. `verify`
  also tolerates a CRLF manifest defensively, and the "no sha256sum" error
  now points Windows users at the `.ps1` port.
- **`ledger-gates.ps1` runs again.** Fixed a PowerShell binding crash
  (`Cannot bind parameter because parameter 'PathType' is specified more
  than once` — two `Test-Path` calls chained by `-or` without parenthesizing
  each) that made every gate fail on Windows.
- **No agent starts blind.** Bootstrap (and `update`) now install a root
  `CLAUDE.md` pointer, because Claude Code auto-loads `CLAUDE.md`, not
  `AGENTS.md`, and a session that never reads the digest runs with zero
  `.context_ledger/` discipline (a logged fleet failure). `CLAUDE.md` routes into
  `AGENTS.md` + the kickoff; the bootstrap guidance and `AGENTS.md` header
  now name the other agent entrypoints (Copilot/Cursor/Gemini) that should
  carry the same one-line pointer. Existing `CLAUDE.md` files are never
  overwritten.

**Migration from 0.8.x:** fully compatible — the seven formal event types
keep their exact meaning; `note` is additive. New bootstraps and `update`
install `.context_ledger/.gitattributes`. If a project was already checked out with
CRLF (Windows `core.autocrlf=true`), run once after updating:
`git add --renormalize . && git commit -m "chore(ledger): normalize line endings to LF"`
(or set `core.autocrlf=false` and `git checkout -- .context_ledger`). The `.ps1`
ports could not be executed on the maintainer's Mac (no `pwsh`); they were
updated by mirroring the POSIX behavior and are cross-checked against the
manifest — a Windows validation pass is still owed.

## 0.8.0 — 2026-08-17

**Explicit lifecycle command gates.** Agents now have mechanical,
project-owned gates instead of relying only on prose instructions.

- **`ledger-gates` + `ledger-gates.ps1`:** add `checkpoint`,
  `pre-commit`, `integration`, and `exit` gate commands with consistent
  exit behavior and observable command output.
- **Per-agent-turn checkpoint:** refreshes working-tree and collaboration
  state before the next action, reducing stale-context work.
- **Project command registry:** new `memory/workflows/gates.conf` supports
  explicit commands per lifecycle gate. `mode=hybrid` uses safe conventional
  package.json/Python discovery only when no explicit command is configured;
  `mode=explicit` fails when a required gate has no command.
- **Mandatory transitions:** protocol editions, kickoff, AGENTS digest,
  and schema now require gates before commits, branch integration, and
  session exit. Integration includes `ledger-collab check` when a
  collaboration session/issue is supplied.

**Migration from 0.7.x:** existing projects remain compatible. New
bootstraps receive `gates.conf`; existing projects can initialize it with
`sh .context_ledger/core/bin/ledger-gates init` or the PowerShell equivalent.

## 0.7.0 — 2026-08-17

**Collaboration integration-readiness checks.** The collaboration helper
now provides a mechanical gate before product branches are integrated.

- **`ledger-collab check`:** validates required event metadata, event ID
  uniqueness, resolvable same-session/same-issue references, complete agreements,
  selected options, peer participants, owners, active claim overlaps,
  unresolved proposals/assessments/corrections/handoffs, and product
  commit references on releases.
- **PowerShell parity:** `ledger-collab.ps1 check` delegates to the
  PowerShell validator with the same checks and exit-code contract.
- **Operational split:** `status` remains the live-work view; `check` is
  the integration-readiness gate and fails when the event trail is not
  complete.

**Migration from 0.6.x:** none. Existing event trails remain readable;
projects gain the check helpers on their next core update.

## 0.6.0 — 2026-08-17

**Peer collaboration for concurrent and shared-issue sessions.** The
single-agent workflow remains the default, while agents can now opt into a
shared session/issue and coordinate without a mutable global lock.

- **Isolated workspaces:** collaborating agents use separate clones or git
  worktrees and `collab/<session-id>/<agent-id>` product branches; product
  commits never happen in the same checkout or directly on the shared
  integration branch during collaboration. Events publish to the shared
  event-only `collab/<session-id>/coordination` ref.
- **Immutable event trail:** projects gain `memory/collaboration/`, where
  each claim, proposal, assessment, agreement, correction, handoff, and
  release is a separate event file. Independent files avoid concurrent EOF
  append conflicts and preserve the complete reasoning trail.
- **Evidence-based peer agreement:** overlapping scopes require assessments
  and an agreement selecting the best-supported option and exactly one
  implementation owner. There is no timestamp, priority, or agent-ID
  winner; genuinely tied evidence pauses for the user.
- **Corrections:** an agent can record the observed mistake, evidence, likely
  cause, candidate repairs, and suggested fixer; peers agree on the repair
  and owner before the correction is applied.
- **`core/bin/ledger-collab` + `ledger-collab.ps1`:** POSIX and
  PowerShell helpers for atomic event creation and overlap/status inspection.
- **Schema and protocol:** both editions, kickoff, AGENTS digest, README,
  and schema now distinguish single-agent `tasks/current.md` locking from
  collaboration event coordination.

**Migration from 0.5.x:** none required for existing single-agent
projects. New bootstraps receive `memory/collaboration/README.md`; an
existing project that opts in copies that template into
`.context_ledger/memory/collaboration/` during its first collaboration session.
Core updates never touch memory. Event files are created only when a
project opts into collaboration.

## 0.5.0 — 2026-07-31

**The session-scoped memory release.** Session history is now self-contained
and disposable — separate from durable project knowledge — preventing
`.context_ledger/` bloat while preserving continuity.

- **New `memory/sessions/` module:**
  - `memory/sessions/SUMMARY.md` — compressed session history (~1 line
    per session, prunable). Unlike `agents/sessions.md` (append-only
    forever), entries here may be removed when a session is no longer
    useful. Future agents skim the last ~10 entries at startup for
    compact continuity.
  - `memory/sessions/<date>-N/notes.md` — per-session detailed notes
    (append-only while active, deletable after promotion). Optional — a
    trivial session creates no directory. Holds research, exploration,
    dead ends, and implementation reasoning that would otherwise bloat the
    global logs or the compact summary.
- **Context Promotion (new in Step 17 of both editions):** at session end,
  the agent evaluates session notes and promotes durable facts to their
  persistent domain (`decisions.md`, `backlog.md`, `inefficiencies/log.md`,
  `preferences.md`, `flaws/log.md`). The promotion invariant: **permanent
  context must never depend exclusively on an individual session** — a
  fact that matters beyond the session lives in its domain file, so
  deleting the session directory cannot delete the knowledge.
- **"Session data is disposable" principle:** enshrined in both editions
  (rule 7 of the `.context_ledger/` Rules) and in `memory/sessions/README.md`.
  Session directories may be deleted; SUMMARY.md entries pruned; the
  formal registry (`agents/sessions.md`) is the permanent record.
- **Three-layer model:** session detail (disposable) → session summary
  (prunable) → permanent registry (append-only). Together with the
  durable domain files, this gives a clean lifecycle: new information →
  session notes → summary → evaluate durability → promote or discard.
- **Schema:** new `sessions/` entries in `ledger-schema.md` and
  `ledger.schema.json`; reading order now includes `SUMMARY.md`.
- **Templates:** `memory/sessions/README.md`, `SUMMARY.md`, and `notes.md`
  added under `core/templates/memory/sessions/`.
- **Migration from 0.4.x:** none required. The `sessions/` directory
  appears on first use; existing memory files are valid as-is. The new
  `Notes:` line in `agents/sessions.md` entries and the `SUMMARY.md`
  append are additive — sessions on 0.4.x cores continue to work,
  upgrading when their project pulls 0.5.0.

## 0.4.0 — 2026-07-30

**The Windows release.** The tool no longer assumes a POSIX shell. Windows
agents run PowerShell, not `sh`, so a `sh`-only `ledger-sync` failed at
session startup (`verify`/`status`) with no fallback. This adds a
PowerShell port of the session commands.

- **`core/bin/ledger-sync.ps1` (PowerShell port):** covers the project-mode
  commands an agent hits inside a session — `status`, `verify`, `update`,
  `rollback`, `lock`. Requires PowerShell 5.1+ (`pwsh` or Windows
  PowerShell). Invoke as
  `pwsh -File .context_ledger/core/bin/ledger-sync.ps1 <cmd>`; the `--major`
  update gate is the `-Major` switch. Byte-compatible with the `sh` tool's
  `MANIFEST.sha256` (identical SHA-256 hashes, forward-slash paths), so a
  core verified on one platform verifies on the other.
- **Package-mode commands stay `sh`-only:** `manifest`, `bootstrap`, and
  `harvest` are not ported — the maintainer runs them from a package clone
  on macOS/Linux. The `.ps1` prints a pointer to the `sh` script if asked
  for one of them.
- **Docs:** `sh …/ledger-sync <cmd>` invocations across the kickoff,
  QUICKSTART, and schema now show the PowerShell equivalent for Windows.
- **Migration from 0.3.x:** none. The port is additive; existing projects
  gain `ledger-sync.ps1` on their next `update`. macOS/Linux behavior is
  unchanged.

## 0.3.0 — 2026-07-21

**The harvest release.** Closes the upstream loop the `flaws/` directory
only ever promised: project memory now flows back to the package
mechanically instead of by hand.

- **`ledger-sync harvest` (package mode):** run from a package clone, it
  reads `fleet.md`, reaches every listed project read-only (a sibling
  clone matched by remote URL, else a shallow clone), and collects three
  signals into `inbox/harvest-<date>.md` for triage — open `flaws/`,
  `Upstream: candidate` inefficiencies, and `[core-defect]` overrides. A
  committed ledger (`inbox/.harvested`) hashes each entry so re-runs never
  re-file it. Never writes to the projects.
- **Fleet registry (`fleet.md`, package root):** `bootstrap` now appends
  each new project's `origin` URL, so the package knows its own
  downstream repos. Append-only; idempotent on the URL.
- **Schema fields for harvest opt-in:**
  - `inefficiencies/log.md` gains an optional `**Upstream:** candidate`
    line — marks protocol-level friction for collection; project-local
    friction stays unmarked and unharvested.
  - `overrides/rules.md` bullets are now tagged `[core-defect]` (a local
    patch to a core bug — harvested) or `[project-local]` (legitimate
    project difference — never harvested). Overrides survive core bumps,
    so an untagged core-defect workaround would otherwise stay stranded
    in one project forever.
- **Migration from 0.2.x:** none required. The two template fields are
  additive and opt-in; existing memory files are valid as-is. Maintainers
  gain `fleet.md` + `inbox/` at the package root (bootstrap creates
  `fleet.md` on first use; back-fill older projects by hand).

## 0.2.0 — 2026-07-14

**The vendored-core release.** The protocol no longer lives in a sibling
clone — it travels inside every project as `.context_ledger/core/`, beside the
project's own memory in `.context_ledger/memory/`.

- **Two-zone layout:** `.context_ledger/core/` (package-owned, read-only,
  version-stamped) + `.context_ledger/memory/` (project-owned, writable, never
  synced). Replaces the basename-based structural/data split; `SYNC.md`
  is retired.
- **Memory modules move under `memory/`:** `agents/`, `tasks/`, `plans/`,
  `flaws/`, `inefficiencies/`, `reviews/`, `system/`, `user/`,
  `workflows/`, `secrets/` keep their names and formats — only the path
  prefix changes. `kickoff.md` and `README.md` stay at the `.context_ledger/`
  root as the front door and zone map.
- **New memory modules:** `memory/overrides/rules.md` (project-local
  protocol adjustments, read after the edition) and `memory/core.lock`
  (last-known-good core version, written by `ledger-sync`).
- **Unified schema:** `core/schemas/ledger-schema.md` (+
  `ledger.schema.json`) is now the single authority on every memory
  file's format, write mode, ownership, and fact scope — including the
  per-agent-type vs per-project vs per-machine scoping rules that stop
  cross-agent-type contamination.
- **`core/bin/ledger-sync`:** POSIX-sh tool — `status`, `verify`,
  `update`, `rollback`, `bootstrap`. Startup change detection, checksum
  integrity via `core/MANIFEST.sha256`, git-based rollback to the
  locked version.
- **Weak-agent translation layer:** bootstrap generates a root
  `AGENTS.md` digest (from `core/templates/AGENTS.md`) so agents that
  never read a 900-line edition still learn the zones, the entry point,
  and the binding rules.
- **Cloud sessions need no package access after bootstrap** — the
  protocol is on disk inside the project. Package PATs are a
  bootstrap-only concern.
- **Migration from 0.1.x:** see `MIGRATION.md` in the package repo.
  Summary: create `memory/`, `git mv` the modules into it, vendor
  `core/`, regenerate `kickoff.md`, delete `SYNC.md`.

## 0.1.0 — 2026-07-13 (retroactive)

The sibling-clone era: two protocol editions at the package root,
`context-skeleton/` bootstrapped into projects as a flat `.context_ledger/`,
structural-vs-data sync per `SYNC.md`, package cloned beside every
project as `../context`. Never formally released; version assigned
retroactively as the baseline `MIGRATION.md` migrates from.
