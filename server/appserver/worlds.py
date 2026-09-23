"""The worlds a run can be driven against — declared as data, built on demand.

A world is what the playgrounds render a form for: a few config fields and the `Environment` those
fields build. Fields are plain dicts (same shape as the playgrounds' `SHARED_FIELDS`), so the renderer
draws them generically and a new world is one `World` row, not app work.

`browser` is in the registry like the rest, but it is the one world that changes the machine's world
(it starts a real Chrome), so the server refuses to build it unless the app asked for writes to be
possible at all — `build(..., allow_writes=False)` is the default, and the confirmer still asks about
every individual action on top of it.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Optional

from ti_matrix.protocols import Action, Observation

from ti_matrix.adapters.context_ledger import LedgerEnvironment
from ti_matrix.adapters.files import FilesEnvironment
from ti_matrix.adapters.maze import MazeEnvironment


@dataclass(frozen=True)
class World:
    name: str
    title: str
    note: str
    fields: tuple[dict[str, Any], ...]
    factory: Callable[[dict[str, Any]], Any]


class RootedFiles(FilesEnvironment):
    """The files world, confined to one root — examples/files_ui.py's guard, carried into the app.

    `FilesEnvironment` takes whatever path it is handed; a host decides where its world begins. A
    relative path resolves under ``root`` and an absolute path that lands outside it is refused as a
    failed probe — information the search can use, never a crash.
    """

    name = "files"

    def __init__(self, root: str) -> None:
        super().__init__()
        self.root = Path(root).expanduser().resolve()

    def _inside(self, raw: Any) -> Optional[Path]:
        if not isinstance(raw, str) or not raw.strip():
            return None
        candidate = Path(raw).expanduser()
        resolved = (candidate if candidate.is_absolute() else self.root / candidate).resolve()
        return resolved if resolved == self.root or self.root in resolved.parents else None

    async def probe(self, action: Action) -> Observation:
        if "path" not in action.args:
            return await super().probe(action)  # a bad-arguments failure the engine can use
        asked = action.args["path"]
        safe = self._inside(asked)
        if safe is None:
            return Observation(action, False, f"refused: {asked!r} is not a path inside {self.root}")
        rooted = Action(action.tool, {**action.args, "path": str(safe)}, action.why)
        obs = await super().probe(rooted)
        # The answer belongs to the action the engine proposed, not to the path we rewrote it to.
        return Observation(action, obs.ok, obs.text, obs.predicted)


# ── the factories ───────────────────────────────────────────────────────────


def _maze_world(config: dict[str, Any]) -> MazeEnvironment:
    # Endless scenarios: a blank seed generates a brand-new maze every run; an integer seed builds
    # the same maze again — reproducible, comparable, auditable. No numbers at all: the classic map.
    from .scenarios import generate_maze

    width, height = config.get("width"), config.get("height")
    seed = config.get("seed")
    if width or height or seed not in (None, ""):
        seed_i = int(seed) if str(seed).strip() not in ("", "None") else None
        return MazeEnvironment(generate_maze(int(width or 11), int(height or 9), seed_i))
    return MazeEnvironment()


def _files_world(config: dict[str, Any]) -> RootedFiles:
    root = str(config.get("root", "")).strip()
    if not root:
        raise ValueError("the files world needs a root directory")
    return RootedFiles(root)


def _ledger_world(config: dict[str, Any]) -> LedgerEnvironment:
    project = str(config.get("project", "")).strip()
    if not project:
        raise ValueError("the ledger world needs a project directory")
    return LedgerEnvironment(project)


def _browser_world(config: dict[str, Any]) -> Any:
    from ti_matrix.adapters.browser import BrowserEnvironment

    url = str(config.get("url", "")).strip() or None
    # headless=False on purpose: a person is watching, and the app's confirmer dialogs pair with it.
    return BrowserEnvironment(url, headless=bool(config.get("headless", False)))


# ── the registry — the whole list of what v1 can drive ──────────────────────

WORLDS: dict[str, World] = {
    w.name: w
    for w in (
        World("maze", "The maze",
              "A hidden maze the engine must search. A blank seed means a brand-new maze every run; "
              "give the seed a number to run the same maze again.",
              ({"name": "width", "label": "Width (cells)", "default": 11},
               {"name": "height", "label": "Height (cells)", "default": 9},
               {"name": "seed", "label": "Seed (blank = new world every run)", "default": ""}),
              _maze_world),
        World("files", "Local files",
              "Every action reads. Paths resolve under the root; one that escapes it is refused.",
              ({"name": "root", "label": "Read files under", "default": "", "placeholder": "C:\\path\\or\\/home/you/code"},),
              _files_world),
        World("ledger", "Context Ledger",
              "A project's memory, read as an environment. Write-back happens only when you ask for it.",
              ({"name": "project", "label": "Project directory (holding .context_ledger/)",
                "default": "", "placeholder": "C:\\path\\to\\project"},
               {"name": "write_back", "label": "Write the run's findings back into the vault",
                "default": False, "kind": "checkbox"}),
              _ledger_world),
        World("browser", "Real browser",
              "A real Chrome at the URL you name. Clicks and typing are asked before they happen.",
              ({"name": "url", "label": "Start URL", "default": "", "placeholder": "https://example.com"},
               {"name": "headless", "label": "Run Chrome headless (no window)", "default": False, "kind": "checkbox"},),
              _browser_world),
    )
}


def describe() -> list[dict[str, Any]]:
    """The registry as the app's world selector wants it: name, title, note, fields."""
    return [{"name": w.name, "title": w.title, "note": w.note, "fields": list(w.fields)}
            for w in WORLDS.values()]


def build(name: str, config: dict[str, Any]) -> Any:
    """One world, built from its config. Unknown names and bad configs raise ValueError to report."""
    w = WORLDS.get(name)
    if w is None:
        raise ValueError(f"no world named {name!r} — the known ones: {', '.join(WORLDS)}")
    return w.factory(dict(config))
