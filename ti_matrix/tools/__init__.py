"""Tool sets: several sources of actions, resolved into the one set a model is shown.

An environment supplies its own actions (``tools()``), and that is the engine's whole requirement of it.
The moment more than one source of actions exists — a shipped environment, an application's own actions,
the engine's own memory tools — something has to decide what the model is shown when two of them offer the
same thing, and that decision is the whole content of this package.

Three rules, all deterministic, because the alternative (asking a model whether two tools "work alike")
would put an unverifiable belief in the one place this engine refuses to keep them:

  - **A name decides.** Two tools sharing a name are the same tool as far as any model can tell.
  - **Preference is declared, never inferred.** A user's tool beats a built-in by default, or the other way
    round with ``prefer="builtin"``; a tool whose name differs but whose job is the same says so itself,
    with ``supersedes="<tool>"``. Nothing is guessed from a description.
  - **The resolution is a record.** ``ToolSet.resolution()`` reports what was kept, renamed and dropped, so
    a host can print it or emit it as an event instead of leaving the model's tool list a mystery.

A tool that loses a collision needs no new engine behaviour: it is simply absent from the tools the model is
shown, and an action the environment does not know is already remembered as a failed move. Shadowing is a
decision about who wins, made once, at construction.

Identity is settled here too, and that matters beyond the prompt: an ``Action``'s fingerprint is its tool
name plus its arguments, so the name a tool resolves to *is* the identity every later record is keyed by.
Two implementations of one tool that each kept their own name would leave indistinguishable history; two
that resolve to one name is exactly what a shadow is supposed to mean.

The parts:

    registry.py       ToolSource, Resolution, ToolSet — the resolution, and nothing that performs anything
    composite.py      CompositeEnvironment — several environments presented as one, each action routed home
    engine_tools.py   EngineTools — the tool the engine itself insists on (``recall``), wrapped around any
                      environment, plus the Memory port it answers from
"""
from ti_matrix.tools.composite import CompositeEnvironment
from ti_matrix.tools.engine_tools import EngineTools, Memory
from ti_matrix.tools.registry import Resolution, ToolSet, ToolSetError, ToolSource

__all__ = [
    "CompositeEnvironment",
    "EngineTools",
    "Memory",
    "Resolution",
    "ToolSet",
    "ToolSetError",
    "ToolSource",
]
