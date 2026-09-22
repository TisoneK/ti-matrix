"""What the engine learns from its own runs — counted, never narrated — and what it does with it.

The engine already emits everything needed to learn from: every probe carries whether it worked, how long
it took and how much it returned; every outcome carries the progress the evaluator judged it worth; every
selection says which action the search actually took. What was missing was memory — ``AgentState`` is built
fresh for each run, so a cold start re-proposes the action that failed twice yesterday.

The constraint that shapes everything here: **it is arithmetic.** Every number is a count, a sum or a rate
derived from an event the engine already produced; not one is a sentence a model wrote about itself. That is
the project's existing promise — a state rebuilt from real observations, never from the model's memory of a
chat — applied across runs instead of within one. A layer that accumulated the model's *reasons* would
reintroduce exactly the drift the engine was built to prevent, more slowly and harder to see. So
``Observation.ok`` is trusted here and ``Evaluation.reason`` is not even read.

The parts:

    statistics.py   the record itself: per tool and per exact action, plus the facts observations left
    proposer.py     LearningProposer — spends the record on the fan, so experience decides what is tried
    cache.py        CachingEnvironment — stops asking an unchanged world the same question twice
"""
from ti_matrix.learning.cache import CachingEnvironment
from ti_matrix.learning.proposer import LearningProposer
from ti_matrix.learning.statistics import ActionRecord, Statistics

__all__ = ["ActionRecord", "CachingEnvironment", "LearningProposer", "Statistics"]
