"""The wire protocol between the desktop app and the sidecar — one version, named, with its own tests.

The app and the sidecar are shipped separately (an Electron bundle and a PyInstaller bundle), so the only
thing they may assume about each other is this file. `PROTOCOL` is the version of the handshake line and
every frame shape here; an app that reads `TM1` speaks everything below and nothing else.

The handshake. The sidecar binds loopback on an ephemeral port, mints a one-time token, and prints one
line — `TM1 <port> <token>` — then flushes. The app's main process reads it, health-checks, and hands
`port` + `token` to the renderer. Nobody else on the machine ever sees the token: it is only ever spoken
over the loopback socket this process owns.

The frames. `EngineEvent.to_dict()` is the event payload verbatim — `ti_matrix.adapters.run_log` already
reads that shape, so a run streamed here and a run written to disk are the same record, and nothing was
invented. The two frames the engine does not emit are the ones the confirmer needs: a `confirm-request`
the server sends when the engine asks to change the world, and the `confirm-response` that answers it.

Client → server:
    {"type": "goal",   "text": str, "world": str, "config": {...}, "budget": {...}?,
                        "remember": path?, "record": path?}
    {"type": "confirm-response", "id": str, "granted": bool}
    {"type": "stop"}

Server → client:
    {"type": "event",             ...EngineEvent.to_dict()}
    {"type": "confirm-request",   "id": str, "action": {"tool", "args", "label"}, "reason": str}
    {"type": "settled",           "answer": str | null, "reason": str | null, "events": int,
                                  "summary": str | null, "record": str | null}
    {"type": "error",             "message": str}
    {"type": "worlds",            "worlds": [{...}]}          (answer to GET /worlds, also pushed here)
"""
from __future__ import annotations

import json
import re
import secrets
from typing import Any, Optional

PROTOCOL = 1  # the "1" in TM1; bumped only for a breaking frame change
LINE = re.compile(r"^TM(\d+) (\d+) ([0-9a-f]{32})$")  # TM<protocol> <port> <token>


def handshake_line(port: int, token: str, protocol: int = PROTOCOL) -> str:
    """The one line the sidecar prints for its parent process to read."""
    return f"TM{protocol} {port} {token}"


def parse_handshake(line: str) -> Optional[tuple[int, int, str]]:
    """(protocol, port, token) from a handshake line, or None when the line is not one."""
    m = LINE.match(line.strip())
    return None if m is None else (int(m.group(1)), int(m.group(2)), m.group(3))


def new_token() -> str:
    return secrets.token_hex(16)  # 32 hex chars, one run of the app


def encode(frame_type: str, **fields: Any) -> str:
    """One frame, as one line of JSON the socket carries as a single text message."""
    return json.dumps({"type": frame_type, **fields}, ensure_ascii=False, default=str)


def decode(raw: str | bytes) -> Optional[dict[str, Any]]:
    """One client frame, or None — a malformed frame is dropped, never a crash."""
    try:
        body = json.loads(raw if isinstance(raw, str) else raw.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return None
    return body if isinstance(body, dict) and isinstance(body.get("type"), str) else None


# The fields each client frame may carry. A frame with unknown fields is accepted and the extras
# ignored — forward compatibility beats strictness for a pair of surfaces shipped together.
GOAL_FIELDS = {"text", "world", "config", "budget", "remember", "record"}
BUDGET_FIELDS = {"max_depth", "max_branches", "max_model_calls", "max_backtracks"}


def parse_goal(body: dict[str, Any]) -> tuple[str, str, dict[str, Any], dict[str, int]]:
    """(text, world, config, budget) from a `goal` frame's fields, with the noisy parts dropped.

    Raises ValueError when the frame cannot name a goal — the one client mistake worth reporting
    rather than dropping.
    """
    text = str(body.get("text", "")).strip()
    world = str(body.get("world", "")).strip()
    if not text:
        raise ValueError("a goal frame needs text")
    if not world:
        raise ValueError("a goal frame needs world")
    config = body.get("config")
    config = dict(config) if isinstance(config, dict) else {}
    budget_in = body.get("budget")
    budget: dict[str, int] = {}
    if isinstance(budget_in, dict):
        budget = {k: int(v) for k, v in budget_in.items() if k in BUDGET_FIELDS and isinstance(v, (int, float))}
    return text, world, config, budget
