"""A model port over any OpenAI-compatible chat endpoint — standard library only.

No provider SDK, no host configuration, no ambient state: the endpoint, the model and (optionally) an
environment variable holding the key are passed in by whoever constructs it. The key VALUE is never logged,
echoed or embedded in an error message.
"""
from __future__ import annotations

import asyncio
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Optional

_DEFAULT_TIMEOUT_S = 120.0

# The one provider named in this module's own docstring that publishes an account-balance endpoint.
# No OpenAI-compatible standard covers this, so `fetch_balance` is deliberately narrow rather than
# guessing at a path that might not exist on Groq, OpenRouter, Ollama or a plain OpenAI account.
_DEEPSEEK_HOST_SUFFIX = "deepseek.com"

# A reasoning model thinks before it writes, and `max_tokens` bounds the thinking and the answer TOGETHER. Sized
# for the answer alone, the budget can run out mid-thought: the call returns `finish_reason="length"` with EMPTY
# content, which the engine can only read as "the model proposed nothing" (live against deepseek-flash,
# 2026-09-22: 4 of 6 proposer calls at fan size 4, and the run stopped `no_moves` with `settled: false`). The
# allowance is additive, so the answer still gets the room `max_chars` asks for. Hosts whose model caps output
# below this (an older OpenAI model, say) can pass `reasoning_allowance=0`.
_DEFAULT_REASONING_ALLOWANCE = 8192


class OpenAICompatModel:
    """`POST {base_url}/chat/completions` — works with OpenAI, DeepSeek, Groq, OpenRouter, Ollama, vLLM, …"""

    def __init__(
        self,
        base_url: str,
        model: str,
        *,
        api_key: Optional[str] = None,
        api_key_env: Optional[str] = None,
        timeout_s: float = _DEFAULT_TIMEOUT_S,
        reasoning_allowance: int = _DEFAULT_REASONING_ALLOWANCE,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self._api_key = api_key or (os.environ.get(api_key_env or "", "") or None)  # the one env read, in the adapter
        self._timeout_s = timeout_s
        self._reasoning_allowance = max(0, reasoning_allowance)
        # Running totals across every call this instance has made — a host's own running counter, not a
        # billing record: a provider that omits `usage` from its response leaves the token fields at 0
        # while `calls` still counts, so a silent gap reads as "unknown" rather than "free".
        self.usage: dict[str, int] = {"calls": 0, "prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}

    def _max_tokens(self, max_chars: int) -> int:
        # The answer, plus room for a reasoning model to think its way to it.
        return max(256, min(4096, max_chars // 2)) + self._reasoning_allowance

    def _payload(self, prompt: str, max_tokens: int) -> bytes:
        body = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.2,
            # ask for the whole answer, but never unbounded: the engine parses JSON out of it
            "max_tokens": max_tokens,
        }
        return json.dumps(body).encode("utf-8")

    def _call(self, url: str, *, data: Optional[bytes] = None) -> dict[str, Any]:
        """One request, GET or POST, with the auth header and error shape every endpoint here shares."""
        headers = {}
        if data is not None:
            headers["Content-Type"] = "application/json"
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        req = urllib.request.Request(url, data=data, headers=headers, method="POST" if data is not None else "GET")
        try:
            with urllib.request.urlopen(req, timeout=self._timeout_s) as resp:  # noqa: S310 — the URL is the caller's choice
                raw = resp.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:300]
            raise RuntimeError(f"{exc.code} from {url}: {detail}") from None
        except urllib.error.URLError as exc:
            raise RuntimeError(f"cannot reach {url}: {exc.reason}") from None
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, dict) else {}

    def _record_usage(self, usage: object) -> None:
        """One call's token usage folded into the running total — `usage` is an OpenAI-compatible
        response's own `usage` object when the provider sends one, absent (`None`) otherwise."""
        self.usage["calls"] += 1
        if not isinstance(usage, dict):
            return
        for key in ("prompt_tokens", "completion_tokens", "total_tokens"):
            value = usage.get(key)
            if isinstance(value, int):
                self.usage[key] += value

    def _post(self, payload: bytes, max_tokens: int) -> str:
        data = self._call(f"{self.base_url}/chat/completions", data=payload)
        self._record_usage(data.get("usage"))
        choices = data.get("choices") or []
        if not choices:
            raise RuntimeError(f"no choices in the response: {json.dumps(data)[:200]}")
        choice = choices[0]
        content = (choice.get("message") or {}).get("content") or ""
        if not content.strip():
            # Never hand back "" as if it were an answer: the engine reads an empty answer as "the model had
            # no ideas" and stops honestly but WRONGLY, with nothing in the event log naming the real cause.
            finish = choice.get("finish_reason")
            if finish == "length":
                raise RuntimeError(
                    f"empty answer from {self.model}: it spent all {max_tokens} output tokens reasoning and "
                    f"never wrote one (raise reasoning_allowance, currently {self._reasoning_allowance})")
            raise RuntimeError(f"empty answer from {self.model} (finish_reason={finish!r})")
        return str(content)

    async def complete(self, prompt: str, *, max_chars: int = 4000) -> str:
        max_tokens = self._max_tokens(max_chars)
        text = await asyncio.to_thread(self._post, self._payload(prompt, max_tokens), max_tokens)
        return text[:max_chars]

    def usage_snapshot(self) -> dict[str, int]:
        """A copy of the running token totals across every call this instance has made so far."""
        return dict(self.usage)

    async def fetch_balance(self) -> Optional[dict[str, Any]]:
        """The account's remaining balance, when this port is talking to DeepSeek — `None` for any
        other host, since no OpenAI-compatible standard names a balance endpoint at all. Raises
        ``RuntimeError`` (never returns a guess) when DeepSeek itself refuses or cannot be reached,
        the same shape ``complete`` already reports a bad call in."""
        host = urllib.parse.urlparse(self.base_url).netloc
        if not host.endswith(_DEEPSEEK_HOST_SUFFIX):
            return None
        scheme = urllib.parse.urlparse(self.base_url).scheme or "https"
        return await asyncio.to_thread(self._call, f"{scheme}://{host}/user/balance")

    async def list_models(self) -> list[str]:
        """The model ids this endpoint currently offers, from the OpenAI-compatible ``GET /models`` —
        every provider named in this module's own docstring implements it, unlike the balance endpoint
        above. Raises ``RuntimeError`` on a bad call, the same shape ``complete`` and ``fetch_balance``
        already report one in; a response with no recognisable ``data`` list is an empty result, not an
        error — some hosts answer with nothing to offer yet, not with a malformed reply."""
        data = await asyncio.to_thread(self._call, f"{self.base_url}/models")
        items = data.get("data")
        if not isinstance(items, list):
            return []
        return sorted({str(it["id"]) for it in items if isinstance(it, dict) and it.get("id")})


def describe_balance(info: dict[str, Any]) -> str:
    """`fetch_balance`'s response, in the one line a CLI prints — DeepSeek's own shape, read back for a
    person rather than dumped as JSON. An unrecognised shape says so instead of guessing at a number."""
    infos = info.get("balance_infos")
    if not isinstance(infos, list) or not infos:
        return "(unrecognised balance response)"
    bits = ", ".join(f"{b.get('total_balance', '?')} {b.get('currency', '')}".strip()
                     for b in infos if isinstance(b, dict))
    if not info.get("is_available", True):
        bits += " (account not available for new calls)"
    return bits or "(unrecognised balance response)"
