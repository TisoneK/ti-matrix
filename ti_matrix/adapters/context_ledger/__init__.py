"""A repository's Context Ledger as the engine's world — and the run's results back into it.

The engine already remembers everything: what real observations established, what it tried, what failed. It
remembers inside one run. `.context_ledger/` is a *repository's* memory of exactly that kind — plain markdown
in git, written by one session for the next one to read before it touches anything:

    memory/office/    the live office — who is working now, the task in flight, the backlog,
                      the decisions in force, and two logs of traps the last agents hit
    memory/history/   closed offices, frozen verbatim
    memory/user/      who the human is, and how they like things done
    memory/system/    the machines and the models, with the commands verified on them

This adapter closes the loop between the two, in the two directions the ledger's own rule asks for — *start by
reading the ledger, finish by updating it*:

  - ``LedgerEnvironment`` is the READ half: read-only actions over the vault — the orientation digest, the
    work queue, the decisions, the session registry, the friction logs, and a search across all of them. Every
    action reads, so a run can explore a project's memory with no possibility of damaging it — and the
    engine's own boundary (an action that is not read-only is never probed) guarantees it.
  - ``LedgerRecorder`` is the WRITE half, and it is deliberately not an Environment action: the engine never
    performs a write, so the host feeds the recorder the run's own events and it appends what the run
    established — the facts, the dead ends, the answer — in the ledger's entry formats, promoting the durable
    facts into the parking lot's Findings, where the next session's reading order finds them.

What that buys is the thing neither project has alone: a run that starts from what the project already knows
and ends by adding to it, so the next run — a different model, a different machine, a fresh context window —
does not re-investigate what was settled or re-try what already failed.

Both halves are files plus the formats the vault's own schema defines
(`.context_ledger/core/schemas/ledger-schema.md`); nothing here invents a shape, and nothing here needs a host
application, a server or a dependency.

The parts:

    parsing.py       the vault's markdown as data — the entry formats, and the traps in reading them
    vault.py         where the memory is: reading, searching, and the three narrow shapes of writing
    environment.py   the read actions the engine may probe, and the writes it may only reason about
    recorder.py      what a run learned, appended back into the project's memory
"""
from ti_matrix.adapters.context_ledger.environment import (
    LEDGER_ACTIONS,
    LEDGER_READ_ACTIONS,
    LEDGER_WRITE_ACTIONS,
    LedgerEnvironment,
    environment_for,
)
from ti_matrix.adapters.context_ledger.parsing import (
    Decision,
    LogEntry,
    RosterRow,
    Row,
    SessionEntry,
)
from ti_matrix.adapters.context_ledger.recorder import LedgerRecorder, LedgerWrite
from ti_matrix.adapters.context_ledger.vault import LedgerVault

__all__ = [
    "LEDGER_ACTIONS",
    "LEDGER_READ_ACTIONS",
    "LEDGER_WRITE_ACTIONS",
    "Decision",
    "LedgerEnvironment",
    "LedgerRecorder",
    "LedgerVault",
    "LedgerWrite",
    "LogEntry",
    "RosterRow",
    "Row",
    "SessionEntry",
    "environment_for",
]
