"""The engine: the run loop of a state-driven search, and the event record it produces.

The loop is a beam of one with backtracking — propose candidate actions at a state, probe the read-only
ones (or predict them, when a Simulator is configured and an action cannot be probed), score every
outcome in one model call, apply the best, and when nothing beats where the state stands, retreat to the
parent state keeping every real fact and pruning the action that led into the dead end.

The loop itself knows nothing about any particular environment. It takes an Environment (where actions
happen), a Proposer and an Evaluator (the model's two jobs), an optional Simulator, a budget, and a list
of TerminalConditions. Every step is an ``EngineEvent`` — states, actions, outcomes, never reasoning.
"""
from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Optional, Sequence

from ti_matrix.protocols import (
    Action,
    Confirmer,
    Environment,
    Evaluator,
    Goal,
    Observation,
    Proposer,
    Simulator,
    TerminalCondition,
    TerminalContext,
)
from ti_matrix.state import AgentState


@dataclass(frozen=True)
class EngineBudget:
    """What a run may spend. Every dimension is a hard stop, and each stop is reported honestly."""

    max_depth: int = 6
    max_branches: int = 3
    max_model_calls: int = 16
    max_backtracks: int = 2


@dataclass
class EngineEvent:
    """One step, as a plain record. This is the UI contract: states, actions, outcomes — never reasoning.

    kinds: state | candidates | probe | evaluation | selected | backtrack | confirmation |
    needs_confirmation | done | stopped
    Tree ids: `state` carries `node` and `parent`; `selected`/`backtrack` name the node they move to.
    """

    kind: str
    data: dict[str, Any] = field(default_factory=dict)
    seq: int = 0  # position in the run
    t_ms: int = 0  # ms since the run started

    def to_dict(self) -> dict[str, Any]:
        return {"seq": self.seq, "t_ms": self.t_ms, "kind": self.kind, **self.data}


# ─── Terminal conditions: the ways a search can be over ─────────────────────
# Each is small, tabled and testable on its own; the loop asks them where it would otherwise run on.
# The reason strings are the ones the UI and the tests already speak.


class BudgetExhausted:
    """Depth or model-call budget is spent before another fan can be proposed."""

    point = "before_propose"

    def check(self, state: AgentState, ctx: TerminalContext, point: str) -> Optional[str]:
        if point != self.point:
            return None
        b = ctx.budget
        if state.depth >= b.max_depth or ctx.calls + 2 > b.max_model_calls:
            return "budget"
        return None


class NoRunnableActions:
    """Nothing the model proposed can be probed here, and there is nowhere left to retreat to."""

    point = "no_actions"

    def check(self, state: AgentState, ctx: TerminalContext, point: str) -> Optional[str]:
        if point != self.point:
            return None
        return "no_moves" if ctx.runnable == 0 and ctx.history_len == 0 else None


class NothingImproves:
    """No outcome beat the state we are standing on, and backtracks are spent or unavailable."""

    point = "no_improvement"

    def check(self, state: AgentState, ctx: TerminalContext, point: str) -> Optional[str]:
        if point != self.point:
            return None
        if ctx.best_done or ctx.runnable == 0 or ctx.best_progress > ctx.state_progress:
            return None
        if ctx.backtracks >= ctx.budget.max_backtracks or ctx.history_len == 0:
            return "no_progress"
        return None


DEFAULT_TERMINAL_CONDITIONS: tuple[TerminalCondition, ...] = (BudgetExhausted(), NoRunnableActions(), NothingImproves())


