"""Does the learning layer pay for itself? A deterministic measurement, with no model in the loop.

The engine's scarce resource is its model budget: one call to propose a fan, one to score it. So "is the engine
better with what it has learned" is a question about *rounds* — how many fans a goal takes — and about the
probe work a fan wastes. This bench answers it with numbers rather than adjectives.

Three ways to run the same eight goals, in the same order:

    cold        a fresh engine each time: no accumulated record, no cache, nothing carried in
    warm        the same goals, with the record carried between runs and the learning layer on
    control     the same two runs again with a fan wide enough to hold every candidate

The control holds the fan fixed and varies only the learning, which is the comparison that means something:
learning here can only act through the fan — ordering candidates, dropping hopeless ones, skipping a repeated
probe — so with a fan that already holds everything there is nothing left for it to do. A gain in the control
would mean the numbers came from the bench rather than from the layer. (A wide fan settling goals faster than
a narrow one is not a result about learning at all; it is just a wider fan, which is why the control is
fan-to-fan and not wide-to-cold.)

What the model is: a scripted proposer with an uninformed, fixed order, and a scripted scorer that recognises
the answer when it sees it. That is the point — an uninformed proposer is exactly what makes the engine's own
experience worth having, and it keeps this measurement about the engine's learning rather than about any
model's quality. The numbers are counts of things that happened, plus one clearly-labelled model of what real
model calls would have cost in wall time.
"""
from __future__ import annotations

import asyncio
import time

from ti_matrix import (
    Action,
    ActionSpec,
    CachingEnvironment,
    EngineBudget,
    Evaluation,
    Goal,
    LearningProposer,
    Observation,
    StateEngine,
    Statistics,
)

CALL_MS = 800  # a plausible round-trip to a real endpoint, used only for the modelled column
FAN = 3  # max_branches: how many candidates a fan has room for
GOALS = 8

ANSWERS = {"answer_a": "value=11", "answer_b": "value=22", "answer_c": "value=33"}
ORDER = ["dead", "muted", "partial", *ANSWERS]  # the uninformed order, useless tools first
PARTIAL = "partial: something related"


class World:
    """A fixed world with four kinds of tool: one that fails, one that answers uselessly, one that half
    answers, and the ones that really do. Nothing here changes between runs — which is what makes the cache's
    "unchanged" claim in this bench true by construction rather than optimistic."""

    name = "bench-world"

    def __init__(self):
        self.asked: list[str] = []
        self._specs = {t: ActionSpec(t, f"does {t}") for t in ORDER}

    def tools(self):
        return self._specs

    def is_read_only(self, action):
        return None if action.tool not in self._specs else True

    async def probe(self, action):
        self.asked.append(action.tool)
        if action.tool == "dead":
            return Observation(action, False, "unsupported on this platform")
        if action.tool == "muted":
            return Observation(action, True, "nothing useful here")
        if action.tool == "partial":
            return Observation(action, True, PARTIAL)
        return Observation(action, True, ANSWERS.get(action.tool, "no such tool"))


class Uninformed:
    """A proposer with a fixed order — what a model does when it does not know this world's affordances."""

    def __init__(self):
        self.calls = 0

    async def propose(self, state, n, avoid):
        self.calls += 1
        moves = [Action(t, {}, "because") for t in ORDER]
        return [m for m in moves if m.fingerprint() not in avoid][:n]


class Scorer:
    """A deterministic stand-in for the evaluator: the answer when it sees it, half credit for the partial."""

    def __init__(self, expected):
        self.expected = expected
        self.calls = 0

    async def evaluate(self, state, outcomes):
        self.calls += 1
        out = []
        for o in outcomes:
            if o.ok and self.expected in o.text:
                out.append(Evaluation(1.0, True, self.expected, "found it"))
            elif o.ok and PARTIAL in o.text:
                out.append(Evaluation(0.4, False, "", "half an answer"))
            else:
                out.append(Evaluation(0.0, False, "", "nothing useful"))
        return out


async def run_goal(goal_text, expected, world, *, stats=None, fan=FAN):
    """One engine run. With `stats`, the run both reads the record and adds to it."""
    inner = Uninformed()
    proposer = LearningProposer(inner, stats) if stats is not None else inner
    evaluator = Scorer(expected)
    engine = StateEngine(world, proposer=proposer, evaluator=evaluator,
                         budget=EngineBudget(max_branches=fan, max_model_calls=8))
    events = []
    async for event in engine.run(Goal(goal_text)):
        events.append(event)
        if stats is not None:
            stats.observe(event)
    settled = events[-1].kind == "done"
    return {"settled": settled, "calls": evaluator.calls + inner.calls,
            "probes": sum(1 for e in events if e.kind == "probe"),
            "rounds": sum(1 for e in events if e.kind == "candidates")}


