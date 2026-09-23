"""The engine's two seats, filled by rules instead of a model.

This is an adapter, not engine core, and the boundary test is what says so: `MazeReasoner` knows the
maze's vocabulary — cells, openings, the exit — exactly as `MazeEnvironment` does, and the core is not
allowed to know any of that (the dependency runs adapter -> engine, never back). A reasoner that
understands one world is the same kind of thing as the world itself.

Why this exists. `LLMMoveProposer` and `LLMEvaluator` are the only things that have ever sat in the
proposer's and the evaluator's seats, so every run has needed an OpenAI-compatible endpoint, a model
name that actually resolves there, and twenty-odd seconds per decision. A viewer with none of those
gets a run that stops at its second event — one `state`, one `stopped: proposer_error` — and every
panel in the window correctly draws nothing, because there is genuinely nothing to draw. The search
is not what failed there; the seats were empty.

These fill them with rules. Nothing here talks to a network, so a run starts instantly and always
produces a real search — real probes against the real environment, real facts, real retreats, real
events in the same shapes `run_log` writes. What it is not is a model: it does not read a goal's
words, and it cannot generalise past the world it knows. `EngineBudget.max_model_calls` counts
consultations of these seats the same way it counts a model's, which is the engine's own rule (see
its docstring) — the number reported is what was counted, never a rule dressed up as a model.

Two reasoners:

`MazeReasoner` knows the maze world specifically. It rebuilds what the run has seen from the facts
the run itself collected — never from the maze, which it cannot see any more than a model can — and
walks the frontier nearest to where it stands. That is a genuine search: it meets dead ends, and it
retreats out of them through the engine's own backtracking.

`SurveyReasoner` is the fallback for every other world: try each action once, prefer what has not
been tried, and score by how much a probe actually returned. Shallow on purpose — it is a way to see
the machine move, not a claim to solve a filesystem.
"""
from __future__ import annotations

import re
from typing import Any, Optional, Sequence

from ti_matrix.protocols import Action, ActionSpec, Evaluation, Observation
from ti_matrix.state import AgentState

# north is up, as the maze writes itself; imported rather than re-guessed.
from ti_matrix.adapters.maze import STEPS

BUILTIN = "builtin"
"""The model name that selects these seats. Not a model id — the absence of one."""

Cell = tuple[int, int]

# `cell 3,5 — open: north, east · THIS IS THE EXIT` — the one shape the maze states a cell in.
_CELL = re.compile(r"cell (-?\d+),(-?\d+) — open: ([^·\n]*)(· THIS IS THE EXIT)?")
# `step(cell=1,1, direction=east)` as `Action.label` writes it, for reading the trail back.
_STEP = re.compile(r"step\(cell=(-?\d+),(-?\d+), direction=(\w+)\)")
_GRID = re.compile(r"grid holding (\d+) cells")


class MazeKnowledge:
    """What the run has established about the maze, rebuilt from its own facts.

    This is deliberately the same input a model gets — `state.facts` and `state.trail`, nothing else.
    A reasoner that peeked at `MazeEnvironment` would not be searching, it would be reciting.
    """

    def __init__(self, state: AgentState) -> None:
        self.open: dict[Cell, set[str]] = {}
        self.exit: Optional[Cell] = None
        self.total: Optional[int] = None
        for fact in state.facts:
            grid = _GRID.search(fact)
            if grid:
                self.total = int(grid.group(1))
            # A single `step` fact states the cell it arrived in; `look`/`entry` state the one asked for.
            for x, y, ways, is_exit in _CELL.findall(fact):
                cell = (int(x), int(y))
                open_ways = {w.strip() for w in ways.split(",") if w.strip() in STEPS}
                self.open.setdefault(cell, set()).update(open_ways)
                if is_exit:
                    self.exit = cell
        self.at = self._position(state)

    @staticmethod
    def _position(state: AgentState) -> Optional[Cell]:
        """Where the run stands: the far side of the last step it actually applied."""
        for label in reversed(state.trail):
            hit = _STEP.search(label)
            if hit:
                x, y, way = int(hit.group(1)), int(hit.group(2)), hit.group(3)
                dx, dy = STEPS[way]
                return (x + dx, y + dy)
        return None

    def entered(self) -> set[Cell]:
        """Every cell the run knows the openings of — the only cells it may step out of."""
        return set(self.open)

    def frontier(self) -> list[tuple[Cell, str]]:
        """Every (cell, direction) that leads somewhere not yet known. The search's live edge."""
        edge = []
        for cell, ways in self.open.items():
            for way in sorted(ways):
                dx, dy = STEPS[way]
                if (cell[0] + dx, cell[1] + dy) not in self.open:
                    edge.append((cell, way))
        return edge

    def distances(self, origin: Optional[Cell]) -> dict[Cell, int]:
        """Hops from ``origin`` through corridors already known — the order a walker would meet them."""
        if origin is None or origin not in self.open:
            return {}
        seen = {origin: 0}
        queue = [origin]
        while queue:
            cell = queue.pop(0)
            for way in self.open.get(cell, ()):
                dx, dy = STEPS[way]
                nxt = (cell[0] + dx, cell[1] + dy)
                if nxt in self.open and nxt not in seen:
                    seen[nxt] = seen[cell] + 1
                    queue.append(nxt)
        return seen


