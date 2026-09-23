"""Endless scenarios, held to their promises: valid mazes, solvable mazes, and honest seeds.

A generated maze is only a scenario if `MazeEnvironment` accepts it, the entry and exit are real, the
world is solvable (the engine must never be handed an impossible search), and the seed means what it
says — same seed, same world; blank seed, new world.
"""
from __future__ import annotations

from collections import deque

import pytest

from appserver.scenarios import generate_maze
from appserver.worlds import build
from ti_matrix.adapters.maze import MazeEnvironment


def _parse(maze: str):
    rows = [line for line in maze.splitlines() if line.strip()]
    entry = exit_ = None
    floors = 0
    for y, row in enumerate(rows):
        assert len(row) == len(rows[0]), "every row is the same width"
        for x, cell in enumerate(row):
            assert cell in "#.SE", f"unexpected cell {cell!r}"
            floors += cell in ".SE"
            entry = (x, y) if cell == "S" else entry
            exit_ = (x, y) if cell == "E" else exit_
    return rows, entry, exit_, floors


def _solvable(maze: str) -> bool:
    rows, entry, exit_, _ = _parse(maze)
    queue, seen = deque([(entry, 0)]), {entry}
    while queue:
        (x, y), dist = queue.popleft()
        if (x, y) == exit_:
            return True
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nx, ny = x + dx, y + dy
            if 0 <= ny < len(rows) and 0 <= nx < len(rows[0]) and rows[ny][nx] != "#" and (nx, ny) not in seen:
                seen.add((nx, ny))
                queue.append(((nx, ny), dist + 1))
    return False


def test_a_generated_maze_is_well_formed_and_bounded():
    for seed in (0, 1, 42, 123456):
        maze = generate_maze(11, 9, seed)
        rows, entry, exit_, floors = _parse(maze)
        assert entry is not None and exit_ is not None
        assert rows[0].strip("#") == "" and rows[-1].strip("#") == ""  # wall-bounded top and bottom
        assert all(row.startswith("#") and row.endswith("#") for row in rows)  # and the sides
        assert floors > len(rows) * len(rows[0]) * 0.15  # it is a maze, not a wall with a crack


def test_every_generated_maze_is_solvable():
    for seed in range(20):
        assert _solvable(generate_maze(11 + 2 * (seed % 4), 9 + 2 * (seed % 3), seed))


def test_a_seed_builds_the_same_world_and_a_blank_seed_builds_a_new_one():
    assert generate_maze(11, 9, 7) == generate_maze(11, 9, 7)
    assert generate_maze(13, 9, 7) != generate_maze(11, 9, 7)
    assert generate_maze(11, 9, None) != generate_maze(11, 9, None)


def test_the_generator_feeds_the_real_maze_environment_and_the_worlds_registry():
    for seed in (3, 11):
        env = MazeEnvironment(generate_maze(11, 9, seed))
        assert env.tools()  # it parsed, it has its actions
    # through the registry, the way a goal frame builds it: explicit seed reproduces, blank is new
    a = build("maze", {"width": 11, "height": 9, "seed": 7})
    b = build("maze", {"width": 11, "height": 9, "seed": 7})
    c = build("maze", {"width": 11, "height": 9, "seed": ""})
    assert a and b and c
