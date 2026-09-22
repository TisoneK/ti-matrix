"""What the learning layer does with the record — and the one claim that matters: a second run is better.

The integration test at the bottom is the honest version of "the engine learns": the same goal, the same
uninformed proposer, the same world, run twice, with the second run carrying what the first one's events
taught. If it ever stops being true, that test fails and the claim in the README is wrong.
"""
from __future__ import annotations

import sqlite3

import pytest

from ti_matrix import (
    Action,
    ActionRecord,
    ActionSpec,
    CachingEnvironment,
    EngineBudget,
    Goal,
    LearningProposer,
    Observation,
    Statistics,
    StateEngine,
)
from ti_matrix.adapters import stats_file
from ti_matrix.adapters.stats_sqlite import SqliteStore


def mv(tool, **args):
    return Action(tool, args or {}, "because")


class FixedProposer:
    """A proposer with an uninformed, fixed order — what a model does when it does not know this world.

    It cuts to ``n`` and honours ``avoid`` exactly as ``LLMMoveProposer`` does, so the fan the engine sees is
    decided here.
    """

    def __init__(self, order):
        self.order = list(order)
        self.calls = 0

    async def propose(self, state, n, avoid):
        self.calls += 1
        moves = [mv(t) for t in self.order]
        return [m for m in moves if m.fingerprint() not in avoid][:n]


class World:
    """An environment whose tools answer from a table, and which counts what it was asked."""

    name = "world"

    def __init__(self, answers, *, builtin=False):
        self.answers, self.builtin, self.asked = answers, builtin, []
        self._specs = {t: ActionSpec(t, f"does {t}") for t in answers}

    def tools(self):
        return self._specs

    def is_read_only(self, action):
        found = self._specs.get(action.tool)
        return None if found is None else found.read_only

    async def probe(self, action):
        self.asked.append(action.tool)
        ok, text = self.answers.get(action.tool, (False, "no such tool"))
        return Observation(action, ok, text)


# ─── the proposer ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_it_drops_a_hopeless_tool_so_the_fan_spends_its_slots_on_plausible_actions():
    stats = Statistics()
    stats.by_tool["dead"] = stats.record("dead")
    for _ in range(3):
        stats.by_fingerprint[f"dead{_}"] = stats.record("dead")  # evidence enough, on the tool's record
    stats.by_tool["dead"] = type(stats.record("dead"))("dead", probes=3, failures=3)

    inner = FixedProposer(["dead", "good", "other"])
    proposer = LearningProposer(inner, stats, min_tries=3)
    moves = await proposer.propose(None, 3, set())
    assert [m.tool for m in moves] == ["good", "other"]  # the dead tool gave up its slot


@pytest.mark.asyncio
async def test_it_orders_by_prior_so_a_tool_that_has_paid_off_lands_inside_a_narrow_fan():
    stats = Statistics()
    stats.by_tool["good"] = type(stats.record("good"))("good", probes=2, selections=2, progress=2.0, scored=2)
    inner = FixedProposer(["unknown", "good", "unproven"])
    proposer = LearningProposer(inner, stats)

    assert [m.tool for m in await proposer.propose(None, 3, set())] == ["good", "unknown", "unproven"]
    assert [m.tool for m in await proposer.propose(None, 2, set())] == ["good", "unknown"]


@pytest.mark.asyncio
async def test_it_keeps_the_models_own_order_where_the_experience_cannot_separate_two_tools():
    proposer = LearningProposer(FixedProposer(["a", "b", "c"]), Statistics())
    assert [m.tool for m in await proposer.propose(None, 3, set())] == ["a", "b", "c"]


@pytest.mark.asyncio
async def test_it_never_answers_with_an_empty_fan_when_the_model_proposed_something():
    """The floor: "nothing is worth trying" is a worse answer than the model's least hopeless idea."""
    stats = Statistics()
    stats.by_tool["dead"] = type(stats.record("dead"))("dead", probes=9, failures=9)
    proposer = LearningProposer(FixedProposer(["dead"]), stats, min_tries=3)
    assert [m.tool for m in await proposer.propose(None, 3, set())] == ["dead"]
    assert await LearningProposer(FixedProposer([]), stats).propose(None, 3, set()) == []


