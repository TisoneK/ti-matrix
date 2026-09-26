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

    def considered(self, state: AgentState) -> Optional[int]:
        """Every unexplored opening the run could have taken from what it knows."""
        known = MazeKnowledge(state)
        if not known.open:
            return None            # nothing entered yet: the opening moves are not a frontier
        return len(known.frontier())

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
# An absolute path in a search answer, on either platform: `C:\Users\me\repo` or `/home/me/repo`, up to the
# ` · ` the world joins hits with. The old pattern only knew forward slashes, so on Windows every hit of a
# search was invisible to this seat — which is half of why a search could return candidates and the run
# still never weigh more than one of them.
_ABS_PATH = re.compile(r"(?:[A-Za-z]:\\[^\s·]+|/[^\s·]+)")
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
                # A hit ending in a separator is a directory, which is what the world writes for one. They
                # used to be dropped on the floor along with every Windows path; now a matched *folder* is a
                # candidate like any other — the seat proposes opening it — and a matched file is proposed
                # for reading. That is the fan: several candidates from one search, to be probed and weighed
                # against each other instead of the first name that happened to look right.
                for hit in _ABS_PATH.findall(fact):
                    hit = hit.strip()
                    if not hit or is_noise(hit):
                        continue
                    if hit.endswith("/") or hit.endswith("\\"):
                        dirs.add(hit.rstrip("/\\"))
                    else:
                        files.add(hit)
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
            # can honestly be: the answer is the file's own text, not an inference from it. "Named" is
            # checked against the file's own basename, not the whole path — a goal word that only
            # matches an ancestor directory (an ordinary word like "test" or "app") is not the same
            # claim as the goal actually naming this file. And a lockfile or generated bundle whose name
            # happens to carry a goal word by convention is excluded outright: `package-lock.json`
            # answering a goal that merely contains the word "package" is the failure mode this guards.
            read = obs.move.tool == "read_file"
            path = str(obs.move.args.get("path", ""))
            basename = path.rsplit("/", 1)[-1].lower()
            named = any(w in basename for w in words) and not is_generated_artifact(path)
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


# `goto` answers "loaded <url> — <title>"; `links` writes "- <text> — <href>" one per line.
_LOADED = re.compile(r"loaded (\S+)")
_LINK = re.compile(r"^- (.*?) — (\S+)$", re.M)