class MazeReasoner:
    """Both seats for the maze: propose the nearest unexplored opening, score what walking found."""

    def __init__(self, specs: Optional[dict[str, ActionSpec]] = None) -> None:
        self._specs = specs or {}

    # ── the proposer's seat ──

    async def propose(self, state: AgentState, n: int, avoid: set[str]) -> list[Action]:
        known = MazeKnowledge(state)
        wanted: list[Action] = []

        def offer(action: Action) -> None:
            fp = action.fingerprint()
            if fp in avoid or fp in state.failed:
                return
            if any(fp == a.fingerprint() for a in wanted):
                return
            wanted.append(action)

        # Opening moves: the size of the board, then the cell the run is standing in.
        if known.total is None:
            offer(Action("grid", {}, "how big is this maze"))
        if not known.open:
            offer(Action("entry", {}, "where does a run come in, and which ways are open"))
            return wanted[:n]

        # The exit is known: look at it, so the answer rests on a fact rather than a memory.
        if known.exit is not None:
            offer(Action("look", {"cell": f"{known.exit[0]},{known.exit[1]}"}, "confirm the exit"))

        # The frontier, nearest first: the opening closest to where the run stands is the one a walker
        # would take, and taking it keeps the trail a path rather than a set of disconnected hops.
        hops = known.distances(known.at)
        edge = known.frontier()
        edge.sort(key=lambda item: (hops.get(item[0], 10_000), item[0][1], item[0][0], item[1]))
        for cell, way in edge:
            offer(Action("step", {"cell": f"{cell[0]},{cell[1]}", "direction": way},
                         f"unexplored: {way} from {cell[0]},{cell[1]}"))
            if len(wanted) >= n:
                break
        return wanted[:n]

    # ── the evaluator's seat ──

    async def evaluate(self, state: AgentState, outcomes: Sequence[Observation]) -> list[Evaluation]:
        known = MazeKnowledge(state)
        # What the run already knows, as a count: every cell whose openings it has, plus the board size
        # once it has that. Progress is this number growing, which is the only honest measure a rule has
        # — and it must grow strictly, because the engine retreats from a step that does not beat where
        # it stands (`best_progress <= state.progress`).
        standing = len(known.open) + (1 if known.total is not None else 0)
        total = known.total or 0
        # +1 for the board size itself, so the denominator matches what `standing` counts.
        room = (total or 40) + 1
        out: list[Evaluation] = []
        for obs in outcomes:
            if not obs.ok:
                out.append(Evaluation(0.0, False, "", "probe failed"))
                continue
            # The engine refuses `done` on a predicted outcome anyway; saying so here keeps the reason
            # honest rather than letting it be overwritten downstream.
            if "THIS IS THE EXIT" in obs.text and not obs.predicted:
                hit = _CELL.search(obs.text)
                where = f"{hit.group(1)},{hit.group(2)}" if hit else "the exit cell"
                out.append(Evaluation(1.0, True, f"the exit is at cell {where}",
                                      "the exit was walked into"))
                continue
            # What this outcome adds on top of that: a cell the run had not seen, or the board size.
            gain = 0
            for x, y, _ways, _exit in _CELL.findall(obs.text):
                if (int(x), int(y)) not in known.open:
                    gain += 1
            if known.total is None and _GRID.search(obs.text):
                gain += 1
            # A probe that told the run nothing new scores where it already stands, which the engine
            # reads as no improvement — and retreating out of that is exactly the right move.
            share = min(0.95, (standing + gain) / room)
            out.append(Evaluation(round(share, 4), False, "",
                                  f"{standing + gain} of {total or '?'} cells known"
                                  if gain else "nothing new here"))
        return out


