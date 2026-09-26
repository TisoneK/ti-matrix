"""Orient from a repository's Context Ledger, run a goal against it, and record what the run established.

    python -m ti_matrix.adapters.ledger_cli --base-url http://localhost:11434/v1 --model qwen2.5:7b \
        --vault . "what is in flight in this project, and what did the last session leave open?"

The run reads the ledger and nothing else — every action this environment offers is read-only, so the
search can look anywhere in the project's memory and change nothing. When it ends, what it established
is appended back: the run's detail (facts, dead ends, answer) into the office's session notes, and the
durable facts into the parking lot's Findings, where the next session's reading order finds them.

    --no-record   leave the vault untouched (a look-only run)
    --dry-run     print exactly what would be appended, then leave the vault untouched

A hosted model needs its key; pass it by NAME, never by value:  --api-key-env OPENAI_API_KEY
    --model builtin   the world's own rule-based reasoner — no endpoint, no key, no network at all
"""
import argparse
import asyncio
import json
import sys

from ti_matrix import EngineBudget, Goal, StateEngine
from ti_matrix.adapters.context_ledger import LedgerEnvironment, LedgerRecorder
from ti_matrix.adapters.openai_compat import OpenAICompatModel
from ti_matrix.adapters.session import Session


async def _main(a) -> int:
    env = LedgerEnvironment(a.vault)
    if not env.vault.exists():
        print(f"no Context Ledger at {env.vault} — bootstrap one first, or point --vault at a project "
              f"that has `.context_ledger/`", file=sys.stderr)
        return 2
    # No `ask=` here: this environment's write actions are declared so the engine can reason about them,
    # and `LedgerRecorder` performs them after the run rather than the engine asking mid-run. `_args` never
    # defines `--ask` for that reason (see its own comment below) — passing `a.ask` crashed every
    # invocation with `AttributeError: 'Namespace' object has no attribute 'ask'` before this fix.
    session = Session(remember=a.remember, record=a.record)
    env = session.environment(env)
    seats = session.seats("ledger", env, a.model,
                          lambda: OpenAICompatModel(a.base_url, a.model, api_key_env=a.api_key_env or None,
                                                    timeout_s=a.timeout),
                          want_simulator=True)  # the vault's write actions are declared: judge, don't perform
    engine = StateEngine(
        env,
        proposer=seats.proposer,
        evaluator=seats.evaluator,
        synthesizer=seats.synthesizer,
        simulator=seats.simulator,
        budget=EngineBudget(max_model_calls=a.budget_calls),
    )
    recorder = LedgerRecorder(env.vault, agent=a.agent, model=a.model)
    try:
        async for ev in engine.run(Goal(a.goal)):
            recorder.observe(ev)
            session.observe(ev)
            print(json.dumps(ev.to_dict(), ensure_ascii=False) if a.json else f"[{ev.kind}] {ev.data}")
    finally:
        for note in (session.save(), await session.usage_note(seats.model, balance=a.balance)):
            if note:
                print(note, file=sys.stderr)
    if not a.no_record:
        write = recorder.record(dry_run=a.dry_run)
        print(write.to_text() if not a.json else json.dumps(
            {"run_notes": write.run_notes, "findings": list(write.findings),
             "skipped": list(write.skipped), "dry_run": write.dry_run}))
    return 0


def _args(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("goal")
    ap.add_argument("--vault", default=".", help="the project holding .context_ledger/ (or that directory)")
    ap.add_argument("--base-url", default="http://localhost:11434/v1", help="any OpenAI-compatible endpoint")
    ap.add_argument("--model", default="qwen2.5:7b", help="'builtin' runs the rule-based reasoner instead")
    ap.add_argument("--api-key-env", default="OPENAI_API_KEY", help="the NAME of the env var holding the key")
    ap.add_argument("--agent", default="Ti Matrix", help="the name this run is recorded under")
    ap.add_argument("--balance", action="store_true",
                    help="after the run, print what the account has left (DeepSeek endpoints only)")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--timeout", type=float, default=120.0,
                    help="seconds to wait on one model call; raise it for a big local model")
    ap.add_argument("--budget-calls", type=int, default=12)
    ap.add_argument("--no-record", action="store_true", help="do not write the run back into the ledger")
    ap.add_argument("--dry-run", action="store_true", help="print what would be written, write nothing")
    ap.add_argument("--remember", default=None,
                    help="a file of what earlier runs learned here: read it, learn into it, save it back")
    ap.add_argument("--record", default=None, help="write every event to this file, one JSON line each")
    # No --ask here on purpose: this environment's write actions are declared so the engine can reason about
    # them, and LedgerRecorder performs them after the run — not the engine. There is nothing to ask about,
    # and a flag that cannot change anything is a lie in the help text.
    return ap.parse_args(argv)


def main(argv=None) -> int:
    return asyncio.run(_main(_args(argv)))


if __name__ == "__main__":
    sys.exit(main())
