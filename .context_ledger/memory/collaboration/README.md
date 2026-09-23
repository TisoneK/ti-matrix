# Peer Collaboration

This directory is the shared coordination surface for multiple agents
working on one issue or project session. It is **opt-in**: when no
collaboration session is declared, the normal single-agent workflow and
`tasks/current.md` lock still apply.

**Solo sessions use the same light path.** The event tools are
mode-agnostic: when no collaboration session is declared, your session
still writes a `claim` (with `--paths` for the task scope) at start and
a `release` (citing the product commit) at close into this same
`events/` directory, committed with your normal `chore(ledger):` memory
commits on the shared branch — `session` is your roster codename
(`S<NNN>`) and `issue` a short task slug. Notes are collaboration
politeness; solo, claim + release is the whole ceremony. The point is
arrival safety: any agent that walks in mid-session sees your live
scope — paths and all — on the board, in any mode.

**You and your teammates are one team with one goal — the working
product — and the human is your supervisor.** You are not bidding against
each other and there is no prize for being first. Think of it as a
workplace: you say out loud what you're picking up, you leave a quick note
when something might affect a coworker, you glance at what others are doing
before you start, and when two of you disagree you compare notes and pick
the stronger option *together*. Most coordination is just talking. The
heavier machinery below (proposals, assessments, agreements) is the
escalation for a genuine conflict, not the everyday path.

## Who you are — pick a name

