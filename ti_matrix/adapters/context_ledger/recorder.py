"""The write half: what the run found, back into the project's memory.

A write is not an Environment action — the engine performs read-only actions only, by construction — so this
is the host's half of the loop: hand every event you consume from ``engine.run(goal)`` to a recorder, then
call :meth:`LedgerRecorder.record` once at the end. It appends the run's detail to the office's session notes
and promotes the durable facts into the parking lot's Findings, which is where the next session's own
start-of-session reading finds them.

A dead end is an action the next agent should not retry, and it is read off the events the same way the engine
itself decides one: a probe that really failed, a fingerprint the engine put in ``state.failed``, and — when a
run ends in ``no_progress`` — the probes of that last fan, every one of which the engine marked failed at that
state. A *predicted* outcome is never a dead end, because nothing was tried. Each is named as the action, not
as a fingerprint: this file is read by people and models, and neither can do anything with a sha.

Nothing is overwritten, and a target that is not there is reported rather than created.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any, Optional

from ti_matrix.adapters.context_ledger.parsing import _clip, _one_line
from ti_matrix.adapters.context_ledger.vault import LedgerVault

_SUMMARY_CHARS = 180  # how much of a fact a promoted parking-lot row carries
_NOTES = "memory/office/sessions/notes.md"
_PARKING = "memory/office/tasks/parking-lot.md"

@dataclass(frozen=True)
class LedgerWrite:
    """What a recorder wrote — and what it deliberately did not, with the reason."""

    run_notes: str = ""
    findings: tuple[str, ...] = ()
    skipped: tuple[str, ...] = ()
    dry_run: bool = False
    preview: str = ""

    def to_text(self) -> str:
        verb = "would write" if self.dry_run else "wrote"
        lines = [f"ledger: {verb} the run's detail to {self.run_notes}" if self.run_notes
                 else "ledger: the run's detail was NOT written"]
        if self.findings:
            lines.append(f"ledger: {verb} {len(self.findings)} finding(s) to {_PARKING}: "
                         + ", ".join(self.findings))
        lines += [f"ledger: skipped — {s}" for s in self.skipped]
        if self.dry_run and self.preview:
            lines.append("── preview ──\n" + self.preview)
        return "\n".join(lines)


@dataclass
class _Run:
    """One engine run, accumulated from its events."""

    goal: str = ""
    outcome: str = ""
    settled: bool = False
    answer: str = ""
    facts: list[str] = field(default_factory=list)
    trail: list[str] = field(default_factory=list)
    dead_ends: list[str] = field(default_factory=list)
    labels: dict[str, str] = field(default_factory=dict)
    pending: list[str] = field(default_factory=list)
    calls: int = 0


class LedgerRecorder:
    """Feeds on a run's events and appends what the run established into the vault.

    One recorder records one run: a second call to :meth:`record` reports that it already wrote rather than
    appending the same block twice, because a byte-identical duplicate is the one thing this vault's own
    compaction rules exist to clean up.
    """

    def __init__(
        self,
        vault: str | Path | LedgerVault,
        *,
        agent: str = "Ti Matrix",
        model: str = "",
        platform: str = "",
        promote_findings: bool = True,
        max_findings: int = 5,
    ) -> None:
        self.vault = vault if isinstance(vault, LedgerVault) else LedgerVault(vault)
        self.agent = agent
        self.model = model
        self.platform = platform
        self.promote_findings = promote_findings
        self.max_findings = max(0, max_findings)
        self.run = _Run()
        self._recorded = False

    def _dead_end(self, name: Any) -> None:
        if isinstance(name, str) and name and name not in self.run.dead_ends:
            self.run.dead_ends.append(name)

    def observe(self, event: Any) -> None:
        """Take one ``EngineEvent`` (anything with ``.kind`` and ``.data``)."""
        kind, data = getattr(event, "kind", ""), getattr(event, "data", None) or {}
        fp, label = data.get("fp"), data.get("move")
        if isinstance(fp, str) and isinstance(label, str):
            self.run.labels[fp] = label  # every fingerprint→label pair, so dead ends read as actions
        if kind == "state":
            if isinstance(data.get("goal"), str):
                self.run.goal = data["goal"]  # every state event carries the goal it is searching toward
            if isinstance(data.get("fact_list"), list):
                self.run.facts = [str(f) for f in data["fact_list"]]
            if isinstance(data.get("trail"), list):
                self.run.trail = [str(t) for t in data["trail"]]
            for failed in data.get("failed_fps", []) if isinstance(data.get("failed_fps"), list) else []:
                self._dead_end(self.run.labels.get(str(failed), str(failed)))
        elif kind == "probe" and not data.get("predicted") and label:
            if data.get("ok"):
                self.run.pending.append(label)
            else:
                self._dead_end(label)
        elif kind == "selected":
            self.run.pending.clear()  # this fan chose an action; its siblings were not chosen, not failures
            if label and label not in self.run.trail:
                self.run.trail.append(label)
        elif kind in ("done", "stopped"):
            if kind == "stopped" and str(data.get("reason", "")) == "no_progress":
                # The engine marked this whole fan failed at this state before it stopped.
                for name in self.run.pending:
                    self._dead_end(name)
            self.run.pending.clear()
            self.run.outcome = "done" if kind == "done" else str(data.get("reason", "unknown"))
            self.run.settled = kind == "done"
            self.run.answer = str(data.get("answer", ""))
            if isinstance(data.get("model_calls"), int):
                self.run.calls = data["model_calls"]
            if kind == "stopped":
                if isinstance(data.get("facts"), list):
                    self.run.facts = [str(f) for f in data["facts"]]
                if data.get("needs"):  # a goal this engine may not settle, and the action it would need
                    self._dead_end(f"needs an action the engine may not perform: {data['needs']}")

    # ── composing ──

    def run_block(self, day: Optional[str] = None) -> str:
        """The run's detail, in the shape the office's own `sessions/notes.md` template carries."""
        r = self.run
        stamp = day or date.today().isoformat()
        who = f"{self.agent} / {self.model}" if self.model else self.agent
        outcome = (f"done — {_clip(r.answer, 400)}" if r.settled and r.answer
                   else "done — no answer recorded" if r.settled
                   else f"stopped ({r.outcome or 'unknown'}) — the goal is NOT settled")
        lines = [f"## {stamp} — {who} (engine run)", f"- **Goal:** {_clip(r.goal, 400)}",
                 f"- **Outcome:** {outcome}"]
        if self.platform:
            lines.append(f"- **Platform:** {self.platform}")
        lines.append(f"- **Facts established ({len(r.facts)}):**")
        lines += [f"  - {_one_line(f)}" for f in r.facts] or ["  - none"]
        lines.append(f"- **Dead ends, do not retry ({len(r.dead_ends)}):**")
        lines += [f"  - {_one_line(d)}" for d in r.dead_ends] or ["  - none"]
        if r.trail:
            lines.append("- **Trail:** " + " → ".join(r.trail))
        if r.calls:
            lines.append(f"- **Model calls:** {r.calls}")
        return "\n".join(lines)

    def finding_rows(self, day: Optional[str] = None) -> list[str]:
        """One parking-lot row per fact the run really established, minus anything already parked.

        A fact is a sentence, but a row is a table cell: a `|` inside one (an observation of a markdown
        table, say) would split the row into cells that are not there, so pipes become slashes.
        """
        if not self.run.facts or not self.max_findings or not self.vault.exists():
            return []
        stamp = day or date.today().isoformat()
        parked = _one_line(" ".join(r.summary for r in self.vault.parking_lot())).lower()
        n = self.vault.id_sequence(_PARKING, "P-", stamp)
        rows: list[str] = []
        for fact in self.run.facts:
            if len(rows) >= self.max_findings:
                break
            summary = _clip(fact, _SUMMARY_CHARS).replace("|", "/")
            if summary[:60].lower() in parked:  # already recorded by an earlier run — no second row
                continue
            n += 1
            rows.append(f"| P-{stamp}-{n} | {summary} — from the \"{_clip(self.run.goal, 80)}\" engine "
                        f"run (`sessions/notes.md`) |")
        return rows

    def record(self, goal: str = "", *, day: Optional[str] = None, dry_run: bool = False) -> LedgerWrite:
        """Append this run to the vault. Returns exactly what was written and what was not.

        One recorder records one run: a second call reports that it already wrote rather than appending
        the same block twice, because a byte-identical duplicate is the one thing the ledger's own
        compaction rules exist to clean up.
        """
        if goal and not self.run.goal:
            self.run.goal = goal
        block = self.run_block(day)
        rows = self.finding_rows(day) if self.promote_findings else []
        preview = block + ("\n\n" + "\n".join(rows) if rows else "")
        planned = tuple(r.split("|")[1].strip() for r in rows)

        if not self.vault.exists():
            return LedgerWrite(skipped=(f"{self.vault} is not a bootstrapped Context Ledger — nothing "
                                        f"was written",), dry_run=dry_run, preview=preview)
        if dry_run:
            return LedgerWrite(run_notes=_NOTES, findings=planned, dry_run=True, preview=preview)
        if self._recorded:
            return LedgerWrite(skipped=("this recorder already recorded this run — one run, one entry",
                                        ), preview=preview)
        skipped: list[str] = []
        written = _NOTES if self.vault.append(_NOTES, block) else ""
        if not written:
            skipped.append(f"{_NOTES} is not in this vault — the run's detail was not recorded")
        promoted: tuple[str, ...] = ()
        if rows:
            if self.vault.add_rows(_PARKING, "## Findings", rows):
                promoted = planned
            else:
                skipped.append(f"{_PARKING} has no Findings table — nothing promoted (the run's detail "
                               f"still carries every fact)")
        self._recorded = True
        return LedgerWrite(run_notes=written, findings=promoted, skipped=tuple(skipped), preview=preview)


