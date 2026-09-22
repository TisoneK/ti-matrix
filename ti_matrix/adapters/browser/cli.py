"""Run a goal against a real browser, from the shell — the browser adapter's own front door.

    python -m ti_matrix.adapters.browser.cli "what does this page say about refunds?" \\
        --url https://example.com/docs --base-url http://localhost:11434/v1 --model qwen2.5:7b

By default the engine may *read* the page and nothing more: text, links, markup, a selector's existence, a
screenshot. `--perform click,type` grants the actions that change something, and the run will then carry them
out — which is a real decision, so it is a flag you have to type rather than a default you inherit.

    --headless off     watch the browser work instead of hiding it
    --attach 127.0.0.1:9222   drive a browser you started yourself
    --shots DIR        where screenshots go (they are for you: the engine reads text)
    --remember FILE    learn across runs: read the record, order proposals by it, offer `recall`, save it back
    --record FILE      write the run down, then read it: python -m ti_matrix.adapters.run_log FILE
    --ask click,type   ask me before these actions — per action, with the model's reason, at the moment
    --profile DIR      keep a browser profile between runs, so a signed-in site stays signed in
"""
import argparse
import asyncio
import json
import sys

from ti_matrix import EngineBudget, Goal, LLMEvaluator, LLMSimulator, StateEngine
from ti_matrix.adapters.browser import BrowserEnvironment, find_browser
from ti_matrix.adapters.openai_compat import OpenAICompatModel
from ti_matrix.adapters.session import Session


async def _main(a) -> int:
    if find_browser() is None and a.attach is None and a.binary is None:
        print("no Chrome or Chromium found — install one, or point --binary/--attach at a browser you have",
              file=sys.stderr)
        return 2
    offered = {name.strip() for name in (a.only or "").split(",") if name.strip()}
    env = BrowserEnvironment(
        a.url,
        perform={name.strip() for name in (a.perform or "").split(",") if name.strip()},
        only=offered or None,
        headless=a.headless != "off", attach_to=a.attach, binary=a.binary, screenshot_dir=a.shots,
        user_data_dir=a.profile,
    )
    reads = sum(1 for spec in env.tools().values() if spec.read_only)
    print(f"# {reads} of {len(env.tools())} actions may be performed unasked; "
          f"the rest are refused unless --perform names them", file=sys.stderr)
    port = OpenAICompatModel(a.base_url, a.model, api_key_env=a.api_key_env or None, timeout_s=a.timeout)
    session = Session(remember=a.remember, record=a.record, ask=a.ask)
    env = session.environment(env)
    engine = StateEngine(
        env,
        proposer=session.proposer(port, env.tools()),
        evaluator=LLMEvaluator(port),
        simulator=LLMSimulator(port),  # so a refused click is judged instead of only reported
        confirmer=session.confirmer(env.tools()),
        budget=EngineBudget(max_model_calls=a.budget_calls),
    )
    # The state a run renders says nothing about where the browser is, so a model with no fact yet will
    # happily navigate somewhere it invented — from the example URL in an action's description, in the run
    # that found this. A constraint is the engine's own way of telling it where it already stands.
    constraints = (f"the browser is already open at {a.url} — read that page; do not navigate elsewhere "
                   f"unless the goal needs it",) if a.url and a.url != "about:blank" else ()
    try:
        async for event in engine.run(Goal(a.goal, constraints)):
            session.observe(event)
            print(json.dumps(event.to_dict(), ensure_ascii=False) if a.json
                  else f"[{event.kind}] {event.data}")
    finally:
        note = session.save()
        if note:
            print(note, file=sys.stderr)
        env.close()  # the browser this started stops with the run
    return 0


def _args(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("goal")
    ap.add_argument("--url", default="about:blank", help="the page to start on")
    ap.add_argument("--perform", default="", help="actions this run may carry out: click,type,press,evaluate")
    ap.add_argument("--only", default="", help="offer only these actions, comma separated. Every tool in the "
                                              "prompt costs a local model time on every single call")
    ap.add_argument("--headless", default="on", help="'off' to watch the browser work")
    ap.add_argument("--attach", default=None, help="drive a browser already listening at host:port")
    ap.add_argument("--binary", default=None, help="the browser to start, if it is not where we look")
    ap.add_argument("--shots", default=None, help="where screenshots are written")
    ap.add_argument("--profile", default=None,
                    help="a browser profile to keep between runs (logins survive; you delete it)")
    ap.add_argument("--base-url", default="http://localhost:11434/v1")
    ap.add_argument("--model", default="qwen2.5:7b")
    ap.add_argument("--api-key-env", default="OPENAI_API_KEY")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--timeout", type=float, default=120.0,
                    help="seconds to wait on one model call; raise it for a big local model")
    ap.add_argument("--budget-calls", type=int, default=12)
    ap.add_argument("--remember", default=None,
                    help="a file of what earlier runs learned here: read it, learn into it, save it back")
    ap.add_argument("--record", default=None, help="write every event to this file, one JSON line each")
    ap.add_argument("--ask", default=None,
                    help="ask before performing these actions, comma separated; nobody at the terminal, or a "
                         "blank answer, is a refusal")
    return ap.parse_args(argv)


def main(argv=None) -> int:
    return asyncio.run(_main(_args(argv)))


if __name__ == "__main__":
    sys.exit(main())