async def series(*, learn: bool, fan: int, cache: bool):
    """The whole goal set in one world, optionally carrying experience from goal to goal."""
    world = World()
    stats = Statistics() if learn else None
    environment = CachingEnvironment(world) if cache else world
    rows, started = [], time.perf_counter()
    for i in range(GOALS):
        tool = list(ANSWERS)[i % len(ANSWERS)]
        row = await run_goal(f"what is value #{i + 1}?", ANSWERS[tool], environment,
                             stats=stats, fan=fan)
        rows.append(row)
    elapsed = (time.perf_counter() - started) * 1000
    return {"rows": rows, "ms": elapsed, "stats": stats, "world": world,
            "cache": environment if cache else None}


def report(label, result, control=False):
    rows = result["rows"]
    settled = sum(1 for r in rows if r["settled"])
    calls = sum(r["calls"] for r in rows)
    probes = sum(r["probes"] for r in rows)
    hits = result["cache"].hits if result["cache"] is not None else 0
    print(f"\n{label}")
    print(f"  settled      {settled}/{len(rows)} goals")
    print(f"  model calls  {calls}  ({calls / len(rows):.1f} per goal)")
    print(f"  probes       {probes}  ({hits} served from cache)")
    print(f"  rounds       {sum(r['rounds'] for r in rows)}")
    print(f"  elapsed      {result['ms']:.1f} ms measured; "
          f"{calls * CALL_MS / 1000:.1f} s modelled at {CALL_MS} ms per model call")
    per_goal = "".join("o" if r["settled"] else "-" for r in rows)
    print(f"  per goal     {per_goal}  ('o' settled, '-' not settled)")
    if control:
        print("  (control: this fan holds every candidate — learning can only act through the fan, so a gain "
              "here would be the bench talking)")
    return {"settled": settled, "calls": calls, "probes": probes, "hits": hits}


async def main():
    print(f"{GOALS} goals, one fixed world, fan of {FAN} candidates, uninformed proposer order {ORDER}.")
    print("All numbers are counted from the engine's own events, except the modelled column, which is "
          f"labelled and is only model calls × {CALL_MS} ms.")

    cold = await series(learn=False, fan=FAN, cache=False)
    cold_summary = report("cold — nothing carried in", cold)
    warm = await series(learn=True, fan=FAN, cache=True)
    warm_summary = report("warm — the record carried between goals, with the cache", warm)

    wide_cold = await series(learn=False, fan=len(ORDER), cache=False)
    control_off = report("control, learning off — fan wide enough to hold every candidate", wide_cold, True)
    wide_warm = await series(learn=True, fan=len(ORDER), cache=True)
    control_on = report("control, learning on — the same fan", wide_warm, True)

    print("\nwhat it came to")
    print(f"  model calls   {cold_summary['calls']} cold → {warm_summary['calls']} warm "
          f"({warm_summary['calls'] - cold_summary['calls']:+d}, "
          f"{(1 - warm_summary['calls'] / cold_summary['calls']):.0%} fewer)")
    print(f"  probes        {cold_summary['probes']} cold → {warm_summary['probes']} warm "
          f"({warm_summary['probes'] - cold_summary['probes']:+d}, {warm_summary['hits']} of the warm ones "
          f"served from cache)")
    print(f"  settled       {cold_summary['settled']} cold → {warm_summary['settled']} warm "
          f"(of {GOALS})")
    print(f"  control       {control_off['calls']} calls with learning off → {control_on['calls']} with it on "
          f"({control_on['calls'] - control_off['calls']:+d}; expected 0)")

    print("\nwhat the record says afterwards (warm run)")
    print(warm["stats"].to_text())

    print("\nper goal, cold then warm")
    print("  goal    cold: rounds/probes/settled    warm: rounds/probes/settled")
    for i, (c, w) in enumerate(zip(cold["rows"], warm["rows"])):
        print(f"  {i + 1:>4}    {c['rounds']:>4} /{c['probes']:>3} /{str(c['settled']):<6}"
              f"     {w['rounds']:>4} /{w['probes']:>3} /{str(w['settled']):<6}")
    print("\nEarly goals are the burn-in: nothing is known yet, so warm matches cold or trails it. "
          "The claim is about what happens once the record has something in it.")


if __name__ == "__main__":
    asyncio.run(main())