# ─── the cache ──────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_the_cache_serves_a_repeated_read_only_probe_and_asks_only_once():
    world = World({"read": (True, "the answer")})
    cached = CachingEnvironment(world)

    first = await cached.probe(mv("read", path="x"))
    second = await cached.probe(mv("read", path="x"))
    other = await cached.probe(mv("read", path="y"))  # same tool, different arguments: a different question

    assert first.text == second.text == other.text == "the answer"
    assert world.asked == ["read", "read"]  # three probes, two real calls
    assert cached.hits == 1 and cached.misses == 2
    assert "served from cache: 1 (33% of 3)" in cached.stats()


@pytest.mark.asyncio
async def test_the_cache_never_remembers_a_failure_so_bad_luck_does_not_become_news():
    world = World({"flaky": (False, "the lock is held")})
    cached = CachingEnvironment(world)
    await cached.probe(mv("flaky"))
    await cached.probe(mv("flaky"))
    assert world.asked == ["flaky", "flaky"] and cached.hits == 0


@pytest.mark.asyncio
async def test_a_write_is_never_served_from_the_cache_when_one_is_offered():
    class Writing(World):
        name = "writing"

        def __init__(self):
            super().__init__({"write": (True, "wrote it")})
            self._specs["write"] = ActionSpec("write", "writes", read_only=False)

    world = Writing()
    cached = CachingEnvironment(world)
    await cached.probe(mv("write"))
    await cached.probe(mv("write"))
    assert world.asked == ["write", "write"] and cached.hits == 0


@pytest.mark.asyncio
async def test_a_changed_world_makes_the_cache_ask_again_and_a_broken_version_check_never_fails_the_run():
    world = World({"read": (True, "the answer")})
    generation = {"n": 1}
    cached = CachingEnvironment(world, version=lambda: generation["n"])

    await cached.probe(mv("read"))
    await cached.probe(mv("read"))
    assert world.asked == ["read"] and cached.hits == 1

    generation["n"] = 2  # the world moved
    await cached.probe(mv("read"))
    assert world.asked == ["read", "read"] and cached.hits == 1

    def broken():
        raise RuntimeError("cannot read the version")

    guarded = CachingEnvironment(world, version=broken)
    await guarded.probe(mv("read"))
    await guarded.probe(mv("read"))
    assert guarded.hits == 0 and world.asked == ["read"] * 4  # a fresh read every time, and no crash


# ─── the store ──────────────────────────────────────────────────────────────


def test_the_store_round_trips_and_a_missing_or_unreadable_file_is_a_cold_start_not_a_crash(tmp_path):
    stats = Statistics()
    stats.by_tool["read"] = type(stats.record("read"))("read", probes=2, selections=1, progress=1.0, scored=1)
    stats.add_facts(["read() -> ok: the answer"])
    path = tmp_path / "nested" / "experience.json"

    assert stats_file.load(path).by_tool == {}  # nothing there yet
    stats_file.save(path, stats)  # creates the directory it needs
    assert stats_file.load(path).to_dict() == stats.to_dict()

    path.write_text("{ this is not json")
    assert stats_file.load(path).by_tool == {}  # lenient: a run must not fail over bookkeeping
    with pytest.raises(ValueError):
        stats_file.load(path, strict=True)

    path.write_text('{"version": 42, "tools": {"read": {"probes": 9}}}')
    assert stats_file.load(path).by_tool == {}
    with pytest.raises(ValueError, match="no experience this version can read"):
        stats_file.load(path, strict=True)


# ─── the claim: the second run is better than the first ─────────────────────


async def run_one(goal, world, order, *, stats=None, n=2, budget=3):
    """One engine run against the world, optionally carrying what earlier runs learned."""
    inner = FixedProposer(order)
    proposer = LearningProposer(inner, stats) if stats is not None else inner
    engine = StateEngine(world, proposer=proposer, evaluator=Scorer(),
                        budget=EngineBudget(max_branches=n, max_model_calls=budget))
    events = []
    async for event in engine.run(Goal(goal)):
        events.append(event)
        if stats is not None:
            stats.observe(event)  # learn as the run goes, exactly as a host does
    return events


