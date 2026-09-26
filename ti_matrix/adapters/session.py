"""What a shell command wants around a run: remembering, recording, and answering.

Three things were built and none of them had reached a command: the learning record (`ti_matrix.learning`), the
fact that a run can be written down (`run_log`), and the fact that the engine will *ask* before it does
something that changes the world (`confirm`). This is the one place they are wired together, so each CLI gets
the same semantics and there is one description of what the flags mean.

    --remember FILE   load what earlier runs learned from FILE, learn into it, save it back. The proposer is
                      ordered by that record, `recall` joins the tool set so the model itself can ask what is
                      known here, and the file is written even when the run fails.
    --record FILE     append every event, one JSON line each, to read afterwards:
                      `python -m ti_matrix.adapters.run_log FILE`.
    --ask NAMES       ask whoever is at the terminal whether these actions may be performed — per action, at
                      the moment it would happen, showing the model's own reason. Nobody there, or a blank
                      answer, is a refusal.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Optional, TextIO

from ti_matrix.adapters import run_log, stats_file
from ti_matrix.adapters.confirm import Ask
from ti_matrix.learning import LearningProposer, Statistics
from ti_matrix.model import LLMEvaluator, LLMMoveProposer, LLMSynthesizer
from ti_matrix.protocols import Action, ActionSpec, Confirmer, Environment, Proposer

__all__ = ["Seats", "Session"]


def _names(flag: Optional[str]) -> set[str]:
    return {name.strip() for name in (flag or "").split(",") if name.strip()}


@dataclass
class Seats:
    """What one run needs in its seats — the two required ones, and the two that only a real model fills.

    ``model`` is the ``OpenAICompatModel`` a hosted run spends tokens through, or ``None`` for
    ``builtin`` — the rule-based reasoner touches no network and has no usage or balance to report.
    A CLI reads ``model.usage_snapshot()`` (and, opt in, ``await model.fetch_balance()``) after the run,
    the same thing the desktop app's sidecar does for its own ``settled`` frame.
    """

    proposer: Proposer
    evaluator: Any
    simulator: Optional[Any] = None
    synthesizer: Optional[Any] = None
    model: Optional[Any] = None


class Session:
    """One command's run, with what it carries in and what it leaves behind."""

    def __init__(
        self,
        *,
        remember: Optional[str | Path] = None,
        record: Optional[str | Path] = None,
        ask: Optional[str] = None,
        stream: Optional[TextIO] = None,
    ) -> None:
        self.remember = Path(remember).expanduser() if remember else None
        self.record = Path(record).expanduser() if record else None
        self._ask_names = _names(ask)
        self._asker: Optional[Ask] = Ask(stream) if self._ask_names else None
        self.statistics = Statistics()
        self._probes_before = 0
        if self.remember:
            self.statistics = stats_file.load(self.remember)
            self._probes_before = sum(record.probes for record in self.statistics.by_tool.values())

    # ── what goes in ──

    def environment(self, environment: Environment) -> Environment:
        """The environment a run will use. With a record to consult, the engine's own `recall` joins it."""
        if not self.remember:
            return environment
        from ti_matrix.tools import EngineTools

        return EngineTools(environment, memory=self.statistics)

    def proposer(self, port: Any, specs: dict[str, ActionSpec]) -> Proposer:
        """The model's proposals, ordered by what this world has actually rewarded — when there is a record."""
        return self._learned(LLMMoveProposer(port, specs))

    def synthesizer(self, port: Any) -> LLMSynthesizer:
        """Answers from the facts when a run stops unsettled. Costs no extra call: the budget reserved one."""
        return LLMSynthesizer(port)

    def _learned(self, proposer: Proposer) -> Proposer:
        """Wrapped in what earlier runs rewarded, when there is a record — the one thing every proposer
        gets regardless of whether it is a model's guesses or a world's own rules."""
        return LearningProposer(proposer, self.statistics) if self.remember else proposer

    def seats(self, world_name: str, env: Environment, model_name: str,
              model_factory: Callable[[], Any], *, want_simulator: bool = False) -> Seats:
        """The seats for one run, routed by ``model_name``.

        ``"builtin"`` fills both required seats with this world's rule-based reasoner
        (``ti_matrix.adapters.builtin.reasoner_for``) and never calls ``model_factory`` — the CLIs used
        to build an ``OpenAICompatModel`` unconditionally, so ``--model builtin`` still dialled the
        default ``base_url`` and every run hit ``proposer_error`` against nothing listening there.
        Anything else builds the model from ``model_factory`` and wires the three LLM-backed seats
        exactly as before. A reasoner has nothing to predict with, so ``want_simulator`` is only honoured
        for a real model — a world driven by rules only ever names a non-read-only action for
        confirmation, the same as a real model with no simulator configured.
        """
        from ti_matrix.adapters.builtin import is_builtin, reasoner_for

        tools = env.tools()
        if is_builtin(model_name):
            reasoner = reasoner_for(world_name, tools, env)
            return Seats(self._learned(reasoner), reasoner)
        model = model_factory()
        simulator = None
        if want_simulator:
            from ti_matrix.simulator import LLMSimulator
            simulator = LLMSimulator(model)
        return Seats(self.proposer(model, tools), LLMEvaluator(model, tools), simulator, self.synthesizer(model), model)

    def confirmer(self, available: dict[str, ActionSpec]) -> Optional[Confirmer]:
        """The confirmer, having checked its names against the actions that exist.

        A name that matches nothing is a typo in a flag, and a typo that silently refuses every action would
        look exactly like an engine that never asks — so it stops the command instead.
        """
        if self._asker is None:
            return None
        unknown = sorted(self._ask_names - set(available))
        if unknown:
            raise SystemExit(f"--ask names actions this environment does not have: {', '.join(unknown)}")
        return _OnlyThese(self._asker, self._ask_names)

    # ── what happens during, and after ──

    def observe(self, event: Any) -> None:
        """Take one event: learn from it, and write it down if a log was asked for."""
        self.statistics.observe(event)
        if self.record:
            run_log.write(self.record, event)

    def save(self) -> str:
        """Write the record back and say what changed. The caller runs this even when the run failed."""
        if not self.remember:
            return ""
        probes_now = sum(record.probes for record in self.statistics.by_tool.values())
        stats_file.save(self.remember, self.statistics)
        learned = probes_now - self._probes_before
        return (f"remembered: {learned} new probe(s), {len(self.statistics.by_tool)} tool(s) known in "
                f"{self.remember}") if learned else f"remembered: nothing new to add to {self.remember}"

    async def usage_note(self, model: Optional[Any], *, balance: bool = False) -> str:
        """One line for stderr: the tokens this run spent, and — opt in — what the account has left.

        ``model`` is ``Seats.model``: ``None`` for ``builtin``, which touched no network and spent
        nothing to report. A hosted endpoint that never sent a ``usage`` object back also reports
        nothing, honestly, rather than a set of zeroes that would read as "this run cost nothing".
        """
        if model is None:
            return ""
        usage = model.usage_snapshot()
        if not usage["calls"]:
            return ""
        parts = [f"tokens: {usage['prompt_tokens']} in + {usage['completion_tokens']} out = "
                 f"{usage['total_tokens']} total over {usage['calls']} call(s)"]
        if balance:
            from ti_matrix.adapters.openai_compat import describe_balance
            try:
                info = await model.fetch_balance()
            except RuntimeError as exc:
                parts.append(f"balance: unavailable ({exc})")
            else:
                parts.append(f"balance: {describe_balance(info)}" if info is not None
                             else "balance: not published for this endpoint")
        return " · ".join(parts)


class _OnlyThese:
    """Asks about the actions it was told to care about, and refuses the rest without asking."""

    def __init__(self, inner: Confirmer, names: set[str]) -> None:
        self.inner, self.names = inner, names

    async def confirm(self, action: Action, reason: str) -> bool:
        if action.tool not in self.names:
            return False
        return await self.inner.confirm(action, reason)
