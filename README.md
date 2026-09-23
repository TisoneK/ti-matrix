# Ti Matrix

A **state-driven agent engine**. A goal becomes a search over states: a model proposes candidate actions, the
engine performs the ones it may, scores what they produced, keeps the best, and backs out of dead ends — under a
budget, and always ending honestly.

It is **environment-agnostic**. Nothing here knows what it is driving: a program supplies an `Environment` (its
actions, and which of them are safe to perform) and a `ModelPort` (anything that answers a prompt), and the engine
supplies the search. A desktop app, a shell, a code repository, a browser, a game — anything that can describe its
actions and perform them can be driven this way.

The engine owns the state — what is known, what was tried, what failed, how deep the search went — and rebuilds it
from real observations, never from the model's memory of a chat. The model has exactly two jobs: propose candidate
actions, and score outcomes.

```
Goal ─► State ─► Proposer ─► candidate Actions ─► Environment.probe    (or Simulator.predict)
                                                        │
                                        Evaluator ◄─────┘   one call scores every outcome
                                            │
                              the search (beam of one + backtracking) ─► Transition ─► new State
                                            │
                                  TerminalCondition decides when it is over
```

- [Install](#install)
- [Run a goal](#run-a-goal)
- [Use it from your code](#use-it-from-your-code)
- [Play with it](#play-with-it)
- [Core concepts](#core-concepts)
- [Writing an adapter](#writing-an-adapter)
- [Asking before it acts](#asking-before-it-acts)
- [Adapters](#adapters)
- [What happened, afterwards](#what-happened-afterwards)
- [Layout](#layout)
- [Status](#status)
- [**Design notes**](DESIGN.md) — why the engine is shaped this way

## Install

```bash
pip install ti-matrix          # not on PyPI yet; from source:
pip install -e ".[dev]"        # development + tests
```

Python 3.10+, **no runtime dependencies** — the engine is standard library only.

## Run a goal

The repo ships five adapters that need nothing but Python: a read-only local filesystem, a project's Context
Ledger, a real browser, a hidden maze, and any OpenAI-compatible endpoint (Ollama, vLLM, OpenAI, DeepSeek, Groq,
OpenRouter, …).

```bash
# a local model, no API key, no other program installed
python -m ti_matrix.adapters.files_cli --base-url http://localhost:11434/v1 --model qwen2.5:7b \
    "how many python files are under ~/code, and which is the newest?"
```

A hosted endpoint needs its key, and the key travels by **name**, never by value:

```bash
python -m ti_matrix.adapters.files_cli --api-key-env DEEPSEEK_API_KEY \
    --base-url https://api.deepseek.com/v1 --model deepseek-chat \
    "which of my python files changed most recently?"
```

The other two are `python -m ti_matrix.adapters.ledger_cli` and `python -m ti_matrix.adapters.browser.cli`. Each
takes `--base-url`, `--model` and `--api-key-env`; `--help` lists the rest.

## Use it from your code

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

## The model is a seat, not an ingredient

`proposer` and `evaluator` are two seats an object sits in, and nothing says a model has to sit in either. Put
your own logic there and the engine runs with no model at all — no latency floor, no token cost, no endpoint:

```python
class ByThreshold:                       # a proposer that decides by rule
    def __init__(self, tools): self.tools = tools
    async def propose(self, state, n, avoid):
        return [Action("read_tick")] if state.progress < 1.0 else []

class ByRule:                            # an evaluator that decides by rule
    async def evaluate(self, state, outcomes):
        return [Evaluation(1.0, True, "the exit condition was met", "rule")
                if "exit" in o.text else Evaluation(0.3, False, "", "still watching")
                for o in outcomes]

StateEngine(env, proposer=ByThreshold(env.tools()), evaluator=ByRule(), budget=EngineBudget(max_model_calls=2))
```

The engine's own tests run this way — `ScriptedProposer`, `FixedProposer`, `KnowsTheAnswer` — so it is a
first-class configuration rather than a trick, and it is what makes the tool usable in worlds an LLM round trip
would be too slow or too expensive for: a threshold rule, a state machine, a spread check across two APIs, a
lookup table. The run above takes about a millisecond and makes no network call of any kind.

One naming note: `EngineBudget` counts "model calls" whether or not a model is there — it is counting
consultations of the two seats, which is what they cost when a model fills them. A rule-based run reports the
same number, and what binds it there is depth and branches rather than the call budget. What the engine still gives you there is everything except the judgment: the search and the
backtrack, the frozen read-only boundary, the hard budget, the honest stop, and the record of what was read.

What each seat buys, so you can choose rather than inherit:

| in the seat | you get | you pay |
|---|---|---|
| a model (`LLMMoveProposer`, `LLMEvaluator`) | judgment about a world you cannot enumerate in code | seconds and tokens per round |
| your own logic | speed, no cost, exact behaviour | you have to write the rule |

They mix: a model proposing while a rule scores, or a rule proposing while a model judges outcomes, are both
ordinary configurations — and the `Simulator`, `Confirmer` and `Synthesizer` seats are all optional, so a
model-free run simply leaves them empty.

## Play with it

`examples/` holds four playgrounds — one file each, standard library plus this package, no build step and nothing
to install. Each starts a page on loopback, runs real goals against a model endpoint you configure, and shows every
step as it happens: the candidates the model proposed, the probes that really ran, the scores, the selection, the
backtracks, and the honest stop when the goal cannot be settled.

```bash
python examples/files_ui.py  --root ~/code                            # your filesystem, read-only under there
python examples/ledger_ui.py --vault ~/code/my-project                # a project's Context Ledger
python examples/tools_ui.py  --vault ~/code/my-project --root ~/code  # several worlds, one tool set
python examples/browser_ui.py --url https://example.com               # a real browser, reads only
```

- **files** — the smallest useful world: four read-only actions. Relative paths resolve under your root and an
  absolute path that escapes it is refused, so a curious model cannot roam.
- **ledger** — nine read actions over a project's memory, plus `recall`. Tick the box and the run's results are
  appended back into the vault; leave it unticked and nothing is written.
- **tools** — the tool set: two shipped environments and one of your own, resolved by declared rules. One tool in
  that file replaces one of ours, so the resolution it prints is worth reading.
- **browser** — a real browser. Eleven of its seventeen actions read; the six that change something are refused
  unless you name them in the box, so a goal needing a click stops and names the click. Unticking "headless" lets
  you watch it work.

Each is a single file on purpose: copy one anywhere and it still runs.

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

Rules that keep a run honest: `probe` returns an `Observation` instead of raising (a failed action is information
the search uses), and an action you mark as not read-only is never performed by the engine.

## Asking before it acts

The engine performs read-only actions freely and will not perform anything else on its own. That used to be a
dead end: a run that needed a button pressed said so and stopped, and a person had to go and do it. A
`Confirmer` is the third answer — the engine asks, per action, at the moment it would happen:

```python
from ti_matrix import StateEngine
from ti_matrix.adapters.confirm import Granted

engine = StateEngine(env, proposer=..., evaluator=...,
                     confirmer=Granted(names={"click"}))          # this run may click, when it asks
confirmer = Granted(fingerprints={Action("click", {"selector": "#buy"}).fingerprint()})
```

Granting by *name* and granting by *exact action* are different powers, and that is the point: a tool may be
acceptable in general and one use of it not. The question carries the model's own reason, the answer is an
`EngineEvent` like everything else — so a run's record shows what it asked and what it was told, not only what
it did — and a refusal prunes the action so the same question is not asked forever. A confirmer that breaks is
a refusal with the error in the record, never a crash mid-run.

```
[confirmation]      click(selector=#go) granted=True  (the confirmer granted it)
[probe]             click(selector=#go) ok=True  clicked <button> Show the price
[probe]             page_text() ok=True  Widgets £42.50 Show the price
[done]              the price is £42.50
```

From the shell, `--ask click,type` asks at the terminal (a blank answer, or nobody there, is a refusal) and
`--perform click` says yes in advance. Everything else is unchanged: no confirmer and no grant means an action
that changes something is predicted, or named, and never performed.

## Adapters

### files

`ti_matrix.adapters.files.FilesEnvironment` — four read-only actions (`list_dir`, `read_file`, `stat_path`,
`find_files`). Every action reads; nothing here can change a filesystem. It takes whatever path it is handed, since
an adapter does not get to decide where a host's world begins — confine it in your own wrapper if you need to
(that is what `examples/files_ui.py` does).

### The maze

`ti_matrix.adapters.maze.MazeEnvironment` — four read-only actions (`grid`, `entry`, `look`, `step`) over a maze
written as ASCII, the way a person draws one. **A run is never shown the map**: it learns a cell by stepping into
it, and `step` hands back the far side, so a route has to be walked rather than read off. Walking counts as a read
for the same reason the browser's `goto` does — it changes what the run can see, not the world.

```python
from ti_matrix.adapters.maze import MazeEnvironment

env = MazeEnvironment()                       # the maze in the module, or pass your own ASCII
env = MazeEnvironment("""
    #########
    #S..#...#
    #.#####.#
    #E##.##.#
    #########
""")                                          # '#' is wall, '.' is floor, 'S' is the entry, 'E' the exit
```

It is the first world here that makes the engine *search* — the others are answered in a probe or two and never
make it retreat — which is why it exists. `DESIGN.md` says what it settled.

### The Context Ledger

`ti_matrix.adapters.context_ledger` closes the loop on a project's
[Context Ledger](https://github.com/TisoneK/context-ledger) in the two directions the ledger's own rule asks for —
*start by reading the ledger, finish by updating it.*

```bash
python -m ti_matrix.adapters.ledger_cli --vault ~/code/my-project \
    --base-url http://localhost:11434/v1 --model qwen2.5:7b \
    "what is in flight here, and what did the last session leave open?"
```

- **`LedgerEnvironment`** is the read half: nine read-only actions over the vault — the orientation digest, the
  work queue, the decisions, the session registry, the friction logs, a search across all of it, and whole-file
  reads. The ledger's write actions are declared too, marked not-read-only, so the engine reasons about them (or
  asks) and never performs one.
- **`LedgerRecorder`** is the write half, and it is not an Environment action: the host hands it the run's events,
  and it appends what the run established — its facts, its dead ends, its answer — to the office's session notes,
  promoting the durable facts into the parking lot's Findings, which is where the next session's finding order
  looks.

```python
from ti_matrix.adapters.context_ledger import LedgerEnvironment, LedgerRecorder

env = LedgerEnvironment("~/code/my-project")
engine = StateEngine(env, proposer=LLMMoveProposer(port, env.tools()), evaluator=LLMEvaluator(port))
recorder = LedgerRecorder(env.vault, model="qwen2.5:7b")

async for event in engine.run(Goal("what is parked, and why?")):
    recorder.observe(event)      # the run's own events, as they happen
recorder.record()                # what it learned, into the vault
```

Every write lands in a file the vault's schema already defines, in the ledger's own entry format. A vault that is
missing its notes file, or its Findings table, is reported rather than patched. A project with no vault yet gets one
from the ledger's own bootstrapper (`sh context-ledger/core/bin/ledger-sync bootstrap path/to/your-project`); this
adapter only reads and appends, and never initialises one.

### The browser

`ti_matrix.adapters.browser.BrowserEnvironment` puts a real browser behind the engine's `Environment`. Eleven of
its seventeen actions read: a page's text, its links, its markup, whether a selector matches, a screenshot. Six can
change the world — `click`, `type`, `press`, `evaluate`, opening and closing tabs — and a run may not perform any of
them unless the host says so:

```python
from ti_matrix.adapters.browser import BrowserEnvironment

env = BrowserEnvironment("https://example.com")                     # reads only
env = BrowserEnvironment("https://example.com", perform={"click"})   # this engine may click here
env = BrowserEnvironment("https://example.com", only={"page_text", "links"})   # or offer four actions, not 17
```

A run that needs a button pressed stops and names the button, with the prediction it made:

```text
[probe]    click(selector=#go) -> the price would appear on the page   (predicted, not performed)
[stopped]  reason: needs_action · needs: click(selector=#go) · settled: false
```

```bash
python -m ti_matrix.adapters.browser.cli "what does this page cost?" --url https://example.com
python -m ti_matrix.adapters.browser.cli "search for widgets" --url https://example.com --perform click,type
```

There is nothing to install for this: the WebSocket and DevTools protocol code is part of this package rather than
a dependency of it. Pass `attach_to="127.0.0.1:9222"` to drive a browser you started yourself, which is what you
want when you would rather watch. Each run starts and closes its own browser, and a profile you name with
`user_data_dir=` is yours — `close()` deletes only the throwaway one it made.

If you already drive a browser with the `agent-browser` CLI, the engine can use that instead — or as well:

```python
from ti_matrix import CompositeEnvironment
from ti_matrix.adapters.browser import AgentBrowser, BrowserEnvironment

env = CompositeEnvironment(BrowserEnvironment("about:blank"), AgentBrowser(session="run-7"))
print(env.resolution().to_text())   # both offer click, screenshot and find: this says who won each
```

`AgentBrowser` exposes the CLI's whole surface as 78 actions and holds the same boundary: **39 read** and are
performed, **39 change something** and are refused unless you say so. `perform={"all"}` says so for everything;
`only={"snapshot", "get", "click"}` narrows the other way, which matters when a run needs four tools and not
seventy-six. The CLI is not installed on the adapter's behalf — a missing one is a failed probe that says how to get
it. A password never travels through an action's arguments: `auth_save` takes the *name* of an environment variable
and pipes the value in on stdin, so it reaches neither the model, nor the event log, nor `ps`.

### Learning across runs

The engine's state dies with the run, so a cold start re-proposes the action that failed twice yesterday.
`ti_matrix.learning` is what previous runs established, and it is arithmetic on purpose — every number is a count
derived from an event the engine already emitted. `Observation.ok` is trusted, and `Evaluation.reason` is not even
read.

- **`Statistics`** — keyed two ways: by **tool** ("what is this world like?", generalising across arguments) and by
  **fingerprint** ("have we made this exact call before?").
- **`LearningProposer`** — asks the model for a couple more candidates than the fan needs, drops tools that have
  never once worked here, and orders the rest by what has paid off.
- **`CachingEnvironment`** — a repeated read-only probe of an unchanged world is not asked again. Only reads, only
  successes, and `version=` is your word for what "unchanged" means (a file's mtime, a commit hash).
- **Persistence** — `adapters.stats_file` writes one JSON document (readable, diffable, right for a single writer),
  and `adapters.stats_sqlite` keeps the same record in SQLite, where `save` replaces and `add` composes. Both carry
  the same record, so switching is a one-line change.

```python
from ti_matrix import CompositeEnvironment, EngineTools

env = CompositeEnvironment(
    FilesEnvironment(),                                  # ours
    EngineTools(LedgerEnvironment(vault), memory=stats),  # the engine's own `recall`, around a ledger
    MyApplicationEnvironment(),                           # yours
)
print(env.resolution().to_text())    # who won, who was shadowed, who was renamed
```

`EngineTools` wraps any environment to add the one tool the engine insists on: `recall`, which answers from the
same record. When two sources offer the same tool, `ToolSet` decides by declared rules — your tool beats a built-in
by default (`prefer="user"`), or the other way round, and a replacement named differently says what it replaces
(`ActionSpec("read_local_file", ..., supersedes="read_file")`). `resolution()` reports what was kept, renamed and
dropped, so the model's tool list is never a mystery.

From the shell, `--remember FILE` is the whole of it: read the record, order proposals by it, offer `recall`,
save it back — even when the run fails.

What that buys, measured on a live site with a real hosted model rather than in a benchmark: the record
accumulates (6 tools known after one run, 10-11 probes added per run), and it changes what gets proposed — a
model kept proposing an action this engine may not perform, which cost a simulation call every time it came up,
and after three of those the action left the fan for good. What it did *not* do is make those particular runs
cheaper: on an open-ended goal ("what does this site offer, and what are its main sections?") every run spent
its whole budget, because the cost there is the model exploring and the evaluator never judging the goal
settled. Narrow goals against the same live site settle in **two model calls** — "what are the nav links on
this page?" and "what price is shown for EUR/USD?" both did, with answers taken from the page. The honest
summary is that the record's levers are ordering and dropping, and neither bounds exploration; if you want
open-ended runs to be cheap, the lever is the evaluator's judgment, not the memory.

## When it stops with something to say

A run could end with an answer only if the model declared `done`, which left a specific hole: a run that read
its way to ten useful facts and ran out of calls reported the facts and no answer. Four runs did exactly that
on a live site — progress climbing the whole way (0.7, 0.85, 0.95, 0.98), so nothing had stalled; the budget
had run out holding the answer.

So the budget now pays for the report as well as the search. One call proposes a fan, one scores it, and the
**last call belongs to the answer** when there is anything to answer from — a fan that would spend it is not
proposed. With a `Synthesizer` (`LLMSynthesizer` over any `ModelPort`; every CLI has one), a stop that has
facts is asked once what they amount to:

```
[stopped]  reason: budget · settled: false · model_calls: 7 (budget 8)
           partial_answer: "Based only on the facts provided… CryptonicHub is presented as a Forex &
                            Binary Trading Platform…"
           answer_basis:   synthesised from 6 fact(s) established by real readings; NOT verified
```

An answer with an honest label, and deliberately not `done`: the field is `partial_answer` rather than
`answer`, `settled` stays false, and the basis says how many readings it came from. A run that answered on the
way out has to be distinguishable from one that earned it — that distinction is the reason this engine can be
left unattended. A synthesizer that breaks or returns nothing leaves the stop exactly as it was, with a note
saying so, and costs nothing.

## What happened, afterwards

Every step of a run is an event, and nothing used to keep them — a run existed while it printed and then it was
gone. `--record FILE` writes one JSON line per event, and the same module reads it back:

```bash
python -m ti_matrix.adapters.browser.cli "what is the price?" --url https://example.com --record run.jsonl
python -m ti_matrix.adapters.run_log run.jsonl
```

```
12 events, 2 model calls, 3 probes, 0 backtracks
settled: the price is £42.50
probes, in order:
  ok  click(selector=#go) — clicked <button> Show the price
  ok  page_text() — Widgets £42.50 Show the price
facts established (2): …
```

That is a run's *record*, not its state: resuming a run means saving the state it reached, which is a different
thing and is not pretended here. What this is for is reading a run after the fact — including a run that failed,
whose log stops with the reason.

## Layout

```
ti_matrix/            the engine — standard library only, no host application
├── protocols.py      the contracts (Environment, ModelPort, Simulator, Proposer, Evaluator, TerminalCondition)
├── state.py          Goal, AgentState, Action, Observation, Evaluation
├── search.py         the loop, the budget, the terminal conditions, the event record
├── model.py          the model's two jobs (propose, score) over a ModelPort
├── simulator.py      predicting an action that must not be performed
├── tools/            several sources of actions, resolved into the one set a model is shown
├── learning/         what previous runs established, and the wrappers that spend it
└── adapters/         host-free environments and hosts:
    ├── files.py             a read-only local filesystem
    ├── maze.py              a hidden maze — the one world that makes the engine search
    ├── context_ledger/      a project's Context Ledger — read as an environment, written back by a host
    ├── browser/             a real browser: WebSocket + DevTools Protocol, standard library only
    ├── openai_compat.py     any OpenAI-compatible endpoint
    ├── builtin.py           the two seats filled by rules — a real search with no model in it
    ├── confirm.py           answering the engine when it asks to do something that changes the world
    ├── session.py           what a command carries in and leaves behind: --remember, --record, --ask
    ├── run_log.py           a run written down, and read back: python -m ti_matrix.adapters.run_log FILE
    ├── stats_file.py        the learning record on disk, as one JSON document
    ├── stats_sqlite.py      the same record in SQLite, for more than one writer
    └── files_cli.py / ledger_cli.py / browser/cli.py   run a goal from the shell
examples/             four single-file playgrounds — a page, a real run, your endpoint and your world
benchmarks/           does the learning layer pay for itself? measured, with a control
tests/                the engine's behaviour, plus a guard that fails the build if the core ever
                      reaches for a host application, an external record system, or ambient configuration
```

The dependency runs one way: an adapter imports the engine; the engine imports nothing of the adapter. `DESIGN.md`
explains why each piece is shaped the way it is.

## Status

**v0.1** — the engine, the search with backtracking, the simulator, five example adapters (a local filesystem, a
project's Context Ledger, a real browser, a hidden maze, any OpenAI-compatible endpoint), the tool set, the learning
layer, the confirmer, and four playgrounds to drive them from a page. Run end-to-end against real model providers,
a local filesystem, a real `.context_ledger/` vault, real Chrome, and the `agent-browser` CLI — including live
against a real site with a hosted model, where narrow goals settle in two model calls. 206 tests cover the state,
the loop, the terminal conditions, the host boundary, what it asks before it acts, precedence between sources of
tools, what the engine learns from its own events, the model port, a world that makes it retreat, the WebSocket and
DevTools plumbing, the CLI contract against the real tool, and the playgrounds. Green on Python 3.10 through 3.13,
and on Windows with 3.11; the browser tests skip themselves where no browser is installed.

Next, in rough order: **making an open-ended goal settle rather than merely get answered** — the label is honest
and the facts are there, but a `done` would be better whenever the facts really are enough, and that is the
evaluator's bar rather than the search's (it sits behind a model's judgment: the same goal, same site, same tools
settled in two calls under a reasoning model and never settled under a chat model). Then resuming a run from
persisted state (`--record` is the substrate; saving the state itself is the missing half), then a wider beam (a
real search strategy, once a second strategy exists to justify the interface).

## License

MIT — see [LICENSE](LICENSE). Copyright (c) 2026 Tisone Kironget.