# `list_dir` writes entries as "📁 name" / "📄 name (123 B)" joined by " · "; `find_files` writes
# absolute paths joined by the same separator. Both are read back here rather than re-derived.
_DIR_ENTRY = re.compile(r"📁 ([^·\n(]+)")
_FILE_ENTRY = re.compile(r"📄 ([^·\n(]+?) \(")
_ABS_PATH = re.compile(r"(/[^\s·]+)")
_LISTED = re.compile(r"Contents of ([^\s—]+)")
# Words too common to tell one file from another; a goal is mostly these.
_STOPWORDS = frozenset("""a an and are as at be by do does find for from get give how i in is it its
me my of on or say tell that the then there this to what when where which who why with you your""".split())

# Directories that are somebody else's code or this machine's bookkeeping. A filesystem goal is almost
# never answered inside one, and they dwarf the real tree — searching this repo for "project" returns
# 412 files, nearly all of them under node_modules. Without this the first rule-based files run settled
# on `node_modules/iconv-lite/.idea/inspectionProfiles/Project_Default.xml`, which is a correct match
# and a useless answer.
_NOISE = frozenset("""node_modules .venv venv .git .hg .svn __pycache__ .pytest_cache .mypy_cache
dist build target out .next .cache .idea .vscode .tox site-packages vendor Pods .gradle""".split())


def is_noise(path: str) -> bool:
    """Whether a path runs through a directory whose contents are not this project's answer."""
    parts = path.split("/")
    return any(p in _NOISE or p.endswith(".egg-info") for p in parts)


def goal_words(text: str) -> list[str]:
    """The words in a goal worth searching a filesystem for, longest first."""
    words = {w.strip(".,:;!?'\"()[]") for w in str(text).split()}
    kept = [w for w in words if len(w) > 2 and w.lower() not in _STOPWORDS]
    return sorted(kept, key=len, reverse=True)[:4]


class FilesReasoner:
    """Both seats for a filesystem: look for what the goal names, then read it.

    Why this is not the survey below. `SurveyReasoner` proposes each action with no arguments, and
    every action this world has needs a `path` — so every probe came back "bad arguments for
    list_dir", the first evaluation scored zero, and the run stopped on `no_progress` at its second
    event. That made `builtin` — which is the app's default — functional for exactly one of the four
    shipped worlds while the window offered all four as equals. A reasoner for a world whose actions
    take arguments has to know where to start, and for a rooted filesystem that is simply the root.
    """

    def __init__(self, specs: Optional[dict[str, ActionSpec]] = None, env: Any = None) -> None:
        self._specs = specs or {}
        # `RootedFiles` carries the directory the world begins at. Without one there is nowhere to
        # start, and this reasoner says so by proposing nothing rather than guessing at "/".
        root = getattr(env, "root", None)
        self._root = str(root) if root is not None else ""

    def _known(self, state: AgentState) -> tuple[set[str], set[str], set[str]]:
        """Directories seen, files seen, and directories already listed — from the run's own facts."""
        dirs: set[str] = set()
        files: set[str] = set()
        listed: set[str] = set()
        for fact in state.facts:
            here = _LISTED.search(fact)
            base = here.group(1) if here else self._root
            if here:
                listed.add(here.group(1))
            for name in _DIR_ENTRY.findall(fact):
                dirs.add(f"{base.rstrip('/')}/{name.strip()}")
            for name in _FILE_ENTRY.findall(fact):
                files.add(f"{base.rstrip('/')}/{name.strip()}")
            if "with '" in fact:  # a find_files answer: absolute paths, already whole
                files.update(p for p in _ABS_PATH.findall(fact) if not is_noise(p))
        return dirs, files, listed

    async def propose(self, state: AgentState, n: int, avoid: set[str]) -> list[Action]:
        if not self._root:
            return []
        wanted: list[Action] = []

        def offer(action: Action) -> None:
            fp = action.fingerprint()
            if fp in avoid or fp in state.failed:
                return
            if any(fp == a.fingerprint() for a in wanted):
                return
            wanted.append(action)

        dirs, files, listed = self._known(state)
        words = goal_words(state.goal.text)

        # The root first: nothing can be proposed about a tree nobody has looked at.
        if not listed:
            offer(Action("list_dir", {"path": self._root}, "what is at the root"))
            for word in words[:2]:
                offer(Action("find_files", {"path": self._root, "contains": word},
                             f"anything named like {word!r}"))
            return wanted[:n]

        # A file whose name carries a word from the goal is the best thing to read next — but "best"
        # has to be ranked, or the first match wins and the first match is whatever sorted() found in
        # somebody else's vendored tree. Shallowest path first, and never through a noise directory.
        def rank(path: str) -> tuple[int, int, str]:
            name = path.rsplit("/", 1)[-1].lower()
            exact = 0 if any(name.startswith(w.lower()) for w in words) else 1
            return (exact, path.count("/"), path)

        for word in words:
            hits = [p for p in files if word.lower() in p.rsplit("/", 1)[-1].lower() and not is_noise(p)]
            for path in sorted(hits, key=rank):
                offer(Action("read_file", {"path": path}, f"{word!r} is in this file's name"))
                if len(wanted) >= n:
                    return wanted[:n]

        # Then widen: search by name, and open directories nobody has opened.
        for word in words:
            offer(Action("find_files", {"path": self._root, "contains": word}, f"search for {word!r}"))
        for path in sorted(dirs - listed, key=lambda p: (p.count("/"), p)):
            if path.rsplit("/", 1)[-1].startswith(".") or is_noise(path):
                continue  # dot-directories and vendored trees are rarely the answer, and are enormous
            offer(Action("list_dir", {"path": path}, "not looked in yet"))
            if len(wanted) >= n:
                break
        return wanted[:n]

    async def evaluate(self, state: AgentState, outcomes: Sequence[Observation]) -> list[Evaluation]:
        _dirs, files, listed = self._known(state)
        standing = len(files) + len(listed)
        words = [w.lower() for w in goal_words(state.goal.text)]
        out: list[Evaluation] = []
        for obs in outcomes:
            if not obs.ok:
                out.append(Evaluation(0.0, False, "", "probe failed"))
                continue
            # Reading a file the goal named, and getting real content back, is as settled as a rule
            # can honestly be: the answer is the file's own text, not an inference from it.
            read = obs.move.tool == "read_file"
            named = any(w in str(obs.move.args.get("path", "")).lower() for w in words)
            if read and named and not obs.predicted and obs.text.strip():
                head = " ".join(obs.text.split())[:200]
                out.append(Evaluation(1.0, True, f"{obs.move.args.get('path')}: {head}",
                                      "read the file the goal named"))
                continue
            # Otherwise progress is how much of the tree is known, which only ever grows.
            gain = len(_ABS_PATH.findall(obs.text)) + len(_FILE_ENTRY.findall(obs.text))
            share = min(0.9, (standing + gain) / 60)
            out.append(Evaluation(round(share, 4), False, "",
                                  f"{standing + gain} path(s) known" if gain else "nothing new here"))
        return out


