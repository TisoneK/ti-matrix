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
"""
import argparse
import asyncio
import json
import sys

from ti_matrix import EngineBudget, Goal, LLMEvaluator, LLMMoveProposer, StateEngine
from ti_matrix.adapters.context_ledger import LedgerEnvironment, LedgerRecorder
from ti_matrix.adapters.openai_compat import OpenAICompatModel


async def _main(a) -> int:
    env = LedgerEnvironment(a.vault)
    if not env.vault.exists():
        print(f"no Context Ledger at {env.vault} — bootstrap one first, or point --vault at a project "
              f"that has `.context_ledger/`", file=sys.stderr)
        return 2
    port = OpenAICompatModel(a.base_url, a.model, api_key_env=a.api_key_env or None)
    engine = StateEngine(
        env,
        proposer=LLMMoveProposer(port, env.tools()),
        evaluator=LLMEvaluator(port),
        budget=EngineBudget(max_model_calls=a.budget_calls),
    )
    recorder = LedgerRecorder(env.vault, agent=a.agent, model=a.model)
    async for ev in engine.run(Goal(a.goal)):
        recorder.observe(ev)
        print(json.dumps(ev.to_dict(), ensure_ascii=False) if a.json else f"[{ev.kind}] {ev.data}")
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
    ap.add_argument("--model", default="qwen2.5:7b")
    ap.add_argument("--api-key-env", default="OPENAI_API_KEY", help="the NAME of the env var holding the key")
    ap.add_argument("--agent", default="Ti Matrix", help="the name this run is recorded under")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--budget-calls", type=int, default=12)
    ap.add_argument("--no-record", action="store_true", help="do not write the run back into the ledger")
    ap.add_argument("--dry-run", action="store_true", help="print what would be written, write nothing")
    return ap.parse_args(argv)


def main(argv=None) -> int:
    return asyncio.run(_main(_args(argv)))


if __name__ == "__main__":
    sys.exit(main())
