"""The desktop app's confirmer: the engine asks, the renderer answers, one round-trip.

The engine's whole contract is `Confirmer.confirm(action, reason) -> bool`, asked at the moment it
would perform something that changes the world. On the wire that moment becomes a `confirm-request`
frame and the run's fan pauses until the `confirm-response` with the same id comes back — which is the
whole feature: an Allow/Deny button in the app *is* the engine's confirmer.

`session.py --ask`'s rule carries over: nobody there to answer, or a socket that dropped, is a refusal.
The safe default is the one that has to be overridden deliberately.
"""
from __future__ import annotations

import asyncio
import uuid
from typing import Callable, Optional

from ti_matrix.protocols import Action


class WsConfirmer:
    """Implements the engine's Confirmer protocol over a frame callback and a reply future."""

    def __init__(self, send: Callable[[str], None]) -> None:
        self._send = send
        self._pending: dict[str, asyncio.Future[bool]] = {}
        self.asked: list[tuple[str, str, bool]] = []  # what was decided, in order — the record

    async def confirm(self, action: Action, reason: str) -> bool:
        request_id = uuid.uuid4().hex[:12]
        loop = asyncio.get_running_loop()
        future: asyncio.Future[bool] = loop.create_future()
        self._pending[request_id] = future
        self._send(encode_confirm_request(request_id, action, reason))
        try:
            granted = await future
        except _SocketClosed:
            granted = False  # a dropped socket is a refusal — nobody there to say yes
        finally:
            self._pending.pop(request_id, None)
        self.asked.append((action.label(), reason, granted))
        return granted

    def resolve(self, request_id: str, granted: bool) -> bool:
        """A `confirm-response` arrived. False when the id is unknown, stale, or already answered."""
        future = self._pending.get(request_id)
        if future is None or future.done():
            return False
        future.set_result(granted)
        return True

    def close(self) -> None:
        """The socket went away: every open request is refused, the way `Ask` refuses a blank line."""
        for future in self._pending.values():
            if not future.done():
                future.set_exception(_SocketClosed())
        self._pending.clear()


class _SocketClosed(Exception):
    pass


def encode_confirm_request(request_id: str, action: Action, reason: str) -> str:
    from .protocol import encode

    return encode("confirm-request", id=request_id,
                  action={"tool": action.tool, "args": dict(action.args), "label": action.label()},
                  reason=reason)


def parse_confirm_response(body: dict) -> Optional[tuple[str, bool]]:
    """(id, granted) from a `confirm-response` frame, or None when it is malformed."""
    request_id = body.get("id")
    granted = body.get("granted")
    if not isinstance(request_id, str) or not isinstance(granted, bool):
        return None
    return request_id, granted
