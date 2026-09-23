# Project Kickoff — `.context_ledger/` Workflow Entry Point (Inbound)

<!-- GENERATED AT BOOTSTRAP — the universal kickoff's bootstrap step fills
this in. This file is project DATA: core updates never overwrite it. If
its template (.context_ledger/core/templates/kickoff.md) materially changes in a
core release, the next session regenerates it and refills the facts.

Generation rules for the bootstrapping agent:
1. Fill every fact <PLACEHOLDER> OUTSIDE this HTML comment — in "Project
   Facts", in the intro blockquote (the clone URL), AND in the Entry
   Steps code blocks — from the external kickoff's Pre-Flight + what you
   verified on disk (git remote, default branch). Facts you verified
   beat facts the user typed — record what's true. The ONLY placeholders
   that stay symbolic are the token forms
   (`<..._WITH_TOKEN_IF_PRIVATE>`, `${GIT_TOKEN}`) — never a real token.
   After filling, scan:
   `grep -n "<PROJECT\|<GIT_\|<LIVE_\|<REPO>" .context_ledger/kickoff.md` —
   hits are allowed only inside this comment and in the token forms.
2. Do NOT copy session parameters here — they live in
   memory/workflows/active.md (single source of truth). This file only
   points at them.
3. Do NOT put secrets, PATs, or tokens anywhere in this file. Ever.
4. Delete nothing else — the Phases below are pre-written and
   correct for every post-bootstrap session. Fill their fact
   placeholders (rule 1) but change no step logic.
5. Keep facts current in later sessions: if a fact changes (repo renamed,
   new default branch, live URL added), update it in place and note the
   change in your session entry.
-->

> **This is the project's own kickoff file — the front door for every
> session.** The full protocol is vendored inside this repo at
> `.context_ledger/core/` — nothing needs to be cloned or fetched to run a
> session. To start one, point any agent here:
>
> - **Local agent** (already inside the repo): *"Read `.context_ledger/kickoff.md`
>   and follow it."* Add a target description in the same message if you
>   have one.
> - **Cloud/sandbox agent** (empty workspace): *"Clone
>   `<PROJECT_REPO_URL>`, read `.context_ledger/kickoff.md`, follow it."* If the
>   project repo is private — or the session will push (it will) — paste
>   a PAT for **this project repo** in that same chat message. That is
>   the only credential any session needs: the protocol is already in
>   the repo.

---

## Project Facts (generated — keep current)

- **Project name:** <PROJECT_NAME>
- **Project repository URL:** <PROJECT_REPO_URL>
- **Project repo privacy:** <Public / Private>
- **Default branch:** <main>
- **Live application:** <LIVE_URL or N/A>
- **Git identity:** <GIT_NAME> `<GIT_EMAIL>`
- **Protocol:** vendored at `.context_ledger/core/` (version: see `.context_ledger/core/VERSION`)
- **Package upstream (core updates + flaw back-ports):** <https://github.com/TisoneK/context-ledger.git or fork/mirror URL>
- **Edition routing:** local agents → `.context_ledger/core/rules/ai-engineering-protocol-local.md`; cloud/sandbox agents → `.context_ledger/core/rules/ai-engineering-protocol.md`

## Session Parameters

Standing defaults live in
[`memory/workflows/active.md`](memory/workflows/active.md) — scope,
target, push policy, deliverable, commit style. **A target in the
user's chat message overrides the standing Target.** If the chat
message is just "start," use the standing Target.

**Agent identity:** never guess your model version. If your system
prompt states the exact model ID, record that; otherwise ask the user
once, or record `unknown`.

---

## Phases (every session after bootstrap)

Six phases, in order. **Each names exactly what to read or run** — the
how and why live in exactly one place each (the file named), not restated
here. This is deliberate: a fresh session used to pay for the check-in
ceremony, the reading order, and the gate rules being explained three
times over (this file, `AGENTS.md`, the edition) before any real work
started. Now each of those is written once, and this file's only job is
routing to the right one at the right moment.

**Execute each phase before reading the next one — do not read this
whole file front-to-back first and start acting afterward.** If you
arrived here already having skimmed Phase 3 or later, stop: go back and
push Phase 2's check-in now, from what you already know, before reading
any further. Reading ahead (the full edition before checking in, the
rest of these phases before checking in) is exactly how two sessions
collide on a codename — the check-in is a write these phases are
building up to, not a topic covered somewhere in the reading.

