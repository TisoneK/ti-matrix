"""The protocol is the one contract the app and the sidecar share — so it gets its own tests.

The handshake line, the frame encoder's shape, and the goal parser's lenience are asserted here. A
breaking change to any of these is a protocol bump, and these tests are what notice first.
"""
from __future__ import annotations

import json

import pytest

from appserver import protocol


def test_the_handshake_line_round_trips_and_carries_its_version():
    line = protocol.handshake_line(52134, "a" * 32)
    assert line == f"TM{protocol.PROTOCOL} 52134 {'a' * 32}"
    parsed = protocol.parse_handshake(line)
    assert parsed == (protocol.PROTOCOL, 52134, "a" * 32)


def test_the_parser_reads_any_tm_line_and_the_app_checks_the_version():
    # Parsing and matching are separate: the parser reads the line, the app compares the version —
    # which is how it can say "the sidecar speaks TM2" instead of failing silently.
    assert protocol.parse_handshake(f"TM2 52134 {'a' * 32}") == (2, 52134, "a" * 32)
    assert protocol.parse_handshake(f"TM{protocol.PROTOCOL} 52134 {'a' * 32}")[0] == protocol.PROTOCOL
    for bad in ("", "TM1 52134", "TM1 52134 notahex", "TM1 52134 " + "g" * 32,
                "not a handshake at all"):
        assert protocol.parse_handshake(bad) is None


def test_tokens_are_hex_and_do_not_repeat():
    tokens = {protocol.new_token() for _ in range(20)}
    assert len(tokens) == 20
    assert all(len(t) == 32 and all(c in "0123456789abcdef" for c in t) for t in tokens)


def test_a_frame_is_one_json_object_with_a_type():
    raw = protocol.encode("settled", answer="x", reason=None, events=3)
    body = json.loads(raw)
    assert body == {"type": "settled", "answer": "x", "reason": None, "events": 3}


def test_decode_drops_malformed_frames_never_crashes():
    assert protocol.decode("not json") is None
    assert protocol.decode(b"\xff\xfe") is None
    assert protocol.decode(json.dumps(["a", "list"])) is None
    assert protocol.decode(json.dumps({"no": "type"})) is None
    body = protocol.decode(json.dumps({"type": "stop"}))
    assert body == {"type": "stop"}


def test_a_goal_frame_needs_text_and_world():
    with pytest.raises(ValueError):
        protocol.parse_goal({"type": "goal"})
    with pytest.raises(ValueError):
        protocol.parse_goal({"type": "goal", "text": "go", "world": "  "})
    text, world, config, budget = protocol.parse_goal(
        {"type": "goal", "text": " reach the exit ", "world": "maze",
         "config": {"base_url": "http://x/v1", "model": "m", "junk": 1},
         "budget": {"max_model_calls": 9, "nonsense": 4, "max_depth": "5"}})
    assert text == "reach the exit" and world == "maze"
    assert config == {"base_url": "http://x/v1", "model": "m", "junk": 1}  # a world reads what it knows
    assert budget == {"max_model_calls": 9}  # unknown and non-numeric ("5" is a string) are dropped
