"""Run a goal with no host application at all: the engine + the filesystem environment + any OpenAI-compatible model.

    python -m ti_matrix.adapters.files_cli --base-url http://localhost:11434/v1 --model qwen2.5:7b \
        "how many python files are under ~/code, and which of them are newest?"

A hosted model needs its key; pass it by NAME, never by value:  --api-key-env OPENAI_API_KEY

    --model builtin   the world's own rule-based reasoner — no endpoint, no key, no network at all. Unlike a
                      real model, it cannot invent a starting path from the goal's own words, so it needs
                      --root to know where to make its first move; --help prints the directory it defaults
                      to on this machine.
"""
import argparse
import asyncio
import json
import sys
from pathlib import Path

from ti_matrix import EngineBudget, Goal, StateEngine
from ti_matrix.adapters.builtin import is_builtin
from ti_matrix.adapters.files import FilesEnvironment
from ti_matrix.adapters.openai_compat import OpenAICompatModel
from ti_matrix.adapters.session import Session


class _RootedFiles(FilesEnvironment):
    """`FilesEnvironment` plus the one fact `FilesReasoner` cannot do without: where to start.

    No path confinement — a real model already reads wherever the goal points it, unconfined, and this
    only exists to give the builtin reasoner a first move. A picker that must confine a chosen directory
    (the desktop app's world picker) has its own rooted subclass; this one is CLI-local.
    """

    def __init__(self, root: str) -> None:
        super().__init__()
        self.root = str(Path(root).expanduser().resolve())


async def _main(goal_text: str, base_url: str, model: str, api_key_env: str, as_json: bool, max_calls: int,
                timeout_s: float = 120.0, remember: str = "", record: str = "", balance: bool = False,
                root: str = "") -> None:
    # The builtin reasoner cannot infer a root from the goal text the way a real model can, so it gets the
    # home directory when nobody named one — the same default the app's files world uses, and a directory
    # that exists on every machine, unlike the one the command happened to be typed in. A real model's
    # behavior is unchanged either way.
    root = root or (str(Path.home()) if is_builtin(model) else "")
    session = Session(remember=remember, record=record)
    env = session.environment(_RootedFiles(root) if root else FilesEnvironment())
    seats = session.seats("files", env, model,
                          lambda: OpenAICompatModel(base_url, model, api_key_env=api_key_env or None,
                                                    timeout_s=timeout_s))
    engine = StateEngine(
        env,
        proposer=seats.proposer,
        evaluator=seats.evaluator,
        synthesizer=seats.synthesizer,
        budget=EngineBudget(max_model_calls=max_calls),
    )
    try:
        async for ev in engine.run(Goal(goal_text)):
            session.observe(ev)
            print(json.dumps(ev.to_dict(), ensure_ascii=False) if as_json else f"[{ev.kind}] {ev.data}")
    finally:
        for note in (session.save(), await session.usage_note(seats.model, balance=balance)):
            if note:
                print(note, file=sys.stderr)


def _args(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("goal")
    ap.add_argument("--base-url", default="http://localhost:11434/v1", help="any OpenAI-compatible endpoint")
    ap.add_argument("--model", default="qwen2.5:7b", help="'builtin' runs the rule-based reasoner instead")
    ap.add_argument("--api-key-env", default="OPENAI_API_KEY", help="the NAME of the env var holding the key")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--timeout", type=float, default=120.0,
                    help="seconds to wait on one model call; raise it for a big local model")
    ap.add_argument("--budget-calls", type=int, default=12)
    ap.add_argument("--remember", default=None,
                    help="a file of what earlier runs learned here: read it, learn into it, save it back")
    ap.add_argument("--record", default=None, help="write every event to this file, one JSON line each")
    ap.add_argument("--balance", action="store_true",
                    help="after the run, print what the account has left (DeepSeek endpoints only)")
    ap.add_argument("--root", default="",
                    help=f"give the builtin reasoner somewhere to start (default: {Path.home()}); "
                         "a real model ignores this and reads wherever the goal points it")
    return ap.parse_args(argv)


if __name__ == "__main__":
    a = _args()
    asyncio.run(_main(a.goal, a.base_url, a.model, a.api_key_env, a.json, a.budget_calls, a.timeout,
                      a.remember, a.record, a.balance, a.root))
