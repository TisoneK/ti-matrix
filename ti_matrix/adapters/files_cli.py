"""Run a goal with no host application at all: the engine + the filesystem environment + any OpenAI-compatible model.

    python -m ti_matrix.adapters.files_cli --base-url http://localhost:11434/v1 --model qwen2.5:7b \
        "how many python files are under ~/code, and which of them are newest?"

A hosted model needs its key; pass it by NAME, never by value:  --api-key-env OPENAI_API_KEY
"""
import argparse
import asyncio
import json

from ti_matrix import EngineBudget, Goal, LLMEvaluator, LLMMoveProposer, StateEngine
from ti_matrix.adapters.files import FilesEnvironment
from ti_matrix.adapters.openai_compat import OpenAICompatModel


async def _main(goal_text: str, base_url: str, model: str, api_key_env: str, as_json: bool, max_calls: int) -> None:
    env = FilesEnvironment()
    port = OpenAICompatModel(base_url, model, api_key_env=api_key_env or None)
    engine = StateEngine(
        env,
        proposer=LLMMoveProposer(port, env.tools()),
        evaluator=LLMEvaluator(port),
        budget=EngineBudget(max_model_calls=max_calls),
    )
    async for ev in engine.run(Goal(goal_text)):
        print(json.dumps(ev.to_dict(), ensure_ascii=False) if as_json else f"[{ev.kind}] {ev.data}")


def _args(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("goal")
    ap.add_argument("--base-url", default="http://localhost:11434/v1", help="any OpenAI-compatible endpoint")
    ap.add_argument("--model", default="qwen2.5:7b")
    ap.add_argument("--api-key-env", default="OPENAI_API_KEY", help="the NAME of the env var holding the key")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--budget-calls", type=int, default=12)
    return ap.parse_args(argv)


if __name__ == "__main__":
    a = _args()
    asyncio.run(_main(a.goal, a.base_url, a.model, a.api_key_env, a.json, a.budget_calls))
