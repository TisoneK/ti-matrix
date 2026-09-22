# Ti Matrix

A **state-driven agent engine**. A goal becomes a search over states: a model proposes candidate actions,
the engine performs the ones it may, scores what they produced, keeps the best, and backs out of dead ends —
under a budget, and always ending honestly.

An agent that improvises each step inside a growing conversation forgets, drifts and promises. Ti Matrix
does neither: the **engine** owns the state — what is known, what was tried, what failed, how deep the
search went — and it is rebuilt from real observations, never from the model's memory of a chat. The model
has exactly two jobs: propose candidate actions, and score outcomes.

It is **environment-agnostic**. Nothing here knows what it is driving. A program supplies an `Environment`
(its actions, and which of them are safe to perform) and a `ModelPort` (anything that answers a prompt);
the engine supplies the search. A desktop app, a shell, a code repository, a browser, a game — anything
that can describe its actions and perform them can be driven this way.

## Install

```bash
pip install ti-matrix          # not on PyPI yet; from source:
pip install -e ".[dev]"        # development + tests
```

Python 3.10+, **no runtime dependencies** — the engine is standard library only.

## Run a goal

The repo ships four adapters that need nothing but Python: a read-only local filesystem, a project's
[Context Ledger](#remembering-across-runs-a-projects-context-ledger), a
[real browser](#driving-a-browser-reads-run-clicks-wait-to-be-asked), and any OpenAI-compatible endpoint
(Ollama, vLLM, OpenAI, DeepSeek, Groq, OpenRouter, …).

```bash
# a local model, no API key, no other program installed
python -m ti_matrix.adapters.files_cli --base-url http://localhost:11434/v1 --model qwen2.5:7b \
    "how many python files are under ~/code, and which is the newest?"
```

Or drive it from your own code:

```python
from ti_matrix import EngineBudget, Goal, LLMEvaluator, LLMMoveProposer, StateEngine
from ti_matrix.adapters.files import FilesEnvironment
from ti_matrix.adapters.openai_compat import OpenAICompatModel

env = FilesEnvironment()
port = OpenAICompatModel("http://localhost:11434/v1", "qwen2.5:7b")

engine = StateEngine(
    env,
    proposer=LLMMoveProposer(port, env.tools()),
    evaluator=LLMEvaluator(port),
    budget=EngineBudget(max_model_calls=12),
)

async for event in engine.run(Goal("which of my python files changed most recently?")):
    print(event.to_dict())        # every step: states, actions, outcomes — never hidden reasoning
```

## Play with it

`examples/` holds four playgrounds — one file each, standard library plus this package, no build step and
nothing to install. Each starts a page on loopback, runs real goals against a model endpoint you configure, and
shows every step as it happens: the candidates the model proposed, the probes that really ran, the scores, the
selection, the backtracks, and the honest stop when the goal cannot be settled.

```bash
python examples/files_ui.py  --root ~/code                            # your filesystem, read-only under there
python examples/ledger_ui.py --vault ~/code/my-project                # a project's Context Ledger
python examples/tools_ui.py  --vault ~/code/my-project --root ~/code  # several worlds, one tool set
python examples/browser_ui.py --url https://example.com               # a real browser, reads only
```

- **files** — the smallest useful world: four read-only actions. Relative paths resolve under your root and an
  absolute path that escapes it is refused, so a curious model cannot roam. Every observation is sent to the
  endpoint you choose, which the page says plainly.
- **ledger** — nine read actions over a project's memory, plus `recall`. Tick the box and the run's results are
  appended back into the vault; leave it unticked and nothing is written. The box names the two files it would
  touch.
- **tools** — the tool set: two shipped environments and one of your own, resolved by declared rules. One tool
  in that file deliberately replaces one of ours, so the resolution it prints is worth reading — change
  `prefer` and watch the roles reverse.
- **browser** — a real browser. Eleven of its seventeen actions read; the six that change something are refused
  unless you name them in the box, so a goal needing a click stops and names the click. Each run starts and
  closes its own browser, and unticking "headless" lets you watch it work.

Each is a single file on purpose: copy one anywhere and it still runs. They share a byte-identical shell and a
test holds it that way, so the duplication cannot drift.

## How it works

```
Goal ─► State ─► Proposer ─► candidate Actions ─► Environment.probe    (or Simulator.predict)
                                                        │
                                        Evaluator ◄─────┘   one call scores every outcome
                                            │
                              the search (beam of one + backtracking) ─► Transition ─► new State
                                            │
                                  TerminalCondition decides when it is over
```

- **The state is the engine's.** `AgentState` is immutable — the goal, the facts real observations
  established, the actions that failed, the path taken, progress and depth — rendered compactly for the
  model with no chat history, and fingerprinted so an action that failed is never proposed twice.
- **Probing is real.** A read-only action is performed and its actual output recorded. Nothing is invented.
- **Scoring is one call per fan**, with deterministic guards: a failed probe never counts as progress, and
  `done` requires an answer grounded in facts.
- **Backtracking keeps what was learned.** When nothing beats where the state stands, the engine retreats
  to the parent state with every real fact intact and the action that led into the dead end pruned.
- **An action that must not be performed is predicted, not performed** (`Simulator`): the prediction is
  labelled, never learned as a fact, and can never settle the goal — a run that needs one stops and names it.
- **Every step is an event.** `EngineEvent`s (`state`, `candidates`, `probe`, `evaluation`, `selected`,
  `backtrack`, `needs_confirmation`, `done`, `stopped`) are the whole record, so any interface — a CLI, a
  web UI, a game-tree explorer — can be built on them without reading the engine's internals.

## Remembering across runs: a project's Context Ledger

The engine's state dies with the run. That is what keeps it honest — nothing is remembered that was not
observed — and it is also its one blind spot: the next run starts from nothing. A repository that keeps a
[Context Ledger](https://github.com/TisoneK/context-ledger) already holds that memory as plain markdown in
git: the task in flight, the decisions in force, which approach already failed, what the last sessions hit.

`ti_matrix.adapters.context_ledger` closes the loop, in the two directions the ledger's own rule asks for —
*start by reading the ledger, finish by updating it.*

```bash
python -m ti_matrix.adapters.ledger_cli --vault ~/code/my-project \
    --base-url http://localhost:11434/v1 --model qwen2.5:7b \
    "what is in flight here, and what did the last session leave open?"
```

A project with no vault yet gets one from the ledger's own bootstrapper —
`sh context-ledger/core/bin/ledger-sync bootstrap path/to/your-project`, or hand
[`universal-kickoff.md`](https://github.com/TisoneK/context-ledger/blob/main/universal-kickoff.md) to any
agent. The adapter only reads and appends to the vault's own files; it never initialises one.

- **`LedgerEnvironment`** is the read half: nine read-only actions over the vault — the orientation digest,
  the work queue, the decisions, the session registry, the friction logs, a search across all of it, and
  whole-file reads. A run can look anywhere in a project's memory and change nothing. The ledger's write
  actions are declared too, marked not-read-only, so the engine reasons about them (or asks) and never
  performs one.
- **`LedgerRecorder`** is the write half, and deliberately *not* an Environment action: the host hands it
  the run's events, and it appends what the run established — its facts, its dead ends, its answer — to the
  office's session notes, promoting the durable facts into the parking lot's Findings, which is where the
  next session's own reading order finds them.

Nothing is invented and nothing is overwritten. Every write lands in a file the vault's schema already
defines, in the ledger's own entry format — appended, or inserted as a row in the table that owns that kind
of knowledge. A vault that is missing its notes file, or its Findings table, is reported rather than
patched: those shapes belong to the schema, not to this adapter.

```python
from ti_matrix.adapters.context_ledger import LedgerEnvironment, LedgerRecorder

env = LedgerEnvironment("~/code/my-project")
engine = StateEngine(env, proposer=LLMMoveProposer(port, env.tools()), evaluator=LLMEvaluator(port))
recorder = LedgerRecorder(env.vault, model="qwen2.5:7b")

async for event in engine.run(Goal("what is parked, and why?")):
    recorder.observe(event)      # the run's own events, as they happen
recorder.record()                # what it learned, into the vault
```

A run that does *not* settle its goal records that too. The ledger's most valuable entries are the traps and
the dead ends — "which approach already failed" is the thing the next agent cannot re-derive — so a run that
says plainly what it tried and could not do is worth more than one that sounds confident.

## Driving a browser: reads run, clicks wait to be asked

`ti_matrix.adapters.browser` puts a real browser behind the engine's `Environment`, and the engine's own
boundary turns out to be exactly the right shape for one. Eleven of the seventeen actions read: a page's text,
its links, its markup, whether a selector matches, a screenshot. Six can change the world — `click`, `type`,
`press`, `evaluate`, opening and closing tabs — and a run may not perform any of them unless the host says so:

```python
from ti_matrix.adapters.browser import BrowserEnvironment

env = BrowserEnvironment("https://example.com")                     # reads only
env = BrowserEnvironment("https://example.com", perform={"click"})   # this engine may click here
```

So a run that only needs to read looks anywhere and changes nothing, and a run that needs a button pressed
stops and names the button — with the prediction it made, and `settled: false`, the same honest ending it gives
any goal it cannot reach:

```text
[probe]    click(selector=#go) -> the price would appear on the page   (predicted, not performed)
[stopped]  reason: needs_action · needs: click(selector=#go) · settled: false
```

Grant the action and the same goal settles from the page itself: click, then read what the page says now.

```bash
python -m ti_matrix.adapters.browser.cli "what does this page cost?" --url https://example.com
python -m ti_matrix.adapters.browser.cli "search for widgets" --url https://example.com --perform click,type
```

There is nothing to install for this. Chrome's DevTools Protocol is JSON over a WebSocket, and neither is in
the standard library — so `websocket.py` (RFC 6455: the handshake, the frames, ping and close) and `cdp.py`
(start Chrome, find its pages, drive one) are part of this package rather than dependencies of it. A launch is
a `subprocess` call and discovery is an HTTP GET. Pass `attach_to="127.0.0.1:9222"` to drive a browser you
started yourself, which is what you want when you would rather watch.

### Two sources, and they compose

The environment above is this package's own and covers reading a page and acting on it. If you already drive a
browser with the `agent-browser` CLI, the engine can use that instead — or as well:

```python
from ti_matrix import CompositeEnvironment
from ti_matrix.adapters.browser import AgentBrowser, BrowserEnvironment

env = CompositeEnvironment(BrowserEnvironment("about:blank"), AgentBrowser(session="run-7"))
print(env.resolution().to_text())   # both offer click, screenshot and find: this says who won each
```

`AgentBrowser` exposes the CLI's whole surface as 76 actions and holds the same boundary: **39 read** and are
performed, **37 change something** and are refused unless you say so. `perform={"all"}` says so for everything
— and that word is doing real work, since it is the difference between an engine that can look at a page and
one you have handed the machine. `only={"snapshot", "get", "click"}` narrows the other way, which matters when
a run needs four tools and not seventy-six.

What is in there: the accessibility-tree `snapshot` with its `@eN` refs and `find` by role or text rather than
markup; `get` and `is` for element state; tabs, navigation, waiting, screenshots, PDF; `network_requests` and
full request bodies, HAR recording, mocking or blocking a route; cookies and storage; console output and page
errors; axe-core audits and Core Web Vitals; trace, profiler and video recording; the React component tree and
render profiling; the CLI's own `confirm`/`deny` queue, which is the same idea as the engine's
`needs_confirmation` one layer down. It installs nothing on its behalf — a missing CLI is a failed probe that
says how to get one — and every action runs in a session of its own, so a run cannot navigate away from a page
you left open.

The classification is the one question this project asks everywhere else: does performing it hand the run
something to observe, or does it change the world it is observing? A HAR file, a trace and a screenshot are
reads. So are a page comparison and a console dump. Not reads: the mouse, the clipboard, `batch` (whatever it
contains), `eval`, anything that configures the browser rather than observing it, anything that reaches
outside it — `plugin_add` and `plugin_run` install and execute external code; `auth_save` and `auth_login`
write credentials — and `confirm`/`deny`, because approving an action is not observing one.

A password never travels through an action's arguments. `auth_save` takes the *name* of an environment variable
and pipes the value in on stdin, so it reaches neither the model, nor the event log, nor `ps`.

This is what the tool registry is for rather than an alternative to it. The package does not reimplement
axe-core, the React DevTools protocol or network interception; it exposes what you already have as actions an
engine can search over, judge, refuse and learn from — and keeps its own dependency-free environment for
everything that does not need them.

Two limits stated plainly. **A screenshot is for a person**: the evaluator is a text model, so a screenshot's
fact is its path and size — a multimodal host can read the file, and nothing here pretends a PNG is text. And
**do not put a browser behind the cache** without a version token taken from the page: a page moves, and a
remembered probe would answer about a page that no longer exists.

## Core concepts

| Concept | What it is |
|---|---|
| `Goal` | what is being pursued, plus any constraints on a sound answer |
| `AgentState` | the engine's own state: facts, failed actions, path, progress, depth (immutable) |
| `Action` (`Move`) | one thing that could be done next, with arguments and a reason |
| `Observation` | what an action really produced (or a labelled prediction of it) |
| `Evaluation` | how much of the goal an outcome advances, and whether it settles it |
| `Environment` | where actions happen: their specs, which are read-only, and `probe(action)` |
| `ToolSet` | several sources of actions resolved into one — precedence declared, and the resolution readable |
| `ModelPort` | the engine's entire model dependency: `async complete(prompt) -> str` |
| `Simulator` | predicts an action's outcome without performing it |
| `TerminalCondition` | when the search is over, and why — injectable, each declaring the point it applies at |
| `EngineBudget` | the hard limits: depth, branches, model calls, backtracks |
| `Statistics` | what previous runs established about one environment — counters, keyed by tool and by exact action |

## Writing an adapter

Two objects and a budget is the whole integration surface:

```python
from ti_matrix import ActionSpec, EngineBudget, Goal, Observation, StateEngine
from ti_matrix.model import LLMEvaluator, LLMMoveProposer

class MyEnvironment:                                          # where actions happen
    name = "my-env"
    def tools(self) -> dict[str, ActionSpec]: ...             # what can be done; read_only per action
    def is_read_only(self, action) -> bool | None: ...        # None = not an action here
    async def probe(self, action) -> Observation: ...         # perform it; never raise

engine = StateEngine(
    MyEnvironment(),
    proposer=LLMMoveProposer(my_model_port, environment.tools()),
    evaluator=LLMEvaluator(my_model_port),
    simulator=None,                        # optional: predict actions that must not be performed
    budget=EngineBudget(max_model_calls=16),
)
```

Rules that keep a run honest: `probe` returns an `Observation` instead of raising (a failed action is
information the search uses), and an action you mark as not read-only is never performed by the engine.

## Many tools, and who wins

An environment supplies its own actions, and for one environment that is the whole story. The moment there is
more than one source — a shipped environment, your application's actions, the engine's own memory tool —
something has to decide what the model is shown when two of them offer the same thing. `ToolSet` decides, by
rules you declare rather than rules it guesses:

- **A name decides.** Two tools sharing a name are the same tool as far as any model can tell.
- **Preference is declared.** Your tool beats a built-in by default (`prefer="user"`), or the other way round
  (`prefer="builtin"`), and a replacement that is named differently says what it replaces:
  `ActionSpec("read_local_file", ..., supersedes="read_file")`.
- **The resolution is a record.** `resolution()` reports what was kept, renamed and dropped, so the model's tool
  list is never a mystery you have to guess at. `require(*names)` fails loudly when a run depends on a tool the
  set does not carry.

```python
from ti_matrix import CompositeEnvironment, EngineTools

env = CompositeEnvironment(
    FilesEnvironment(),                                  # ours
    EngineTools(LedgerEnvironment(vault), memory=stats),  # the engine's own `recall`, around a ledger
    MyApplicationEnvironment(),                           # yours
)
print(env.resolution().to_text())    # who won, who was shadowed, who was renamed
```

`EngineTools` is where "mandatory" lives, and it is deliberately a wrapper rather than an obligation on
environments: the one tool the engine insists on is `recall` — what its own previous runs established about
this world — and it is added around whatever environment you already have. Everything else stays the
environment's business. A tool that loses a collision needs no new engine behaviour at all: it is simply absent
from the tools the model is shown, and an action the environment does not know is already remembered as a
failed move.

## Getting better at its own job

The engine remembers within a run and forgets between them: `AgentState` is built fresh for every goal, so a
cold start re-proposes the action that failed twice yesterday. `ti_matrix.learning` is the fix, and it is
arithmetic on purpose — every number is a count derived from an event the engine already emitted, never a
sentence a model wrote about itself. That is the same promise the state makes, applied across runs instead of
within one: `Observation.ok` is trusted, and `Evaluation.reason` is not even read.

- **`Statistics`** — what previous runs established about one environment, keyed two ways: by **tool** ("what is
  this world like?", generalising across arguments) and by **fingerprint** ("have we made this exact call
  before?", for the cache and the cross-run avoid list).
- **`LearningProposer`** — asks the model for a couple more candidates than the fan needs, drops tools that have
  never once worked here, and orders the rest by what has paid off. If that would empty the fan it keeps the
  model's best idea, because "nothing is worth trying" is a worse answer than a long shot.
- **`CachingEnvironment`** — a repeated read-only probe of an unchanged world is not asked again. Only reads,
  only successes, and `version=` is your word for what "unchanged" means (a file's mtime, a commit hash).
- **Persistence is an adapter**, and there are two because the record has two shapes of use.
  `adapters.stats_file` writes one JSON document — readable, diffable, right for a single writer, and a missing
  or unreadable file is a cold start rather than a crash. `adapters.stats_sqlite` keeps the same record in a
  real database: `save` replaces, `add` composes, so two runs that finish at once both keep their learning
  where a JSON save is last-writer-wins, and facts are queryable without loading them. Both are stdlib only —
  `sqlite3` ships with Python — and both carry the same record, so switching is a one-line change.

`EngineTools(memory=statistics)` is what lets a *model* spend it too: `recall` answers from the same record.

A note for whoever is tempted to move a *project's* memory into SQLite next: `.context_ledger/` stays
markdown, and that is a decision rather than an oversight. That memory has to be read by people, diffed in a
review, and merged across machines and agents — git does that for text and for nothing else. The engine's
record is the opposite kind of data: counters nothing reviews, that only this engine reads, where "merging two
versions" means adding them. Two datasets, two stores, and the word "store" is all they share.

[`benchmarks/bench.py`](benchmarks/bench.py) measures whether that pays for itself — eight goals, one fixed
world, an uninformed proposer order, and a control that holds the fan fixed so only the learning varies:

| run | model calls | probes | settled |
|---|---|---|---|
| cold — nothing carried in | 36 | 50 | 8/8 |
| warm — record carried between goals + cache | 26 | 38 (30 from cache) | 8/8 |
| control — learning off → on, fan wide enough for everything | 16 → 16 | 48 → 43 | 8/8 |

28% fewer model calls in that scenario, and the control's **zero** gain is the point of the control: learning
here can only act through the fan, so a fan that already holds every candidate leaves it nothing to do. The
early goals are burn-in where warm matches cold, because the record is still empty. And this bench measures
*cost*; a scenario where learning changes the outcome — a goal the cold engine abandons and the warm one
settles — is in `tests/test_learning.py`, which is also where the claim would break first.

## Layout

```
ti_matrix/            the engine — standard library only, no host application
├── protocols.py      the contracts (Environment, ModelPort, Simulator, Proposer, Evaluator, TerminalCondition)
├── state.py          Goal, AgentState, Action, Observation, Evaluation
├── search.py         the loop, the budget, the terminal conditions, the event record
├── model.py          the model's two jobs (propose, score) over a ModelPort
├── simulator.py      predicting an action that must not be performed
├── tools/            several sources of actions, resolved into the one set a model is shown
│   ├── registry.py        who wins a collision, and the record of what the resolution was
│   ├── composite.py       many environments presented as one, each action routed to its source
│   └── engine_tools.py    the engine's own `recall`, wrapped around any environment
├── learning/         what previous runs established, and the wrappers that spend it
│   ├── statistics.py      the counters, per tool and per exact action
│   ├── proposer.py        ordering and dropping by what this world has actually rewarded
│   └── cache.py           not asking an unchanged world the same question twice
└── adapters/         host-free environments and hosts:
    ├── files.py             a read-only local filesystem
    ├── context_ledger/      a project's Context Ledger — read as an environment, written back by a host
    ├── browser/             a real browser: WebSocket + DevTools Protocol, standard library only
    ├── openai_compat.py     any OpenAI-compatible endpoint
    ├── stats_file.py        the learning record on disk, as one JSON document
    ├── stats_sqlite.py      the same record in SQLite, for more than one writer
    └── files_cli.py / ledger_cli.py / browser/cli.py   run a goal from the shell
examples/             three single-file playgrounds — a page, a real run, your endpoint and your world
benchmarks/           does the learning layer pay for itself? measured, with a control
tests/                the engine's behaviour, plus a guard that fails the build if the core ever
                      reaches for a host application, an external record system, or ambient configuration
```

The dependency runs one way: an adapter imports the engine; the engine imports nothing of the adapter. That
is what lets the same engine drive different worlds — and what `tests/test_boundary.py` enforces.

## Status

**v0.1** — the engine, the search with backtracking, the simulator, four example adapters (a local filesystem, a
project's Context Ledger, a real browser, any OpenAI-compatible endpoint), the tool set, the learning layer, and
four playgrounds to drive them from a page. Run end-to-end against real model providers, a local filesystem, a
real `.context_ledger/` vault, real Chrome, and the `agent-browser` CLI; 165 tests cover the state, the loop, the terminal conditions, the
host boundary, precedence between sources of tools, what the engine learns from its own events, the WebSocket
and DevTools plumbing, the CLI contract against the real tool, and the playgrounds. Green on Python 3.10 through 3.13; the browser tests skip
themselves where no browser is installed.

Next, in rough order: a wider beam (a real search strategy, once a second strategy exists to justify the
interface), resuming a run from persisted engine state (the record says what a run *established*; the state
itself still dies with the run), executing a confirmed action after simulating it, and a role overlay so a
ledger run can check in and out like any other session.

## License

MIT — see [LICENSE](LICENSE). Copyright (c) 2026 Tisone Kironget.
