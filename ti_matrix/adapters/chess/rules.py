"""The rules of chess, on the standard library alone.

Written by hand because an adapter here may import nothing outside the standard library, so
`python-chess` is not available — and because the rules are the part that must be *right* rather than
clever. Correctness is checked against published perft counts (`tests/test_chess.py`), which is the only
honest way to test a move generator: they are numbers other people computed, so agreeing with them is
evidence rather than a restatement of this file's own opinions.

Representation is 0x88. A board of 128 squares where the valid ones satisfy ``sq & 0x88 == 0`` makes
"did that slide leave the board" a single mask instead of a pair of bounds checks, and off-board
squares sit in the gaps rather than wrapping from the h-file to the a-file. `sq = rank * 16 + file`,
with rank 0 being White's back rank.

A `Position` is immutable and `make_move` returns a new one. That is not decoration: the engine probes
a fan of candidate moves **concurrently** from one position, so anything that mutated a shared board
would have siblings reading each other's work. It is the same reason the maze's memory only grows and
the browser world had to be fixed.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterator, Optional

FILES = "abcdefgh"

WHITE_PIECES = "PNBRQK"
BLACK_PIECES = "pnbrqk"
EMPTY = "."

# Where each piece may go, as 0x88 offsets. Sliders repeat their offset until blocked.
KNIGHT = (33, 31, 18, 14, -33, -31, -18, -14)
BISHOP = (17, 15, -17, -15)
ROOK = (16, 1, -16, -1)
KING = QUEEN = BISHOP + ROOK

START_FEN = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"


def on_board(square: int) -> bool:
    return not (square & 0x88)


def square_name(square: int) -> str:
    return f"{FILES[square & 7]}{(square >> 4) + 1}"


def name_square(name: str) -> int:
    text = str(name).strip().lower()
    if len(text) != 2 or text[0] not in FILES or text[1] not in "12345678":
        raise ValueError(f"not a square: {name!r}")
    return (int(text[1]) - 1) * 16 + FILES.index(text[0])


@dataclass(frozen=True)
class Move:
    """One move. ``promotion`` is the piece a pawn becomes, lowercase, or empty."""

    origin: int
    target: int
    promotion: str = ""

    def uci(self) -> str:
        return f"{square_name(self.origin)}{square_name(self.target)}{self.promotion}"

    @staticmethod
    def from_uci(text: str) -> "Move":
        raw = str(text).strip().lower().replace("-", "")
        if len(raw) not in (4, 5):
            raise ValueError(f"not a move: {text!r} — write them like e2e4, or e7e8q to promote")
        promotion = raw[4] if len(raw) == 5 else ""
        if promotion and promotion not in "qrbn":
            raise ValueError(f"cannot promote to {promotion!r} — use q, r, b or n")
        return Move(name_square(raw[:2]), name_square(raw[2:4]), promotion)


@dataclass(frozen=True)
class Position:
    """A whole position: the board, whose turn, what is still allowed, and the clocks.

    Everything here is part of the position's *identity*, not decoration. Two boards that look alike
    but differ in castling rights or the en-passant square are different positions, because different
    moves are legal from them — which is exactly why a transposition table hashes these fields too.
    """

    board: tuple[str, ...]
    white_to_move: bool
    castling: str          # any of "KQkq", or "-" for none
    ep_square: int         # the square a pawn may capture onto, or -1
    halfmove: int          # plies since the last capture or pawn move — the fifty-move rule
    fullmove: int

    # ── reading and writing FEN ──

    @staticmethod
    def from_fen(fen: str = START_FEN) -> "Position":
        parts = str(fen).split()
        if len(parts) < 4:
            raise ValueError(f"not a position: {fen!r}")
        rows = parts[0].split("/")
        if len(rows) != 8:
            raise ValueError("a board has eight ranks")
        board = [EMPTY] * 128
        for index, row in enumerate(rows):
            rank = 7 - index                       # FEN starts at rank 8
            file = 0
            for char in row:
                if char.isdigit():
                    file += int(char)
                elif char in WHITE_PIECES + BLACK_PIECES:
                    if file > 7:
                        raise ValueError(f"rank {rank + 1} is too long")
                    board[rank * 16 + file] = char
                    file += 1
                else:
                    raise ValueError(f"not a piece: {char!r}")
            if file != 8:
                raise ValueError(f"rank {rank + 1} does not add up to eight squares")
        castling = parts[2] if parts[2] and set(parts[2]) <= set("KQkq-") else "-"
        ep = -1 if parts[3] == "-" else name_square(parts[3])
        return Position(tuple(board), parts[1] == "w", castling or "-", ep,
                        int(parts[4]) if len(parts) > 4 and parts[4].isdigit() else 0,
                        int(parts[5]) if len(parts) > 5 and parts[5].isdigit() else 1)

    def fen(self) -> str:
        rows = []
        for rank in range(7, -1, -1):
            row, gap = "", 0
            for file in range(8):
                piece = self.board[rank * 16 + file]
                if piece == EMPTY:
                    gap += 1
                    continue
                if gap:
                    row += str(gap)
                    gap = 0
                row += piece
            rows.append(row + (str(gap) if gap else ""))
        return " ".join(("/".join(rows), "w" if self.white_to_move else "b", self.castling,
                         square_name(self.ep_square) if self.ep_square >= 0 else "-",
                         str(self.halfmove), str(self.fullmove)))

    # ── who owns what ──

    def piece_at(self, square: int) -> str:
        return self.board[square]

    def is_ours(self, square: int) -> bool:
        piece = self.board[square]
        return piece != EMPTY and (piece.isupper() == self.white_to_move)

    def is_theirs(self, square: int) -> bool:
        piece = self.board[square]
        return piece != EMPTY and (piece.isupper() != self.white_to_move)

    def king_square(self, white: bool) -> int:
        king = "K" if white else "k"
        for square in range(128):
            if on_board(square) and self.board[square] == king:
                return square
        return -1


# ── attacks ────────────────────────────────────────────────────────────────


def _slides(board: tuple[str, ...], origin: int, offsets, movers: str) -> bool:
    for step in offsets:
        square = origin + step
        while on_board(square):
            piece = board[square]
            if piece != EMPTY:
                if piece in movers:
                    return True
                break
            square += step
    return False


def attacked(position: Position, square: int, by_white: bool) -> bool:
    """Whether ``square`` is attacked by the given side. Used for check and for castling through check."""
    board = position.board
    pawn, knight, king = ("P", "N", "K") if by_white else ("p", "n", "k")
    bishops = "BQ" if by_white else "bq"
    rooks = "RQ" if by_white else "rq"

    # A pawn attacks diagonally *forwards*, so look backwards from the target square.
    for step in ((-17, -15) if by_white else (17, 15)):
        near = square + step
        if on_board(near) and board[near] == pawn:
            return True
    for step in KNIGHT:
        near = square + step
        if on_board(near) and board[near] == knight:
            return True
    for step in KING:
        near = square + step
        if on_board(near) and board[near] == king:
            return True
    return _slides(board, square, BISHOP, bishops) or _slides(board, square, ROOK, rooks)


def in_check(position: Position, white: Optional[bool] = None) -> bool:
    side = position.white_to_move if white is None else white
    king = position.king_square(side)
    return king >= 0 and attacked(position, king, not side)


# ── generating moves ───────────────────────────────────────────────────────


def _pseudo_moves(position: Position) -> Iterator[Move]:
    """Every move that follows the pieces' movement rules, before asking whether it leaves a king in check."""
    board = position.board
    white = position.white_to_move
    forward, start_rank, last_rank = (16, 1, 7) if white else (-16, 6, 0)

    for origin in range(128):
        if not on_board(origin) or not position.is_ours(origin):
            continue
        piece = board[origin].upper()

        if piece == "P":
            ahead = origin + forward
            if on_board(ahead) and board[ahead] == EMPTY:
                if (ahead >> 4) == last_rank:
                    for promotion in "qrbn":
                        yield Move(origin, ahead, promotion)
                else:
                    yield Move(origin, ahead)
                    two = ahead + forward
                    if (origin >> 4) == start_rank and board[two] == EMPTY:
                        yield Move(origin, two)
            for step in ((15, 17) if white else (-15, -17)):
                target = origin + step
                if not on_board(target):
                    continue
                if position.is_theirs(target):
                    if (target >> 4) == last_rank:
                        for promotion in "qrbn":
                            yield Move(origin, target, promotion)
                    else:
                        yield Move(origin, target)
                elif target == position.ep_square:
                    yield Move(origin, target)
            continue

        if piece in ("N", "K"):
            for step in (KNIGHT if piece == "N" else KING):
                target = origin + step
                if on_board(target) and not position.is_ours(target):
                    yield Move(origin, target)
            continue

        for step in {"B": BISHOP, "R": ROOK, "Q": QUEEN}[piece]:
            target = origin + step
            while on_board(target):
                if position.is_ours(target):
                    break
                yield Move(origin, target)
                if position.is_theirs(target):
                    break
                target += step

    # Castling: the king's two squares of travel must be empty and unattacked, and so must its own.
    king_from = 4 if white else 116
    rights = position.castling
    if board[king_from] == ("K" if white else "k") and not attacked(position, king_from, not white):
        for right, rook_from, empties, path in (
            ("K" if white else "k", king_from + 3, (king_from + 1, king_from + 2), (king_from + 1, king_from + 2)),
            ("Q" if white else "q", king_from - 4, (king_from - 1, king_from - 2, king_from - 3),
             (king_from - 1, king_from - 2)),
        ):
            if right not in rights:
                continue
            if board[rook_from] != ("R" if white else "r"):
                continue
            if any(board[sq] != EMPTY for sq in empties):
                continue
            if any(attacked(position, sq, not white) for sq in path):
                continue
            yield Move(king_from, path[1])


