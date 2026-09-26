"""The engine's search behavior, with scripted stubs — no environment, no host, no model."""
from __future__ import annotations

import time

import pytest

from ti_matrix import ActionSpec, AgentState, EngineBudget, Evaluation, Goal, Move, Observation, StateEngine
from ti_matrix.model import LLMEvaluator, LLMMoveProposer, parse_json

GOAL = Goal("find the project name")


def mv(tool="dir_explorer", **args):
    return Move(tool, args or {"path": "/x"}, "why")


class ScriptedProposer:
    """Returns the next scripted list of moves, minus anything in `avoid` (as the real one does)."""

    def __init__(self, *rounds):
        self.rounds, self.seen_avoid = list(rounds), []

    async def propose(self, state, n, avoid):
        self.seen_avoid.append(set(avoid))
        moves = self.rounds.pop(0) if self.rounds else []
        return [m for m in moves if m.fingerprint() not in avoid][:n]


class FakeExecutor:
    def __init__(self, results):  # {fingerprint-or-label: (ok, text)}
        self.results, self.ran = results, []

    async def run(self, move):
        self.ran.append(move.label())
        ok, text = self.results.get(move.label(), (True, "ok"))
        return Observation(move, ok, text)


CATALOG = {
    s.name: s
    for s in (
        ActionSpec("dir_explorer", "look in a folder", '{"path": "..."}'),
        ActionSpec("file_read", "read a file", '{"path": "..."}'),
        ActionSpec("file_write", "write a file", '{"path": "...", "content": "..."}', read_only=False),
        ActionSpec("shell", "run a command", '{"command": "..."}', read_only=False),
    )
}


class ScriptedEnvironment:
    """The smallest environment the engine needs: a tool table and a probe."""

    name = "scripted"

    def __init__(self, executor, catalog=None):
        self._executor, self._catalog = executor, catalog or CATALOG

    def tools(self):
        return self._catalog

    def is_read_only(self, action):
        spec = self._catalog.get(action.tool)
        return None if spec is None else spec.read_only

    async def probe(self, action):
        return await self._executor.run(action)


class RaisingEnvironment(ScriptedEnvironment):
    """A world that violates the probe contract for one path: it raises instead of returning
    a failed observation — the shape of a sandbox that times out, a driver that disconnects."""

    async def probe(self, action):
        if action.args.get("path") == "/boom":
            raise TimeoutError("the world took too long")
        return await super().probe(action)


class ScriptedEvaluator:
    def __init__(self, table):  # {label: Evaluation}
        self.table = table

    async def evaluate(self, state, outcomes):
        return [self.table.get(o.move.label(), Evaluation()) if o.ok else Evaluation() for o in outcomes]


class RetryEvaluator:
    """Raises on its first call, then scores from the table — recording every call it received,
    so a test can pin what the engine asked for on the retry. Its signature takes `view_chars`,
    so the engine is allowed to shorten the view on the retry."""

    def __init__(self, table):
        self.table, self.calls = table, []

    async def evaluate(self, state, outcomes, *, view_chars=None):
        self.calls.append(view_chars)
        if len(self.calls) == 1:
            raise RuntimeError("empty answer from the model: it spent all its output tokens reasoning")
        return [self.table.get(o.move.label(), Evaluation()) if o.ok else Evaluation() for o in outcomes]


class PlainRetryEvaluator:
    """The rule-based seats' plain signature — no `view_chars` keyword at all. Same script:
    raises once, then scores. If the engine ever sent one a `view_chars` keyword anyway, Python
    would raise the same TypeError a real plain seat would — which is exactly what the engine
    must never do; discovering the capability from the signature, not hoping, is what protects them."""

    def __init__(self, table):
        self.table, self.calls = table, []

    async def evaluate(self, state, outcomes):
        self.calls.append(None)
        if len(self.calls) == 1:
            raise RuntimeError("empty answer from the model: it spent all its output tokens reasoning")
        return [self.table.get(o.move.label(), Evaluation()) if o.ok else Evaluation() for o in outcomes]


class AlwaysFailingEvaluator(RetryEvaluator):
    async def evaluate(self, state, outcomes, *, view_chars=None):
        self.calls.append(view_chars)
        raise RuntimeError("empty answer from the model: it spent all its output tokens reasoning")


async def collect(engine, goal=GOAL):
    return [e async for e in engine.run(goal)]


