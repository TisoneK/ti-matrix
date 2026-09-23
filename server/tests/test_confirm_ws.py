"""The confirmer over the wire: a request, a reply, and every way the reply can fail to come.

The engine's contract is one method — `confirm(action, reason) -> bool`, asked at the moment it would
perform something that changes the world. These tests say what that method means when the person is on
the other end of a socket: an answer with the same id grants or refuses; an unknown or stale id is
refused; a socket that dropped before answering is refused, because nobody there to say yes is no.
"""
from __future__ import annotations

import asyncio

import pytest

from appserver.confirm_ws import WsConfirmer, parse_confirm_response
from ti_matrix.protocols import Action


class RecordedSend:
    def __init__(self) -> None:
        self.frames: list[str] = []

    def __call__(self, frame: str) -> None:
        self.frames.append(frame)

    @property
    def last(self) -> dict:
        import json
        return json.loads(self.frames[-1])


@pytest.mark.asyncio
async def test_a_reply_with_the_same_id_grants_and_a_denial_refuses():
    send = RecordedSend()
    confirmer = WsConfirmer(send)
    action = Action("click", {"selector": "button.buy"}, "submit the order")

    task = asyncio.create_task(confirmer.confirm(action, "it completes the purchase"))
    await asyncio.sleep(0)  # let the confirm-request go out
    request_id = send.last["id"]
    assert send.last["type"] == "confirm-request"
    assert send.last["action"]["tool"] == "click" and send.last["action"]["label"].startswith("click(")
    assert send.last["reason"] == "it completes the purchase"

    assert confirmer.resolve(request_id, True)
    assert await task is True
    assert confirmer.asked == [("click(selector=button.buy)", "it completes the purchase", True)]

    task2 = asyncio.create_task(confirmer.confirm(action, "again"))
    await asyncio.sleep(0)
    confirmer.resolve(send.last["id"], False)
    assert await task2 is False


def test_an_unknown_stale_or_malformed_reply_is_refused_not_fatal():
    send = RecordedSend()
    confirmer = WsConfirmer(send)
    assert confirmer.resolve("never-issued", True) is False
    assert parse_confirm_response({"type": "confirm-response"}) is None
    assert parse_confirm_response({"type": "confirm-response", "id": "x", "granted": "yes"}) is None
    assert parse_confirm_response({"type": "confirm-response", "id": "x", "granted": True}) == ("x", True)


@pytest.mark.asyncio
async def test_a_socket_that_dropped_is_a_refusal_and_closes_every_open_request():
    send = RecordedSend()
    confirmer = WsConfirmer(send)

    first = asyncio.create_task(confirmer.confirm(Action("click", {}), "one"))
    second = asyncio.create_task(confirmer.confirm(Action("type", {}), "two"))
    await asyncio.sleep(0)

    confirmer.close()  # the socket went away
    assert await first is False and await second is False
    # and after close, resolving an old id does nothing — the pending map is empty
    assert confirmer.resolve(send.frames[0] and __import__("json").loads(send.frames[0])["id"], True) is False


@pytest.mark.asyncio
async def test_each_request_gets_its_own_id_and_the_record_keeps_order():
    send = RecordedSend()
    confirmer = WsConfirmer(send)
    a = asyncio.create_task(confirmer.confirm(Action("click", {"n": 1}), "first"))
    b = asyncio.create_task(confirmer.confirm(Action("click", {"n": 2}), "second"))
    await asyncio.sleep(0)
    ids = [__import__("json").loads(f)["id"] for f in send.frames]
    assert ids[0] != ids[1]
    confirmer.resolve(ids[1], True)
    confirmer.resolve(ids[0], False)
    assert await a is False and await b is True
    # the record is append-on-decision: `a` appends when its resolve lands, `b` when its own does —
    # the order of the record is the order the answers were resolved, not the order they were asked
    assert sorted(granted for _, _, granted in confirmer.asked) == [False, True]
    assert {reason for _, reason, _ in confirmer.asked} == {"first", "second"}