def make_move(position: Position, move: Move) -> Position:
    """The position after a move. Never validates — `legal_moves` decides what may be passed here."""
    board = list(position.board)
    white = position.white_to_move
    piece = board[move.origin]
    captured = board[move.target]

    board[move.target] = piece
    board[move.origin] = EMPTY

    # En passant: the pawn that is taken is not on the square the capturing pawn lands on.
    if piece.upper() == "P" and move.target == position.ep_square and captured == EMPTY:
        board[move.target - (16 if white else -16)] = EMPTY
        captured = "p" if white else "P"

    if move.promotion:
        board[move.target] = move.promotion.upper() if white else move.promotion

    # The rook moves with the king, and only ever between those four squares.
    if piece.upper() == "K" and abs(move.target - move.origin) == 2:
        if move.target > move.origin:
            board[move.target - 1], board[move.target + 1] = board[move.target + 1], EMPTY
        else:
            board[move.target + 1], board[move.target - 2] = board[move.target - 2], EMPTY

    # A king or rook that has moved, or a rook that has been taken, ends the right it stood for.
    rights = set(position.castling) - {"-"}
    for square, right in ((4, "KQ"), (116, "kq"), (7, "K"), (0, "Q"), (123, "k"), (112, "q")):
        if move.origin == square or move.target == square:
            rights -= set(right)
    castling = "".join(c for c in "KQkq" if c in rights) or "-"

    ep = -1
    if piece.upper() == "P" and abs(move.target - move.origin) == 32:
        ep = (move.origin + move.target) // 2

    reset = piece.upper() == "P" or captured != EMPTY
    return Position(tuple(board), not white, castling, ep,
                    0 if reset else position.halfmove + 1,
                    position.fullmove + (0 if white else 1))


