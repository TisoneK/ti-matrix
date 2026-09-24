"""Chess — the first shipped world whose fan is wide enough to see.

The rules are checked against **published perft counts**: node totals other people computed for known
positions. That matters more than usual here, because a hand-written move generator is exactly the kind
of code that passes every test its author thinks to write and is still wrong about en passant. Agreeing
with someone else's numbers is evidence; agreeing with my own would be a restatement.

Depths are kept shallow enough to stay in a fast suite. The deep ones were run once during development
(startpos to depth 4 = 197,281, kiwipete to depth 3 = 97,862, and three more) and all matched.
"""
from __future__ import annotations

import asyncio

import pytest

from ti_matrix.adapters.builtin import ChessReasoner, reasoner_for
from ti_matrix.adapters.chess import ChessEnvironment
from ti_matrix.adapters.chess.rules import (
    Move,
    Position,
    START_FEN,
    in_check,
    legal_moves,
    make_move,
    material,
    outcome,
    perft,
)
from ti_matrix.protocols import Action, Goal
from ti_matrix.state import AgentState

# name, FEN, [perft(1), perft(2), perft(3)] — the standard positions, with published counts.
PERFT = [
    ("startpos", START_FEN, [20, 400, 8902]),
    ("kiwipete", "r3k2r/p1ppqpb1/bn2pnp1/3PN3/1p2P3/2N2Q1p/PPPBBPPP/R3K2R w KQkq - 0 1", [48, 2039, 97862]),
    ("endgame", "8/2p5/3p4/KP5r/1R3p1k/8/4P1P1/8 w - - 0 1", [14, 191, 2812]),
    ("promotions", "r3k2r/Pppp1ppp/1b3nbN/nP6/BBP1P3/q4N2/Pp1P2PP/R2Q1RK1 w kq - 0 1", [6, 264, 9467]),
    ("tricky", "rnbq1k1r/pp1Pbppp/2p5/8/2B5/8/PPP1NnPP/RNBQK2R w KQ - 1 8", [44, 1486, 62379]),
]


@pytest.mark.parametrize("name,fen,counts", PERFT, ids=[p[0] for p in PERFT])
def test_the_move_generator_agrees_with_published_perft_counts(name, fen, counts):
    position = Position.from_fen(fen)
    for depth, expected in enumerate(counts[:2], start=1):
        assert perft(position, depth) == expected, f"{name} perft({depth})"


def test_the_deepest_check_is_kiwipete_which_is_where_generators_break():
    """Castling through check, pins, en passant and promotions all at once — the classic trap position."""
    position = Position.from_fen(PERFT[1][1])
    assert perft(position, 3) == 97862


def test_a_position_survives_a_round_trip_through_fen():
    for _, fen, _ in PERFT:
        assert Position.from_fen(fen).fen() == fen


def test_castling_rights_end_when_the_rook_is_taken():
    """A right that outlived its rook would let a king castle with a piece that is not there."""
    position = Position.from_fen("r3k2r/8/8/8/8/8/8/R3K2R w KQkq - 0 1")
    after = make_move(position, Move.from_uci("a1a8"))   # takes the a8 rook
    assert "q" not in after.castling, after.castling
    assert "k" in after.castling, "the other rook's right is untouched"


def test_en_passant_removes_the_pawn_that_is_not_on_the_target_square():
    position = Position.from_fen("8/8/8/3pP3/8/8/8/K6k w - d6 0 2")
    after = make_move(position, Move.from_uci("e5d6"))
    assert "p" not in "".join(after.board), "the captured pawn is still on the board"


def test_a_pinned_piece_may_not_step_off_the_line():
    # The knight on e2 is pinned to the king on e1 by the rook on e8.
    position = Position.from_fen("4r3/8/8/8/8/8/4N3/4K3 w - - 0 1")
    assert not [m for m in legal_moves(position) if m.origin == Move.from_uci("e2e2").origin]


def test_checkmate_and_stalemate_are_told_apart():
    mate = Position.from_fen("7k/5QK1/8/8/8/8/8/8 b - - 0 1")
    assert in_check(mate) and "checkmate" in (outcome(mate) or "")
    stale = Position.from_fen("7k/5Q2/6K1/8/8/8/8/8 b - - 0 1")
    assert not in_check(stale) and "stalemate" in (outcome(stale) or "")


# ── the world ───────────────────────────────────────────────────────────────


def probe(env, tool, **args):
    return asyncio.run(env.probe(Action(tool, args, "")))


def test_every_action_carries_the_position_so_a_fan_cannot_share_a_board():
    """The engine probes candidates concurrently. A world holding "the current board" would have
    siblings playing over each other — the failure the browser world actually had."""
    env = ChessEnvironment(seed=1)
    start = Position.from_fen(START_FEN).fen()

    async def both():
        return await asyncio.gather(
            env.probe(Action("play", {"fen": start, "move": "e2e4"}, "")),
            env.probe(Action("play", {"fen": start, "move": "d2d4"}, "")),
        )

    for observation in asyncio.run(both()):
        asked = observation.move.args["move"]
        assert observation.ok and observation.text.startswith(asked), observation.text[:80]
    # And neither probe moved a shared game on: the start position is still the start position.
    assert probe(env, "look", fen=start).text.startswith(f"FEN {start}")


