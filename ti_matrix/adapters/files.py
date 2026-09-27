"""A read-only filesystem environment — the engine driving something that is not an application at all.

This is adapter #2, and its job is to keep adapter #1 honest: it imports nothing from any host, uses only the
standard library, and needs no server, no settings file and no credentials. If the engine ever acquires an
accidental dependency on the application it first ran inside, this adapter stops working.

    python -m ti_matrix.adapters.files_cli --base-url <url> --model <name> "<goal>"
"""
from __future__ import annotations

import asyncio
import datetime
import time
from collections import deque
from pathlib import Path
from typing import Optional

from ti_matrix.protocols import Action, ActionSpec, Observation

_OBS_MAX_CHARS = 3000
_MAX_ENTRIES = 200
# A name search is the one action here that can run for minutes: it walks whatever tree it was pointed
# at, and the files world now begins at the home directory, so the tree is somebody's whole profile —
# caches, `AppData`, every `node_modules` they own. Three bounds, all reported rather than silent: how
# many entries may be looked at, how deep the walk goes, and how long it may run. They exist so that
# "nothing matched" and "I stopped looking" are different answers, which is the difference between an
# empty result a run can trust and one it cannot. Measured: unbounded, a search of a real home directory
# on Windows did not finish inside five minutes and left the window showing a run at 0% that had not
# stopped. The entry cap alone was not enough on its own: one large, slow-to-stat subtree can burn real
# wall-clock time without ever tripping a count, so the walk also carries its own clock.
_WALK_MAX_ENTRIES = 20_000
_WALK_MAX_DEPTH = 6
_WALK_MAX_MS = 2_500

# Directories that are somebody else's code or this machine's bookkeeping. A filesystem goal is almost
# never answered inside one, and they dwarf the real tree — searching this repo for "project" returns
# 412 files, nearly all of them under node_modules. Skipped at walk time, not just after: entering one
# is where the walk's own budget used to go to die — a search that dove into `~/Library` or
# `node_modules` could burn its entire entry cap there and never reach a real, shallow match sitting
# right beside it. `FilesReasoner` (ti_matrix.adapters.builtin) imports this rather than keeping its own
# copy — the walk and the reasoner agreeing on what "noise" means is the property that matters, and two
# separately-maintained lists is how that agreement quietly drifts.
_NOISE = frozenset("""node_modules .venv venv .git .hg .svn __pycache__ .pytest_cache .mypy_cache
dist build target out .next .cache .idea .vscode .tox site-packages vendor Pods .gradle""".split())


def is_noise(path: str) -> bool:
    """Whether a path runs through a directory whose contents are not this project's answer."""
    parts = path.split("/")
    return any(p in _NOISE or p.endswith(".egg-info") for p in parts)


def _is_noise_name(name: str) -> bool:
    """Whether one path component, on its own, names a directory the walk should never enter."""
    return name in _NOISE or name.endswith(".egg-info")


# A file named by convention, not by intent: a lockfile pins dependency versions, a manifest restates
# what the package manager already knows, a minified bundle is generated. Reading one is still fine as
# ordinary evidence, but it must never be mistaken for "the file the goal named" and settle a run on its
# own — a goal containing the word "package" is not, coincidentally, answered by `package-lock.json`.
_GENERATED_BASENAMES = frozenset("""
package-lock.json npm-shrinkwrap.json yarn.lock pnpm-lock.yaml
Cargo.lock poetry.lock Pipfile.lock composer.lock Gemfile.lock
""".split())
_GENERATED_SUFFIXES = (".min.js", ".min.css", ".lock", ".map")


def is_generated_artifact(path: str) -> bool:
    """Whether this path is a lockfile, manifest, or build artifact — named by convention, not intent."""
    name = path.rsplit("/", 1)[-1]
    return name in _GENERATED_BASENAMES or name.endswith(_GENERATED_SUFFIXES)