def engine(proposer, executor, evaluator, catalog=None, simulator=None, environment=None, **budget):
    return StateEngine(
        environment or ScriptedEnvironment(executor, catalog), proposer=proposer,
        evaluator=evaluator, simulator=simulator, budget=EngineBudget(**budget) if budget else None,
    )


@pytest.mark.asyncio
async def test_one_step_done_returns_a_grounded_answer():
    a = mv(path="/a")
    ev = await collect(engine(ScriptedProposer([a]), FakeExecutor({}),
                              ScriptedEvaluator({a.label(): Evaluation(1.0, True, "3 files", "found")})))
    assert [e.kind for e in ev][-1] == "done" and ev[-1].data["answer"] == "3 files"


# ─── The challenge round: a `done` claim is not taken on its own say-so ──────


@pytest.mark.asyncio
async def test_a_done_claim_survives_a_challenge_that_finds_nothing_better():
    """B-2026-09-26-5: one more fan is proposed with the claimed action pruned, and only when nothing
    there beats it does the claim settle. Here the challenge asks and gets nothing back."""
    a = mv(path="/a")
    prop = ScriptedProposer([a])  # the challenge round's ask finds the script exhausted
    ev = await collect(engine(prop, FakeExecutor({}),
                              ScriptedEvaluator({a.label(): Evaluation(1.0, True, "3 files", "found")})))
    assert ev[-1].kind == "done" and ev[-1].data["answer"] == "3 files"
    assert ev[-1].data["challenged"] is True
    assert prop.seen_avoid[-1] == {a.fingerprint()}  # the challenge explicitly excluded the claim


@pytest.mark.asyncio
async def test_a_competing_claim_that_scores_higher_wins_the_challenge():
    """The supervisor's policy: when a challenge produces a second `done` claim, the better-scoring
    one settles — the exact shape of a run that named a folder sharing the goal's name over the real one."""
    shallow, real = mv(path="/a"), mv(path="/b")
    prop = ScriptedProposer([shallow], [real])
    evalr = ScriptedEvaluator({
        shallow.label(): Evaluation(0.9, True, "a folder sharing the goal's name", "matches by name"),
        real.label(): Evaluation(1.0, True, "the actual checkout", "verified"),
    })
    ev = await collect(engine(prop, FakeExecutor({}), evalr))
    assert ev[-1].kind == "done" and ev[-1].data["answer"] == "the actual checkout"
    assert ev[-1].data["challenged"] is True


@pytest.mark.asyncio
async def test_a_better_but_unsettled_challenger_keeps_the_search_going():
    """A challenger that outscores the claim without itself being done invalidates the claim: the run
    takes the better state and keeps searching, rather than settle on what it just outscored."""
    shallow, better, real = mv(path="/a"), mv(path="/b"), mv(path="/c")
    prop = ScriptedProposer([shallow], [better], [real])
    evalr = ScriptedEvaluator({
        shallow.label(): Evaluation(0.9, True, "a folder sharing the goal's name", "matches by name"),
        better.label(): Evaluation(0.95, False, "", "closer, but not settled yet"),
        real.label(): Evaluation(1.0, True, "the actual checkout", "verified"),
    })
    ev = await collect(engine(prop, FakeExecutor({}), evalr))
    assert ev[-1].kind == "done" and ev[-1].data["answer"] == "the actual checkout"
    selected_moves = [e.data["move"] for e in ev if e.kind == "selected"]
    assert better.label() in selected_moves  # the better state was actually taken, not discarded
    assert shallow.label() not in selected_moves  # the shallow claim was never applied


@pytest.mark.asyncio
async def test_an_unaffordable_challenge_is_marked_not_a_silent_pass():
    """The challenge costs two calls; when the budget cannot afford them the claim goes unchallenged,
    and the record says so rather than looking identical to a challenge that ran and found nothing."""
    a = mv(path="/a")
    ev = await collect(engine(ScriptedProposer([a]), FakeExecutor({}),
                              ScriptedEvaluator({a.label(): Evaluation(1.0, True, "ans")}),
                              max_model_calls=3))
    assert ev[-1].kind == "done" and ev[-1].data["answer"] == "ans"
    assert ev[-1].data["challenged"] is False


