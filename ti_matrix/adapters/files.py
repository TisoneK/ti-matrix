"""A read-only filesystem environment — the engine driving something that is not an application at all.

This is adapter #2, and its job is to keep adapter #1 honest: it imports nothing from any host, uses only the
standard library, and needs no server, no settings file and no credentials. If the engine ever acquires an
accidental dependency on the application it first ran inside, this adapter stops working.

    python -m ti_matrix.adapters.files_cli --base-url <url> --model <name> "<goal>"
"""
from __future__ import annotations

import datetime
from pathlib import Path
from typing import Optional

from ti_matrix.protocols import Action, ActionSpec, Observation

_OBS_MAX_CHARS = 3000
_MAX_ENTRIES = 200

FILES_ACTIONS: dict[str, ActionSpec] = {
    s.name: s
    for s in (
        ActionSpec("list_dir", "List the entries in a directory.", '{"path": "<dir>"}'),
        ActionSpec("read_file", "Read the text of one file.", '{"path": "<file>"}'),
        ActionSpec("stat_path", "Facts about a path: exists, kind, size, modified.", '{"path": "<path>"}'),
        ActionSpec("find_files", "Find files whose NAME contains a substring, under a directory.",
                   '{"path": "<dir>", "contains": "<substring>"}'),
    )
}


def _display(p: Path) -> str:
    return str(p)


class FilesEnvironment:
    """Every action reads. Nothing here can change a filesystem."""

    name = "files"

    def __init__(self, actions: Optional[dict[str, ActionSpec]] = None) -> None:
        self._actions = actions if actions is not None else FILES_ACTIONS

    def tools(self) -> dict[str, ActionSpec]:
        return self._actions

    def is_read_only(self, action: Action) -> Optional[bool]:
        spec = self._actions.get(action.tool)
        return None if spec is None else spec.read_only

    async def probe(self, action: Action) -> Observation:
        try:
            return Observation(action, *getattr(self, f"_{action.tool}")(**action.args))
        except TypeError as exc:  # wrong or missing arguments — a failure the search can use
            return Observation(action, False, f"bad arguments for {action.tool}: {exc}")
        except Exception as exc:  # noqa: BLE001 — a failed probe is an observation, never a crash
            return Observation(action, False, f"{type(exc).__name__}: {exc}"[:400])

    # ── the actions ──
    @staticmethod
    def _read_text(p: Path) -> str:
        text = p.read_text(encoding="utf-8", errors="replace")
        return text[:_OBS_MAX_CHARS] + ("\n… (truncated)" if len(text) > _OBS_MAX_CHARS else "")

    def _list_dir(self, path: str) -> tuple[bool, str]:
        d = Path(path).expanduser()
        if not d.is_dir():
            return False, f"not a directory: {_display(d)}"
        entries = sorted(d.iterdir(), key=lambda e: (e.is_file(), e.name.lower()))
        shown = [
            f"{'📄' if e.is_file() else '📁'} {e.name}" + (f" ({e.stat().st_size} B)" if e.is_file() else "")
            for e in entries[:_MAX_ENTRIES]
        ]
        more = f" … (+{len(entries) - _MAX_ENTRIES} more)" if len(entries) > _MAX_ENTRIES else ""
        return True, f"Contents of {_display(d)} — {len(entries)} entries: " + " · ".join(shown) + more

    def _read_file(self, path: str) -> tuple[bool, str]:
        p = Path(path).expanduser()
        if not p.is_file():
            return False, f"not a file: {_display(p)}"
        return True, self._read_text(p)

    def _stat_path(self, path: str) -> tuple[bool, str]:
        p = Path(path).expanduser()
        if not p.exists():
            return False, f"does not exist: {_display(p)}"
        st = p.stat()
        kind = "dir" if p.is_dir() else "file"
        when = datetime.datetime.fromtimestamp(st.st_mtime)
        return True, f"{_display(p)} — {kind}, {st.st_size} bytes, modified {when:%Y-%m-%d %H:%M}"

    def _find_files(self, path: str, contains: str) -> tuple[bool, str]:
        root = Path(path).expanduser()
        if not root.is_dir():
            return False, f"not a directory: {_display(root)}"
        needle = contains.lower()
        hits = [p for p in root.rglob("*") if p.is_file() and needle in p.name.lower()]
        if not hits:
            searched = len(list(root.rglob("*")))
            return True, f"no file under {_display(root)} has {contains!r} in its name ({searched} paths searched)"
        names = " · ".join(_display(p) for p in hits[:40])
        return True, f"{len(hits)} file(s) under {_display(root)} with {contains!r} in the name: {names}"
