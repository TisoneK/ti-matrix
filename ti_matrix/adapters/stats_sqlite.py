"""The engine's record in a real database — for when it stops being a small file.

``stats_file`` keeps the record in one JSON document, and that is the right shape for a single writer: you can
read it, diff it, and hand it to someone. It has three limits that a record of this kind eventually reaches:
every save rewrites every byte, two runs that save at once lose one another's learning, and nothing can be
asked of it without loading all of it.

SQLite is the standard answer to all three, and ``sqlite3`` is in the standard library — so this stays true to
the project's no-runtime-dependencies rule, and a host still passes the path in rather than the engine
discovering one.

Two ways to write, and the difference is the whole reason to prefer this store:

    save(record)   replace what is stored with this record — one writer, the whole picture
    add(record)    ADD these counters to what is stored

``add`` is the one to reach for when runs can overlap. Two processes that each ran a goal and each add their
own increments both keep their learning, where a JSON file's last writer wins. It expects *increments* — feed
it a ``Statistics`` built from one run's events — because adding the same totals twice counts them twice, and
nothing here can tell the difference.

What this store is deliberately not: a place for a project's memory. A ``.context_ledger/`` vault stays
markdown, because that memory has to be read by people, diffed in a pull request, and merged across machines
and agents — and a binary file does none of those. The two have nothing in common but the word "store": this
one holds counters, which nothing reviews and only this engine reads.
"""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from ti_matrix.learning.statistics import ActionRecord, Statistics

# The counter columns, in one place: the schema, the insert and the add-statement all have to agree, and a
# drift between them would silently stop recording something.
_COUNTERS = ("probes", "failures", "selections", "progress", "scored", "ms", "chars", "predicted")

_SCHEMA = f"""
CREATE TABLE IF NOT EXISTS tools (
    tool TEXT PRIMARY KEY,
    {', '.join(f'{c} {"REAL" if c == "progress" else "INTEGER"} NOT NULL DEFAULT 0' for c in _COUNTERS)}
);
CREATE TABLE IF NOT EXISTS actions (
    fingerprint TEXT PRIMARY KEY,
    tool TEXT NOT NULL DEFAULT '',
    {', '.join(f'{c} {"REAL" if c == "progress" else "INTEGER"} NOT NULL DEFAULT 0' for c in _COUNTERS)}
);
CREATE TABLE IF NOT EXISTS facts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fact TEXT NOT NULL UNIQUE
);
"""


_TOOL_COLUMNS = ("tool", *_COUNTERS)
_ACTION_COLUMNS = ("fingerprint", "tool", *_COUNTERS)


def _upsert(table: str, key: str, columns: tuple[str, ...], *, accumulate: bool) -> str:
    """Insert or update one row from `columns`, which the caller's rows must match exactly.

    Counters either replace or add, depending on the mode. A text column is never added to: it takes what the
    new row offers, unless that is empty — a fingerprint first seen before a candidates event listed it has no
    tool name, and a later write that knows it should be able to say so without erasing it back to nothing.
    """
    sets = []
    for column in columns:
        if column == key:
            continue
        if column in _COUNTERS:
            sets.append(f"{column} = {column} + excluded.{column}" if accumulate
                        else f"{column} = excluded.{column}")
        else:
            sets.append(f"{column} = COALESCE(NULLIF(excluded.{column}, ''), {column})")
    placeholders = ", ".join("?" * len(columns))
    return (f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({placeholders}) "
            f"ON CONFLICT({key}) DO UPDATE SET {', '.join(sets)}")


def _escape(text: str) -> str:
    """A `LIKE` pattern with the caller's text taken literally (backslash-escaped for ESCAPE '\\')."""
    return "%" + text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"


