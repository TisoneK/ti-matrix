# Design notes

> In Python everything is an object. Here, everything the engine knows is a state — and everything else is a
> transition into one, or a pure function that reads one.

Why Ti Matrix is shaped the way it is. The [README](README.md) says what it does and how to use it; this says what
each choice was made *against*. It is the long form of reasoning that would otherwise live in commit messages.

- [The loop](#the-loop)
- [The state is the engine's](#the-state-is-the-engines)
- [Ending honestly](#ending-honestly)
- [The Context Ledger: read as an environment, write as a host](#the-context-ledger-read-as-an-environment-write-as-a-host)
- [The browser: what counts as a read](#the-browser-what-counts-as-a-read)
- [Several sources of tools, and who wins](#several-sources-of-tools-and-who-wins)
- [Learning across runs, as arithmetic](#learning-across-runs-as-arithmetic)
- [Two stores, and the one word they share](#two-stores-and-the-one-word-they-share)
- [The benchmark, and its control](#the-benchmark-and-its-control)

## The loop

```
Goal ─► State ─► Proposer ─► candidate Actions ─► Environment.probe    (or Simulator.predict)
                                                        │
                                        Evaluator ◄─────┘   one call scores every outcome
                                            │
                              the search (beam of one + backtracking) ─► Transition ─► new State
                                            │
                                  TerminalCondition decides when it is over
```

- **The state is the engine's.** `AgentState` is immutable — the goal, the facts real observations established, the
  actions that failed, the path taken, progress and depth — rendered compactly for the model with no chat history,
  and fingerprinted so an action that failed is never proposed twice.
- **Probing is real.** A read-only action is performed and its actual output recorded. Nothing is invented.
- **Scoring is one call per fan**, with deterministic guards: a failed probe never counts as progress, and `done`
  requires an answer grounded in facts.
- **Backtracking keeps what was learned.** When nothing beats where the state stands, the engine retreats to the
  parent state with every real fact intact and the action that led into the dead end pruned.
- **An action that must not be performed is predicted, not performed** (`Simulator`): the prediction is labelled,
  never learned as a fact, and can never settle the goal — a run that needs one stops and names it.
- **Every step is an event.** `EngineEvent`s (`state`, `candidates`, `probe`, `evaluation`, `selected`, `backtrack`,
  `needs_confirmation`, `done`, `stopped`) are the whole record, so any interface — a CLI, a web UI, a game-tree
  explorer — can be built on them without reading the engine's internals.

## The state is the engine's

An agent that improvises each step inside a growing conversation forgets, drifts and promises. This one does
neither: the state is rebuilt from real observations, never from the model's memory of a chat, and the model is
never asked what it has already learned. That is why `AgentState` is immutable and why a transition returns a new
one — the search can then hold several states at once, compare them, and retreat to a parent without any state
having been mutated out from under it.

Two mechanical consequences carry most of the weight. Facts are appended only when a probe really ran and really
succeeded (`obs.ok and not obs.predicted`), so nothing enters the state that was not observed. And every action's
fingerprint is remembered, so an action that failed is never proposed twice — a dead end costs one probe, not one
per turn.

The state is also rendered *compactly* for the model: the goal, the progress, the last few facts, the recent trail.
Bounding the view is not tidiness, it is the mechanism — there is no history to grow, so a long run does not get
more expensive to describe.

## Ending honestly

A run that cannot settle its goal says so: `settled: false`, a reason (`no_progress`, `no_moves`, `budget`,
`needs_action`, `proposer_error`), and whatever facts it did establish. This is the property the rest of the design
is arranged around, because the alternative — a confident answer the engine cannot ground — is worse than no answer.

Two decisions follow from it. A predicted outcome can never settle a goal, so an action the host withheld produces
`needs_action` naming that action rather than a guess about what it would have shown. And the budget is a hard
limit, not a target: `EngineBudget` counts depth, branches, model calls and backtracks, and the engine stops when
one runs out instead of quietly continuing.

## The Context Ledger: read as an environment, write as a host

The engine's state dies with the run. That is what keeps it honest — nothing is remembered that was not observed —
and it is also its one blind spot: the next run starts from nothing. A repository that keeps a
[Context Ledger](https://github.com/TisoneK/context-ledger) already holds that memory as plain markdown in git: the
task in flight, the decisions in force, which approach already failed, what the last sessions hit.

The adapter closes that loop in the two directions the ledger's own rule asks for — *start by reading the ledger,
finish by updating it* — and the asymmetry between reading and writing is the design decision.

**Reading is an environment.** Nine read-only actions over the vault, so a run can look anywhere in a project's
memory and change nothing. The ledger's write actions are declared too, marked not-read-only, so the engine reasons
about them (or asks) and never performs one. Declaring them matters: a boundary that only omits what it cannot do is
indistinguishable from one that has not thought about it.

**Writing is a recorder, not an action.** `LedgerRecorder` is deliberately *not* an Environment action: the host
hands it the run's events and it appends what the run established. An action is something a model may propose and
the engine may search over; a write to a project's durable memory is not that. Making it an action would put the
vault inside the search space.

Nothing is invented and nothing is overwritten. Every write lands in a file the vault's schema already defines, in
the ledger's own entry format — appended, or inserted as a row in the table that owns that kind of knowledge. A
vault that is missing its notes file, or its Findings table, is reported rather than patched: those shapes belong to
the schema, not to this adapter. And the adapter never initialises a vault; bootstrapping is the ledger's own
bootstrapper's job.

A run that does *not* settle its goal records that too. The ledger's most valuable entries are the traps and the
dead ends — "which approach already failed" is the thing the next agent cannot re-derive — so a run that says
plainly what it tried and could not do is worth more than one that sounds confident.

## The browser: what counts as a read

The classification is the one question this project asks everywhere else: does performing it hand the run something
to observe, or does it change the world it is observing?

A HAR file, a trace and a screenshot are reads. So are a page comparison and a console dump. Not reads: the mouse,
the clipboard, `batch` (whatever it contains), `eval`, anything that configures the browser rather than observing
it, anything that reaches outside it — `plugin_add` and `plugin_run` install and execute external code; `auth_save`
and `auth_login` write credentials — and `confirm`/`deny`, because approving an action is not observing one.

That is why `BrowserEnvironment` performs eleven of seventeen actions and refuses the other six unless the host
grants them by name, and why the `agent-browser` CLI's 76 actions split **39 read / 37 change something** with the
same rule. `perform={"all"}` is the difference between an engine that can look at a page and one you have handed the
machine.

A password never travels through an action's arguments. `auth_save` takes the *name* of an environment variable and
pipes the value in on stdin, so it reaches neither the model, nor the event log, nor `ps`.

There is nothing to install for the browser layer. Chrome's DevTools Protocol is JSON over a WebSocket, and neither
is in the standard library — so `websocket.py` (RFC 6455: the handshake, the frames, ping and close) and `cdp.py`
(start Chrome, find its pages, drive one) are part of this package rather than dependencies of it. A launch is a
`subprocess` call and discovery is an HTTP GET. Each `agent-browser` action runs in a session of its own, so a run
cannot navigate away from a page you left open.

Two limits stated plainly. **A screenshot is for a person**: the evaluator is a text model, so a screenshot's fact
is its path and size — a multimodal host can read the file, and nothing here pretends a PNG is text. And **do not
put a browser behind the cache** without a version token taken from the page: a page moves, and a remembered probe
would answer about a page that no longer exists.

One more piece of ownership, since it destroys data when it is wrong: a profile the host names with
`user_data_dir=` belongs to the host. `close()` removes only the throwaway profile it created itself, and decides
that by remembering whether it made one — not by looking at where it sits, because a host's profile under the temp
directory is still the host's.

## Several sources of tools, and who wins

An environment supplies its own actions, and for one environment that is the whole story. The moment there is more
than one source — a shipped environment, your application's actions, the engine's own memory tool — something has to
decide what the model is shown when two of them offer the same thing. `ToolSet` decides, by rules you declare rather
than rules it guesses:

- **A name decides.** Two tools sharing a name are the same tool as far as any model can tell.
- **Preference is declared.** Your tool beats a built-in by default (`prefer="user"`), or the other way round
  (`prefer="builtin"`), and a replacement that is named differently says what it replaces:
  `ActionSpec("read_local_file", ..., supersedes="read_file")`.
- **The resolution is a record.** `resolution()` reports what was kept, renamed and dropped, so the model's tool
  list is never a mystery you have to guess at. `require(*names)` fails loudly when a run depends on a tool the set
  does not carry.

`EngineTools` is where "mandatory" lives, and it is deliberately a wrapper rather than an obligation on
environments: the one tool the engine insists on is `recall` — what its own previous runs established about this
world — and it is added around whatever environment you already have. Everything else stays the environment's
business.

A tool that loses a collision needs no new engine behaviour at all: it is simply absent from the tools the model is
shown, and an action the environment does not know is already remembered as a failed move. This is what the tool
registry is for rather than an alternative to it — the package does not reimplement axe-core, the React DevTools
protocol or network interception; it exposes what you already have as actions an engine can search over, judge,
refuse and learn from, and keeps its own dependency-free environment for everything that does not need them.

## Learning across runs, as arithmetic

The engine remembers within a run and forgets between them: `AgentState` is built fresh for every goal, so a cold
start re-proposes the action that failed twice yesterday. `ti_matrix.learning` is the fix, and it is arithmetic on
purpose — every number is a count derived from an event the engine already emitted, never a sentence a model wrote
about itself. That is the same promise the state makes, applied across runs instead of within one: `Observation.ok`
is trusted, and `Evaluation.reason` is not even read.

Three wrappers spend that record, each of which a caller can turn off:

- **`LearningProposer`** asks for a couple more candidates than the fan needs. This is the one that makes the rest
  matter: a proposer cuts its own list to the fan size before anyone sees it, so by the time experience could
  reorder the candidates, the useful ones may already be gone. Asking for two more costs output tokens inside the
  same model call, not another call. It drops tools that have never once worked here and orders the rest by prior —
  with an untried tool sitting neutrally in the middle rather than last, because exploring is not a mistake. One
  floor, because the alternative is worse than either: if filtering would leave the fan empty, the best candidate
  the model offered is kept. A learner that answers "nothing is worth trying" to a goal the model had a plausible
  idea for has made the engine worse, not smarter.
- **`CachingEnvironment`** treats a repeated read-only probe of an unchanged world as already answered. Only reads,
  only successes, and `version=` is your word for what "unchanged" means (a file's mtime, a commit hash).
- **`EngineTools(memory=statistics)`** is what lets a *model* spend the record too: `recall` answers from it.

Persistence is an adapter, and there are two because the record has two shapes of use. `adapters.stats_file` writes
one JSON document — readable, diffable, right for a single writer, and a missing or unreadable file is a cold start
rather than a crash. `adapters.stats_sqlite` keeps the same record in a real database: `save` replaces, `add`
composes, so two runs that finish at once both keep their learning where a JSON save is last-writer-wins, and facts
are queryable without loading them. Both are stdlib only — `sqlite3` ships with Python — and both carry the same
record, so switching is a one-line change.

## Two stores, and the one word they share

A note for whoever is tempted to move a *project's* memory into SQLite next: `.context_ledger/` stays markdown, and
that is a decision rather than an oversight. That memory has to be read by people, diffed in a review, and merged
across machines and agents — git does that for text and for nothing else. The engine's record is the opposite kind
of data: counters nothing reviews, that only this engine reads, where "merging two versions" means adding them. Two
datasets, two stores, and the word "store" is all they share.

## The benchmark, and its control

[`benchmarks/bench.py`](benchmarks/bench.py) measures whether the learning layer pays for itself — eight goals, one
fixed world, an uninformed proposer order, and a control that holds the fan fixed so only the learning varies:

| run | model calls | probes | settled |
|---|---|---|---|
| cold — nothing carried in | 36 | 50 | 8/8 |
| warm — record carried between goals + cache | 26 | 38 (30 from cache) | 8/8 |
| control — learning off → on, fan wide enough for everything | 16 → 16 | 48 → 43 | 8/8 |

28% fewer model calls in that scenario, and the control's **zero** gain is the point of the control: learning here
can only act through the fan, so a fan that already holds every candidate leaves it nothing to do. The early goals
are burn-in where warm matches cold, because the record is still empty. And this bench measures *cost*; a scenario
where learning changes the outcome — a goal the cold engine abandons and the warm one settles — is in
`tests/test_learning.py`, which is also where the claim would break first.

## Examples are single files, on purpose

Each playground in `examples/` is one file with no build step, so you can copy one anywhere and it still runs. They
share a byte-identical shell and a test holds it that way, so the duplication cannot drift.
