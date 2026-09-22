"""State Agent — a state-driven agent engine, environment-agnostic by construction.

The agent is a state-transition system that uses a model to propose and judge actions; the ENGINE owns the
state, not the model:

    Goal -> State -> Proposer -> candidate Actions -> Environment.probe (or Simulator.predict)
                                                              |
                                              Evaluator <-----+   (one call scores every outcome)
                                                  |
                                    the search (beam of one + backtracking) -> Transition -> new State
                                                  |
                                         TerminalCondition decides when it is over

Nothing in this package knows what an environment is. Adapters supply one:

    from ti_matrix import EngineBudget, Goal, LLMEvaluator, LLMMoveProposer, StateEngine
    from ti_matrix.adapters.files import FilesEnvironment
    from ti_matrix.adapters.openai_compat import OpenAICompatModel

    env = FilesEnvironment()
    port = OpenAICompatModel("http://localhost:11434/v1", "qwen2.5:7b")   # any OpenAI-compatible endpoint

    engine = StateEngine(
        env,
        proposer=LLMMoveProposer(port, env.tools()),
        evaluator=LLMEvaluator(port),
        budget=EngineBudget(max_model_calls=12),
    )
    async for event in engine.run(Goal("how many python files are under ~/code?")):
        print(event.to_dict())

Two optional layers extend that picture without changing it, and both are wrappers rather than engine
features — a run that uses neither behaves exactly as before:

    tools      several sources of actions resolved into one tool set (``ToolSet``), and the engine's own
               memory tool wrapped around any environment (``EngineTools``) — see ``ti_matrix.tools``
    learning   what previous runs established, counted from the events they emitted (``Statistics``), and
               the two wrappers that spend it: ``LearningProposer`` and ``CachingEnvironment``

The public surface is the contracts (``protocols``), the state (``state``), the loop (``search``), the model's
two jobs (``model``), the tool set (``tools``), and what the engine learns from its own runs (``learning``).
If you are writing an adapter, you need ``Environment``, a ``ModelPort``, and the ``StateEngine`` constructor.
"""
from ti_matrix.learning import ActionRecord, CachingEnvironment, LearningProposer, Statistics
from ti_matrix.model import LLMEvaluator, LLMMoveProposer, LLMSynthesizer, ModelPort, parse_json
from ti_matrix.protocols import (
    Action,
    ActionSpec,
    Environment,
    Evaluation,
    Evaluator,
    Goal,
    Move,
    Observation,
    Proposer,
    Simulator,
    TerminalCondition,
    TerminalContext,
    render_action_specs,
)
from ti_matrix.search import (
    DEFAULT_TERMINAL_CONDITIONS,
    BudgetExhausted,
    EngineBudget,
    EngineEvent,
    NoRunnableActions,
    NothingImproves,
    StateEngine,
)
from ti_matrix.simulator import LLMSimulator
from ti_matrix.state import AgentState
from ti_matrix.tools import (
    CompositeEnvironment,
    EngineTools,
    Memory,
    Resolution,
    ToolSet,
    ToolSetError,
    ToolSource,
)

__all__ = [
    # contracts
    "Action", "ActionSpec", "Environment", "Evaluation", "Evaluator", "Goal", "Move", "Observation",
    "Proposer", "Simulator", "TerminalCondition", "TerminalContext", "render_action_specs",
    # state
    "AgentState",
    # engine
    "StateEngine", "EngineBudget", "EngineEvent",
    # terminal conditions
    "DEFAULT_TERMINAL_CONDITIONS", "BudgetExhausted", "NoRunnableActions", "NothingImproves",
    # model layer
    "ModelPort", "LLMMoveProposer", "LLMEvaluator", "LLMSimulator", "LLMSynthesizer", "parse_json",
    # tool sets
    "CompositeEnvironment", "EngineTools", "Memory", "Resolution", "ToolSet", "ToolSetError", "ToolSource",
    # what the engine learns from its own runs
    "ActionRecord", "CachingEnvironment", "LearningProposer", "Statistics",
]