class StateEngine:
    """A state-driven agent run. Construct with an environment and the model's two jobs."""

    def __init__(
        self,
        environment: Environment,
        *,
        proposer: Proposer,
        evaluator: Evaluator,
        simulator: Optional[Simulator] = None,
        confirmer: Optional[Confirmer] = None,
        budget: Optional[EngineBudget] = None,
        terminal_conditions: Sequence[TerminalCondition] = DEFAULT_TERMINAL_CONDITIONS,
    ) -> None:
        self.environment = environment
        self.proposer = proposer
        self.evaluator = evaluator
        self.simulator = simulator
        self.confirmer = confirmer
        self.budget = budget or EngineBudget()
        self.terminal_conditions = tuple(terminal_conditions)

    async def run(self, goal: Goal) -> AsyncIterator[EngineEvent]:
        """`_steps` stamped with the run clock, a sequence number and the tree ids a UI needs."""
        t0 = time.monotonic()
        seq = 0
        counter = 0
        cur: Optional[str] = None
        stack: list[str] = []
        pending_parent: Optional[str] = None
        async for ev in self._steps(goal):
            if ev.kind == "state":
                node = f"n{counter}"
                counter += 1
                ev.data.update(node=node, parent=pending_parent)
                if pending_parent is not None:
                    stack.append(pending_parent)
                cur, pending_parent = node, None
            elif ev.kind == "selected":
                pending_parent = cur
            elif ev.kind == "backtrack":
                cur = stack.pop() if stack else cur
                ev.data["node"] = cur
            if ev.kind not in ("state", "backtrack"):
                ev.data["at"] = cur
            seq += 1
            ev.seq, ev.t_ms = seq, int((time.monotonic() - t0) * 1000)
            yield ev

    def _stop_reason(self, state: AgentState, ctx: TerminalContext, point: str) -> Optional[str]:
        """Ask every configured condition about the decision the loop is making right now."""
        for condition in self.terminal_conditions:
            reason = condition.check(state, ctx, point)
            if reason:
                return reason
        return None

    async def _steps(self, goal: Goal) -> AsyncIterator[EngineEvent]:
        b = self.budget
        state = AgentState(goal)
        history: list[AgentState] = []  # ancestors, for backtracking
        calls = backtracks = 0
        yield EngineEvent("state", {"depth": 0, "goal": goal.text, **state.to_dict()})

        while True:
            ctx = self._ctx(state, calls, backtracks, 1, False, 0.0, len(history))
            stop = self._stop_reason(state, ctx, "before_propose")
            if stop:
                yield self._stopped(stop, state, calls)
                return

            avoid = set(state.failed) | set(state.tried)
            try:
                actions = await self.proposer.propose(state, b.max_branches, avoid)
            except Exception as exc:  # noqa: BLE001
                yield self._stopped(f"proposer_error: {exc}", state, calls)
                return
            calls += 1
            yield EngineEvent(
                "candidates",
                {"moves": [{"fp": m.fingerprint(), "label": m.label(), "tool": m.tool, "why": m.why} for m in actions]},
            )

            # Which of these can this environment run? An action it does not have is remembered as failed;
            # one that is not read-only is predicted when a simulator is configured, otherwise surfaced for
            # confirmation (refuse only on a fact you verified yourself).
            runnable: list[Action] = []
            predicted: dict[str, Observation] = {}
            for m in actions:
                known = self.environment.is_read_only(m)
                if known is None:
                    state = state.with_failed(m.fingerprint())
                    continue
                if known:
                    runnable.append(m)
                    continue
                # An action that changes something. Ask whoever can grant it — a person, a policy — and if
                # nobody grants it, fall back to predicting it, and failing that, name it and carry on.
                granted, reason = await self._ask(m)
                if reason:  # a decision was made, so it belongs in the record like everything else
                    yield EngineEvent(
                        "confirmation",
                        {"fp": m.fingerprint(), "move": m.label(), "granted": granted, "why": reason},
                    )
                if granted:
                    runnable.append(m)
                elif self.simulator is not None:
                    predicted[m.fingerprint()] = await self.simulator.predict(state, m)
                    runnable.append(m)
                else:
                    if reason:  # a decision was made against it, so stop proposing it
                        state = state.with_failed(m.fingerprint())
                    yield EngineEvent(
                        "needs_confirmation",
                        {"fp": m.fingerprint(), "move": m.label(), "why": m.why, "confirmer_said": reason},
                    )

            if not runnable:
                ctx = self._ctx(state, calls, backtracks, 0, False, 0.0, len(history))
                if self._stop_reason(state, ctx, "no_actions"):
                    yield self._stopped("no_moves", state, calls)
                    return
                state, history, backtracks, ev = self._backtrack(state, history, backtracks)
                if ev is None:
                    yield self._stopped("no_moves", state, calls)
                    return
                yield ev
                continue

            timed = await asyncio.gather(*(self._probe(m, predicted.get(m.fingerprint())) for m in runnable))
            outcomes: list[Observation] = [o for o, _ in timed]
            for o, ms in timed:
                yield EngineEvent(
                    "probe",
                    {
                        "fp": o.move.fingerprint(), "move": o.move.label(), "ok": o.ok, "chars": len(o.text),
                        "ms": ms, "excerpt": " ".join(o.text.split())[:320], "predicted": o.predicted,
                    },
                )

            try:
                evals = await self.evaluator.evaluate(state, outcomes)
            except Exception as exc:  # noqa: BLE001
                yield self._stopped(f"evaluator_error: {exc}", state, calls)
                return
            calls += 1
            for o, e in zip(outcomes, evals):
                yield EngineEvent(
                    "evaluation",
                    {"fp": o.move.fingerprint(), "move": o.move.label(), "progress": e.progress, "done": e.done,
                     "reason": e.reason},
                )

            ranked = sorted(
                (p for p in zip(outcomes, evals) if p[0].ok),
                key=lambda p: (p[1].done, p[1].progress),
                reverse=True,
            )
            # A predicted outcome may be scored and compared — it must never BE the transition. The world
            # did not change: only a real probe becomes knowledge, moves the state, or settles a goal.
            ranked_real = [p for p in ranked if not p[0].predicted]
            predicted_only = [p for p in ranked if p[0].predicted]
            best_done = bool(ranked_real and ranked_real[0][1].done)
            best_progress = ranked_real[0][1].progress if ranked_real else 0.0

            if not ranked_real and predicted_only:
                # Everything worth doing here would have to be performed, and this engine performs only
                # read-only actions. That is an honest stop — and it names the action it would need.
                obs, val = predicted_only[0]
                yield self._needs_action(obs, val, state, calls)
                return

            if not ranked or (not best_done and best_progress <= state.progress):
                # Nothing beats where we stand: keep what the real probes taught, then back up.
                for o in outcomes:
                    state = state.learn(o).with_failed(o.move.fingerprint())
                ctx = self._ctx(state, calls, backtracks, len(runnable), False, best_progress, len(history))
                if self._stop_reason(state, ctx, "no_improvement"):
                    yield self._stopped("no_progress", state, calls)
                    return
                state, history, backtracks, ev = self._backtrack(state, history, backtracks)
                if ev is None:
                    yield self._stopped("no_progress", state, calls)
                    return
                yield ev
                continue

            best_obs, best_eval = ranked_real[0]
            history.append(state)
            for o in outcomes:
                if o is not best_obs:
                    state = state.learn(o)
                if not o.ok:
                    # A probe that really failed is remembered as failed HERE too, not only on a backtrack:
                    # the same action would fail again at the next state, and the point of fingerprinting is
                    # that it is not proposed twice.
                    state = state.with_failed(o.move.fingerprint())
            state = state.apply(best_obs, best_eval)
            yield EngineEvent(
                "selected",
                {"fp": best_obs.move.fingerprint(), "move": best_obs.move.label(), "progress": best_eval.progress},
            )
            yield EngineEvent("state", {"depth": state.depth, **state.to_dict()})
            if best_eval.done:
                yield EngineEvent(
                    "done", {"answer": best_eval.answer, "trail": list(state.trail), "model_calls": calls}
                )
                return

    def _ctx(
        self,
        state: AgentState,
        calls: int,
        backtracks: int,
        runnable: int,
        best_done: bool,
        best_progress: float,
        history_len: int,
    ) -> TerminalContext:
        """What a terminal condition is allowed to see at this point in the run."""
        return TerminalContext(
            budget=self.budget,
            calls=calls,
            backtracks=backtracks,
            depth=state.depth,
            runnable=runnable,
            best_done=best_done,
            best_progress=best_progress,
            state_progress=state.progress,
            history_len=history_len,
        )

    async def _probe(self, action: Action, predicted: Optional[Observation]) -> tuple[Observation, int]:
        """One probe, timed. A predicted outcome never touches the environment."""
        t0 = time.monotonic()
        obs = predicted if predicted is not None else await self.environment.probe(action)
        return obs, int((time.monotonic() - t0) * 1000)

    def _backtrack(
        self, state: AgentState, history: list[AgentState], backtracks: int
    ) -> tuple[AgentState, list[AgentState], int, Optional[EngineEvent]]:
        """Restore the previous state, carrying the failed-action memory (and learned facts) back."""
        if backtracks >= self.budget.max_backtracks or not history:
            return state, history, backtracks, None
        parent = state.retreat_to(history[-1])
        return parent, history[:-1], backtracks + 1, EngineEvent("backtrack", {"to_depth": parent.depth})

    async def _ask(self, action: Action) -> tuple[bool, str]:
        """Ask the confirmer. No confirmer, or one that breaks, is a refusal — never a crash mid-run."""
        if self.confirmer is None:
            return False, ""
        try:
            granted = bool(await self.confirmer.confirm(action, action.why))
            return granted, "the confirmer granted it" if granted else "the confirmer refused it"
        except Exception as exc:  # noqa: BLE001 — a host bug is not a reason to lose the run
            return False, f"the confirmer raised {type(exc).__name__}: {exc}"

    @staticmethod
    def _needs_action(obs: Observation, evaluation, state: AgentState, calls: int) -> EngineEvent:
        """The honest end of a run whose goal needs an action this engine may not perform: name it, with the
        predicted outcome, and say plainly that the goal is NOT settled."""
        return EngineEvent(
            "stopped",
            {
                "reason": "needs_action", "settled": False, "facts": list(state.facts), "trail": list(state.trail),
                "model_calls": calls,
                "needs": obs.move.label(), "needs_why": obs.move.why,
                "predicted": {"ok": obs.ok, "result": obs.text, "progress": evaluation.progress},
            },
        )

    @staticmethod
    def _stopped(reason: str, state: AgentState, calls: int) -> EngineEvent:
        """An honest stop: what is known, and that the goal is NOT settled."""
        return EngineEvent(
            "stopped",
            {
                "reason": reason, "settled": False, "facts": list(state.facts),
                "trail": list(state.trail), "model_calls": calls,
            },
        )
