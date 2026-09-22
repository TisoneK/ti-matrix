"""Two ways to answer the question the engine asks before it does something that changes the world.

A `Confirmer` is asked, per action, at the moment the engine would perform it. These are the two answers a
host usually wants, and they compose: a grant list for what you have already decided about, and a terminal
prompt for the rest — because the interesting case is not "may this run click anything", it is "may it click
*this*, right now, for the reason it gives".

Neither of these is a security boundary on its own. The engine performs only read-only actions; a confirmer is
how a *host* hands back one specific thing, once, on the record. If you want a rule rather than a decision,
use the environment's `perform` set and skip this entirely.
"""
from __future__ import annotations

import sys
from typing import Callable, Iterable, Optional, TextIO

from ti_matrix.protocols import Action


class Granted:
    """Grants the actions it was told to, and refuses everything else.

    ``names`` are tool names (``{"click"}``) and ``fingerprints`` are exact actions
    (``{Action("click", {"selector": "@e3"}).fingerprint()}``) — the difference matters when a tool is
    acceptable in general but one particular use of it is not, which is the whole reason to confirm one
    action at a time.
    """

    def __init__(self, names: Iterable[str] = (), fingerprints: Iterable[str] = ()) -> None:
        self.names = frozenset(names)
        self.fingerprints = frozenset(fingerprints)
        self.asked: list[tuple[str, str, bool]] = []  # (action, reason, granted) — what it decided, in order

    async def confirm(self, action: Action, reason: str) -> bool:
        granted = action.fingerprint() in self.fingerprints or action.tool in self.names
        self.asked.append((action.label(), reason, granted))
        return granted


class Ask:
    """Asks on a stream — the terminal by default — and grants only a clear yes.

    Whatever the stream is: the real terminal, or a pipe a script wrote ``y`` into. A blank line, end of input
    and anything that is not "y"/"yes" are all refusals, because the safe default is the one that has to be
    overridden deliberately.
    """

    def __init__(self, stream: Optional[TextIO] = None, *, ask: bool = True,
                 shower: Optional[Callable[[str], None]] = None) -> None:
        self.stream = stream if stream is not None else sys.stdin
        self.ask, self.shower = ask, shower or (lambda line: print(line, file=sys.stderr))
        self.asked: list[tuple[str, str, bool]] = []

    async def confirm(self, action: Action, reason: str) -> bool:
        self.shower(f"the engine wants to perform: {action.label()}"
                    + (f"\n  because: {reason}" if reason else "")
                    + "\n  allow this one action? [y/N] ")
        granted = False
        if self.ask:
            try:
                granted = (self.stream.readline() or "").strip().lower() in ("y", "yes")
            except (OSError, ValueError):
                granted = False  # no way to ask is a refusal, not a crash
        self.asked.append((action.label(), reason, granted))
        self.shower("  granted" if granted else "  refused")
        return granted


__all__ = ["Ask", "Granted"]