class SqliteStore:
    """The engine's accumulated record, in SQLite, addable by more than one writer.

    The JSON store is two functions because a file is not a resource. A connection is, so this is a class:
    use it as a context manager, or call :meth:`close`. Two side files (``-wal``, ``-shm``) appear beside the
    database while it is open — SQLite's write-ahead log, not something this adapter adds.
    """

    def __init__(self, path: str | Path, *, timeout_s: float = 5.0) -> None:
        self.path = Path(path).expanduser()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.path, timeout=timeout_s, isolation_level=None)
        try:
            self._conn.execute("PRAGMA journal_mode=WAL")  # a reader never blocks a writer
            self._conn.executescript(_SCHEMA)
        except sqlite3.Error as exc:  # not a database, or not one this version understands
            self._conn.close()
            raise sqlite3.DatabaseError(
                f"{self.path} is not a usable SQLite database for this record: {exc}") from exc

    def __enter__(self) -> "SqliteStore":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def close(self) -> None:
        self._conn.close()

    @contextmanager
    def _transaction(self, *, write: bool) -> Iterator[sqlite3.Connection]:
        """One transaction, taking the write lock up front so concurrent `add`s queue instead of failing."""
        self._conn.execute("BEGIN IMMEDIATE" if write else "BEGIN")
        try:
            yield self._conn
            self._conn.execute("COMMIT")
        except Exception:
            self._conn.execute("ROLLBACK")
            raise

    # ── reading and writing the record ──

    def load(self) -> Statistics:
        with self._transaction(write=False) as conn:
            stats = Statistics()
            for row in conn.execute(f"SELECT {', '.join(_TOOL_COLUMNS)} FROM tools"):
                record = ActionRecord.from_dict(dict(zip(_TOOL_COLUMNS, row)))
                stats.by_tool[record.tool] = record
            for row in conn.execute(f"SELECT {', '.join(_ACTION_COLUMNS)} FROM actions"):
                values = dict(zip(_ACTION_COLUMNS, row))
                stats.by_fingerprint[str(values["fingerprint"])] = ActionRecord.from_dict(values)
            stats.add_facts([r[0] for r in conn.execute("SELECT fact FROM facts ORDER BY id")])
        return stats

    def save(self, statistics: Statistics) -> None:
        """Replace what is stored with this record. Use ``add`` instead if anything else may write too."""
        self._write(statistics, accumulate=False)

    def add(self, statistics: Statistics) -> None:
        """Add these counters to what is stored. Pass one run's increments, never a running total."""
        self._write(statistics, accumulate=True)

    def _write(self, statistics: Statistics, *, accumulate: bool) -> None:
        tool_sql = _upsert("tools", "tool", _TOOL_COLUMNS, accumulate=accumulate)
        action_sql = _upsert("actions", "fingerprint", _ACTION_COLUMNS, accumulate=accumulate)
        with self._transaction(write=True) as conn:
            conn.executemany(tool_sql, [(r.tool, *(getattr(r, c) for c in _COUNTERS))
                                        for r in statistics.by_tool.values()])
            conn.executemany(action_sql, [(fp, r.tool, *(getattr(r, c) for c in _COUNTERS))
                                          for fp, r in statistics.by_fingerprint.items()])
            # Facts are append-only and deduplicated by the schema, so a repeat costs nothing.
            conn.executemany("INSERT OR IGNORE INTO facts (fact) VALUES (?)",
                             [(f,) for f in statistics.facts])

    # ── questions SQL answers without loading everything ──

    def search_facts(self, text: str, *, limit: int = 10) -> list[str]:
        """Facts containing ``text``, newest last — the query a host would otherwise scan a list for."""
        if not str(text).strip():
            return []
        with self._transaction(write=False) as conn:
            rows = conn.execute(
                "SELECT fact FROM facts WHERE fact LIKE ? ESCAPE '\\' ORDER BY id DESC LIMIT ?",
                (_escape(str(text)), max(1, limit))).fetchall()
        return [r[0] for r in rows][::-1]

    def top_tools(self, *, limit: int = 5) -> list[ActionRecord]:
        """The tools that have done the most work here, most chosen first."""
        with self._transaction(write=False) as conn:
            rows = conn.execute(f"SELECT {', '.join(_TOOL_COLUMNS)} FROM tools "
                                f"WHERE probes > 0 ORDER BY selections DESC, probes DESC LIMIT ?",
                                (max(1, limit),)).fetchall()
        return [ActionRecord.from_dict(dict(zip(_TOOL_COLUMNS, row))) for row in rows]

    def counts(self) -> dict[str, int]:
        """How much is stored, without reading any of it into Python."""
        with self._transaction(write=False) as conn:
            return {table: conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                    for table in ("tools", "actions", "facts")}


__all__ = ["SqliteStore"]
