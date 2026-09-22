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

The repo ships three adapters that need nothing but Python: a read-only local filesystem, a project's
[Context Ledger](#remembering-across-runs-a-projects-context-ledger), and any OpenAI-compatible endpoint
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
- **Persistence is an adapter**: `ti_matrix.adapters.stats_file` writes the record to JSON, and a missing or
  unreadable file is a cold start rather than a crash.

`EngineTools(memory=statistics)` is what lets a *model* spend it too: `recall` answers from the same record.

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
    ├── openai_compat.py     any OpenAI-compatible endpoint
    ├── stats_file.py        the learning record on disk
    └── files_cli.py / ledger_cli.py   run a goal from the shell
benchmarks/           does the learning layer pay for itself? measured, with a control
tests/                the engine's behaviour, plus a guard that fails the build if the core ever
                      reaches for a host application, an external record system, or ambient configuration
```

The dependency runs one way: an adapter imports the engine; the engine imports nothing of the adapter. That
is what lets the same engine drive different worlds — and what `tests/test_boundary.py` enforces.

## Status

**v0.1** — the engine, the search with backtracking, the simulator, three example adapters (a local filesystem,
a project's Context Ledger, any OpenAI-compatible endpoint), the tool set, and the learning layer. Run
end-to-end against real model providers, against a local filesystem, and against a real `.context_ledger/`
vault; 101 tests cover the state, the loop, the terminal conditions, the host boundary, precedence between
sources of tools, and what the engine learns from its own events.

Next, in rough order: a wider beam (a real search strategy, once a second strategy exists to justify the
interface), resuming a run from persisted engine state (the record says what a run *established*; the state
itself still dies with the run), executing a confirmed action after simulating it, and a role overlay so a
ledger run can check in and out like any other session.

## License

MIT — see [LICENSE](LICENSE). Copyright (c) 2026 Tisone Kironget.