### Phase 0 — Identify

- **Local agent** — you are already inside the repo. Confirm:
  `git remote get-url origin` matches the Project repository URL.
  **Never re-clone the project. No PAT, ever** — your pushes use the
  user's own credentials; if one fails with an auth error, stop and
  tell the user.
- **Cloud/sandbox agent** — clone the project repo only:

  ```bash
  # If private: PAT from chat — strip it from .git/config right after.
  # A missing credential is a missing input: if the repo is private (or
  # you'll push, which you will) and no PAT arrived in chat, ask NOW.
  git clone <PROJECT_REPO_URL_WITH_TOKEN_IF_PRIVATE> <REPO> && cd <REPO>
  git remote set-url origin <PROJECT_REPO_URL>
  git config user.name "<GIT_NAME>" && git config user.email "<GIT_EMAIL>"
  ```

There is **no package repo to find, clone, or authenticate against** —
the protocol travels inside this repo at `.context_ledger/core/`.

### Phase 1 — Sync

```bash
git pull --ff-only
```

If the pull fails (diverged) or the tree has changes you didn't make,
**stop and report** — don't stash or discard someone else's work.

Then check the vendored protocol (never fatal — a session must never
fail over sync):

```bash
sh .context_ledger/core/bin/ledger-sync verify    # integrity: core matches its MANIFEST
sh .context_ledger/core/bin/ledger-sync status    # drift: is a newer core available?
```

On **Windows** (no POSIX shell) run the `.cmd` launcher instead — it runs
the `.ps1` port with `-ExecutionPolicy Bypass` (same commands, same output):

```powershell
.context_ledger/core/bin/ledger-sync.cmd verify
.context_ledger/core/bin/ledger-sync.cmd status
```

- `verify` fails → core was hand-edited or corrupted. Run
  `sh .context_ledger/core/bin/ledger-sync rollback` (Windows:
  `.context_ledger/core/bin/ledger-sync.cmd rollback`), log a flaw in
  `memory/office/flaws/log.md`, continue on the restored core.
- `status` reports a newer core with the **same MAJOR** → run
  `sh .context_ledger/core/bin/ledger-sync update` (Windows:
  `.context_ledger/core/bin/ledger-sync.cmd update`) — it replaces `core/` only,
  memory is never touched — then commit as
  `chore(ledger): update core to <version>`, and read the new
  `core/CHANGELOG.md` entries.
- A **MAJOR** bump, or no update source reachable → note it in your
  session entry and move on with the core you have.

### Phase 2 — Check in