@pytest.mark.asyncio
async def test_a_challenge_that_only_re_examines_the_same_candidate_does_not_count():
    """A model can pass the direct-look guard by looking at its own claim's candidate and nothing
    else — that is the same candidate confirmed by a second tool, not an alternative. The challenge
    round excludes any action sharing the claim's own path before it is ever probed."""
    shallow = mv(tool="dir_explorer", path="/a")
    same_subject = mv(tool="file_read", path="/a")  # a different tool — at the very thing already claimed
    prop = ScriptedProposer([shallow], [same_subject])
    evalr = ScriptedEvaluator({
        shallow.label(): Evaluation(0.9, True, "a folder matching by name", "matches by name"),
        same_subject.label(): Evaluation(1.0, True, "confirmed by looking", "looked directly"),
    })
    ev = await collect(engine(prop, FakeExecutor({}), evalr))
    assert ev[-1].kind == "done" and ev[-1].data["answer"] == "a folder matching by name"
    assert ev[-1].data["challenged"] is True
    # excluded before it could even be probed — not merely outscored
    assert not any(e.kind == "probe" for e in ev if e.data.get("move") == same_subject.label())


@pytest.mark.asyncio
async def test_a_challenge_still_recognises_a_genuinely_different_candidate():
    """The same-subject exclusion must not swallow a real alternative — only one that shares the
    claim's own path is filtered; a different path is a real competitor, exactly as before."""
    shallow, real = mv(path="/a"), mv(path="/b")
    prop = ScriptedProposer([shallow], [real])
    evalr = ScriptedEvaluator({
        shallow.label(): Evaluation(0.9, True, "a folder matching by name", "matches by name"),
        real.label(): Evaluation(1.0, True, "the actual checkout", "verified"),
    })
    ev = await collect(engine(prop, FakeExecutor({}), evalr))
    assert ev[-1].kind == "done" and ev[-1].data["answer"] == "the actual checkout"
    assert any(e.kind == "probe" and e.data.get("move") == real.label() for e in ev)


@pytest.mark.asyncio
async def test_no_progress_backtracks_and_never_repeats_a_failed_move():
    a, b, c = mv(path="/a"), mv(path="/b"), mv(path="/c")
    prop = ScriptedProposer([a], [b], [a, c])  # depth0: a (progress) ; depth1: b (stalls) ; back at depth0: a is now failed
    evalr = ScriptedEvaluator({
        a.label(): Evaluation(0.4), b.label(): Evaluation(0.1), c.label(): Evaluation(1.0, True, "ans"),
    })
    ev = await collect(engine(prop, FakeExecutor({}), evalr))
    kinds = [e.kind for e in ev]
    assert "backtrack" in kinds and kinds[-1] == "done"
    assert a.fingerprint() in prop.seen_avoid[-1]  # the move that led nowhere is remembered


# ── An empty evaluator answer costs a retry, not the run ─────────────────────


@pytest.mark.asyncio
async def test_a_failed_evaluation_is_retried_once_and_the_run_settles():
    """A hosted model that spends its whole output allowance reasoning and returns nothing used to
    end the run at step one — `evaluator_error`, the probes already paid for discarded from the
    window even though the stop re-learned them. The scoring call gets one more chance first."""
    a = mv(path="/a")
    evalr = RetryEvaluator({a.label(): Evaluation(1.0, True, "ans", "found")})
    ev = await collect(engine(ScriptedProposer([a]), FakeExecutor({}), evalr))
    assert evalr.calls == [None, 1000]  # first call plain, the retry with a shorter view
    assert ev[-1].kind == "done" and ev[-1].data["answer"] == "ans"
    assert ev[-1].data["model_calls"] == 3  # propose + the failed evaluate + the retry that settled
    retry_marks = [e for e in ev if e.kind == "thinking" and e.data.get("attempt") == 2]
    assert len(retry_marks) == 1 and retry_marks[0].data["phase"] == "evaluate"


@pytest.mark.asyncio
async def test_the_retry_uses_a_shorter_view_and_it_reaches_the_seat():
    """What the retry actually changes is the prompt's view of each outcome — the thinking is about
    the text. A seat that accepts `view_chars` must receive it on the retry and only on the retry."""
    a = mv(path="/a")
    evalr = RetryEvaluator({a.label(): Evaluation(0.4)})
    ev = await collect(engine(ScriptedProposer([a]), FakeExecutor({a.label(): (True, "result text")}), evalr))
    assert evalr.calls == [None, 1000]
    assert ev[-1].kind == "stopped"  # progress did not beat the root, so the run backs up and stops


