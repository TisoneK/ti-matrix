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
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self._api_key = api_key or (os.environ.get(api_key_env or "", "") or None)  # the one env read, in the adapter
        self._timeout_s = timeout_s

    def _payload(self, prompt: str, max_chars: int) -> bytes:
        body = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.2,
            # ask for the whole answer, but never unbounded: the engine parses JSON out of it
            "max_tokens": max(256, min(4096, max_chars // 2)),
        }
        return json.dumps(body).encode("utf-8")

    def _post(self, payload: bytes) -> str:
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
        return str(choices[0].get("message", {}).get("content") or "")

    async def complete(self, prompt: str, *, max_chars: int = 4000) -> str:
        text = await asyncio.to_thread(self._post, self._payload(prompt, max_chars))
        return text[:max_chars]
