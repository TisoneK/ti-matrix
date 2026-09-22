"""The engine's memory of its own runs: counts, keys, and the one line it must not cross.

The line is the point of most of these tests. A probe that really happened is evidence about the world; a
*predicted* outcome is not, however plausible the model made it sound. Everything here either checks a count
that came from a real event or checks that something unreal was kept out of the record.
"""
from __future__ import annotations

import pytest

from ti_matrix import Statistics
from ti_matrix.learning.statistics import ActionRecord, HOPELESS_TRIES


def events(*specs):
    """A tiny scripted run: candidates, then probes/evaluations/selections keyed by those fingerprints."""
    out = [{"kind": "candidates", "data": {"moves": [{"fp": fp, "label": f"{tool}()", "tool": tool}
                                                     for fp, tool in specs]}}]
    return out


def probe(fp, ok=True, ms=10, chars=100, predicted=False):
    return {"kind": "probe", "data": {"fp": fp, "move": f"{fp}()", "ok": ok, "ms": ms, "chars": chars,
                                      "predicted": predicted}}


def evaluation(fp, progress=0.0):
    return {"kind": "evaluation", "data": {"fp": fp, "move": f"{fp}()", "progress": progress}}


def selected(fp):
    return {"kind": "selected", "data": {"fp": fp, "move": f"{fp}()"}}


class Ev:
    def __init__(self, kind, data):
        self.kind, self.data = kind, data


def observe(stats, *raw):
    for item in raw:
        stats.observe(Ev(item["kind"], item["data"]))
    return stats


def test_it_counts_what_really_happened_against_both_keys():
    stats = observe(Statistics(), *events(("f1", "read_file"), ("f2", "read_file"), ("f3", "search")),
                    probe("f1", ok=True, ms=20, chars=500), evaluation("f1", 0.6), selected("f1"),
                    probe("f2", ok=False, ms=5, chars=0), evaluation("f2", 0.0),
                    probe("f3", ok=True, ms=30, chars=100), evaluation("f3", 0.1))

    read = stats.record("read_file")
    assert (read.probes, read.failures, read.selections) == (2, 1, 1)
    assert read.ok_rate == 0.5 and read.select_rate == 0.5 and read.mean_progress == 0.3
    assert read.mean_ms == 12 and read.chars == 500
    assert stats.record("search").probes == 1
    assert stats.by_fingerprint["f1"].tool == "read_file"  # the exact action remembers its tool
    assert stats.by_fingerprint["f2"].failures == 1


def test_a_predicted_outcome_is_remembered_as_a_prediction_and_never_as_evidence():
    """The engine predicted a write instead of performing it: it may remember predicting, not that it worked."""
    stats = observe(Statistics(), *events(("fp", "add_row")),
                    probe("fp", ok=True, ms=1, chars=40, predicted=True), evaluation("fp", 0.9))

    assert stats.by_fingerprint["fp"].predicted == 1  # the prediction is on record
    assert stats.by_fingerprint["fp"].probes == 0  # but nothing was probed, so nothing was learned
    assert stats.by_fingerprint["fp"].scored == 0
    assert "add_row" not in stats.by_tool  # the tool's record stays empty, i.e. neutral
    assert stats.record("add_row").prior() == 0.5  # still worth trying
    assert stats.avoids() == set()  # and never an avoid entry, however the prediction was scored


def test_an_untried_tool_sits_neutral_while_a_hopeless_one_sorts_below_it():
    stats = observe(Statistics(), *events(("f1", "dead")),
                    *[e for i in range(HOPELESS_TRIES) for e in (probe("f1", ok=False), evaluation("f1", 0.0))])
    assert stats.record("dead").hopeless() is True
    assert stats.hopeless_tools() == {"dead"}
    assert stats.record("nobody_tried_this").prior() == 0.5  # exploring is not a mistake
    assert stats.record("dead").prior() < 0.5  # a tried-and-failed tool is worse than an unknown one


def test_one_early_failure_is_not_enough_to_call_a_tool_hopeless():
    stats = observe(Statistics(), *events(("f1", "flaky")), probe("f1", ok=False), evaluation("f1", 0.0))
    assert stats.record("flaky").hopeless() is False
    assert stats.hopeless_tools() == set()


