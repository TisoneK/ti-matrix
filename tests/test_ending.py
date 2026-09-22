"""The ending: a run that stops with facts says what they amount to — and never claims it settled.

Measured before building: four runs spent their whole budget, reported ten facts and no answer, with progress
climbing the whole way (0.7, 0.85, 0.95, 0.98). Nothing had stalled. The budget had run out holding the answer,
which is why the fix is arithmetic on the budget rather than a guess about progress.
"""
from __future__ import annotations

import pytest

from ti_matrix import (
    Action,
    ActionSpec,
    AgentState,
    EngineBudget,
    Evaluation,
    Goal,
    Observation,
    StateEngine,
    TerminalContext,
)
from ti_matrix.search import BudgetExhausted


class Grinds:
    """An environment whose every action succeeds — so facts accumulate and the goal still never settles."""

    name = "grinds"

    def tools(self):
        return {"look": ActionSpec("look", "read something", '{"n": 1}')}

    def is_read_only(self, action):
        return None if action.tool not in self.tools() else True

    async def probe(self, action):
        return Observation(action, True, f"fact number {action.args.get('n')}")


class FreshEveryRound:
    """Proposes a different action each round, so nothing is ever in `avoid`."""

    def __init__(self):
        self.round = 0

    async def propose(self, state, n, avoid):
        self.round += 1
        return [Action("look", {"n": self.round}, "because")]


class Halfway:
    """Always some progress, never settled — the shape a chat model produced on an open-ended question."""

    async def evaluate(self, state, outcomes):
        return [Evaluation(0.5, False, "", "closer, not there") for _ in outcomes]


class Answers:
    """A synthesizer that records being asked."""

    def __init__(self, text="the facts amount to this"):
        self.text, self.asked = text, 0

    async def answer(self, state):
        self.asked += 1
        return self.text


async def grind(*, synthesizer=None, budget: int = 6):
    engine = StateEngine(Grinds(), proposer=FreshEveryRound(), evaluator=Halfway(), synthesizer=synthesizer,
                         budget=EngineBudget(max_model_calls=budget))
    return [event async for event in engine.run(Goal("find the thing"))]


# ─── the arithmetic, which needs no engine ──────────────────────────────────


def ctx(*, calls: int, budget: int, reserve: int, max_depth: int = 6) -> TerminalContext:
    return TerminalContext(budget=EngineBudget(max_model_calls=budget, max_depth=max_depth), calls=calls,
                           backtracks=0, depth=0,
                           runnable=1, best_done=False, best_progress=0.0, state_progress=0.0, history_len=0,
                           answer_reserve=reserve)


def test_the_last_affordable_call_belongs_to_the_answer():
    """A fan costs two calls and the answer costs one, so the last fan that fits is the one before it."""
    with_facts = AgentState(Goal("g"), facts=("something real",))
    nothing_known = AgentState(Goal("g"))

    assert BudgetExhausted().check(with_facts, ctx(calls=4, budget=6, reserve=1), "before_propose") == "budget"
    assert BudgetExhausted().check(with_facts, ctx(calls=3, budget=6, reserve=1), "before_propose") is None
    # with nothing to answer from, there is nothing to reserve, so the search gets the call
    assert BudgetExhausted().check(nothing_known, ctx(calls=4, budget=6, reserve=1), "before_propose") is None
    # and without a synthesizer the arithmetic is exactly what it always was
    assert BudgetExhausted().check(with_facts, ctx(calls=4, budget=6, reserve=0), "before_propose") is None
    assert BudgetExhausted().check(with_facts, ctx(calls=5, budget=6, reserve=0), "before_propose") == "budget"


def test_depth_still_stops_a_run_on_its_own():
    deep = AgentState(Goal("g"), facts=("something",), depth=3)
    assert BudgetExhausted().check(deep, ctx(calls=0, budget=99, reserve=1, max_depth=3),
                                   "before_propose") == "budget"


# ─── the ending, through the engine ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_a_run_that_runs_out_still_says_what_its_facts_amount_to():
    answer = Answers("it read three things; the goal needs one it could not reach")
    events = await grind(synthesizer=answer)
    last = events[-1]

    assert last.kind == "stopped" and last.data["settled"] is False  # a stop, never a settled run
    assert last.data["reason"] == "budget"
    assert last.data["partial_answer"].startswith("it read three things")
    assert "NOT verified" in last.data["answer_basis"] and "fact(s)" in last.data["answer_basis"]
    assert answer.asked == 1
    assert last.data["facts"], "the facts are still reported in full"
    assert last.data["model_calls"] <= 6, "the answering call came out of the budget, not on top of it"


@pytest.mark.asyncio
async def test_the_answer_costs_a_fan_not_extra_money():
    """The same run with and without a synthesizer: one fewer fan, one answer, inside the same budget."""
    without = await grind()
    with_answer = await grind(synthesizer=Answers())
    fans = lambda events: sum(1 for e in events if e.kind == "candidates")  # noqa: E731

    assert fans(with_answer) == fans(without) - 1
    assert with_answer[-1].data["model_calls"] <= without[-1].data["model_calls"]
    assert "partial_answer" not in without[-1].data  # nothing invented when nobody can answer


@pytest.mark.asyncio
async def test_nothing_a_synthesizer_says_can_settle_a_goal():
    """The one property worth protecting: an unverified answer is never reported as a settled run."""
    events = await grind(synthesizer=Answers("I am completely certain and here is the answer"))
    endings = [e for e in events if e.kind in ("done", "stopped")]
    assert len(endings) == 1 and endings[0].data["settled"] is False
    assert "answer" not in endings[0].data  # `answer` belongs to `done`; this one is `partial_answer`
    assert endings[0].data["reason"] == "budget"


@pytest.mark.asyncio
async def test_a_break_or_an_empty_answer_leaves_the_stop_honest():
    class Broken:
        async def answer(self, state):
            raise RuntimeError("the endpoint went away")

    broken = (await grind(synthesizer=Broken()))[-1]
    assert broken.data["settled"] is False and "partial_answer" not in broken.data
    assert "the endpoint went away" in broken.data["answer_note"]

    silent = (await grind(synthesizer=Answers("")))[-1]
    assert "partial_answer" not in silent.data and "answer_note" not in silent.data
    assert silent.data["model_calls"] <= 6, "an answer that never came is not charged for"


@pytest.mark.asyncio
async def test_a_run_that_settles_never_asks_for_an_answer():
    """A settled run already has its answer, and the synthesizer is not consulted."""
    answer = Answers()
    engine = StateEngine(Grinds(), proposer=FreshEveryRound(),
                         evaluator=Halfway(), synthesizer=answer,
                         budget=EngineBudget(max_model_calls=6))

    class SettlesOnTheFirstFan:
        async def evaluate(self, state, outcomes):
            return [Evaluation(1.0, True, "the thing was found", "found it") for _ in outcomes]

    engine.evaluator = SettlesOnTheFirstFan()
    events = [event async for event in engine.run(Goal("find the thing"))]

    assert events[-1].kind == "done" and events[-1].data["answer"] == "the thing was found"
    assert answer.asked == 0
    assert not any(e.kind == "stopped" for e in events)