@pytest.mark.asyncio
async def test_a_second_failure_stops_honestly_with_the_fans_facts_learned():
    """One retry, not a loop: a second empty answer ends the run — but the fan's real observations
    are learned first, so the stop reports what the probes found instead of an empty window."""
    a = mv(path="/a")
    evalr = AlwaysFailingEvaluator({})
    ev = await collect(engine(ScriptedProposer([a]), FakeExecutor({a.label(): (True, "useful listing")}), evalr))
    assert evalr.calls == [None, 1000]  # exactly one retry was attempted
    assert ev[-1].kind == "stopped" and "evaluator_error" in ev[-1].data["reason"]
    assert len(ev[-1].data["facts"]) == 1 and "useful listing" in ev[-1].data["facts"][0]


@pytest.mark.asyncio
async def test_an_evaluator_without_a_view_keyword_still_gets_its_retry():
    """`view_chars` is a capability the engine offers, not a protocol change: the rule-based seats
    keep their plain signatures, and a failure in one of them retries the same way — a fresh call,
    which for a flaky endpoint or a transient parse is often the fix on its own."""
    a = mv(path="/a")
    evalr = PlainRetryEvaluator({a.label(): Evaluation(1.0, True, "ans", "found")})
    ev = await collect(engine(ScriptedProposer([a]), FakeExecutor({}), evalr))
    assert evalr.calls == [None, None]
    assert ev[-1].kind == "done" and ev[-1].data["answer"] == "ans"


@pytest.mark.asyncio
async def test_a_raising_probe_becomes_a_failed_observation_and_the_fan_survives():
    """The probe contract says an environment returns an Observation rather than raise — but one
    raising call (a sandbox that times out, a driver that disconnects) used to kill the whole fan
    through `asyncio.gather`, ending the run with an error string for a reason and the other
    candidates' real results discarded. The engine now survives the violation: the raiser is a
    failed probe, the rest of the fan proceeds, and the record says what actually happened."""
    boom, good = mv(path="/boom"), mv(path="/good")
    prop = ScriptedProposer([boom, good])
    evalr = ScriptedEvaluator({good.label(): Evaluation(0.6)})
    ev = await collect(engine(prop, FakeExecutor({good.label(): (True, "the good listing")}), evalr,
                              environment=RaisingEnvironment(FakeExecutor({good.label(): (True, "the good listing")}))))
    probe = next(e for e in ev if e.kind == "probe" and e.data.get("move") == boom.label())
    assert probe.data["ok"] is False and "took too long" in probe.data["excerpt"]
    assert any(e.kind == "probe" and e.data.get("move") == good.label() and e.data["ok"] for e in ev)
    states = [e for e in ev if e.kind == "state"]
    assert states[-1].data["failed"] == 1 and states[-1].data["facts"] == 1  # the raiser remembered, the reader learned
    assert any(e.kind == "evaluation" and e.data.get("move") == good.label() for e in ev)


@pytest.mark.asyncio
async def test_failed_probes_are_not_progress_and_the_stop_is_honest():
    a = mv(path="/nope")
    ev = await collect(engine(ScriptedProposer([a]), FakeExecutor({a.label(): (False, "not found")}),
                              ScriptedEvaluator({}), max_backtracks=0))
    assert ev[-1].kind == "stopped" and ev[-1].data["settled"] is False and ev[-1].data["reason"] == "no_progress"


@pytest.mark.asyncio
async def test_a_move_that_is_not_read_only_is_never_executed():
    w = Move("file_write", {"path": "/x", "content": "y"}, "create it")
    ex = FakeExecutor({})
    ev = await collect(engine(ScriptedProposer([w]), ex, ScriptedEvaluator({})))
    assert ex.ran == []
    assert any(e.kind == "needs_confirmation" for e in ev)


@pytest.mark.asyncio
async def test_unknown_tools_are_dropped_and_remembered():
    ghost = Move("teleport", {}, "?")
    prop = ScriptedProposer([ghost])
    ev = await collect(engine(prop, FakeExecutor({}), ScriptedEvaluator({})))
    assert ev[-1].kind == "stopped" and ev[-1].data["reason"] == "no_moves"


@pytest.mark.asyncio
async def test_depth_budget_stops_honestly_with_what_is_known():
    rounds = [[mv(path=f"/{i}")] for i in range(10)]
    evalr = ScriptedEvaluator({m[0].label(): Evaluation(0.1 * (i + 1)) for i, m in enumerate(rounds)})
    ev = await collect(engine(ScriptedProposer(*rounds), FakeExecutor({}), evalr, max_depth=3))
    last = ev[-1]
    assert last.kind == "stopped" and last.data["reason"] == "budget" and len(last.data["facts"]) == 3


