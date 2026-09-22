"""The vault itself: where a project's memory is, and how to read, search and append to it.

Reading is bounded everywhere — `read` and `search` clip what they return — because every answer here is
destined for a model's prompt inside a fan, and an unbounded listing would spend the run's budget on text
nobody asked about.

Writing is deliberately narrow: append a block at the end, insert rows into a table that already exists, or
don't write at all. Nothing here creates a file. A vault's file shapes belong to its schema, and a missing one
is something to report rather than to invent.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

from ti_matrix.adapters.context_ledger.parsing import (
    Decision,
    LogEntry,
    RosterRow,
    Row,
    SessionEntry,
    _ADR,
    _CODENAME,
    _DATED,
    _ROW,
    _clip,
    _fields,
    _one_line,
    _sections,
    _strip_comments,
    _table_rows,
)

LEDGER_DIR = ".context_ledger"
_OBS_MAX_CHARS = 2600  # an observation the evaluator can see whole (its view is 2800)
_CLIP = 200  # how much of one memory line a list action shows
_TEXT_SUFFIXES = {".md", ".json", ".txt", ".conf", ".lock", ".yml", ".yaml"}
_PLAIN_TEXT_NAMES = {"VERSION", ".gitignore", ".gitattributes"}
_ARCHIVE_DIR = "archive"  # zipped cold storage — never read at session start, never searched by default
_MAX_SEARCH_BYTES = 256 * 1024
SCOPES = ("memory", "office", "history", "all")  # what a search or a listing may look at

class LedgerVault:
    """A `.context_ledger/` directory, read as data.

    ``root`` may be the project directory that contains the ledger or the ledger directory itself — a
    caller naming a vault should not have to know which one they are holding.
    """

    def __init__(self, root: str | Path) -> None:
        p = Path(root).expanduser()
        self.dir = p if p.name == LEDGER_DIR else p / LEDGER_DIR
        self.memory = self.dir / "memory"
        self.office = self.memory / "office"
        self.history = self.dir / "history"

    def __str__(self) -> str:
        return str(self.dir)

    def exists(self) -> bool:
        """True when this is a bootstrapped vault rather than a path someone hoped was one."""
        return (self.office / "agents").is_dir() or (self.office / "STATE.md").is_file()

    # ── locating and reading files ──

    def path(self, rel: str) -> Optional[Path]:
        """Resolve `rel` (relative to the ledger dir). None when it points outside the ledger."""
        candidate = (self.dir / rel).resolve()
        root = self.dir.resolve()
        return candidate if candidate == root or root in candidate.parents else None

    def read(self, rel: str, *, max_chars: int = _OBS_MAX_CHARS) -> Optional[str]:
        """The text of one ledger file, or None when it is not a file or not inside the ledger."""
        p = self.path(rel)
        if p is None or not p.is_file():
            return None
        text = p.read_text(encoding="utf-8", errors="replace")
        return text[:max_chars] + ("\n… (truncated)" if len(text) > max_chars else "")

    def _files(self, scope: str) -> list[tuple[str, Path]]:
        """The readable files of a scope, as (path relative to the ledger dir, absolute path).

        The relative path is POSIX (`memory/office/tasks/backlog.md`), never the host's separator: this text
        goes to the model and comes back as an argument to `read_memory`, and the ledger's own files and docs
        name paths that way. On Windows `str(Path)` would otherwise hand the model backslashes to echo."""
        base = {"office": self.office, "memory": self.memory, "history": self.history, "all": self.dir}.get(scope)
        if base is None or not base.is_dir():
            return []
        out: list[tuple[str, Path]] = []
        for p in sorted(base.rglob("*")):
            if not p.is_file() or _ARCHIVE_DIR in p.parts or ".git" in p.parts:
                continue
            if p.suffix in _TEXT_SUFFIXES or p.name in _PLAIN_TEXT_NAMES:
                out.append((p.relative_to(self.dir).as_posix(), p))
        return out

    def search(self, needle: str, *, scope: str = "memory", limit: int = 25) -> tuple[list[tuple[str, int, str]], int]:
        """Case-insensitive substring search over a scope: (hits, total lines) — hits capped, total honest."""
        low = needle.lower()
        hits: list[tuple[str, int, str]] = []
        total = 0
        for rel, p in self._files(scope):
            try:
                if p.stat().st_size > _MAX_SEARCH_BYTES:
                    continue
                text = p.read_text(encoding="utf-8", errors="replace")
            except OSError:  # a file that vanished or cannot be read is skipped, not fatal
                continue
            for i, line in enumerate(text.splitlines(), 1):
                if low in line.lower():
                    total += 1
                    if len(hits) < limit:
                        hits.append((rel, i, _clip(_strip_comments(line), _CLIP)))
        return hits, total

    # ── the parsers ──

    def core_version(self) -> str:
        f = self.dir / "core" / "VERSION"
        return f.read_text(encoding="utf-8").strip() if f.is_file() else ""

    def digest(self) -> Optional[str]:
        return self.read("memory/office/STATE.md", max_chars=1_000_000)

    def roster(self) -> list[RosterRow]:
        text = self.read("memory/office/agents/roster.md", max_chars=1_000_000)
        if text is None:
            return []
        rows: list[RosterRow] = []
        for cells in _table_rows(_strip_comments(text)):
            padded = (cells + [""] * 6)[:6]
            if not _CODENAME.match(padded[1]):  # the header row, and anything that is not a person
                continue
            rows.append(RosterRow(*padded))
        return rows

    def current_task(self) -> dict[str, str]:
        text = self.read("memory/office/tasks/current.md", max_chars=1_000_000)
        return _fields(_strip_comments(text)) if text is not None else {}

    def backlog(self) -> list[Row]:
        return self._queue("memory/office/tasks/backlog.md", prefix="B-")

    def parking_lot(self) -> list[Row]:
        return self._queue("memory/office/tasks/parking-lot.md", prefix="P-")

    def _queue(self, rel: str, *, prefix: str) -> list[Row]:
        text = self.read(rel, max_chars=1_000_000)
        if text is None:
            return []
        out: list[Row] = []
        for heading, body in _sections(_strip_comments(text), levels=(2, 3)):
            if not heading:  # the preamble above the first section is prose, not a table
                continue
            for cells in _table_rows(body):
                if cells and cells[0].startswith(prefix):
                    out.append(Row(cells[0], _one_line(" ".join(cells[1:])), heading))
        return out

    def decisions(self) -> list[Decision]:
        text = self.read("memory/office/plans/decisions.md", max_chars=1_000_000)
        if text is None:
            return []
        out: list[Decision] = []
        for heading, body in _sections(_strip_comments(text)):
            m = _ADR.match(heading)
            if m:
                out.append(Decision(m.group("number"), _one_line(m.group("title")), m.group("date"),
                                    _one_line(_fields(body).get("Status", "")), body))
        return out

    def log_entries(self, log: str) -> list[LogEntry]:
        d = "flaws" if log == "flaws" else "inefficiencies"
        text = self.read(f"memory/office/{d}/log.md", max_chars=1_000_000)
        if text is None:
            return []
        out: list[LogEntry] = []
        for heading, body in _sections(_strip_comments(text)):
            m = _DATED.match(heading)
            if m:
                out.append(LogEntry(m.group("date"), _one_line(m.group("who")), _fields(body)))
        return out

    def sessions(self, limit: int = 5) -> list[SessionEntry]:
        text = self.read("memory/office/agents/sessions.md", max_chars=1_000_000)
        if text is None:
            return []
        out: list[SessionEntry] = []
        for heading, body in _sections(_strip_comments(text)):
            m = _DATED.match(heading)
            if m:
                out.append(SessionEntry(heading, m.group("date"), _one_line(m.group("who")), _fields(body)))
        return out[-limit:] if limit > 0 else []

    def id_sequence(self, rel: str, prefix: str, day: str) -> int:
        """The highest `<prefix><day>-<n>` already used in a file — the next row continues from there."""
        text = self.read(rel, max_chars=1_000_000) or ""
        used = [int(n) for n in re.findall(rf"{re.escape(prefix)}{re.escape(day)}-(\d+)", text)]
        return max(used, default=0)

    # ── writing: append-only, and only into a table that is already there ──

    def append(self, rel: str, block: str) -> bool:
        """Append a block at the end of a memory file (its schema's `append-only` mode). Nothing is edited."""
        p = self.path(rel)
        if p is None or not p.is_file():
            return False
        text = p.read_text(encoding="utf-8", errors="replace")
        joiner = "" if text.endswith("\n\n") else ("\n" if text.endswith("\n") else "\n\n")
        p.write_text(text + joiner + block.rstrip("\n") + "\n", encoding="utf-8")
        return True

    def add_rows(self, rel: str, section: str, rows: list[str]) -> bool:
        """Add table rows at the end of `section`'s table. False when that table is not there to add to."""
        p = self.path(rel)
        if p is None or not p.is_file() or not rows:
            return False
        lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
        start = next((i for i, line in enumerate(lines) if line.strip() == section.strip()), None)
        if start is None:
            return False
        end = next((i for i in range(start + 1, len(lines)) if lines[i].startswith("## ")), len(lines))
        # The section's last table row — skipping the file's own `<!-- -->` template comment, whose
        # example rows are a shape to copy, not rows to append after.
        last, in_comment = None, False
        for i in range(start, end):
            line = lines[i]
            if in_comment or line.lstrip().startswith("<!--"):
                in_comment = "-->" not in line
                continue
            if _ROW.match(line):
                last = i
        if last is None:
            return False
        lines[last + 1:last + 1] = rows
        p.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return True

