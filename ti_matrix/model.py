"""The model's two jobs: propose actions, and judge outcomes — over a ``ModelPort``. It never owns the state.

Both are *seats*, not ingredients: ``StateEngine`` takes any object with ``propose`` or ``evaluate``, and the
engine's own tests drive it with plain classes and no model at all. What a model buys in a seat is judgment
about a world you cannot enumerate in code; what it costs is a round trip per round. Put your own rule in
either seat and that seat becomes instant and free — which is the whole difference between an engine that can
only drive slow, unstructured worlds and one that can drive a spread check.

Both are written against a ``ModelPort`` — anything that can answer a prompt with text:

    class ModelPort(Protocol):
        async def complete(self, prompt: str, *, max_chars: int = 4000) -> str: ...

The port is the whole model dependency of the engine. A host supplies one (over its own provider client,
a stdlib HTTP call, or a scripted string in a test).
"""
from __future__ import annotations

import json
import re
from typing import Optional, Protocol, Sequence, runtime_checkable

from ti_matrix.protocols import Action, ActionSpec, Evaluation, Observation, render_action_specs
from ti_matrix.state import AgentState

# The environment bounds a probe result; the evaluator must see (nearly) all of it — a 900-char view hid
# the answer inside a 24-entry listing and every outcome scored 0 (live, 2026-09-21).
_EVAL_VIEW_CHARS = 2800


@runtime_checkable
class ModelPort(Protocol):
    """One prompt in, text out. The engine's entire model dependency."""

    async def complete(self, prompt: str, *, max_chars: int = 4000) -> str: ...


_DRIVE_PATH = re.compile(r"[A-Za-z]:\\[^\\]")  # C:\x — a drive path written with SINGLE backslashes
_SINGLE_BACKSLASH = re.compile(r"(?<!\\)\\(?!\\)")
_LONE_BACKSLASH = re.compile(r'\\(?!["\\/bfnrtu])')


def parse_json(text: str) -> Optional[dict]:
    """First JSON object in ``text`` (models wrap it in fences or prose).

    Windows paths arrive as ``C:\\Users\\me\\notes`` with SINGLE backslashes. Some of those are invalid JSON
    escapes (``\\U``) and some are valid but wrong (``\\n`` would silently become a newline), so when a drive path
    with single backslashes is present every lone backslash is doubled first."""
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if not m:
        return None
    raw = m.group(0)
    if _DRIVE_PATH.search(raw):
        candidates = (_SINGLE_BACKSLASH.sub(r"\\\\", raw), raw)
    else:
        candidates = (raw, _LONE_BACKSLASH.sub(r"\\\\", raw))
    for candidate in candidates:
        try:
            obj = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        return obj if isinstance(obj, dict) else None
    return None


class LLMMoveProposer:
    """Asks the model for a few different next actions, dropping anything already ruled out."""

    def __init__(self, model: ModelPort, specs: dict[str, ActionSpec]) -> None:
        self._model, self._specs = model, specs

    async def propose(self, state: AgentState, n: int, avoid: set[str]) -> list[Action]:
        prompt = (
            "You plan the next steps toward a goal. Propose up to "
            f"{n} DIFFERENT next actions, each using one available action. Prefer actions that reveal "
            "the most about the goal. Do not repeat an action already tried.\n\n"
            f"{state.render()}\n\nACTIONS:\n{render_action_specs(self._specs)}\n\n"
            'Reply with JSON only: {"moves": [{"tool": "<name>", "args": {...}, "why": "<short>"}]}'
        )
        obj = parse_json(await self._model.complete(prompt)) or {}
        moves: list[Action] = []
        for raw in obj.get("moves", []) if isinstance(obj.get("moves"), list) else []:
            if not isinstance(raw, dict) or not isinstance(raw.get("tool"), str):
                continue
            args = raw.get("args") if isinstance(raw.get("args"), dict) else {}
            mv = Action(raw["tool"].strip(), args, str(raw.get("why", ""))[:120])
            if mv.fingerprint() not in avoid and all(mv.fingerprint() != m.fingerprint() for m in moves):
                moves.append(mv)
        return moves[:n]