@pytest.mark.asyncio
async def test_unselected_probes_still_teach_facts():
    a, b = mv(path="/a"), mv(path="/b")
    ev = await collect(engine(ScriptedProposer([a, b]), FakeExecutor({b.label(): (True, "the name is Foo")}),
                              ScriptedEvaluator({a.label(): Evaluation(1.0, True, "x"), b.label(): Evaluation(0.5)})))
    assert ev[-1].kind == "done"
    st = next(e for e in reversed(ev) if e.kind == "state")
    assert st.data["facts"] == 2  # the winner's fact + the runner-up's real observation


def test_state_is_immutable_and_render_is_bounded_per_fact_not_by_count():
    """The bound is `_FACT_CHARS` on each observation, not a cap on how many the model may see.

    `render` used to show only the last eight facts, which cost 60% of a maze run's probes to
    re-learning places it already knew (see `AgentState.render`). The truncation that matters is this
    one: a 5,000-character read enters the state at 320, so every fact can be shown without the prompt
    growing without limit.
    """
    s0 = AgentState(GOAL)
    s1 = s0.apply(Observation(mv(), True, "x" * 5000), Evaluation(0.5))
    assert s0.depth == 0 and s1.depth == 1 and s0.facts == ()
    assert len(s1.render()) < 900 and s1.progress == 0.5
    assert mv(path="/a").fingerprint() == mv(path="/a").fingerprint() != mv(path="/b").fingerprint()


def test_the_model_is_shown_every_fact_the_run_has_established():
    state = AgentState(GOAL)
    for i in range(30):
        state = state.apply(Observation(mv(path=f"/f{i}"), True, f"fact {i}"), Evaluation(0.1))
    shown = [line for line in state.render().splitlines() if line.startswith("  - ")]
    assert len(shown) == 30, f"the run holds 30 facts and showed {len(shown)}"
    assert "fact 0" in state.render(), "the earliest fact was dropped"
    # A caller that wants a narrower view can still ask for one.
    assert len([l for l in state.render(5).splitlines() if l.startswith("  - ")]) == 5


def test_every_fact_carries_the_moment_it_was_observed():
    """A fact and its time are appended together, so the two tuples are always the same length — the
    contract a UI or a reasoner relies on when it zips `fact_list` with `fact_ages_ms`."""
    s0 = AgentState(GOAL)
    s1 = s0.apply(Observation(mv(path="/a"), True, "a"), Evaluation(0.1))
    s2 = s1.learn(Observation(mv(path="/b"), True, "b"))
    assert s0.fact_times == ()
    assert len(s1.fact_times) == len(s1.facts) == 1
    assert len(s2.fact_times) == len(s2.facts) == 2
    # No timestamp was supplied, so both default to "now" — close together, both sane.
    now = time.monotonic()
    assert all(0 <= now - t < 1.0 for t in s2.fact_times)


def test_a_failed_or_predicted_observation_never_gets_a_fact_time_either():
    """`facts` and `fact_times` grow on exactly the same conditions — a failed probe or a prediction
    is not a fact, so it must not leave a dangling timestamp with nothing to pair it to."""
    s0 = AgentState(GOAL)
    failed = s0.apply(Observation(mv(path="/a"), False, "nope"), Evaluation(0.0))
    predicted = s0.apply(Observation(mv(path="/b"), True, "maybe", predicted=True), Evaluation(0.0))
    assert failed.facts == () and failed.fact_times == ()
    assert predicted.facts == () and predicted.fact_times == ()


def test_observed_at_can_be_supplied_explicitly_and_to_dict_reports_the_age():
    """A caller that knows precisely when a probe returned (the engine, mid-fan) can say so, and
    `to_dict` turns that into an age in milliseconds a reader does not have to compute by hand."""
    ten_seconds_ago = time.monotonic() - 10.0
    s = AgentState(GOAL).apply(Observation(mv(), True, "old news"), Evaluation(0.1), observed_at=ten_seconds_ago)
    ages = s.to_dict()["fact_ages_ms"]
    assert len(ages) == 1
    assert 9_500 <= ages[0] <= 10_500, f"expected roughly 10000ms, got {ages[0]}"