def legal_moves(position: Position) -> list[Move]:
    """Every move that is actually legal here — the pseudo-legal ones that do not leave the king in check."""
    white = position.white_to_move
    legal = []
    for move in _pseudo_moves(position):
        after = make_move(position, move)
        if not in_check(after, white):
            legal.append(move)
    return legal


def perft(position: Position, depth: int) -> int:
    """Count the leaf nodes at ``depth``. The standard way to prove a move generator, against published counts."""
    if depth <= 0:
        return 1
    if depth == 1:
        return len(legal_moves(position))
    return sum(perft(make_move(position, move), depth - 1) for move in legal_moves(position))


# ── describing a position in words ─────────────────────────────────────────


NAMES = {"P": "pawn", "N": "knight", "B": "bishop", "R": "rook", "Q": "queen", "K": "king"}
VALUES = {"P": 1, "N": 3, "B": 3, "R": 5, "Q": 9, "K": 0}


def material(position: Position) -> int:
    """White's material minus Black's, in pawns. The crudest honest measure of who is ahead."""
    total = 0
    for square in range(128):
        if not on_board(square):
            continue
        piece = position.board[square]
        if piece == EMPTY:
            continue
        total += VALUES[piece.upper()] * (1 if piece.isupper() else -1)
    return total


def outcome(position: Position) -> Optional[str]:
    """How the game ended here, or None if it has not."""
    if legal_moves(position):
        if position.halfmove >= 100:
            return "draw by the fifty-move rule"
        return None
    if in_check(position):
        return "checkmate — " + ("Black" if position.white_to_move else "White") + " wins"
    return "stalemate — a draw"


def describe(position: Position) -> str:
    """What a run is told about a position, with the parts a reader must not lose stated first.

    Order matters here and is not a style choice. An observation becomes a fact through
    ``Observation.fact()``, which collapses whitespace and cuts at 320 characters — so anything after
    the board drawing is gone by the time a later step reads it back. The FEN is the one thing a
    subsequent move *must* have, since every action in this world names the position it acts from, so
    it leads. The board picture, which is for a person and for a model's intuition rather than for
    machinery, comes last and is the part that may safely be cut.
    """
    moves = legal_moves(position)
    done = outcome(position)
    turn = "White" if position.white_to_move else "Black"

    head = [f"FEN {position.fen()}",
            f"{turn} to move, material {material(position):+d}"]
    if done:
        head.append(done)
    else:
        if in_check(position):
            head.append(f"{turn} is in check")
        head.append(f"{len(moves)} legal: " + " ".join(m.uci() for m in moves))

    board = [f"{rank + 1} " + " ".join(position.board[rank * 16 + f] for f in range(8))
             for rank in range(7, -1, -1)]
    board.append("  a b c d e f g h")
    return " | ".join(head) + "\n" + "\n".join(board)


__all__ = ["BISHOP", "KING", "KNIGHT", "Move", "Position", "QUEEN", "ROOK", "START_FEN", "attacked",
           "describe", "in_check", "legal_moves", "make_move", "material", "name_square", "outcome",
           "perft", "square_name"]
