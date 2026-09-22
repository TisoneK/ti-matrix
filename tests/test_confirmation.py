"""Answering the question the engine asks: may this one action be performed?

The engine's boundary is that it performs read-only actions, and a run that needs anything else stops and names
it. A `Confirmer` is the third answer — a person or a policy granting one action, at the moment it would
happen — and these tests are about the three things that makes true: it is really performed when granted, it is
really not when refused, and the decision is in the run's record either way.
"""
from __future__ import annotations

import io

import pytest

from ti_matrix import (
    Action,
    ActionSpec,
    EngineBudget,
    Evaluation,
    Goal,
    Observation,
    StateEngine,
)
from ti_matrix.adapters.confirm import Ask, Granted


class Reads:
    name = "reads"

    def __init__(self):
        self.performed: list[str] = []

    def tools(self):
        return {
            "look": ActionSpec("look", "read something", "{}"),
            "press": ActionSpec("press", "press the button", "{}", read_only=False),
        }

    def is_read_only(self, action):
        spec = self.tools().get(action.tool)
        return None if spec is None else spec.read_only

    async def probe(self, action):
        self.performed.append(action.label())
        return Observation(action, True, "the button was pressed" if action.tool == "press" else "read it")


class OneMove:
    def __init__(self, *tools):
        self.tools = list(tools)

    async def propose(self, state, n, avoid):
        return [Action(t, {}, "because") for t in self.tools if Action(t, {}).fingerprint() not in avoid][:n]


class Settles:
    """Settles the goal when the fact it is waiting for appears."""

    def __init__(self, needle):
        self.needle = needle

    async def evaluate(self, state, outcomes):
        out = []
        for obs in outcomes:
            hit = obs.ok and self.needle in obs.text
            out.append(Evaluation(1.0 if hit else 0.3, hit, self.needle if hit else "", "looked"))
        return out


class WouldPredict:
    """A simulator that records being asked, so a test can tell whether it was."""

    def __init__(self):
        self.asked = 0

    async def predict(self, state, action):
        self.asked += 1
        return Observation(action, True, "it would be pressed", predicted=True)


async def run(*, tools, confirmer=None, simulator=None, needle="the button was pressed"):
    env = Reads()
    engine = StateEngine(env, proposer=OneMove(*tools), evaluator=Settles(needle), simulator=simulator,
                         confirmer=confirmer, budget=EngineBudget(max_model_calls=6))
    events = [e async for e in engine.run(Goal("press it"))]
    return env, events


@pytest.mark.asyncio
async def test_a_granted_action_is_really_performed_and_the_grant_is_in_the_record():
    confirmer = Granted(names={"press"})
    env, events = await run(tools=["press"], confirmer=confirmer)

    assert env.performed == ["press()"]  # it happened: this is not a prediction
    decision = [e for e in events if e.kind == "confirmation"]
    assert len(decision) == 1 and decision[0].data["granted"] is True
    assert decision[0].data["move"] == "press()" and "granted" in decision[0].data["why"]
    assert events[-1].kind == "done"
    assert any("press()" in fact for fact in events[-1].data["trail"])
    assert confirmer.asked and confirmer.asked[0][0] == "press()"


@pytest.mark.asyncio
async def test_a_refused_action_is_not_performed_and_the_refusal_is_in_the_record():
    env, events = await run(tools=["press"], confirmer=Granted())  # grants nothing

    assert env.performed == []  # it never happened
    decision = [e for e in events if e.kind == "confirmation"]
    assert decision and decision[0].data["granted"] is False
    assert any(e.kind == "needs_confirmation" and e.data["move"] == "press()" for e in events)
    assert events[-1].data["settled"] is False
    assert not any(e.kind == "probe" and e.data["move"] == "press()" for e in events)


@pytest.mark.asyncio
async def test_a_grant_is_preferred_to_a_prediction_and_a_refusal_falls_back_to_one():
    """The order matters: a real yes is better than a hypothesis, and a no is better than nothing."""
    simulator = WouldPredict()
    env, events = await run(tools=["press"], confirmer=Granted(names={"press"}), simulator=simulator)
    assert env.performed == ["press()"] and simulator.asked == 0  # granted, so nothing was predicted

    env, events = await run(tools=["press"], confirmer=Granted(), simulator=simulator)
    assert env.performed == [] and simulator.asked == 1  # refused, so it was predicted instead
    probe = next(e for e in events if e.kind == "probe")
    assert probe.data["predicted"] is True


@pytest.mark.asyncio
async def test_a_confirmer_that_breaks_is_a_refusal_not_a_crash():
    class Broken:
        async def confirm(self, action, reason):
            raise RuntimeError("the person walked away")

    env, events = await run(tools=["press"], confirmer=Broken())
    assert env.performed == []
    decision = next(e for e in events if e.kind == "confirmation")
    assert decision.data["granted"] is False and "the person walked away" in decision.data["why"]
    assert events[-1].kind in ("stopped", "done")  # the run still ends, and ends honestly


@pytest.mark.asyncio
async def test_a_refusal_is_not_proposed_again_in_the_same_run():
    """A refusal is a decision, so the action is pruned — otherwise a run asks the same question forever."""
    env, events = await run(tools=["press", "press"], confirmer=Granted())
    assert len([e for e in events if e.kind == "confirmation"]) <= 2
    assert events[-1].kind == "stopped"


@pytest.mark.asyncio
async def test_without_a_confirmer_nothing_new_happens():
    """The old behaviour is untouched: name it, do not do it."""
    env, events = await run(tools=["press"])
    assert env.performed == []
    assert not any(e.kind == "confirmation" for e in events)
    assert any(e.kind == "needs_confirmation" for e in events)


# ─── the two confirmers a host can use ──────────────────────────────────────


@pytest.mark.asyncio
async def test_granting_by_name_is_not_granting_by_action():
    """The difference is the point: a tool may be fine in general and this use of it not."""
    exact = Action("click", {"selector": "#buy"})
    policy = Granted(names={"click"})
    assert await policy.confirm(exact, "") is True

    one = Granted(fingerprints={exact.fingerprint()})
    assert await one.confirm(exact, "") is True
    assert await one.confirm(Action("click", {"selector": "#sell"}), "") is False  # a different action
    assert [asked[2] for asked in one.asked] == [True, False]


@pytest.mark.asyncio
async def test_asking_at_a_stream_grants_only_a_clear_yes():
    for answer, expected in [("y\n", True), ("Y\n", True), ("yes\n", True), ("\n", False), ("no\n", False),
                             ("", False), ("maybe\n", False)]:
        confirmer = Ask(io.StringIO(answer), shower=lambda line: None)
        assert await confirmer.confirm(Action("click", {"selector": "#buy"}), "it says so") is expected, answer


@pytest.mark.asyncio
async def test_asking_with_no_way_to_ask_refuses_rather_than_hanging():
    class Broken:
        def readline(self):
            raise OSError("not a terminal")

    confirmer = Ask(Broken(), shower=lambda line: None)
    assert await confirmer.confirm(Action("click", {}), "") is False

    silent = Ask(io.StringIO("y\n"), ask=False, shower=lambda line: None)
    assert await silent.confirm(Action("click", {}), "") is False  # told not to ask, so it cannot grant


@pytest.mark.asyncio
async def test_the_question_shows_what_would_be_done_and_why():
    shown: list[str] = []
    confirmer = Ask(io.StringIO("y\n"), shower=shown.append)
    await confirmer.confirm(Action("click", {"selector": "#buy"}), "the price is behind it")
    text = " ".join(shown)
    assert "click(selector=#buy)" in text and "the price is behind it" in text and "[y/N]" in text