class BrowserReasoner:
    """Both seats for a real browser: open the page you were given, read it, follow what the goal names.

    Same failure as the filesystem had. `SurveyReasoner` proposed `goto()`, `page_text()`, `html()` —
    every one with no arguments — and `goto` with no URL cannot do anything. A world whose actions take
    arguments needs a starting point, and for this one it is the start URL the run was configured with.

    Read-only throughout: this proposes nothing that clicks, types or runs script. Those actions exist
    and the engine will surface them for confirmation, but a rule has no business deciding to press a
    button on somebody's behalf — that is a judgement, and judgement is what the model seat is for.
    """

    def __init__(self, specs: Optional[dict[str, ActionSpec]] = None, env: Any = None) -> None:
        self._specs = specs or {}
        start = getattr(env, "start_url", None)
        self._start = str(start) if start else ""

    @staticmethod
    def _seen(state: AgentState) -> tuple[set[str], dict[str, str]]:
        """Pages already loaded, and every link the run has been shown (href -> its text)."""
        loaded: set[str] = set()
        links: dict[str, str] = {}
        for fact in state.facts:
            loaded.update(_LOADED.findall(fact))
            for text, href in _LINK.findall(fact):
                links[href] = text
        return loaded, links

    async def propose(self, state: AgentState, n: int, avoid: set[str]) -> list[Action]:
        wanted: list[Action] = []

        def offer(action: Action) -> None:
            fp = action.fingerprint()
            if fp in avoid or fp in state.failed or any(fp == a.fingerprint() for a in wanted):
                return
            wanted.append(action)

        loaded, links = self._seen(state)
        words = goal_words(state.goal.text)

        if not loaded:
            if not self._start:
                return []  # nowhere to begin, and inventing a URL is not a rule's decision
            offer(Action("goto", {"url": self._start}, "the page this run was pointed at"))
            return wanted[:n]

        # What is on this page, before deciding where to go next.
        offer(Action("title_and_url", {}, "where are we"))
        offer(Action("page_text", {}, "what the page says"))
        offer(Action("links", {}, "where it can go from here"))
        if len(wanted) >= n:
            return wanted[:n]

        # Then follow a link whose text or href carries a word from the goal — never an arbitrary one,
        # because "click the first link" is how a run wanders off a site forever.
        #
        # ONE navigation per fan. The world no longer *lies* when two share one — each goto reports the
        # page it actually landed on, and every read names the page it read — but the waste is real:
        # there is a single page behind the whole fan, so the second navigation throws away the first,
        # and the engine may then apply the one whose page is gone. Proposing navigation on its own is
        # what the design asked for; this is the seat honouring it rather than a comment hoping for it.
        for word in words:
            for href, text in sorted(links.items()):
                if href in loaded:
                    continue
                if word.lower() in text.lower() or word.lower() in href.lower():
                    offer(Action("goto", {"url": href}, f"{word!r} is in this link"))
                    return wanted[:n]
        return wanted[:n]

    async def evaluate(self, state: AgentState, outcomes: Sequence[Observation]) -> list[Evaluation]:
        loaded, links = self._seen(state)
        standing = len(loaded) + len(links)
        words = [w.lower() for w in goal_words(state.goal.text)]
        out: list[Evaluation] = []
        for obs in outcomes:
            if not obs.ok:
                out.append(Evaluation(0.0, False, "", "probe failed"))
                continue
            body = obs.text.lower()
            # Text that actually contains what the goal asked about, read off a page the run really
            # loaded, is as settled as a rule gets here — the answer is the page's own words.
            if obs.move.tool == "page_text" and words and not obs.predicted \
                    and all(w in body for w in words[:2]):
                head = " ".join(obs.text.split())[:240]
                out.append(Evaluation(1.0, True, head, "the page says it"))
                continue
            gain = len(_LINK.findall(obs.text)) + len(_LOADED.findall(obs.text))
            share = min(0.9, (standing + gain) / 40)
            out.append(Evaluation(round(share, 4), False, "",
                                  f"{standing + gain} thing(s) known" if gain else "nothing new here"))
        return out


# `describe` leads every chess observation with "FEN <fen> | ... | N legal: a b c" so both survive the
# 320-character cut that turns an observation into a fact.
_FEN = re.compile(r"FEN (\S+ [wb] \S+ \S+ \d+ \d+)")
_LEGAL = re.compile(r"(\d+) legal: ([a-h1-8qrbn ]+)")
_PLAYED = re.compile(r"play\(fen=(.+?), move=(\w+)\)")