FILES_ACTIONS: dict[str, ActionSpec] = {
    s.name: s
    for s in (
        ActionSpec("list_dir", "List the entries in a directory.", '{"path": "<dir>"}'),
        ActionSpec("read_file", "Read the text of one file.", '{"path": "<file>"}'),
        ActionSpec("stat_path", "Facts about a path: exists, kind, size, modified.", '{"path": "<path>"}'),
        ActionSpec("find_files", "Find files or directories whose NAME contains a substring, under a "
                                 "directory. Bounded: it reports when it stopped before searching everything. "
                                 "A match is a candidate, not a verified answer — look at what it finds "
                                 "(list_dir/read_file/stat_path) before treating it as the goal.",
                   '{"path": "<dir>", "contains": "<substring>"}', surface_only=True),
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
        # Every probe runs on a worker thread rather than on the caller's event loop. A filesystem call
        # is the one thing here that can take real time — a directory listing on a slow disk, a read of a
        # big file, and above all a name search — and the caller awaits it on the loop it serves
        # everything else from. Run on the loop, one slow probe starves the whole host: the sidecar stops
        # answering, so a run cannot be stopped or even reported on while it happens, and the window shows
        # a live-looking run that will not move. These calls are read-only, so a thread costs one hop and
        # takes nothing else with it.
        return await asyncio.to_thread(self._probe_now, action)

    def _probe_now(self, action: Action) -> Observation:
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
        hits: list[Path] = []
        # One walk, not two, and bounded on three axes. The count this reports is the number of entries
        # actually looked at — which, when a bound bit, is *not* the size of the tree, and the line says
        # so rather than leaving a run to read a truncated answer as a whole one.
        #
        # Breadth-first, not depth-first: a stack-based walk fully explores whichever sibling sorts last
        # (LIFO pops the most recently pushed) before ever touching the others, so one large, irrelevant
        # subtree — a real one measured: macOS's own ~/Library — can spend the entire entry budget before
        # the walk ever reaches a shallow, directly relevant match sitting right beside it. A goal asking
        # to locate something wants the near candidates weighed first, not whichever the alphabet visits
        # deepest soonest; a queue does that for free, level by level.
        seen = 0
        stop_reason = ""  # "" | "entries" | "time"
        deadline = time.monotonic() + _WALK_MAX_MS / 1000.0
        queue: deque[tuple[Path, int]] = deque([(root, 0)])
        while queue:
            if time.monotonic() >= deadline:
                stop_reason = "time"
                break
            here, depth = queue.popleft()
            try:
                entries = sorted(here.iterdir(), key=lambda e: e.name.lower())
            except OSError:
                continue  # a directory that cannot be read is not a failed search
            for entry in entries:
                if _is_noise_name(entry.name):
                    # Somebody else's code or this machine's bookkeeping — never the answer, and never
                    # worth entering: this is where an unbounded walk used to spend its whole budget.
                    continue
                seen += 1
                if seen > _WALK_MAX_ENTRIES:
                    stop_reason = "entries"
                    break
                try:
                    if entry.is_symlink():
                        continue  # never followed — a cycle would starve the budget without ever finishing
                    named = needle in entry.name.lower()
                    if entry.is_dir():
                        # A directory can match, and until now it could not. The walk kept only files, so a
                        # goal naming a *folder* — "locate the X repo", "where is the config directory" —
                        # had no way to be answered by search at all: the folder sat in the tree, one level
                        # down, invisible to the one action that searches for anything. Found on a real run
                        # that answered with a runtime directory while the checkout the goal meant was a
                        # directory the search could never return.
                        if named:
                            hits.append(entry)
                        if depth < _WALK_MAX_DEPTH:
                            queue.append((entry, depth + 1))
                    elif entry.is_file() and named:
                        hits.append(entry)
                except OSError:
                    continue  # vanished, or unreadable: it cannot be reported either way
            if stop_reason:
                break
        # The stop is reported whether or not anything was found — a truncated search that happened to
        # find something is still a truncated search, and a reader who cannot tell the two apart reads a
        # partial answer as an exhaustive one. Measured: this is exactly the difference between "found 2"
        # and "found 2, but the walk gave up before it could look everywhere" for the same goal.
        if stop_reason == "entries":
            limit_note = f", stopped at the {_WALK_MAX_ENTRIES}-path limit — more may exist unseen"
        elif stop_reason == "time":
            limit_note = f", stopped after {_WALK_MAX_MS}ms — more may exist unseen"
        else:
            limit_note = ""
        if not hits:
            return True, f"no file or directory under {_display(root)} has {contains!r} in its name ({seen} paths searched{limit_note})"
        dirs = sum(1 for p in hits if p.is_dir())
        kinds = f"{dirs} director{'y' if dirs == 1 else 'ies'}, {len(hits) - dirs} file(s)"
        # A hit that is a directory carries a trailing separator, the same convention `list_dir` and the
        # tree already use — so which of these is a folder is readable without a second probe, and a goal
        # that asks for one can be told apart from a goal that asks for a file.
        names = " · ".join(_display(p) + ("/" if p.is_dir() else "") for p in hits[:40])
        return True, (f"{len(hits)} path(s) under {_display(root)} with {contains!r} in the name ({kinds}{limit_note}): "
                      f"{names}")