class SurveyReasoner:
    """The fallback seats: try each action once, and score by what actually came back.

    No world knowledge at all — it reads the action specs, not the environment. For the worlds whose
    goals are answered in a probe or two (files, ledger) that is enough to move the machine and fill
    the window with a real run; it is not enough to answer a hard question, and it does not pretend to.
    """

    def __init__(self, specs: Optional[dict[str, ActionSpec]] = None) -> None:
        self._specs = specs or {}

    async def propose(self, state: AgentState, n: int, avoid: set[str]) -> list[Action]:
        wanted: list[Action] = []
        for name, spec in self._specs.items():
            if not spec.read_only:
                continue  # a survey never proposes something that would change the world
            action = Action(name, {}, f"survey: {name}")
            fp = action.fingerprint()
            if fp in avoid or fp in state.failed:
                continue
            wanted.append(action)
            if len(wanted) >= n:
                break
        return wanted

    async def evaluate(self, state: AgentState, outcomes: Sequence[Observation]) -> list[Evaluation]:
        out: list[Evaluation] = []
        for obs in outcomes:
            if not obs.ok:
                out.append(Evaluation(0.0, False, "", "probe failed"))
                continue
            # Something real came back; how much of the goal it settles is not a thing rules can judge,
            # so this never claims `done` — a survey run ends on its budget, honestly.
            weight = min(0.9, (len(state.facts) + 1) / 8)
            out.append(Evaluation(round(weight, 3), False, "", f"{len(obs.text)} chars observed"))
        return out


def reasoner_for(world: str, specs: Optional[dict[str, ActionSpec]] = None,
                 env: Any = None) -> Any:
    """The rule-based seats for a world: the maze walker, the filesystem reader, or the survey.

    `env` is optional because a caller may only have the specs, but a world whose actions take
    arguments generally needs it — `FilesReasoner` reads the root it is allowed to start from.
    """
    if world == "maze":
        return MazeReasoner(specs)
    if world == "files":
        return FilesReasoner(specs, env)
    return SurveyReasoner(specs)


def is_builtin(model_name: str) -> bool:
    """Whether a config names these seats rather than a model endpoint."""
    return str(model_name).strip().lower() == BUILTIN


__all__ = ["BUILTIN", "FilesReasoner", "MazeKnowledge", "MazeReasoner", "SurveyReasoner",
           "goal_words", "is_builtin", "is_noise", "reasoner_for"]