**Before the deep read, before analysis, before product work.** Needs
only two files: `memory/office/agents/roster.md` (the board) and the last
entry of `memory/office/agents/sessions.md` (the next free session
number). Pick a real name (not your own model/product name — see the
roster's own header), add your row, commit and push it now:
`chore(ledger): <name> (<codename>) checks in — <task>`. Then regenerate
the session digest for Phase 3:

```bash
sh .context_ledger/core/bin/ledger-state generate
git add .context_ledger/memory/office/STATE.md
git commit -m "chore(ledger): regenerate STATE.md at check-in" && git push
```

Full rules for names, codenames, roster-edit etiquette, and identity
(never infer one from a model-string match) live in `ledger-schema.md` →
"The live office" table and "Office lifecycle" — this file only tells you
*when*, not *how*; don't re-derive the how here.

**Office past `office_size` sessions (default 20)?** It's full — close it
now, as part of check-in, before the deep read:
`sh .context_ledger/core/bin/ledger-history close` (dry run, then
`--confirm`). Full re-seed rules: `ledger-schema.md` → "Office lifecycle,"
"The door trigger."

### Phase 3 — Orient

Read **`memory/office/STATE.md`** — one digest standing in for the eight
files it summarizes (standing params, roster, current task, backlog High
rows, flaws/inefficiencies/decisions counts). Open the file behind a line
only when your task needs more than the summary gives it; full reading
order and "when does this file earn a closer look": `ledger-schema.md` →
"Reading order (session start)".

Always still read in full, regardless of `STATE.md`: `memory/overrides/rules.md`,
`memory/workflows/gates.conf`, `memory/collaboration/README.md` (+ active
events, if collaboration is enabled), `memory/system/`, `memory/user/`.
Note what's in `memory/secrets/` — never print values.

**Decide the mode from evidence.** Solo only if: no shared collaboration
`session`+`issue` was declared, the roster shows no live row you didn't
write, and `office/tasks/current.md` is idle. Otherwise coordinate — join
or declare a `collab/<session-id>/coordination` branch, isolated
worktree/branch, `note` + `claim` before editing. Full rules (a peer's
live row, overlapping claims, the event commands, tear-down):
`ledger-schema.md` → "Peer collaboration" and `memory/collaboration/README.md`.

### Phase 4 — Load the protocol, scaled to the task

Pick the edition by **your agent type** (Phase 0) — never by what memory
says:

- **Local agent** → `.context_ledger/core/rules/ai-engineering-protocol-local.md`
- **Cloud/sandbox agent** → `.context_ledger/core/rules/ai-engineering-protocol.md`

Read its always-relevant core (Binding Rules, Two Surfaces, Peer
Collaboration, Gate Protocol, Git Workflow, Quality Gates, and the
Playbooks index) — a short, fixed read regardless of task size. Then load
only the playbooks your task's shape actually calls for:

| Your task… | Also read |
|---|---|
| Touches product code at all, however small | `core/rules/playbooks/code-review.md` — the baseline checklist, not optional (this row replaces "nothing more": v1 read it unconditionally for every session and that guarantee is worth keeping even after the extraction) |
| Is a UI/UX change | + `core/rules/playbooks/ux-review.md` |
| Touches security-sensitive code | + `core/rules/playbooks/security-review.md` |
| Is a new feature or a substantial review | + `functional-testing.md` |
| Touches performance-sensitive code | + `core/rules/playbooks/performance-review.md` |
| Touches `.context_ledger/core/` itself, or spans multiple sessions | every playbook — read the edition in full |
| Hit a snag partway through | the edition's own **Common Pitfalls** section — it stayed inline, so this row does not point at a separate playbook file |

Also read any role overlay from `.context_ledger/core/roles/` and the
project's `memory/overrides/rules.md` (overrides beat the edition, except
secret-handling and append-only rules).

### Phase 5 — Execute

Follow your edition's own phases in order — don't skip its Setup/Review/
Fix/Report sequence because the task seems small. Before each next
action, checkpoint; before commits, integration, and exit, run the
matching gate:

```bash
sh .context_ledger/core/bin/ledger-gates checkpoint [--session <SESSION_ID> --issue <ISSUE_ID>]
sh .context_ledger/core/bin/ledger-gates run pre-commit
sh .context_ledger/core/bin/ledger-gates run integration --session <SESSION_ID> --issue <ISSUE_ID>
sh .context_ledger/core/bin/ledger-gates run exit
```

(Windows: the `.cmd` launchers, same commands.) A failing gate blocks the
next lifecycle transition; record the exact failing command and output in
the session notes or event trail. Registry missing? `ledger-gates init`.

### Phase 6 — Exit

Not done until:

1. Everything is committed **and pushed**.
2. The session is logged in `memory/office/agents/sessions.md`.
3. `memory/office/tasks/current.md` is cleared (single-agent mode).
4. `sh .context_ledger/core/bin/ledger-mem prune` has been run — a
   report-only nudge; archive anything it flags eligible
   (`ledger-mem prune --apply` does the move for you).
5. `sh .context_ledger/core/bin/ledger-state generate` has been run once
   more — the digest should reflect this session's outcome for whoever
   reads it next.
6. You clock out: remove your row from `memory/office/agents/roster.md`
   in the closing commit — but only when actually leaving. The session
   isn't over until the user says so; if more work arrives after
   clock-out, check back in first (same name and codename) and extend
   your existing `sessions.md` entry, never open a second one.

If the user has to remind you to commit or push, that is a protocol
failure — log it in `memory/office/flaws/log.md`.

---

## If this file is stale or missing

The template lives inside this repo at
`.context_ledger/core/templates/kickoff.md`. Regenerate by copying that
template over this file and filling **Project Facts** from memory
(`memory/user/identity.md`, `memory/workflows/active.md`,
`git remote get-url origin`). Commit as
`chore(ledger): regenerate kickoff.md`.