def test_retreat_keeps_fact_times_aligned_with_the_facts_it_restores():
    parent = AgentState(GOAL)
    child = parent.apply(Observation(mv(path="/a"), True, "a"), Evaluation(0.2))
    child = child.learn(Observation(mv(path="/b"), True, "b"))
    restored = child.retreat_to(parent)
    assert restored.facts == child.facts
    assert restored.fact_times == child.fact_times


@pytest.mark.asyncio
async def test_a_stop_reports_how_old_every_known_fact_is():
    """The engine's own honest-stop event, not just `AgentState.to_dict`'s bounded UI window: a reader
    deciding whether to believe a stopped run's facts needs an age for every one of them, not just the
    last twelve."""
    a, b = mv(path="/a"), mv(path="/b")
    prop = ScriptedProposer([a], [b])
    evalr = ScriptedEvaluator({a.label(): Evaluation(0.4), b.label(): Evaluation(0.1)})
    ev = await collect(engine(prop, FakeExecutor({}), evalr, max_backtracks=0))
    stopped = ev[-1]
    assert stopped.kind == "stopped"
    assert len(stopped.data["fact_ages_ms"]) == len(stopped.data["facts"])
    assert all(isinstance(a, int) and a >= 0 for a in stopped.data["fact_ages_ms"])


def test_parse_json_survives_fences_and_prose():
    assert parse_json('sure!\n```json\n{"moves": []}\n```') == {"moves": []}
    assert parse_json("no json here") is None


class _Port:
    """A model port that returns whatever the test tells it to."""

    def __init__(self, text):
        self.text, self.prompts = text, []

    async def complete(self, prompt, *, max_chars=4000):
        self.prompts.append(prompt)
        return self.text


@pytest.mark.asyncio
async def test_llm_proposer_parses_dedupes_and_respects_avoid():
    a = mv(path="/a")
    text = ('{"moves": [{"tool": "dir_explorer", "args": {"path": "/a"}, "why": "1"},'
            ' {"tool": "dir_explorer", "args": {"path": "/a"}, "why": "dup"},'
            ' {"tool": "file_task", "args": {"path": "/b"}, "why": "2"}, "junk"]}')
    got = await LLMMoveProposer(_Port(text), CATALOG).propose(AgentState(GOAL), 3, set())
    assert [m.tool for m in got] == ["dir_explorer", "file_task"]
    got = await LLMMoveProposer(_Port(text), CATALOG).propose(AgentState(GOAL), 3, {a.fingerprint()})
    assert [m.tool for m in got] == ["file_task"]


@pytest.mark.asyncio
async def test_llm_evaluator_guards_failed_probes_and_answerless_done():
    ok, bad, noans = (Observation(mv(path=p), k, "t") for p, k in (("/a", True), ("/b", False), ("/c", True)))
    text = ('{"evals": [{"i": 0, "progress": 0.7, "done": true, "answer": "yes"},'
            ' {"i": 1, "progress": 0.9, "done": true, "answer": "lie"},'
            ' {"i": 2, "progress": 0.8, "done": true, "answer": ""}]}')
    e = await LLMEvaluator(_Port(text)).evaluate(AgentState(GOAL), [ok, bad, noans])
    assert (e[0].done, e[0].answer) == (True, "yes")
    assert (e[1].progress, e[1].done) == (0.0, False)  # a failed probe never counts, whatever the model says
    assert e[2].done is False  # "done" needs a grounded answer


@pytest.mark.asyncio
async def test_llm_evaluator_refuses_done_on_a_surface_only_hit_alone():
    """B-2026-09-26-7's live repro: find_files(contains=".git") and find_files(contains="package") both
    scored done=True at 100% purely because a name matched — neither ever looked at the folder itself.
    A search/recall finds a candidate; it does not verify one, so `done` needs a direct look too."""
    specs = {"find_files": ActionSpec("find_files", "search", surface_only=True),
             "list_dir": ActionSpec("list_dir", "look")}
    hit = Observation(mv(tool="find_files", path="/x"), True, "found: /Users/bao/LocalMind")
    looked = Observation(mv(tool="list_dir", path="/y"), True, "src/ tests/ setup.py")
    text = ('{"evals": [{"i": 0, "progress": 1.0, "done": true, "answer": "/Users/bao/LocalMind"},'
            ' {"i": 1, "progress": 1.0, "done": true, "answer": "/Users/bao/LocalMind"}]}')
    e = await LLMEvaluator(_Port(text), specs).evaluate(AgentState(GOAL), [hit, looked])
    assert e[0].done is False and "direct look" in e[0].reason
    assert e[1].done is True  # the same claim, backed by an action that actually looked, is untouched


