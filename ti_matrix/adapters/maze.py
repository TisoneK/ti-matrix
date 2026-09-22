"""A hidden maze as an Environment — the first world here that makes the engine search.

Every other shipped world is shallow. A filesystem goal is answered in a probe or two, a ledger goal is a
handful of reads, the browser reads a page. None of them needs a second route and none has ever made the
engine retreat, so the beam and the backtrack have only ever been exercised against scripted problems. A
maze needs both, and it needs no new mechanism: positions, corridors, dead ends, an exit and routes that
meet at the same junction are already `AgentState`, `Action`, `backtrack`, `done` and `EngineBudget`.

A maze is written the way a person draws one:

    MazeEnvironment('''
        #########
        #S..#...#
        #.#.#.#.#
        #.#...#.#
        #.#####.#
        #.......#
        #E##.##.#
        #########
    ''')

`#` is wall, `.` is floor, `S` is where a run enters, `E` is the exit. **A run is never shown the map.**

Four actions, all read-only. Walking is a read for the same reason the browser's `goto` is one: it changes
what the run can see, not the world it is looking at. The walls never move.

The one thing this world remembers is which cells have been *entered*, and it is monotonic on purpose. A fan
is probed all at once, so anything a probe could clobber would come back wrong — a `goto` sharing a fan has
exactly that problem. A set that only ever grows cannot be clobbered by a sibling probe. And growing it on a
probe nobody selected is not a leak: the engine's own rule is that a real observation from an unselected
probe is still a fact (`AgentState.learn`), so the world and the engine agree about what is known.
"""
from __future__ import annotations

from typing import Any, Optional, Union

from ti_matrix.protocols import Action, ActionSpec, Observation

WALL = "#"
_FLOOR, _ENTRY, _EXIT = ".", "S", "E"
# north is up: y grows downward, the way the map is written
STEPS: dict[str, tuple[int, int]] = {"north": (0, -1), "south": (0, 1), "east": (1, 0), "west": (-1, 0)}

DEFAULT_MAZE = """
#########
#S..#...#
#.#.#.#.#
#.#...#.#
#.#####.#
#.......#
#E##.##.#
#########
"""

MAZE_ACTIONS: dict[str, ActionSpec] = {
    s.name: s for s in (
        ActionSpec("grid", "The maze's size and how many cells it holds. No walls.", "{}"),
        ActionSpec("entry", "The cell a run enters at, and which ways are open from it.", "{}"),
        ActionSpec("look", "What is open from a cell you have entered, and whether it is the exit.",
                   '{"cell": "<x,y>"}'),
        ActionSpec("step", "Walk from a cell through one of its openings; the far side becomes known.",
                   '{"cell": "<x,y>", "direction": "north|south|east|west"}'),
    )
}


class MazeEnvironment:
    """A maze a run can only learn by walking it. Every action reads; nothing here changes the maze."""

    name = "maze"

    def __init__(self, maze: Union[str, list[str]] = DEFAULT_MAZE) -> None:
        rows = [line for line in (maze.splitlines() if isinstance(maze, str) else list(maze)) if line.strip()]
        if not rows:
            raise ValueError("a maze needs at least one row")
        width = max(len(r) for r in rows)
        self._rows = [r.ljust(width, WALL) for r in rows]
        self._width, self._height = width, len(rows)
        # Named _start/_exit_at rather than _entry/_exit: an action method is called as `_<tool>`, so a data
        # attribute of the same name would shadow it.
        self._start = self._find(_ENTRY, "no 'S' — a maze needs somewhere for a run to enter")
        self._exit_at = self._find(_EXIT, "no 'E' — a maze needs an exit to find")
        self._seen: set[tuple[int, int]] = {self._start}

    # ── the map ──

    def _find(self, mark: str, complaint: str) -> tuple[int, int]:
        for y, row in enumerate(self._rows):
            x = row.find(mark)
            if x != -1:
                return (x, y)
        raise ValueError(complaint)

    def _open(self, x: int, y: int) -> bool:
        return 0 <= x < self._width and 0 <= y < self._height and self._rows[y][x] != WALL

    def _openings(self, x: int, y: int) -> list[str]:
        return [d for d, (dx, dy) in STEPS.items() if self._open(x + dx, y + dy)]

    def _floors(self) -> int:
        return sum(1 for row in self._rows for ch in row if ch != WALL)

    @staticmethod
    def _label(cell: tuple[int, int]) -> str:
        return f"{cell[0]},{cell[1]}"

    def _describe(self, cell: tuple[int, int]) -> str:
        ways = ", ".join(self._openings(*cell)) or "nothing — this cell is sealed"
        where = " · THIS IS THE EXIT" if cell == self._exit_at else ""
        return f"cell {self._label(cell)} — open: {ways}{where}"

    def _cell(self, text: Any) -> Optional[tuple[int, int]]:
        parts = str(text).strip().replace(" ", "").split(",")
        if len(parts) != 2 or not all(p.lstrip("-").isdigit() for p in parts):
            return None
        x, y = (int(p) for p in parts)
        return (x, y) if self._open(x, y) else None

    # ── the Environment contract ──

    def tools(self) -> dict[str, ActionSpec]:
        return MAZE_ACTIONS

    def is_read_only(self, action: Action) -> Optional[bool]:
        spec = MAZE_ACTIONS.get(action.tool)
        return None if spec is None else spec.read_only

    async def probe(self, action: Action) -> Observation:
        try:
            return Observation(action, *getattr(self, f"_{action.tool}")(**action.args))
        except TypeError as exc:  # wrong or missing arguments — a failure the search can use
            return Observation(action, False, f"bad arguments for {action.tool}: {exc}")
        except Exception as exc:  # noqa: BLE001 — a failed probe is an observation, never a crash
            return Observation(action, False, f"{type(exc).__name__}: {exc}"[:400])

    # ── the actions ──

    def _grid(self) -> tuple[bool, str]:
        return True, (f"a {self._width}x{self._height} grid holding {self._floors()} cells; "
                      f"a run enters at {self._label(self._start)} and looks for the exit")

    def _entry(self) -> tuple[bool, str]:
        return True, self._describe(self._start)

    def _look(self, cell: Any = "") -> tuple[bool, str]:
        at = self._cell(cell)
        if at is None:
            return False, f"not a cell of this maze: {str(cell).strip()!r} — cells are written as <x,y>"
        if at not in self._seen:
            return False, (f"{self._label(at)} has not been entered — a run learns a cell by stepping into "
                           f"it, and this one has only been here: " +
                           ", ".join(sorted(self._label(c) for c in self._seen)))
        return True, self._describe(at)

    def _step(self, cell: Any = "", direction: Any = "") -> tuple[bool, str]:
        at = self._cell(cell)
        if at is None:
            return False, f"not a cell of this maze: {str(cell).strip()!r} — cells are written as <x,y>"
        if at not in self._seen:
            return False, f"{self._label(at)} has not been entered, so a run cannot walk out of it"
        way = str(direction).strip().lower()
        if way not in STEPS:
            return False, f"unknown direction {str(direction).strip()!r} — use one of: {', '.join(STEPS)}"
        dx, dy = STEPS[way]
        ahead = (at[0] + dx, at[1] + dy)
        if not self._open(*ahead):
            return False, f"a wall blocks {way} from {self._label(at)}"
        self._seen.add(ahead)  # the world and the engine agree: a room entered is a room known
        return True, f"from {self._label(at)} {way}: {self._describe(ahead)}"


__all__ = ["DEFAULT_MAZE", "MAZE_ACTIONS", "STEPS", "MazeEnvironment"]
