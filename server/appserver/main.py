"""The sidecar: one loopback server, one run at a time, the engine's events as frames.

What this process is. The desktop app spawns it as a child, reads one line from its stdout —
`TM1 <port> <token>` — and from then on speaks only the frames in `protocol.py` over a WebSocket to
`ws://127.0.0.1:<port>/ws?token=<token>`. Everything else is bookkeeping around that: the two HTTP
endpoints a renderer needs besides the socket (`/healthz`, `/worlds`), and the one-run-at-a-time rule.

The engine is the same `StateEngine` the CLIs drive, and it knows nothing about the server around it:
the world comes from `worlds.py`, the model from the goal frame's config, the confirmer from
`confirm_ws.py`, and the run's events stream through `events.py` in exactly the shapes
`ti_matrix.adapters.run_log` writes to disk — the app's live view and the run's record are one format.

Learning and recording are per-goal flags, straight from `session.py`'s semantics: `remember` loads a
statistics file before the run and saves it back after (even when the run failed), `record` appends
every event as a JSON line. The frames carry paths because the sidecar has no opinions about where an
app keeps its files; the desktop app points both at its user-data directory.
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Optional

from aiohttp import WSMsgType, web

from . import events as events_mod
from . import protocol, worlds
from .confirm_ws import WsConfirmer, parse_confirm_response
from .protocol import decode, encode, parse_goal, parse_list_models

WS_AUTH = "token"


class RunState:
    """The one run this server may be driving, and what the socket handler needs to reach."""

    def __init__(self) -> None:
        self.task: Optional[asyncio.Task] = None
        self.stop = False
        self.environment: Any = None             # built by the goal frame, before the run starts
        self.confirmer = WsConfirmer(send=lambda frame: None)  # re-bound per socket
        self.recorder: Any = None                # the ledger's LedgerRecorder, when write-back was asked

    @property
    def running(self) -> bool:
        return self.task is not None and not self.task.done()


TOKEN_KEY: Any = web.AppKey("token", str)
RUN_KEY: Any = web.AppKey("run", RunState)


# ── building one run's engine ───────────────────────────────────────────────


def _build_engine(env: Any, config: dict[str, Any], budget_in: dict[str, int],
                  confirmer: WsConfirmer, stats_path: Optional[Path]):
    """The engine for one run: the model from config, the world from the registry, the learning record
    when a path for it exists — the wiring the CLIs do via `session.py`, stated plainly.

    Returns ``(engine, statistics, model)`` — ``model`` is the ``OpenAICompatModel`` a hosted run spends
    tokens through, or ``None`` for `builtin` (rule-based seats touch no network and have no usage to
    report). The caller reads its `usage_snapshot()` after the run for the `settled` frame."""
    from ti_matrix.adapters.builtin import is_builtin, reasoner_for
    from ti_matrix.learning import LearningProposer, Statistics
    from ti_matrix.search import EngineBudget, StateEngine
    from ti_matrix.tools import EngineTools

    model_name = str(config.get("model", "")).strip()
    world_name = str(config.get("world", "")).strip() or getattr(env, "name", "")

    # The environment first, and its memory, because wrapping changes the tool list — and the tool list
    # is what the model is shown. Building the seats before this is what made `recall` invisible: the
    # engine would answer the probe, and the model was never told the action existed.
    statistics = Statistics()
    remembering = stats_path is not None
    if remembering:
        from ti_matrix.adapters import stats_file
        if stats_path.exists():
            statistics = stats_file.load(stats_path)
    # Always wrapped, whether or not anything is remembered across runs. The wrapper's other half is the
    # within-run record, which needs no storage and no setting: it is built from the probes passing
    # through it, and it is how a model asks for the part of what it has learned that it needs instead
    # of being handed the whole list. `memory=` adds earlier runs on top when a host asked for them.
    environment = EngineTools(env, memory=statistics if remembering else None)

    # The two seats. `builtin` fills them with rules and touches no network, so a window with no
    # endpoint configured still produces a real run rather than one `stopped: proposer_error`. Any
    # other model name is an OpenAI-compatible endpoint, exactly as before.
    model: Optional[Any] = None
    synthesizer: Optional[Any] = None
    if is_builtin(model_name):
        reasoner = reasoner_for(world_name, env.tools(), env)
        seats: tuple[Any, Any] = (reasoner, reasoner)
    else:
        from ti_matrix.adapters.openai_compat import OpenAICompatModel
        from ti_matrix.model import LLMEvaluator, LLMMoveProposer, LLMSynthesizer

        base_url = str(config.get("base_url", "")).strip()
        if not base_url or not model_name:
            raise ValueError("the goal config needs base_url and model (any OpenAI-compatible "
                             "endpoint) — or model 'builtin' to run with no model at all")
        key_env = str(config.get("api_key_env", "")).strip()
        # A key pasted into the window rides the run config directly — it wins over the env var, and
        # never outlives the run: it is read here, given to the adapter, and nothing writes it down.
        api_key = str(config.get("api_key", "")).strip() or None
        model = OpenAICompatModel(base_url, model_name, api_key=api_key, api_key_env=key_env or None)
        # `environment.tools()`, not `env.tools()` — with memory on this is the world's actions plus
        # `recall`, which is the one tool that lets a model ask what earlier runs established here
        # instead of re-deriving it. The rules above keep the raw world: they read every fact directly
        # and would only propose `recall()` with no arguments.
        seats = (LLMMoveProposer(model, environment.tools()), LLMEvaluator(model, environment.tools()))
        # Every CLI built on `session.py` wires this for a real model; the sidecar never did, so a
        # hosted run that gathered real, useful facts but never hit the evaluator's `done` stopped with
        # nothing to show for the tokens it spent — `stopped: no_progress` and a bare fact list, where
        # the CLIs would have asked the model what those facts amounted to. `builtin` still gets none:
        # a rule has no `.answer()` to call.
        synthesizer = LLMSynthesizer(model)

    budget_kwargs = {k: v for k, v in budget_in.items() if k in protocol.BUDGET_FIELDS}
    proposer: Any = seats[0]
    if stats_path is not None:
        proposer = LearningProposer(proposer, statistics)
    engine = StateEngine(environment, proposer=proposer, evaluator=seats[1], synthesizer=synthesizer,
                         confirmer=confirmer, budget=EngineBudget(**budget_kwargs))
    return engine, statistics, model


def _maybe_recorder(world_name: str, config: dict[str, Any]) -> Any:
    """No app world writes back any more — the Context Ledger world left the picker.

    Kept as the seam rather than deleted: `RunState.recorder` and the `settled` frame's `record` field
    are the general shape for "a run left something behind in its world", and the next world that does
    (a report written, a file moved) plugs in here. `ti_matrix.adapters.context_ledger.LedgerRecorder`
    still exists and `ledger_cli` still drives it; it is only the desktop app that no longer offers it.
    """
    return None


# ── the run's lifecycle on the socket ───────────────────────────────────────


async def _send_frame(ws: web.WebSocketResponse, frame: str) -> None:
    try:
        await ws.send_str(frame)
    except Exception:  # noqa: BLE001 — a socket that died mid-frame is not a crash
        pass


async def _run_goal(state: RunState, ws: web.WebSocketResponse, text: str, world_name: str,
                    config: dict[str, Any], budget_in: dict[str, int],
                    stats_path: Optional[Path], record_path: Optional[Path]) -> None:
    """Stream one goal to its end, then send the one `settled` frame that sums it up."""
    state.stop = False
    collected: list[dict[str, Any]] = []
    answer: Optional[str] = None
    reason: Optional[str] = None
    verified = False
    answer_basis: Optional[str] = None

    async def on_event(frame: dict[str, Any]) -> None:
        statistics.observe(_event_like(frame))  # in-run learning, whether or not it is persisted
        collected.append(dict(frame))
        if record_path is not None:
            from ti_matrix.adapters import run_log
            run_log.write(record_path, frame)
        await _send_frame(ws, encode("event", **frame))

    async def on_done(a: Optional[str], r: Optional[str], v: bool, b: Optional[str]) -> None:
        nonlocal answer, reason, verified, answer_basis
        answer, reason, verified, answer_basis = a, r, v, b

    try:
        engine, statistics, model = _build_engine(state.environment, config, budget_in,
                                                  state.confirmer, stats_path)
    except ValueError as exc:  # a config the engine cannot be built from is an error frame, not a dead task
        await _send_frame(ws, encode("error", message=str(exc)))
        return
    try:
        await events_mod.stream_run(engine, _goal(text), on_event=on_event,
                                    on_done=on_done, stop_requested=lambda: state.stop)
    except asyncio.CancelledError:
        # A client stop cancels the task: it unwinds to here, is recorded as stopped, and the
        # finally below still sends the settled frame with the same tail work any run gets.
        if reason is None and state.stop:
            reason = "stopped"
        raise
    except Exception as exc:  # noqa: BLE001 — a run's failure is a frame, not a dead task
        reason = f"error: {exc}"
    finally:
        learned = ""
        if stats_path is not None:
            from ti_matrix.adapters import stats_file
            stats_file.save(stats_path, statistics)
            learned = f"remembered: {len(statistics.by_tool)} tool(s) known in {stats_path}"
        recorded = None
        if state.recorder is not None:
            recorded = state.recorder.record(text).to_text()
        # `None` for `builtin` (no model, nothing spent) and for a hosted run whose endpoint never sent
        # a `usage` object — either way there is nothing honest to show, so the frame omits it rather
        # than reporting zeroes that would read as "this run cost nothing".
        usage = model.usage_snapshot() if model is not None and model.usage_snapshot()["calls"] else None
        await _send_frame(ws, encode(
            "settled",
            answer=answer, reason=reason, verified=verified, answer_basis=answer_basis,
            events=len(collected),
            summary=events_mod.events_digest(collected),
            record=recorded, learned=learned or None, usage=usage,
        ))


async def _list_models(ws: web.WebSocketResponse, body: dict[str, Any]) -> None:
    """Answer a `list-models` frame — independent of any run, so it never touches `RunState`.

    Its own `models-error` on failure, never the plain `error` frame: that one is a run's, and folding
    an unrelated config lookup into it would leave `useSidecar.ts` reading a "run" that never happened.
    """
    try:
        base_url, api_key, api_key_env = parse_list_models(body)
    except ValueError as exc:
        await _send_frame(ws, encode("models-error", message=str(exc)))
        return
    from ti_matrix.adapters.openai_compat import OpenAICompatModel

    model = OpenAICompatModel(base_url, "", api_key=api_key, api_key_env=api_key_env)
    try:
        models = await model.list_models()
    except RuntimeError as exc:
        await _send_frame(ws, encode("models-error", message=str(exc)))
        return
    await _send_frame(ws, encode("models", models=models))


def _goal(text: str):
    from ti_matrix.protocols import Goal
    return Goal(text)


def _event_like(frame: dict[str, Any]):
    """A wire frame reshaped as `Statistics.observe` expects it — it reads only kind and data."""
    return SimpleNamespace(kind=frame.get("kind"), data=frame)


# ── HTTP + WS handlers ──────────────────────────────────────────────────────


def _version() -> str:
    try:
        from importlib.metadata import version
        return version("ti-matrix-server")
    except Exception:  # noqa: BLE001 — a source checkout has no installed metadata
        return "0.1.0"


async def healthz(_request: web.Request) -> web.Response:
    return web.json_response({"ok": True, "protocol": protocol.PROTOCOL, "version": _version()})


async def worlds_handler(_request: web.Request) -> web.Response:
    return web.json_response({"worlds": worlds.describe()})


async def ws_handler(request: web.Request) -> web.WebSocketResponse:
    if request.query.get(WS_AUTH) != request.app[TOKEN_KEY]:
        ws = web.WebSocketResponse()
        await ws.prepare(request)  # complete the upgrade, then close it — there is no conversation
        await ws.close(code=1008, message=b"bad token")  # 1008: RFC 6455 policy violation
        return ws
    ws = web.WebSocketResponse(heartbeat=30)
    await ws.prepare(request)

    state: RunState = request.app[RUN_KEY]
    loop = asyncio.get_running_loop()
    state.confirmer = WsConfirmer(send=lambda frame: loop.create_task(_send_frame(ws, frame)))
    await _send_frame(ws, encode("worlds", worlds=worlds.describe()))

    async def start_goal(body: dict[str, Any]) -> None:
        try:
            text, world_name, config, budget_in = parse_goal(body)
            state.environment = worlds.build(world_name, config)
        except ValueError as exc:
            await _send_frame(ws, encode("error", message=str(exc)))
            return
        state.recorder = _maybe_recorder(world_name, config)
        stats = Path(str(body["remember"])).expanduser() if body.get("remember") else None
        record = Path(str(body["record"])).expanduser() if body.get("record") else None
        state.stop = False
        state.task = loop.create_task(
            _run_goal(state, ws, text, world_name, config, budget_in, stats, record))

    async for msg in ws:
        if msg.type == WSMsgType.TEXT:
            body = decode(msg.data)
            if body is None:
                continue  # a malformed frame is dropped, never a crash
            kind = body.get("type")
            if kind == "goal":
                if state.running:
                    await _send_frame(ws, encode("error",
                                                 message="a run is already in flight — stop it first"))
                else:
                    await start_goal(body)
            elif kind == "confirm-response":
                parsed = parse_confirm_response(body)
                if parsed is not None:
                    state.confirmer.resolve(*parsed)
            elif kind == "list-models":
                loop.create_task(_list_models(ws, body))
            elif kind == "stop":
                if state.running:
                    state.stop = True
                    state.task.cancel()  # a run waiting on the model stops now, not at its next event
                else:
                    await _send_frame(ws, encode("error", message="nothing is running"))
            else:
                await _send_frame(ws, encode("error", message=f"unknown frame type: {kind!r}"))
        elif msg.type in (WSMsgType.ERROR, WSMsgType.CLOSE, WSMsgType.CLOSING):
            break

    # The socket is gone: open confirmations are refusals, and a run in flight is finished
    # (tail-awaited) rather than abandoned mid-write to the learning record.
    state.confirmer.close()
    if state.running:
        state.stop = True
        state.task.cancel()
        try:
            await state.task
        except asyncio.CancelledError:
            pass
        except Exception:  # noqa: BLE001 — the run already reported itself; never crash the handler
            pass
    return ws


def create_app(token: str) -> web.Application:
    app = web.Application()
    app[TOKEN_KEY] = token
    app[RUN_KEY] = RunState()
    app.router.add_get("/healthz", healthz)
    app.router.add_get("/worlds", worlds_handler)
    app.router.add_get("/ws", ws_handler)
    return app


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="the ti-matrix desktop app's sidecar")
    ap.add_argument("--port", type=int, default=0, help="bind this port (default: an ephemeral one)")
    ap.add_argument("--quiet", action="store_true", help="do not print the handshake line")
    args = ap.parse_args(argv)

    # A parent process reads exactly one line from stdout — keep the pipe clean and encodable even
    # on a Windows console defaulting to cp1252.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    token = protocol.new_token()
    app = create_app(token)

    async def _serve() -> None:
        runner = web.AppRunner(app, access_log=None)
        await runner.setup()
        site = web.TCPSite(runner, "127.0.0.1", args.port)
        await site.start()
        bound = runner.addresses[0][1] if runner.addresses else args.port
        if not args.quiet:
            print(protocol.handshake_line(bound, token), flush=True)
        await asyncio.Event().wait()  # killed by the parent; nothing else ends this

    try:
        asyncio.run(_serve())
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
