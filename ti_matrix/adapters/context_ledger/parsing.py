"""Reading the vault's markdown: the shapes its schema defines, as data.

Every memory file is markdown with an HTML-comment template at the top and entries below it. Three rules from
the vault's own tooling shape these parsers, and upstream the first two were real bugs before they were rules:

  - a value mentioned only inside a `<!-- -->` template comment is a PLACEHOLDER, not data, so comments come
    out before anything is parsed;
  - these files are overwrite-or-update-in-place, so the LAST `- **Key:** value` in one entry is the current
    one (`ledger-state`'s `field()` semantics);
  - one bullet may carry several fields — the session registry packs Agent, Model, Platform and Core onto a
    single line separated by `|` — so a field's value ends at the next label on the line, not at its end.

Nothing here touches a file: these are functions over text, which is what lets the formats be tested alone.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)
_BULLET = re.compile(r"^[ \t]*[-*][ \t]+")
_LABEL = re.compile(r"\*\*(?P<key>[^*:]+):\*\*")
_ROW = re.compile(r"^[ \t]*\|(?P<cells>.*\|)[ \t]*$")
_TABLE_SEP = re.compile(r"^[ \t]*\|[-: |]+\|[ \t]*$")
_HEADING = re.compile(r"^(?P<hashes>#{1,6})[ \t]+(?P<text>.*)$")
_ADR = re.compile(r"^ADR-(?P<number>\d+):[ \t]*(?P<title>.*?)[ \t]*\((?P<date>\d{4}-\d{2}-\d{2})\)[ \t]*$")
_DATED = re.compile(r"^(?P<date>\d{4}-\d{2}-\d{2})[ \t]*—[ \t]*(?P<who>.*?)[ \t]*$")
_CODENAME = re.compile(r"^S\d+$")
_BLANK_RUN = re.compile(r"\n{3,}")


def _strip_comments(text: str) -> str:
    """Out with the template comments, and with the blank runs they leave behind (kept text stays put)."""
    return _BLANK_RUN.sub("\n\n", _COMMENT.sub("", text))


def _one_line(text: str) -> str:
    return " ".join(text.split())


def _clip(text: str, limit: int) -> str:
    text = _one_line(text)
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _fields(body: str) -> dict[str, str]:
    """Every `- **Key:** value` in an entry, last occurrence winning (these files are update-in-place).

    One line may carry several fields — the session registry packs Agent, Model, Platform and Core onto
    one bullet separated by `|` — so a field's value runs to the next `**Label:**` on the line, not to
    the end of it.
    """
    out: dict[str, str] = {}
    for line in body.splitlines():
        if not _BULLET.match(line):
            continue
        marks = list(_LABEL.finditer(line))
        for i, m in enumerate(marks):
            end = marks[i + 1].start() if i + 1 < len(marks) else len(line)
            out[_one_line(m.group("key"))] = line[m.end():end].strip().rstrip("|").strip()
    return out


def _sections(text: str, levels: tuple[int, ...] = (2,)) -> list[tuple[str, str]]:
    """Split markdown into (heading text, body) at the given heading levels.

    Two levels, because the files nest them: `tasks/backlog.md` groups its priority tables as
    `## Open Items` → `### High Priority`, so the row that says what a table *means* is one level down
    from the heading that owns the file's structure. Pass comment-stripped text.
    """
    out: list[tuple[str, str]] = []
    heading, body = "", []
    for line in text.splitlines():
        m = _HEADING.match(line)
        if m and len(m.group("hashes")) in levels:
            if heading or body:
                out.append((heading, "\n".join(body).strip()))
            heading, body = m.group("text").strip(), []
        else:
            body.append(line)
    if heading or body:
        out.append((heading, "\n".join(body).strip()))
    return out


def _table_rows(body: str) -> list[list[str]]:
    """The data rows of a markdown table's cells (header and separator dropped)."""
    rows: list[list[str]] = []
    for line in body.splitlines():
        m = _ROW.match(line)
        if not m or _TABLE_SEP.match(line):
            continue
        cells = [c.strip() for c in m.group("cells").split("|")]
        if cells and cells[-1] == "":
            cells.pop()
        rows.append(cells)
    return rows[1:] if rows else []  # every table in this schema is written with a header row


@dataclass(frozen=True)
class Row:
    """A queue row: a backlog item (`B-` id) or a parked finding (`P-` id)."""

    ident: str
    summary: str
    section: str


@dataclass(frozen=True)
class Decision:
    number: str
    title: str
    date: str
    status: str
    body: str


@dataclass(frozen=True)
class LogEntry:
    date: str
    who: str
    fields: dict[str, str]

    def get(self, key: str) -> str:
        return self.fields.get(key, "")


@dataclass(frozen=True)
class SessionEntry:
    heading: str
    date: str
    who: str
    fields: dict[str, str]

    def get(self, key: str) -> str:
        return self.fields.get(key, "")


@dataclass(frozen=True)
class RosterRow:
    name: str
    codename: str
    model: str
    doing: str
    status: str
    detail: str
