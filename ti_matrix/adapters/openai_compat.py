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
import urllib.request
from typing import Optional

_DEFAULT_TIMEOUT_S = 120.0

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

    def _post(self, payload: bytes, max_tokens: int) -> str:
        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        req = urllib.request.Request(f"{self.base_url}/chat/completions", data=payload, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=self._timeout_s) as resp:  # noqa: S310 — the URL is the caller's choice
                raw = resp.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:300]
            raise RuntimeError(f"{exc.code} from {self.base_url}: {detail}") from None
        except urllib.error.URLError as exc:
            raise RuntimeError(f"cannot reach {self.base_url}: {exc.reason}") from None
        data = json.loads(raw)
        choices = data.get("choices") or []
        if not choices:
            raise RuntimeError(f"no choices in the response: {raw[:200]}")
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