You are a person on this team, not an anonymous ID. You already signed
`../office/agents/roster.md` at session start — **every session does, solo or
not** (see the protocol's check-in step): a real name you choose, your
codename `S<NNN>` (your session number), your model, and one line on what
you're doing. Edit your row's "Doing" cell as your work changes, and
remove the row (clock out) in your closing memory commit. From then on,
**present yourself by that name** in every
event you emit and when you report to the supervisor: `John (S427)`, never
"peer" or a bare model id. Your name and codename are each unique within
the group — if a name is taken, pick another; there is only one John on the
team at a time. `ledger-mem check` flags a clash. The roster is the board
by the door: who's in, and what they're on.

**You are a new arrival until you register.** Never "recognize yourself"
in a row that already exists: a matching model string (or harness UUID)
is not identity — model IDs and harness markers are shared by every
session on that harness or model, so two peers can honestly list the
same model. If your name is on the board without your having signed in
this session, treat it as a peer who happens to share your fingerprint:
pick a fresh name and codename `S<NNN>`, write your own row, and leave
theirs (and their working tree) alone. "That row is mine" is true only
with continuity in your own session — you clocked out earlier in this
same conversation and are checking back in — or when the user says so.

## Goals

- let agents talk — a lightweight `note` is the office channel, so a
  heads-up, a hand-off in plain words, or a peer review has a home that
  isn't a shared file or a heavyweight formal event;
- let agents work concurrently without sharing a mutable working tree;
- make what each agent is doing, and any overlap, visible to every peer;
- when changes genuinely conflict, let peers compare evidence and converge
  on the best option before either applies it;
- let an agent flag a mistake with its cause and proposed repair, and let
  the team settle who fixes it;
- preserve a durable, reviewable trail after agents or sessions disappear.

## The light path and the escalation

Reach for the lightest thing that works:

1. **Say what you're on.** A `note` ("I'm taking the web_acquisition
   timeout; leaving the loop to whoever has it") costs one line and keeps
   peers from colliding with you.
2. **Claim your scope, do the work, release it.** `claim` → work →
   `release` (citing the commit) is the whole lifecycle for the common
   case — non-overlapping work, or work no one else has touched. This is
   the same shape as single-agent mode, plus visibility.
3. **Reviewing a peer's diff?** That's a `note --re <their-claim>`, not a
   competing `proposal`. Praise, concerns, and suggestions are just talk.
4. **Only when two changes genuinely conflict** — the same paths with
   incompatible edits — escalate to `proposal → assessment → agreement`.
   That ceremony exists to resolve a real disagreement fairly; it is the
   exception, and if you open it you finish it.

## Required workspace topology

Each agent gets its own product worktree and branch. Never have two
agents edit the same checkout or push product commits directly to the
shared branch during collaboration.

Coordination events are published to one shared, event-only branch:
`collab/<session-id>/coordination`. This is a shared bulletin board, not a
coordinator: every event is a new file, and a non-fast-forward push is
resolved by rebasing while preserving every event file. Keep a separate
coordination worktree when possible.

```text
project/                              # integration checkout, normally idle
project-agent-a/                      # collab/<session>/<agent-a> (product)
project-agent-b/                      # collab/<session>/<agent-b> (product)
project-collab-session/               # collab/<session>/coordination (events only)
```

Start from a fresh, synchronized base. A typical local setup is:

```bash
git fetch origin
git worktree add ../<project>-<agent-id> \
  -b collab/<session-id>/<agent-id> origin/main
git worktree add ../<project>-collab-<session-id> \
  -b collab/<session-id>/coordination origin/main
```

The first agent publishes the coordination branch; later agents fetch it
and use the same coordination worktree or rebase their event-only branch
onto it. Cloud agents normally get product isolation from separate
clones; they must still publish/fetch the shared coordination ref.

**Teardown — the topology is rented, not owned.** After your final
`release` and the integration of your product branch, remove the product
worktree you created and delete your branch: run `git status` inside the
worktree (clean it or stop if changes are unexplained), then
`git worktree remove ../<project>-<agent-id>` and
`git branch -d collab/<session-id>/<agent-id>` (`-d` refuses an unmerged
branch — that refusal is the safety net; use `git push origin --delete`
too if you pushed the branch). A worktree left behind is a trap: stale
checkouts claim locked files and "unexpected working-tree changes" for
the next session. Never remove another agent's worktree. The
coordination *worktree* may be removed by the last agent to leave (the
next session re-adds it from the branch in one command); the
coordination *branch* is the session's event trail — later agents fetch
it to continue the session — so it is not deleted while the session can
resume. If a worktree directory was already deleted by hand, run
`git worktree prune` so the stale registration doesn't linger.

## Event files are immutable

Every coordination event is a new file under `events/`:

```text
collaboration/
├── README.md
└── events/
    └── <event-id>.json
```

Never edit an event after publishing it. If it is wrong, emit a new
`correction` event that references it. One file per event is deliberate:
two agents can publish at the same time without appending to one shared
log and creating an EOF merge conflict. Commit and push event files
separately from product changes using `chore(ledger):`.

The optional helper creates valid event files atomically:

Pass your chosen name as `--agent` so the trail reads as people. Below,
`John` is the name this agent picked in the roster:

```bash
# a quick word to a coworker (the office channel) — no ceremony:
sh .context_ledger/core/bin/ledger-collab emit note \
  --session <session-id> --agent John --issue <issue-id> \
  --to Ada --re src/auth.py \
  --body "Taking the token-refresh path; leaving the session store to you."

# claim scope, then release it citing the commit:
sh .context_ledger/core/bin/ledger-collab emit claim \
  --session <session-id> --agent John --issue <issue-id> \
  --paths src/auth.py,tests/test_auth.py --body-file /path/to/claim.md
sh .context_ledger/core/bin/ledger-collab status --session <session-id> --issue <issue-id>
sh .context_ledger/core/bin/ledger-collab check --session <session-id> --issue <issue-id>
```

`status` opens with a **Recent chatter** feed of the notes — read it first
to catch up, the way you'd skim a team channel. A `note` never gates
`check` and never needs to be "resolved"; `--to` and `--re` are optional.

`status` is for live work. `check` is the integration-readiness gate and
fails if metadata or references are invalid, claims overlap, agreements are
incomplete, corrections or handoffs remain unresolved, or releases do not
cite a product commit.

On Windows, use the PowerShell port:

```powershell
.context_ledger/core/bin/ledger-collab.cmd emit claim `
  --session <session-id> --agent <agent-id> --issue <issue-id> `
  --paths src/auth.py,tests/test_auth.py --body-file C:\path\claim.md
.context_ledger/core/bin/ledger-collab.cmd status `
  --session <session-id> --issue <issue-id>
.context_ledger/core/bin/ledger-collab.cmd check `
  --session <session-id> --issue <issue-id>
```

The helpers are conveniences; the event contract is authoritative.

## Event contract

Each event is one immutable JSON document (`collab-event.schema.json` v1):

```json
{
  "schema": 1,
  "id": "<UTC-timestamp-agent-random>",
  "type": "note | claim | proposal | assessment | agreement | correction | handoff | release",
  "session": "<shared-collaboration-session-id>",
  "agent": "<stable-agent-id>",
  "created": "<UTC timestamp>",
  "issue": "<shared-issue-id>",
  "body": "<evidence, reasoning, trade-offs, and next action>",
  "paths": ["<repo-relative paths claimed or affected>"],
  "refs": ["<event IDs or commit SHAs cited>"],
  "option": null,
  "selected": null,
  "owner": null,
  "participants": []
}
```

`id`, `type`, `session`, `agent`, `created`, `issue`, and `body` are
always present. Type-specific requirements: `paths` (non-empty) for a
`claim`; `option` for a `proposal`; `refs` for an `assessment`,
`agreement`, `correction`, `handoff`, or `release`; an `agreement` also
requires `selected`, `owner`, and at least two distinct `participants`.
A `note` requires none of the type-specific fields — a body is all it
needs. The full document schema is `core/schemas/collab-event.schema.json`.
Legacy markdown events (`<event-id>.md`, written by pre-0.22.0 cores) are
still read by `status` and `check` — never rewritten.

### Event meanings and lifecycle

The everyday event is **note**; the rest are the formal trail.

0. **note** — the office channel. Say what you're picking up, drop a
   heads-up that might affect a teammate, or review a peer's diff. A note
   carries no obligation: no required `refs`, `owner`, or `participants`,
   and it never gates `check`. Optional `--to <peer>` addresses it;
   optional `--re <event|path|commit>` points at what it's about. When in
   doubt, a note is the right first move.
1. **claim** — state the issue, paths or logical scope, intended change,
   current hypothesis, and why the scope is safe to take. Claims are
   advisory, not locks. Re-read the latest events before editing.
2. **proposal** — *(escalation, for a genuine conflict only)* present one
   concrete option, evidence, affected paths, trade-offs, risks, and how it
   will be verified. You reach for a proposal when two changes genuinely
   conflict and the team needs to choose — not to review or to suggest
   (that's a note). When peers do propose alternatives, they are
   teammates converging on the best answer, not rivals.
3. **assessment** — compare the referenced proposals against the same
   criteria: correctness, regression risk, compatibility, simplicity,
   and verification evidence. Recommend one and explain why; include
   dissent if the evidence is inconclusive.
4. **agreement** — record the option peers accepted, the reasoning that
   makes it best, all participants who accepted it, and exactly one
   implementation owner. No agent applies a conflicting proposal before
   this event is visible.
5. **correction** — report a suspected mistake by referencing the claim,
   proposal, agreement, or commit; state the observed symptom, evidence,
   likely root cause, candidate repairs, and suggested owner. A correction
   does not unilaterally reassign work.
6. **handoff** — transfer an agreed scope to another agent, referencing
   the agreement and stating what is complete, pending, and verified.
7. **release** — declare a claim or handoff complete, referencing the
   relevant event and commit(s), with verification results.

### Peer agreement rule

This is for a real conflict, and the goal is the best answer for the
product, not a winner. There is no coordinator and no timestamp/priority
tiebreak. When options genuinely conflict, each involved agent reads the
alternatives, independently checks the evidence, and records an
assessment — the way colleagues talk a decision through. Peers converge on
the option with the strongest total case, not the one proposed first, and
not "yours" vs "mine". The agreement event is the authority for
implementation and must name the owner. If evidence stays genuinely tied,
record the disagreement in an assessment, pause the conflicting edit, and
ask the user to decide; never silently choose based on agent ID or
arrival time.

For a discovered mistake, the finder proposes the cause and repair in a
`correction`; the original author and/or affected peers assess it; an
`agreement` selects the best repair and owner. The owner then emits a
`release` after re-reading the corrected code and running the relevant
checks.

## Synchronization rules

- Fetch the shared coordination ref before reading collaboration state;
  publish claims and proposals before product edits, then fetch again
  before applying an agreement. If the coordination branch moved, rebase
  and preserve all event files before retrying the push.
- Product commits stay on the agent branch. Event commits stay separate on
  `collab/<session-id>/coordination` and can be merged without combining
  product and memory surfaces.
- A claim is not active after its scope is released or handed off. A peer
  who changes scope emits a new claim rather than editing the old one. A
  `release`/`handoff` closes a claim when it cites the claim's event ID
  **or** simply shares the claim's session + issue and overlaps its paths —
  so citing only the commit SHA still closes the claim. Cite the claim
  event ID when you can (it makes the trail explicit), but you won't strand
  a claim as "active forever" by citing only the commit.
- Coordination event files (including notes) are parsed line by line by the
  helpers. Keep them LF: the shipped `.context_ledger/.gitattributes` enforces
  `eol=lf`, which also keeps the append-only memory logs from showing
  phantom whole-file diffs on Windows.
- Non-overlapping scopes may proceed concurrently. Overlapping paths,
  shared interfaces, migrations, lockfiles, and generated files are
  conflicts even when the files differ; negotiate them explicitly.
- At integration time, merge/rebase each product branch into the shared
  branch in dependency order. Never force-push over a peer's work.
- Normal durable files (`tasks/backlog.md` — a capped work queue, delete
  a row when its item is done, overflow to `tasks/parking-lot.md` —
  `plans/decisions.md`, and
  session logs) are updated after the collaboration event trail is
  published. If two agents need the same durable file, one agent owns
  that update or peers merge it after rebasing; do not use those files as
  the live coordination channel.

## Session identity

All agents fixing the same issue at the same or different times reuse the
same `session` and `issue` values. A later agent starts by fetching the
existing events, emits a new claim or handoff, and continues the trail.
Different issues may share a session only when their scopes do not overlap.
Use a stable, non-secret ID; never put credentials or private tokens in an
event body.