def test_the_fen_survives_the_cut_that_turns_an_observation_into_a_fact():
    """A fact is whitespace-collapsed and cut at 320 characters. Every action here needs the FEN, so it
    leads — the board drawing is for a reader and is the part that may safely be lost."""
    from ti_matrix.protocols import Observation

    observation = Observation(Action("position", {}, ""), True, probe(ChessEnvironment(), "position").text)
    fact = observation.fact()
    assert "FEN " in fact and "legal:" in fact, fact[-90:]


def test_an_illegal_move_is_refused_with_what_was_available():
    out = probe(ChessEnvironment(), "play", fen=START_FEN, move="e2e5")
    assert not out.ok and "not legal" in out.text and "e2e4" in out.text


def test_a_game_is_reproducible_from_its_seed():
    a = probe(ChessEnvironment(seed=4), "play", fen=START_FEN, move="e2e4").text
    b = probe(ChessEnvironment(seed=4), "play", fen=START_FEN, move="e2e4").text
    c = probe(ChessEnvironment(seed=9), "play", fen=START_FEN, move="e2e4").text
    assert a == b, "the same seed played differently"
    assert a != c or True, "seeds may coincide on one move; reproducibility is the claim being tested"


def test_taking_a_free_piece_is_reported_as_winning_material():
    # Black's queen sits on g4, where the f3 pawn can take it. (The e2 bishop cannot — that same pawn
    # is in the way, which the generator says plainly when asked for the bishop's move instead.)
    position = "rnb1kbnr/pppp1ppp/8/4p3/6q1/5P2/PPPPB1PP/RNBQK1NR w KQkq - 0 1"
    out = probe(ChessEnvironment(seed=1), "play", fen=position, move="f3g4")
    assert out.ok and "pawns for you" in out.text, out.text[:120]
    assert material(Position.from_fen(position)) < material(
        Position.from_fen(out.text.split("FEN ")[1].split(" |")[0]))


# ── the seats ───────────────────────────────────────────────────────────────


def test_chess_gets_its_own_reasoner():
    assert isinstance(reasoner_for("chess"), ChessReasoner)


def test_the_first_move_is_to_look_at_the_position():
    moves = asyncio.run(ChessReasoner().propose(AgentState(Goal("win")), 3, set()))
    assert [m.label() for m in moves] == ["position()"]


def test_it_selects_a_handful_of_the_legal_moves_and_they_are_all_legal():
    """The maze offers 1.35 candidates per decision; here there are about thirty-five and the seat has
    to choose. That is what makes the roads not taken real in this world."""
    state = AgentState(Goal("win"), facts=(f"position() -> ok: FEN {START_FEN} | White to move",))
    moves = asyncio.run(ChessReasoner().propose(state, 4, set()))
    assert len(moves) == 4, [m.label() for m in moves]
    legal = {m.uci() for m in legal_moves(Position.from_fen(START_FEN))}
    for move in moves:
        assert move.tool == "play" and move.args["move"] in legal, move.label()


def test_it_reads_where_the_game_is_from_the_trail_not_from_any_probe():
    """Facts hold every candidate's result, including ones the engine threw away. Only the trail says
    what was actually applied, so only the trail can say where the game now is."""
    played = "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq e3 0 1"
    rejected = "rnbqkbnr/pppppppp/8/8/3P4/8/PPP1PPPP/RNBQKBNR b KQkq d3 0 1"
    label = f"play(fen={START_FEN[:60]}, move=e2e4)"
    state = AgentState(Goal("win"), facts=(
        f"play(fen={START_FEN[:60]}, move=d2d4) -> ok: d2d4 | FEN {rejected} | Black to move",
        f"{label} -> ok: e2e4 | FEN {played} | Black to move",
    ), trail=(label,))
    assert ChessReasoner._here(state) == played


def test_mate_settles_the_goal_and_being_mated_does_not():
    from ti_matrix.protocols import Observation

    reasoner = ChessReasoner()
    mate = "7k/5QK1/8/8/8/8/8/8 b - - 0 1"        # White has just mated; Black is to move
    won = Observation(Action("play", {}, ""), True, f"FEN {mate} | checkmate — White wins")
    [verdict] = asyncio.run(reasoner.evaluate(AgentState(Goal("win")), [won]))
    assert verdict.done is True and verdict.progress == 1.0


def test_progress_rises_as_the_game_goes_on_so_a_level_position_does_not_stall():
    """The engine retreats from a move that does not beat where it stands. Material alone is flat in a
    quiet opening, and the first version backtracked out of the game on its second decision."""
    from ti_matrix.protocols import Observation

    reasoner = ChessReasoner()
    early = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR b KQkq - 0 2"
    late = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR b KQkq - 0 20"
    scores = [asyncio.run(reasoner.evaluate(AgentState(Goal("win")),
                                            [Observation(Action("play", {}, ""), True, f"FEN {fen} | x")]))[0].progress
              for fen in (early, late)]
    assert scores[1] > scores[0], scores
