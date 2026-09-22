"""Run a goal with no host application at all: the engine + the filesystem environment + any OpenAI-compatible model.

    python -m ti_matrix.adapters.files_cli --base-url http://localhost:11434/v1 --model qwen2.5:7b \
        "how many python files are under ~/code, and which of them are newest?"

A hosted model needs its key; pass it by NAME, never by value:  --api-key-env OPENAI_API_KEY
"""
import argparse
import asyncio
import json
import sys

from ti_matrix import EngineBudget, Goal, LLMEvaluator, StateEngine
from ti_matrix.adapters.files import FilesEnvironment
from ti_matrix.adapters.openai_compat import OpenAICompatModel
from ti_matrix.adapters.session import Session


async def _main(goal_text: str, base_url: str, model: str, api_key_env: str, as_json: bool, max_calls: int,
                timeout_s: float = 120.0, remember: str = "", record: str = "") -> None:
    port = OpenAICompatModel(base_url, model, api_key_env=api_key_env or None, timeout_s=timeout_s)
    session = Session(remember=remember, record=record)
    env = session.environment(FilesEnvironment())
    engine = StateEngine(
        env,
        proposer=session.proposer(port, env.tools()),
        evaluator=LLMEvaluator(port),
        synthesizer=session.synthesizer(port),
        budget=EngineBudget(max_model_calls=max_calls),
    )
    try:
        async for ev in engine.run(Goal(goal_text)):
            session.observe(ev)
            print(json.dumps(ev.to_dict(), ensure_ascii=False) if as_json else f"[{ev.kind}] {ev.data}")
    finally:
        note = session.save()
        if note:
            print(note, file=sys.stderr)


def _args(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("goal")
    ap.add_argument("--base-url", default="http://localhost:11434/v1", help="any OpenAI-compatible endpoint")
    ap.add_argument("--model", default="qwen2.5:7b")
    ap.add_argument("--api-key-env", default="OPENAI_API_KEY", help="the NAME of the env var holding the key")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--timeout", type=float, default=120.0,
                    help="seconds to wait on one model call; raise it for a big local model")
    ap.add_argument("--budget-calls", type=int, default=12)
    ap.add_argument("--remember", default=None,
                    help="a file of what earlier runs learned here: read it, learn into it, save it back")
    ap.add_argument("--record", default=None, help="write every event to this file, one JSON line each")
    return ap.parse_args(argv)


if __name__ == "__main__":
    a = _args()
    asyncio.run(_main(a.goal, a.base_url, a.model, a.api_key_env, a.json, a.budget_calls, a.timeout,
                      a.remember, a.record))
