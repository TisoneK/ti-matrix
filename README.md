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

The repo ships two adapters that need nothing but Python: a read-only local filesystem, and any
OpenAI-compatible endpoint (Ollama, vLLM, OpenAI, DeepSeek, Groq, OpenRouter, …).

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

## Core concepts

| Concept | What it is |
|---|---|
| `Goal` | what is being pursued, plus any constraints on a sound answer |
| `AgentState` | the engine's own state: facts, failed actions, path, progress, depth (immutable) |
| `Action` (`Move`) | one thing that could be done next, with arguments and a reason |
| `Observation` | what an action really produced (or a labelled prediction of it) |
| `Evaluation` | how much of the goal an outcome advances, and whether it settles it |
| `Environment` | where actions happen: their specs, which are read-only, and `probe(action)` |
| `ModelPort` | the engine's entire model dependency: `async complete(prompt) -> str` |
| `Simulator` | predicts an action's outcome without performing it |
| `TerminalCondition` | when the search is over, and why — injectable, each declaring the point it applies at |
| `EngineBudget` | the hard limits: depth, branches, model calls, backtracks |

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

## Layout

```
ti_matrix/            the engine — standard library only, no host application
├── protocols.py      the contracts (Environment, ModelPort, Simulator, Proposer, Evaluator, TerminalCondition)
├── state.py          Goal, AgentState, Action, Observation, Evaluation
├── search.py         the loop, the budget, the terminal conditions, the event record
├── model.py          the model's two jobs (propose, score) over a ModelPort
├── simulator.py      predicting an action that must not be performed
└── adapters/         host-free examples: files (read-only filesystem), openai_compat (any endpoint)
tests/                the engine's behaviour, plus a guard that fails the build if the core ever
                      reaches for a host application, an external record system, or ambient configuration
```

The dependency runs one way: an adapter imports the engine; the engine imports nothing of the adapter. That
is what lets the same engine drive different worlds — and what `tests/test_boundary.py` enforces.

## Status

**v0.1** — the engine, the search with backtracking, the simulator, and two example adapters. Run
end-to-end against real model providers and against a local filesystem; 34 tests cover the state, the loop,
the terminal conditions and the host boundary.

Next, in rough order: a wider beam (a real search strategy, once a second strategy exists to justify the
interface), persisted state so a run can resume, executing a confirmed action after simulating it, and a
third adapter example against a non-filesystem world.

## License

MIT — see [LICENSE](LICENSE). Copyright (c) 2026 Tisone Kironget.