@pytest.mark.asyncio
async def test_llm_evaluator_with_no_specs_behaves_exactly_as_before():
    """Every existing caller that never passes `specs` must see no behaviour change at all."""
    hit = Observation(mv(tool="find_files", path="/x"), True, "found: /Users/bao/LocalMind")
    text = '{"evals": [{"i": 0, "progress": 1.0, "done": true, "answer": "/Users/bao/LocalMind"}]}'
    e = await LLMEvaluator(_Port(text)).evaluate(AgentState(GOAL), [hit])
    assert e[0].done is True


@pytest.mark.asyncio
async def test_registry_executor_reports_unknown_tool_as_a_failed_observation():
    prop = ScriptedProposer([mv(tool="teleport", path="/x")])
    ev = await collect(engine(prop, FakeExecutor({}), ScriptedEvaluator({})))
    assert not any(e.kind == "probe" for e in ev)  # never probed...
    assert ev[-1].kind == "stopped" and ev[-1].data["reason"] in ("no_moves", "budget")


# ── The event contract any interface consumes ──────────────────────────────


@pytest.mark.asyncio
async def test_events_carry_tree_ids_sequence_clock_and_excerpts():
    a, b = mv(path="/a"), mv(path="/b")
    prop = ScriptedProposer([a], [b])
    evalr = ScriptedEvaluator({a.label(): Evaluation(0.3), b.label(): Evaluation(1.0, True, "ok", "settled")})
    ev = await collect(engine(prop, FakeExecutor({a.label(): (True, "alpha  text")}), evalr))
    assert [e.seq for e in ev] == list(range(1, len(ev) + 1))
    assert all(ev[i].t_ms <= ev[i + 1].t_ms for i in range(len(ev) - 1))
    states = [e for e in ev if e.kind == "state"]
    assert [s.data["node"] for s in states] == ["n0", "n1", "n2"]
    assert [s.data["parent"] for s in states] == [None, "n0", "n1"]
    assert states[0].data["goal"] == GOAL.text
    probe = next(e for e in ev if e.kind == "probe")
    assert probe.data["excerpt"] == "alpha text" and probe.data["fp"] == a.fingerprint() and probe.data["at"] == "n0"
    cand = next(e for e in ev if e.kind == "candidates")
    assert cand.data["moves"][0]["fp"] == a.fingerprint() and "why" in cand.data["moves"][0]
    assert ev[0].to_dict()["kind"] == "state" and ev[-1].to_dict()["answer"] == "ok"


@pytest.mark.asyncio
async def test_backtrack_event_names_the_node_it_returns_to():
    a, b, c = mv(path="/a"), mv(path="/b"), mv(path="/c")
    prop = ScriptedProposer([a], [b], [c])
    evalr = ScriptedEvaluator({a.label(): Evaluation(0.4), b.label(): Evaluation(0.1), c.label(): Evaluation(1.0, True, "x")})
    ev = await collect(engine(prop, FakeExecutor({}), evalr))
    bt = next(e for e in ev if e.kind == "backtrack")
    assert bt.data["node"] == "n0"
    later = [e for e in ev if e.seq > bt.seq and e.kind == "candidates"]
    assert later and later[0].data["at"] == "n0"  # the next fan hangs off the node we returned to


@pytest.mark.asyncio
async def test_a_state_carries_what_it_knows_so_a_ui_can_read_the_search():
    """The state is the point of this engine: the explorer shows its facts, what it ruled out, and its path."""
    a, b = mv(path="/a"), mv(path="/b")
    prop = ScriptedProposer([a], [b])
    evalr = ScriptedEvaluator({a.label(): Evaluation(0.3), b.label(): Evaluation(1.0, True, "ok", "settled")})
    ev = await collect(engine(prop, FakeExecutor({a.label(): (True, "alpha  text")}), evalr))
    states = [e for e in ev if e.kind == "state"]

    first = states[0].data
    assert first["fact_list"] == [] and first["trail"] == []  # nothing learned before the first move
    last = states[-1].data
    assert last["facts"] == len(last["fact_list"]) == 2  # one real observation per applied move
    assert a.label() in last["fact_list"][0] and "alpha text" in last["fact_list"][0]
    assert last["trail"] == [a.label(), b.label()]  # the path of applied moves, in the same words the model sees


