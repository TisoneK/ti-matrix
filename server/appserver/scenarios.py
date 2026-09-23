"""Endless scenarios: seeded procedural worlds for the engine to search.

The maze is the one world that makes the engine search — and a fixed map is a world a model can learn
by heart. A scenario generator answers that: every run can enter a maze it has never seen, and a seed
makes "never seen" reproducible — the same seed builds the same world, so a run can be repeated,
compared, and audited like any other experiment.

The generator is a recursive backtracker over a grid of cells, iteratively (no recursion limit on big
boards): knock walls between neighbors until every cell is reachable, carve the entry at the
top-left floor and the exit at the farthest floor from it (BFS), then render the exact grid-string
`MazeEnvironment` parses — `#` walls, `.` floor, `S` entry, `E` exit, every row wall-bounded. A
generated maze is guaranteed solvable because the carve makes every cell reachable and the exit is a
real floor cell on the carved grid.
"""
from __future__ import annotations

import random
from collections import deque
from typing import Optional


def generate_maze(width: int = 11, height: int = 9, seed: Optional[int] = None) -> str:
    """A new maze in the adapter's own string format — never seen, or seen again given the seed."""
    rng = random.Random(seed)
    width, height = max(3, int(width)), max(3, int(height))
    # Only odd dimensions: every floor cell sits on an odd (x, y), and walls fall between them.
    if width % 2 == 0:
        width += 1
    if height % 2 == 0:
        height += 1

    grid = [["#"] * width for _ in range(height)]

    def carve(x: int, y: int) -> None:
        grid[y][x] = "."

    def neighbors(x: int, y: int):
        for dx, dy in ((2, 0), (-2, 0), (0, 2), (0, -2)):
            nx, ny = x + dx, y + dy
            if 0 < nx < width - 1 and 0 < ny < height - 1:
                yield nx, ny, x + dx // 2, y + dy // 2

    # Iterative recursive backtracker: start at the top-left odd cell, knock a path to a random
    # unvisited odd neighbor (removing the wall between), and backtrack on a dead end.
    start = (1, 1)
    carve(*start)
    stack = [start]
    visited = {start}
    while stack:
        x, y = stack[-1]
        options = [(nx, ny, wx, wy) for nx, ny, wx, wy in neighbors(x, y) if (nx, ny) not in visited]
        if not options:
            stack.pop()
            continue
        nx, ny, wx, wy = rng.choice(options)
        carve(wx, wy)
        carve(nx, ny)
        visited.add((nx, ny))
        stack.append((nx, ny))

    floors = [(x, y) for y in range(height) for x in range(width) if grid[y][x] == "."]
    entry = min(floors, key=lambda c: (c[1], c[0]))  # top-left floor cell

    def bfs_distance(src) -> dict:
        dist = {src: 0}
        queue = deque([src])
        while queue:
            x, y = queue.popleft()
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                nx, ny = x + dx, y + dy
                if 0 <= nx < width and 0 <= ny < height and grid[ny][nx] == "." and (nx, ny) not in dist:
                    dist[(nx, ny)] = dist[(x, y)] + 1
                    queue.append((nx, ny))
        return dist

    dist = bfs_distance(entry)
    exit_cell = max(dist, key=lambda c: (dist[c], -c[1], -c[0]))  # the farthest floor from the entry
    grid[entry[1]][entry[0]] = "S"
    grid[exit_cell[1]][exit_cell[0]] = "E"
    return "\n".join("".join(row) for row in grid)
