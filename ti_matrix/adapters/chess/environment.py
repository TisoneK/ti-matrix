"""Chess as an Environment — the first shipped world with a fan worth the name.

Why this world exists. The maze made the engine search, but it offers **1.35 candidates per decision**
measured over 202 of them: a corridor has one way on. A search tree drawn from that is a line, and no
amount of drawing makes a line look like a matrix. Chess offers about thirty-five legal moves in a
middlegame, so the branch points are actually branch points.

The sharper reason is that chess is the only shipped world whose *evaluations are checkable against
ground truth*. In a maze, "was it right?" is answerable at the end. Here every score is answerable
immediately: the ledger saying a move was worth 0.7 while it hangs a queen is this product's whole
claim — watch it think, and check whether to believe it — made falsifiable in a single row.

**This is not a chess engine and must not become one.** The loop is a beam of one with backtracking: it
commits to a move, explores forward, and retreats when nothing improves. It will not play well. Adding
alpha-beta to the engine core to fix that would be reading this world exactly backwards — it exists to
make the *search legible*, not to win games.

Every action carries the position it acts from. The engine probes a fan concurrently, so a world that
kept "the current board" would have siblings playing over each other — the failure the browser world
actually had. Here `play(fen, move)` names its own origin, the way the maze's `step(cell, direction)`
does, and nothing this world remembers can be clobbered by a sibling probe.
"""
from __future__ import annotations

import random
from typing import Optional

from ti_matrix.protocols import Action, ActionSpec, Observation

from .rules import (
    Move,
    Position,
    START_FEN,
    describe,
    legal_moves,
    make_move,
    material,
    outcome,
)

CHESS_ACTIONS: dict[str, ActionSpec] = {
    spec.name: spec for spec in (
        ActionSpec("position", "The position this game starts from, and every legal move in it.", "{}"),
        ActionSpec("look", "Read a position: the board, whose turn, the material count, and every legal "
                           "reply. Give the FEN you want to look at.",
                   '{"fen": "<FEN>"}'),
        ActionSpec("play", "Play one move from a position and see the opponent's answer. The FEN says "
                           "which position to play it from, so this never depends on what came before.",
                   '{"fen": "<FEN>", "move": "e2e4"}'),
    )
}


class ChessEnvironment:
    """A game of chess a run can only learn by looking and playing.

    The opponent is the world's, not the run's: a seeded replier, so a game is reproducible the way a
    seeded maze is. It is deliberately weak — it takes the best capture it can see and otherwise moves
    at random — because a strong opponent would make every run end the same way and the point here is
    to watch a search, not to hold a tournament.
    """

    name = "chess"

    def __init__(self, fen: str = START_FEN, *, seed: Optional[int] = None,
                 opponent: str = "greedy") -> None:
        self.start = Position.from_fen(fen or START_FEN)
        self._seed = seed
        self._opponent = opponent
        # Monotonic, like the maze's `_seen`: a fan is probed concurrently, and a record that only ever
        # grows cannot come back wrong because a sibling probe touched it.
        self._positions: set[str] = {self.start.fen()}

    # ── the Environment contract ──

    def tools(self) -> dict[str, ActionSpec]:
        return CHESS_ACTIONS

    def is_read_only(self, action: Action) -> Optional[bool]:
        spec = CHESS_ACTIONS.get(action.tool)
        return None if spec is None else spec.read_only

    async def probe(self, action: Action) -> Observation:
        try:
            return Observation(action, *getattr(self, f"_{action.tool}")(**action.args))
        except TypeError as exc:      # wrong or missing arguments — a failure the search can use
            return Observation(action, False, f"bad arguments for {action.tool}: {exc}")
        except Exception as exc:      # noqa: BLE001 — a failed probe is an observation, never a crash
            return Observation(action, False, f"{type(exc).__name__}: {exc}"[:400])

    # ── the actions ──

    def _position(self) -> tuple[bool, str]:
        return True, describe(self.start)

    def _look(self, fen: str = "") -> tuple[bool, str]:
        position = self._parse(fen)
        return True, describe(position)

    def _play(self, fen: str = "", move: str = "") -> tuple[bool, str]:
        position = self._parse(fen)
        if outcome(position) is not None:
            return False, f"this game is already over: {outcome(position)}"
        try:
            wanted = Move.from_uci(move)
        except ValueError as exc:
            return False, str(exc)
        legal = {m.uci(): m for m in legal_moves(position)}
        if wanted.uci() not in legal:
            # A refusal the search can act on, and it says what *was* available rather than only "no".
            return False, (f"{wanted.uci()} is not legal here. Legal moves: "
                           + ", ".join(sorted(legal)) or "none")

        before = material(position)
        after = make_move(position, legal[wanted.uci()])
        self._positions.add(after.fen())

        done = outcome(after)
        if done is not None:
            return True, f"{move}: {done} | {describe(after)}"

        reply = self._reply(after)
        final = make_move(after, reply)
        self._positions.add(final.fen())
        swing = material(final) - before
        # The material change is stated from the mover's point of view, because "did that cost me
        # anything" is the question a score has to answer and the sign convention is otherwise a trap.
        theirs = -swing if position.white_to_move else swing
        verdict = "even" if theirs == 0 else (f"{theirs:+d} pawns for you" if theirs > 0
                                              else f"{theirs:+d} pawns for you — that cost material")
        return True, (f"{move}, opponent answered {reply.uci()}, {verdict} | {describe(final)}")

    # ── the opponent ──

    def _reply(self, position: Position) -> Move:
        """The world's answer. Seeded on the position, so the same game replays the same way."""
        moves = legal_moves(position)
        rng = random.Random(f"{self._seed}:{position.fen()}")
        if self._opponent == "random":
            return rng.choice(moves)
        # Greedy: take the most valuable thing on offer, and break ties the same way every time.
        best, best_gain = None, None
        for move in sorted(moves, key=lambda m: m.uci()):
            gain = material(make_move(position, move)) - material(position)
            gain = -gain if position.white_to_move else gain
            if best_gain is None or gain > best_gain:
                best, best_gain = move, gain
        return best if best_gain and best_gain > 0 else rng.choice(moves)

    def _parse(self, fen: str) -> Position:
        text = str(fen).strip()
        if not text:
            raise ValueError("which position? give the FEN — `position` returns the one to start from")
        return Position.from_fen(text)


__all__ = ["CHESS_ACTIONS", "ChessEnvironment"]