class LLMEvaluator:
    """Scores a whole fan of outcomes in ONE call, with the deterministic guards the search relies on."""

    def __init__(self, model: ModelPort, specs: Optional[dict[str, ActionSpec]] = None) -> None:
        self._model = model
        self._specs = specs or {}

    async def evaluate(self, state: AgentState, outcomes: Sequence[Observation]) -> list[Evaluation]:
        blocks = []
        for i, o in enumerate(outcomes):
            mark = " (PREDICTED, not real)" if o.predicted else ""
            blocks.append(f"[{i}] {o.move.label()} -> {'ok' if o.ok else 'FAILED'}{mark}\n{o.text[:_EVAL_VIEW_CHARS]}")
        prompt = (
            f"{state.render()}\n\nCandidate outcomes (real tool results):\n" + "\n\n".join(blocks) + "\n\n"
            "For EACH outcome give progress 0..1 = the share of what the goal needs that is known once this outcome "
            "is added (a real, relevant result is > 0 even if more is needed; a FAILED outcome is 0). "
            "done=true only if the known facts PLUS that outcome fully settle the goal; then put the final "
            "answer in `answer`, using only facts shown above.\n"
            'Reply with JSON only: {"evals": [{"i": 0, "progress": 0.0, "done": false, "answer": "", "reason": ""}]}'
        )
        obj = parse_json(await self._model.complete(prompt)) or {}
        by_i: dict[int, Evaluation] = {}
        for raw in obj.get("evals", []) if isinstance(obj.get("evals"), list) else []:
            try:
                i = int(raw["i"])
                prog = min(1.0, max(0.0, float(raw.get("progress", 0))))
            except (KeyError, TypeError, ValueError):
                continue
            reason = str(raw.get("reason", ""))[:160]
            by_i[i] = Evaluation(prog, bool(raw.get("done")), str(raw.get("answer", "")), reason)
        out = []
        for i, o in enumerate(outcomes):
            ev = by_i.get(i, Evaluation())
            # Deterministic guards: a failed probe never counts; "done" needs a grounded answer, a real
            # (not predicted) outcome, and — when the tool table says so — a direct look rather than
            # only a search hit: finding a candidate is not the same as having examined it.
            if not o.ok:
                ev = Evaluation(0.0, False, "", ev.reason or "probe failed")
            elif ev.done and (not ev.answer.strip() or o.predicted):
                ev = Evaluation(ev.progress, False, "", "done without a grounded answer")
            elif ev.done and self._specs.get(o.move.tool, ActionSpec("", "")).surface_only:
                ev = Evaluation(ev.progress, False, "", "done needs a direct look, not just a search hit")
            out.append(ev)
        return out


_SYNTH_CHARS = 1200  # room for a short answer, not an essay


class LLMSynthesizer:
    """Asks the model what the facts a run established amount to, when it stopped without settling.

    Plain text rather than JSON, because this is the last thing a run says: it is read by a person, or by
    whatever called the run, and the engine never parses it. The prompt's one hard rule is that the answer comes
    from the facts shown and says what is missing when they are not enough — an answer invented here would be
    the single thing this engine exists to prevent.
    """

    def __init__(self, model: ModelPort) -> None:
        self._model = model

    async def answer(self, state: AgentState) -> str:
        constraints = f"CONSTRAINTS: {'; '.join(state.goal.constraints)}\n" if state.goal.constraints else ""
        facts = "\n".join(f"- {fact}" for fact in state.facts) or "- (the run established nothing)"
        prompt = (
            f"GOAL: {state.goal.text}\n{constraints}\n"
            "The run has stopped without settling the goal. Using ONLY these facts, answer the goal as far as "
            "they allow, and if they cannot answer it say plainly what is missing. Do not invent anything that "
            "is not in them, and do not claim the goal is settled.\n\n"
            f"FACTS:\n{facts}\n\nAnswer:"
        )
        return " ".join((await self._model.complete(prompt, max_chars=_SYNTH_CHARS)).split())