def test_a_tool_that_worked_but_was_never_chosen_is_scored_by_the_progress_it_made():
    stats = observe(Statistics(), *events(("f1", "partial")), probe("f1", ok=True), evaluation("f1", 0.4))
    record = stats.record("partial")
    assert record.selections == 0 and record.prior() == pytest.approx(0.16)  # 0.6*0 + 0.4*0.4


def test_avoiding_lists_actions_that_failed_every_real_try_and_nothing_else():
    stats = observe(Statistics(), *events(("once", "tool_a"), ("twice", "tool_a"), ("fine", "tool_b")),
                    probe("once", ok=False), probe("twice", ok=False), probe("twice", ok=False),
                    probe("twice", ok=False, predicted=True), probe("fine", ok=True))
    assert stats.avoids() == {"twice"}  # one failure is not a pattern, and a prediction is not a failure
    assert stats.avoids(min_tries=3) == set()  # nor are two real failures enough at a higher bar


def test_facts_are_kept_once_newest_last_and_bounded():
    stats = Statistics()
    stats.observe(Ev("state", {"fact_list": ["a fact", "another"]}))
    stats.observe(Ev("state", {"fact_list": ["another", "a third"]}))
    stats.observe(Ev("stopped", {"facts": ["last"]}))
    assert stats.facts == ["a fact", "another", "a third", "last"]
    stats.add_facts([f"f{i}" for i in range(10)], limit=3)
    assert stats.facts == ["f7", "f8", "f9"]


def test_recall_answers_with_matching_facts_then_what_the_actions_taught_it():
    stats = observe(Statistics(), *events(("f1", "open_notes"), ("f2", "legacy_dump")),
                    probe("f1", ok=True), evaluation("f1", 1.0), selected("f1"),
                    *[e for i in range(HOPELESS_TRIES) for e in (probe("f2", ok=False), evaluation("f2", 0.0))])
    stats.add_facts(["open_notes() -> ok: the queue holds one row", "legacy_dump() -> FAILED: unsupported"])

    matching = stats.recall("queue")
    assert "matching 'queue' in earlier runs" in matching and "one row" in matching
    assert "actions that have paid off here: open_notes (chosen 1×, progress 1.00)" in matching
    assert "actions that have never worked here: legacy_dump" in matching

    empty = stats.recall("nothing looks like this")
    assert "nothing in earlier runs matches" in empty

    blank = Statistics().recall()
    assert blank == "nothing learned about this environment yet"


def test_a_record_survives_a_round_trip_and_a_shape_from_elsewhere_is_refused_not_half_read():
    stats = observe(Statistics(), *events(("f1", "read_file")), probe("f1", ok=True, ms=7), evaluation("f1", 0.5))
    stats.add_facts(["read_file() -> ok: hello"])

    restored = Statistics.from_dict(stats.to_dict())
    assert restored.to_dict() == stats.to_dict()
    assert restored.record("read_file").mean_ms == 7 and restored.facts == ["read_file() -> ok: hello"]

    assert Statistics.from_dict({"version": 99, "tools": {"x": {"probes": 5}}}).by_tool == {}
    assert Statistics.from_dict(None).by_tool == {}
    assert Statistics.from_dict({"tools": {"x": {"probes": 2}}}).by_tool == {}  # no version, no guess
    assert "read_file" in Statistics.from_dict(stats.to_dict()).to_text()


def test_it_ignores_anything_it_cannot_attribute_to_a_candidate():
    stats = observe(Statistics(), probe("never_offered", ok=True), evaluation("never_offered", 1.0),
                    {"kind": "selected", "data": {"fp": "never_offered"}},
                    {"kind": "candidates", "data": {"moves": "not a list"}},
                    {"kind": "probe", "data": {"fp": None}}, {"kind": "nonsense", "data": {}})
    assert stats.by_tool == {} and stats.by_fingerprint == {}
    assert stats.recall() == "nothing learned about this environment yet"


def test_a_records_own_line_reads_plainly():
    assert ActionRecord("read_file").to_text() == "read_file: never tried here"
    record = ActionRecord.from_dict({"tool": "open", "probes": 4, "failures": 1, "selections": 2,
                                     "progress": 1.5, "scored": 3, "ms": 40})
    assert "4 probe(s), 1 failed, chosen 2×" in record.to_text() and "mean 10 ms" in record.to_text()