class Scorer:
    """A deterministic stand-in for the evaluator: it knows the answer when it sees it.

    An observation that is merely *ok* scores nothing: returning something is not the same as returning
    something useful, and a scorer that confused the two would make every tool look productive.
    """

    def __init__(self, answer="the answer"):
        self.answer = answer
        self.calls = 0

    async def evaluate(self, state, outcomes):
        from ti_matrix import Evaluation
        self.calls += 1
        return [Evaluation(1.0, True, self.answer, "found it") if o.ok and self.answer in o.text
                else Evaluation(0.0, False, "", "nothing useful") for o in outcomes]


@pytest.mark.asyncio
async def test_a_second_run_settles_a_goal_the_first_one_had_to_abandon(tmp_path):
    """The honest version of the claim: same goal, same uninformed order, same world — twice."""
    world = World({"dead": (False, "unsupported"), "muted": (True, "nothing useful"),
                   "answer": (True, "the answer")})
    order = ["dead", "muted", "answer"]  # the uninformed order puts the useful tool outside a fan of two
    goal = "what is the answer?"

    cold = await run_one(goal, world, order, n=2)
    assert [e.kind for e in cold][-1] == "stopped"
    assert cold[-1].data["settled"] is False  # nothing to go on: the first fan is all dead ends

    stats = Statistics().observe_all(cold)
    facts = [f for e in cold if e.kind == "state" for f in e.data.get("fact_list", [])]
    stats.add_facts(facts)

    warm = await run_one(goal, world, order, stats=stats, n=2)
    assert [e.kind for e in warm][-1] == "done"
    assert warm[-1].data["answer"] == "the answer"

    # And it got there without the wasted fan: the record ordered a tool that works into the slots.
    assert len(stats.by_tool) >= 2
    assert stats.record("answer").selections >= 1


@pytest.mark.asyncio
async def test_the_record_survives_on_disk_so_the_next_process_starts_warm(tmp_path):
    path = tmp_path / "experience.json"
    world = World({"dead": (False, "unsupported"), "muted": (True, "nothing useful"),
                   "answer": (True, "the answer")})
    order = ["dead", "muted", "answer"]

    cold = await run_one("what is the answer?", world, order, n=2)
    stats_file.save(path, Statistics().observe_all(cold))
    assert path.exists()

    warm_stats = stats_file.load(path)  # as a fresh process would
    assert warm_stats.record("dead").probes == 1  # the record crossed the boundary intact
    warm = await run_one("what is the answer?", world, order, stats=warm_stats, n=2)
    assert warm[-1].kind == "done"


# ─── the same record, in a database ─────────────────────────────────────────


def record_for(tool, **counters):
    """A one-tool record, for asking the stores what they do with counters."""
    stats = Statistics()
    stats.by_tool[tool] = ActionRecord(tool, **counters)
    return stats


def rich_record():
    """A record with everything a store has to carry: tools, exact actions, counters and facts."""
    stats = Statistics()
    stats.by_tool["open_notes"] = ActionRecord("open_notes", probes=4, selections=2, progress=2.0, scored=2, ms=12)
    stats.by_tool["legacy_dump"] = ActionRecord("legacy_dump", probes=3, failures=3, ms=9)
    stats.by_fingerprint["abc123"] = ActionRecord("open_notes", probes=2, selections=1, progress=1.0, scored=1)
    stats.by_fingerprint["def456"] = ActionRecord("legacy_dump", probes=3, failures=3, predicted=1)
    stats.add_facts(["open_notes() -> ok: the queue holds one row", "legacy_dump() -> FAILED: unsupported"])
    return stats


def test_both_stores_carry_the_same_record(tmp_path):
    """Two stores, one contract: a host can switch between them and keep its learning."""
    record = rich_record()
    stats_file.save(tmp_path / "record.json", record)
    with SqliteStore(tmp_path / "record.db") as store:
        store.save(record)
        from_sql = store.load()

    assert from_sql.to_dict() == stats_file.load(tmp_path / "record.json").to_dict() == record.to_dict()


