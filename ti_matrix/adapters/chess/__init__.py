"""Chess: the first shipped world whose fan is wide enough to see, and whose scores are checkable.

    rules.py        the game itself — 0x88 board, legal moves, FEN, perft
    environment.py  the world the engine drives, with a seeded opponent

Standard library only, like every adapter here. `python-chess` is not available to this package, which
is why the rules are written out and checked against published perft counts rather than trusted.
"""
from .environment import CHESS_ACTIONS, ChessEnvironment
from .rules import Move, Position, START_FEN, legal_moves, make_move, outcome, perft

__all__ = ["CHESS_ACTIONS", "ChessEnvironment", "Move", "Position", "START_FEN",
           "legal_moves", "make_move", "outcome", "perft"]
