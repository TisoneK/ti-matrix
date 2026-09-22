"""Run a goal against a real browser, from the shell — the browser adapter's own front door.

    python -m ti_matrix.adapters.browser.cli "what does this page say about refunds?" \\
        --url https://example.com/docs --base-url http://localhost:11434/v1 --model qwen2.5:7b

By default the engine may *read* the page and nothing more: text, links, markup, a selector's existence, a
screenshot. `--perform click,type` grants the actions that change something, and the run will then carry them
out — which is a real decision, so it is a flag you have to type rather than a default you inherit.

    --headless off     watch the browser work instead of hiding it
    --attach 127.0.0.1:9222   drive a browser you started yourself
    --shots DIR        where screenshots go (they are for you: the engine reads text)
"""
import argparse
import asyncio
import json
import sys

from ti_matrix import EngineBudget, Goal, LLMEvaluator, LLMMoveProposer, LLMSimulator, StateEngine
from ti_matrix.adapters.browser import BrowserEnvironment, find_browser
from ti_matrix.adapters.openai_compat import OpenAICompatModel


async def _main(a) -> int:
    if find_browser() is None and a.attach is None and a.binary is None:
        print("no Chrome or Chromium found — install one, or point --binary/--attach at a browser you have",
              file=sys.stderr)
        return 2
    env = BrowserEnvironment(
        a.url, perform={name.strip() for name in (a.perform or "").split(",") if name.strip()},
        headless=a.headless != "off", attach_to=a.attach, binary=a.binary, screenshot_dir=a.shots,
    )
    reads = sum(1 for spec in env.tools().values() if spec.read_only)
    print(f"# {reads} of {len(env.tools())} actions may be performed unasked; "
          f"the rest are refused unless --perform names them", file=sys.stderr)
    port = OpenAICompatModel(a.base_url, a.model, api_key_env=a.api_key_env or None)
    engine = StateEngine(
        env,
        proposer=LLMMoveProposer(port, env.tools()),
        evaluator=LLMEvaluator(port),
        simulator=LLMSimulator(port),  # so a refused click is judged instead of only reported
        budget=EngineBudget(max_model_calls=a.budget_calls),
    )
    try:
        async for event in engine.run(Goal(a.goal)):
            print(json.dumps(event.to_dict(), ensure_ascii=False) if a.json
                  else f"[{event.kind}] {event.data}")
    finally:
        env.close()  # the browser this started stops with the run
    return 0


def _args(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("goal")
    ap.add_argument("--url", default="about:blank", help="the page to start on")
    ap.add_argument("--perform", default="", help="actions this run may carry out: click,type,press,evaluate")
    ap.add_argument("--headless", default="on", help="'off' to watch the browser work")
    ap.add_argument("--attach", default=None, help="drive a browser already listening at host:port")
    ap.add_argument("--binary", default=None, help="the browser to start, if it is not where we look")
    ap.add_argument("--shots", default=None, help="where screenshots are written")
    ap.add_argument("--base-url", default="http://localhost:11434/v1")
    ap.add_argument("--model", default="qwen2.5:7b")
    ap.add_argument("--api-key-env", default="OPENAI_API_KEY")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--budget-calls", type=int, default=12)
    return ap.parse_args(argv)


def main(argv=None) -> int:
    return asyncio.run(_main(_args(argv)))


if __name__ == "__main__":
    sys.exit(main())