def test_a_database_record_survives_a_close_and_reopen_like_the_file_one(tmp_path):
    path = tmp_path / "record.db"
    with SqliteStore(path) as store:
        store.save(rich_record())
    with SqliteStore(path) as reopened:  # as a later process would
        assert reopened.load().record("legacy_dump").failures == 3
    assert SqliteStore(path).load().to_dict() == rich_record().to_dict()


def test_adding_from_two_writers_at_once_keeps_both_learnings_where_a_file_would_lose_one(tmp_path):
    """The reason to prefer this store: `add` composes, and a JSON save is last-writer-wins."""
    path = tmp_path / "record.db"
    with SqliteStore(path) as first, SqliteStore(path) as second:  # two connections, as two processes
        first.add(record_for("read", probes=2, failures=1))
        second.add(record_for("read", probes=1, selections=1))
        combined = first.load().record("read")
    assert (combined.probes, combined.failures, combined.selections) == (3, 1, 1)


def test_adding_the_same_increments_twice_counts_them_twice_and_saving_replaces(tmp_path):
    """`add` is for increments and `save` is for the whole picture — the difference nothing can infer."""
    path = tmp_path / "record.db"
    with SqliteStore(path) as store:
        store.add(record_for("read", probes=2))
        store.add(record_for("read", probes=2))
        assert store.load().record("read").probes == 4
        store.save(record_for("read", probes=2))  # replaces, so no longer 6
        assert store.load().record("read").probes == 2


def test_facts_are_deduplicated_kept_in_order_and_queryable_without_loading_everything(tmp_path):
    with SqliteStore(tmp_path / "record.db") as store:
        stats = Statistics()
        stats.add_facts(["the queue holds one row", "a second fact", "the queue is empty"])
        store.add(stats)
        store.add(stats)  # a repeated save must not duplicate the facts
        assert store.load().facts == ["the queue holds one row", "a second fact", "the queue is empty"]
        assert store.search_facts("queue") == ["the queue holds one row", "the queue is empty"]
        assert store.search_facts("queue", limit=1) == ["the queue is empty"]
        assert store.search_facts("nothing like this") == []
        assert store.search_facts("   ") == []


def test_a_query_treats_the_callers_text_literally(tmp_path):
    with SqliteStore(tmp_path / "record.db") as store:
        stats = Statistics()
        stats.add_facts(["progress is 40% done", "a_under_score", "nothing else"])
        store.add(stats)
        assert store.search_facts("40%") == ["progress is 40% done"]  # % is not a wildcard here
        assert store.search_facts("a_under") == ["a_under_score"]  # nor is _ a single character
        assert store.search_facts("%") == ["progress is 40% done"]


def test_top_tools_asks_the_database_the_question_the_prior_asks(tmp_path):
    with SqliteStore(tmp_path / "record.db") as store:
        store.save(rich_record())
        assert [r.tool for r in store.top_tools()] == ["open_notes", "legacy_dump"]
        assert store.top_tools(limit=1)[0].tool == "open_notes"


def test_counts_answers_how_much_is_stored_without_reading_it(tmp_path):
    with SqliteStore(tmp_path / "record.db") as store:
        store.save(rich_record())
        assert store.counts() == {"tools": 2, "actions": 2, "facts": 2}


def test_a_file_that_is_not_a_database_is_reported_rather_than_read_as_empty(tmp_path):
    """Where the JSON store shrugs and starts cold, a broken database is worth knowing about."""
    path = tmp_path / "not-a-db.db"
    path.write_text("this is not a sqlite file, whatever it is")
    with pytest.raises(sqlite3.DatabaseError, match="not a usable SQLite database"):
        SqliteStore(path)
    path.write_bytes(b"")  # an empty file is a new database, not an error
    with SqliteStore(path) as store:
        assert store.counts() == {"tools": 0, "actions": 0, "facts": 0}