@pytest.mark.asyncio
async def test_a_failed_probe_is_remembered_as_failed_even_when_the_round_succeeds():
    a, missing, good = mv(path="/a"), mv(path="/missing"), mv(path="/good")
    prop = ScriptedProposer([a], [missing, good])
    evalr = ScriptedEvaluator({a.label(): Evaluation(0.2), good.label(): Evaluation(1.0, True, "ok", "settled")})
    ex = FakeExecutor({a.label(): (True, "a"), missing.label(): (False, "no such path"), good.label(): (True, "good")})
    ev = await collect(engine(prop, ex, evalr))
    states = [e for e in ev if e.kind == "state"]
    assert missing.fingerprint() in states[-1].data["failed_fps"]  # not lost just because something worked
    assert states[-1].data["failed"] == 1
    assert good.fingerprint() not in states[-1].data["failed_fps"]


# ─── The Simulator: predicting an action that must not be performed ──────────


class ScriptedSimulator:
    """Predicts whatever the test says, and remembers what it was asked about."""

    def __init__(self, ok=True, text="would create notes.md with three lines"):
        self.ok, self.text, self.asked = ok, text, []

    async def predict(self, state, action):
        self.asked.append(action.label())
        return Observation(action, self.ok, self.text, predicted=True)


def _write_move():
    return Move("file_write", {"path": "/tmp/notes.md", "content": "one\ntwo\nthree"}, "write the notes")


@pytest.mark.asyncio
async def test_a_simulated_action_is_predicted_and_never_performed():
    w = _write_move()
    ex, sim = FakeExecutor({w.label(): (True, "should not run")}), ScriptedSimulator()
    ev = await collect(
        engine(ScriptedProposer([w]), ex, ScriptedEvaluator({w.label(): Evaluation(0.8)}), simulator=sim)
    )
    assert ex.ran == []                     # the environment was never touched
    assert sim.asked == [w.label()]         # ... and the simulator was asked instead
    probe = next(e for e in ev if e.kind == "probe")
    assert probe.data["predicted"] is True and probe.data["ok"] is True
    assert not any(e.kind == "needs_confirmation" for e in ev)  # a simulator replaces the refusal


@pytest.mark.asyncio
async def test_without_a_simulator_a_write_is_still_only_offered_for_confirmation():
    w = _write_move()
    ex = FakeExecutor({})
    ev = await collect(engine(ScriptedProposer([w]), ex, ScriptedEvaluator({})))
    assert ex.ran == [] and any(e.kind == "needs_confirmation" for e in ev)


@pytest.mark.asyncio
async def test_a_prediction_is_never_learned_as_a_fact():
    w = _write_move()
    sim = ScriptedSimulator()
    states = [e for e in await collect(
        engine(ScriptedProposer([w]), FakeExecutor({}), ScriptedEvaluator({w.label(): Evaluation(0.8)}), simulator=sim)
    ) if e.kind == "state"]
    # The prediction was scored and selected, but nothing about it entered the state's knowledge.
    assert all(s.data["fact_list"] == [] for s in states)
    assert states[-1].data["facts"] == 0
    assert states[-1].data["progress"] == 0.0  # ... and it did not move progress either


@pytest.mark.asyncio
async def test_a_prediction_can_never_settle_the_goal():
    w = _write_move()
    sim = ScriptedSimulator()
    ev = await collect(
        engine(ScriptedProposer([w]), FakeExecutor({}),
               # the evaluator is fooled into saying "done" about the prediction
               ScriptedEvaluator({w.label(): Evaluation(1.0, True, "notes.md was written", "settled")}),
               simulator=sim, max_backtracks=0)
    )
    assert ev[-1].kind == "stopped" and ev[-1].data["settled"] is False
    assert ev[-1].data["reason"] == "needs_action"          # it says what only a real action could finish
    assert "file_write" in ev[-1].data["needs"]
    assert ev[-1].data["predicted"]["result"] == "would create notes.md with three lines"
    assert not any(e.kind == "done" for e in ev)


@pytest.mark.asyncio
async def test_a_failed_prediction_is_reported_honestly_and_the_action_remembers_it():
    w = _write_move()
    sim = ScriptedSimulator(ok=False, text="the path is not writable")
    ev = await collect(
        engine(ScriptedProposer([w]), FakeExecutor({}), ScriptedEvaluator({}), simulator=sim, max_backtracks=0)
    )
    probe = next(e for e in ev if e.kind == "probe")
    assert probe.data["ok"] is False and probe.data["predicted"] is True
    assert "not writable" in probe.data["excerpt"]