class ChessReasoner:
    """Both seats for chess: weigh a handful of the legal moves, take the one that costs least.

    The point of this seat is not to play well — it plays badly on purpose, one ply deep, and the world
    it drives says why that is correct. The point is that chess is the first shipped world where a fan
    is a real choice. The maze offers 1.35 candidates per decision; here there are about thirty-five,
    and `max_branches` decides how many of them get looked at. So this reasoner does what no maze
    reasoner ever had to: **it selects**, and the ones it passes over are a genuine road not taken.
    """

    def __init__(self, specs: Optional[dict[str, ActionSpec]] = None, env: Any = None) -> None:
        self._specs = specs or {}

    @staticmethod
    def _here(state: AgentState) -> Optional[str]:
        """The position the run actually stands in — from the move it applied, not from any probe.

        Facts hold every probe's result, including the candidates the engine discarded, so reading "the
        last FEN mentioned" would pick up a position the run considered and rejected. The trail holds
        only what was applied, so it is the one honest source for where the game now is.
        """
        for label in reversed(state.trail):
            played = _PLAYED.search(label)
            if played:
                for fact in reversed(state.facts):
                    if fact.startswith(label):
                        found = _FEN.search(fact)
                        if found:
                            return found.group(1)
                return None
        for fact in state.facts:            # nothing applied yet: the opening position
            found = _FEN.search(fact)
            if found:
                return found.group(1)
        return None

    def considered(self, state: AgentState) -> Optional[int]:
        """How many legal moves this position offered. The denominator a chess decision needs."""
        from ti_matrix.adapters.chess.rules import Position, legal_moves

        fen = self._here(state)
        if fen is None:
            return None
        try:
            return len(legal_moves(Position.from_fen(fen)))
        except ValueError:
            return None

    async def propose(self, state: AgentState, n: int, avoid: set[str]) -> list[Action]:
        wanted: list[Action] = []

        def offer(action: Action) -> None:
            fp = action.fingerprint()
            if fp in avoid or fp in state.failed or any(fp == a.fingerprint() for a in wanted):
                return
            wanted.append(action)

        fen = self._here(state)
        if fen is None:
            offer(Action("position", {}, "the position this game starts from"))
            return wanted[:n]

        from ti_matrix.adapters.chess.rules import Position, legal_moves, make_move, material, outcome

        try:
            position = Position.from_fen(fen)
        except ValueError:
            return []
        if outcome(position) is not None:
            return []

        # Rank every legal move by what the position is worth after it, from the mover's side. One ply,
        # deliberately: a seat that searched would be doing the engine's job, and the engine is the thing
        # on display here.
        #
        # Material ties constantly in a quiet opening, and with an alphabetical tiebreak the first run
        # shuffled a rook between a1 and a2 for eighteen moves — correct by its own rule and useless to
        # watch. Mobility breaks the tie: how many replies the position offers afterwards. It is one
        # more line, it is a measure people already use, and it produces a recognisable game without
        # anything resembling a search.
        mine = 1 if position.white_to_move else -1

        def worth(move):
            after = make_move(position, move)
            return (-mine * material(after), -len(legal_moves(after)), move.uci())

        ranked = sorted(legal_moves(position), key=worth)
        for move in ranked:
            offer(Action("play", {"fen": fen, "move": move.uci()}, f"weighed {move.uci()}"))
            if len(wanted) >= n:
                break
        return wanted[:n]

    async def evaluate(self, state: AgentState, outcomes: Sequence[Observation]) -> list[Evaluation]:
        from ti_matrix.adapters.chess.rules import Position, material, outcome

        out: list[Evaluation] = []
        for obs in outcomes:
            if not obs.ok:
                out.append(Evaluation(0.0, False, "", "not a legal move here"))
                continue
            found = _FEN.search(obs.text)
            if found is None:
                out.append(Evaluation(0.05, False, "", "read the position"))
                continue
            after = Position.from_fen(found.group(1))
            # `after` is the position the *opponent* now faces, so the mover is the other side.
            mover_is_white = not after.white_to_move
            ended = outcome(after)
            if ended and "checkmate" in ended and not obs.predicted:
                won = ("White wins" in ended) == mover_is_white
                if won:
                    out.append(Evaluation(1.0, True, ended, "mate"))
                    continue
                out.append(Evaluation(0.0, False, "", "this move is mated"))
                continue
            if ended:
                out.append(Evaluation(0.4, False, "", ended))
                continue
            edge = material(after) * (1 if mover_is_white else -1)
            # Material, plus a small monotone term for the game having advanced.
            #
            # Material alone is flat in a quiet opening, and the engine retreats from a move that does
            # not beat where it stands (`best_progress <= state.progress`) — so a level game stalled on
            # its second decision and backtracked out. Saying a played move is worth slightly more than
            # not having played it is honest here: this world's goal is reached by playing the game out,
            # and a position twenty moves deep is further along than the opening whatever the material.
            # Never 1.0: only mate settles, which is the evaluator's own rule, not a nudge.
            played = min(0.4, 0.02 * after.fullmove)
            out.append(Evaluation(round(min(0.95, max(0.0, 0.3 + edge / 20 + played)), 4), False, "",
                                  f"material {edge:+d} at move {after.fullmove}"))
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
    if world == "browser":
        return BrowserReasoner(specs, env)
    if world == "chess":
        return ChessReasoner(specs, env)
    return SurveyReasoner(specs)


def is_builtin(model_name: str) -> bool:
    """Whether a config names these seats rather than a model endpoint."""
    return str(model_name).strip().lower() == BUILTIN


__all__ = ["BUILTIN", "BrowserReasoner", "ChessReasoner", "FilesReasoner", "MazeKnowledge", "MazeReasoner", "SurveyReasoner",
           "goal_words", "is_builtin", "is_noise", "reasoner_for"]
