"""Writing a run down, and reading it afterwards.

Every step of a run is already an `EngineEvent` — the engine's whole record of states, actions, outcomes and
decisions, with no hidden reasoning in it. What was missing is that nothing kept them: a run existed while it
printed and then it was gone, so it could not be audited, compared, or looked at again.

Two functions and a summary. One line per event, so the file is greppable and `jq`-able and diffable; reading
it back gives the same dicts the engine emitted. This is a run's *record*, not its state — resuming a run means
saving the state it reached, which is a different thing and is not pretended here.

    python -m ti_matrix.adapters.run_log PATH      # what happened in this run
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable, Optional

# What a reader wants first, and how much of it: the ending, then what it did, then what it knew.
_HEADLINE = ("done", "stopped")


def write(path: str | Path, event: Any) -> None:
    """Append one event to a run's log. Takes an ``EngineEvent`` or the dict it turns into."""
    body = event.to_dict() if hasattr(event, "to_dict") else dict(event)
    with Path(path).expanduser().open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(body, ensure_ascii=False, default=str) + "\n")


def read(path: str | Path) -> list[dict]:
    """Every event in a run's log, in the order they happened. A torn last line is skipped, not fatal."""
    events: list[dict] = []
    for line in Path(path).expanduser().read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            events.append(json.loads(line))
        except ValueError:
            continue  # a run killed mid-write leaves half a line; the rest of the run is still worth reading
    return events


def summarize(events: Iterable[dict], *, excerpt: int = 200) -> str:
    """A run in a few lines: how it ended, what it did, what it cost, and what it established."""
    events = list(events)
    if not events:
        return "this run log is empty"
    ending = next((e for e in reversed(events) if e.get("kind") in _HEADLINE), None)
    probes = [e for e in events if e.get("kind") == "probe"]
    decided = [e for e in events if e.get("kind") == "confirmation"]
    backtracks = [e for e in events if e.get("kind") == "backtrack"]
    calls = (ending or {}).get("model_calls")
    lines = [f"{len(events)} events"
             + (f", {calls} model calls" if isinstance(calls, int) else "")
             + f", {len(probes)} probes, {len(backtracks)} backtracks"
             + (f", {len(decided)} confirmation(s)" if decided else "")]
    if ending is None:
        lines.append("it never ended — the log stops before a done or stopped event")
    elif ending["kind"] == "done":
        lines.append(f"settled: {str(ending.get('answer'))[:excerpt]}")
    else:
        lines.append(f"NOT settled: {ending.get('reason')}"
                     + (f" (it would need: {ending['needs']})" if ending.get("needs") else ""))
        if ending.get("partial_answer"):
            lines.append(f"best answer from what it read — {ending.get('answer_basis')}:")
            lines.append(f"  {str(ending['partial_answer'])[:excerpt * 2]}")
    for event in decided:
        lines.append(f"  {'granted' if event.get('granted') else 'refused'}: {event.get('move')}"
                     f" — {str(event.get('why'))[:120]}")
    if probes:
        lines.append("probes, in order:")
        lines += [f"  {'ok ' if p.get('ok') else 'FAILED'} {p.get('move')}"
                  + (" (predicted)" if p.get("predicted") else f" — {str(p.get('excerpt'))[:excerpt]}")
                  for p in probes]
    facts = (ending or {}).get("facts") or []
    if facts:
        lines.append(f"facts established ({len(facts)}):")
        lines += [f"  {str(f)[:excerpt]}" for f in facts]
    return "\n".join(lines)


def main(argv: Optional[list[str]] = None) -> int:
    import argparse

    ap = argparse.ArgumentParser(description="read a run's log back")
    ap.add_argument("path", help="the file a run was recorded to")
    ap.add_argument("--json", action="store_true", help="the events, as they are on disk")
    args = ap.parse_args(argv)
    events = read(args.path)
    if args.json:
        for event in events:
            print(json.dumps(event, ensure_ascii=False))
        return 0
    print(summarize(events))
    return 0 if events else 1


if __name__ == "__main__":
    raise SystemExit(main())
