"""The engine's contracts. Nothing in this file — or in this package — knows what an environment is.

A state-driven agent works on any environment that can describe its actions and perform them: a desktop
app, a shell, a repo, a browser, a game. The engine owns the state and the search; an adapter owns the
environment. That is the whole boundary:

    Goal ─► State ─► Proposer ─► candidates ─► Environment.probe (or Simulator.predict)
                                                      │
                                      Evaluator ◄─────┘  (one call scores every outcome)
                                          │
                                 SearchStrategy ─► Transition (State.apply) ─► new State
                                          │
                                 TerminalCondition decides when it is over

Everything above is data or a Protocol. Importing a host application here is a bug, and
`tests/ti_matrix/test_boundary.py` fails the build if it ever happens.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Optional, Protocol, Sequence, runtime_checkable

_FACT_CHARS = 320  # how much of an observation a stored fact keeps


# ─── The goal, and the actions the engine may take ──────────────────────────


@dataclass(frozen=True)
class Goal:
    """What is being pursued. Constraints are extra conditions on a sound answer."""

    text: str
    constraints: tuple[str, ...] = ()


@dataclass(frozen=True)
class ActionSpec:
    """One thing an environment can be asked to do, as the engine needs to describe it to a model.

    ``read_only`` is the safety boundary: an action that is not read-only is never performed as a probe —
    it is predicted by a Simulator when one is configured, and otherwise surfaced for confirmation.

    ``supersedes`` is how several sources of actions coexist without ambiguity when two of them offer the
    same thing (see ``ti_matrix.tools``): the name of the tool this one is meant to replace, so a
    replacement does not have to be named identically to what it replaces. It never reaches the model's
    prompt — it is a resolution input, not a description. The source that supplies a tool is the
    ``ToolSource`` holding it, which is the one place that fact is stated.
    """

    name: str
    description: str
    args_hint: str = ""
    read_only: bool = True
    supersedes: str = ""


def render_action_specs(specs: Sequence[ActionSpec] | dict[str, ActionSpec]) -> str:
    """The tool section of a proposer prompt: one line per action, stable order."""
    items = specs.values() if isinstance(specs, dict) else specs
    return "\n".join(f"- {s.name}: {s.description} args={s.args_hint}".rstrip() for s in items)


@dataclass(frozen=True)
class Action:
    """Something the engine could do next.

    No action name is reserved, and no action settles a goal: the evaluator's ``done`` does that, and it
    requires an answer grounded in real facts. That is deliberate — a model able to *propose* finishing
    would hold the one decision the search exists to keep honest. A proposal named ``finish`` is simply an
    action no environment knows, and is remembered as a failed move like any other.
    """

    tool: str
    args: dict = field(default_factory=dict)
    why: str = ""

    def fingerprint(self) -> str:
        blob = json.dumps({"t": self.tool, "a": self.args}, sort_keys=True, default=str)
        return hashlib.sha1(blob.encode()).hexdigest()[:12]

    def label(self) -> str:
        arg = ", ".join(f"{k}={str(v)[:60]}" for k, v in self.args.items())
        return f"{self.tool}({arg})"


# `Move` is the engine's older word for an Action; both names are public so callers can read either.
Move = Action


# ─── What happened, and what it was worth ───────────────────────────────────


@dataclass(frozen=True)
class Observation:
    """What an action actually produced. ``predicted`` marks a simulated (not real) outcome.

    A predicted observation may be scored and reasoned about, but it is NOT a fact: the engine never
    records it as known (see ``AgentState.learn/apply``).
    """

    move: Action
    ok: bool
    text: str
    predicted: bool = False

    def fact(self) -> str:
        """One line describing what this observation established — the shape facts are stored in."""
        head = " ".join(self.text.split())[:_FACT_CHARS]
        return f"{self.move.label()} -> {'ok' if self.ok else 'FAILED'}: {head}"


@dataclass(frozen=True)
class Evaluation:
    """How good a state is relative to the goal. ``done`` requires an ``answer`` grounded in facts."""

    progress: float = 0.0  # 0..1
    done: bool = False
    answer: str = ""
    reason: str = ""


# ─── The ports an adapter fills in ──────────────────────────────────────────


@runtime_checkable
class Environment(Protocol):
    """Where actions happen. An adapter implements exactly this.

    ``probe`` must be safe to call for any action the engine marks read-only, and must return an
    Observation rather than raise — a failed probe is information the search uses.
    """

    name: str

    def tools(self) -> dict[str, ActionSpec]: ...

    async def probe(self, action: Action) -> Observation: ...

    def is_read_only(self, action: Action) -> Optional[bool]:
        """True/False from the environment's own declaration, None when it does not know the action."""
        ...


@runtime_checkable
class Simulator(Protocol):
    """Predicts an action's outcome without performing it (for actions that cannot be probed).

    A prediction is labelled ``predicted=True`` downstream and never learned as a fact.
    """

    async def predict(self, state: Any, action: Action) -> Observation: ...


@runtime_checkable
class Proposer(Protocol):
    """Proposes up to ``n`` candidate actions, never one already in ``avoid`` (fingerprints)."""

    async def propose(self, state: Any, n: int, avoid: set[str]) -> list[Action]: ...


@runtime_checkable
class Evaluator(Protocol):
    """Scores every outcome of a fan in one call: progress 0..1, and whether the goal is settled."""

    async def evaluate(self, state: Any, outcomes: Sequence[Observation]) -> list[Evaluation]: ...


class TerminalCondition(Protocol):
    """Decides that the search is over, and says why.

    ``check`` returns a stop reason (the engine then emits ``stopped`` with it and the facts known), or
    None to let the search continue. ``point`` names the decision the loop is making, so a condition
    states where it applies instead of relying on being consulted in the right order:

      - ``"before_propose"``   — may we ask the model for another fan at all? (budgets live here)
      - ``"no_actions"``       — nothing proposed can be run here; is that the end?
      - ``"no_improvement"``   — nothing beat where we stand; is that the end?

    A condition that means "the goal is settled" is not a stop reason: the engine treats the evaluator's
    ``done`` as the settled path and reports ``done`` instead.
    """

    def check(self, state: Any, ctx: "TerminalContext", point: str) -> Optional[str]: ...


@dataclass(frozen=True)
class TerminalContext:
    """Everything a TerminalCondition may look at. Plain data, so conditions are testable alone."""

    budget: Any
    calls: int
    backtracks: int
    depth: int
    runnable: int  # how many of the proposed candidates can actually be probed
    best_done: bool
    best_progress: float
    state_progress: float
    history_len: int


# There is deliberately no ``SearchStrategy`` protocol yet. The loop in ``search.py`` IS the search
# (a beam of one with backtracking), and the parts a different strategy would replace — what to propose,
# how to score outcomes, whether to predict instead of probe, and when to stop — are already injected
# separately (Proposer, Evaluator, Simulator, TerminalCondition). Extracting a strategy protocol before a
# second strategy exists would be an interface with one implementation and no evidence behind it; a beam
# wider than one is the slice that earns it.
