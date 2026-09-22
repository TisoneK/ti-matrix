"""The model port: what it sends, and what it refuses to hand back.

A hosted endpoint is not available to a test, so `urlopen` is replaced with a canned reply. The module's whole
contract is one POST and one parse, so that is what these check — and one of them is a bug that reached a live
run: a reasoning model can spend its entire `max_tokens` thinking and return EMPTY content, which used to come
back as `""`, indistinguishable from "the model proposed nothing". The engine stopped `no_moves`, honestly but
wrongly. An empty completion is now an error that names the cause.
"""
from __future__ import annotations

import io
import json
import urllib.error
import urllib.request

import pytest

from ti_matrix.adapters.openai_compat import OpenAICompatModel


class FakeResponse:
    def __init__(self, body: bytes) -> None:
        self._body = body

    def read(self) -> bytes:
        return self._body

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, *exc: object) -> bool:
        return False


def reply(content: object, finish_reason: str = "stop") -> bytes:
    return json.dumps({"choices": [{"message": {"role": "assistant", "content": content},
                                    "finish_reason": finish_reason}]}).encode()


class Endpoint:
    """Stands in for the network: records the request, replies with whatever the test set."""

    def __init__(self) -> None:
        self.requests: list[urllib.request.Request] = []
        self.body = reply("hello")
        self.error: Exception | None = None

    def __call__(self, req, timeout=None):  # noqa: ANN001, ANN204 — mirrors urlopen's signature
        self.requests.append(req)
        if self.error is not None:
            raise self.error
        return FakeResponse(self.body)

    @property
    def payload(self) -> dict:
        return json.loads(self.requests[-1].data.decode("utf-8"))


@pytest.fixture()
def endpoint(monkeypatch) -> Endpoint:
    ep = Endpoint()
    monkeypatch.setattr(urllib.request, "urlopen", ep)
    return ep


# ─── what it sends ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_the_answer_comes_back_and_the_prompt_really_reached_the_body(endpoint):
    model = OpenAICompatModel("https://api.example.test/v1", "some-model")
    assert await model.complete("do the thing") == "hello"

    assert endpoint.requests[-1].full_url == "https://api.example.test/v1/chat/completions"
    assert endpoint.requests[-1].method == "POST"
    body = endpoint.payload
    assert body["model"] == "some-model"
    assert body["messages"] == [{"role": "user", "content": "do the thing"}]
    assert body["temperature"] == 0.2


@pytest.mark.asyncio
async def test_a_trailing_slash_on_the_base_url_does_not_double_up(endpoint):
    model = OpenAICompatModel("https://api.example.test/v1/", "m")
    await model.complete("x")
    assert endpoint.requests[-1].full_url == "https://api.example.test/v1/chat/completions"


@pytest.mark.asyncio
async def test_the_answer_is_capped_at_max_chars(endpoint):
    endpoint.body = reply("x" * 500)
    model = OpenAICompatModel("https://api.example.test/v1", "m")
    assert len(await model.complete("x", max_chars=100)) == 100


@pytest.mark.asyncio
async def test_max_tokens_leaves_room_for_a_reasoning_model_to_think(endpoint):
    """`max_tokens` bounds the thinking and the answer together, so the answer's room is additive."""
    model = OpenAICompatModel("https://api.example.test/v1", "m")
    await model.complete("x")  # default max_chars=4000 -> 2000 for the answer
    assert endpoint.payload["max_tokens"] == 2000 + 8192

    refuses = OpenAICompatModel("https://api.example.test/v1", "m", reasoning_allowance=0)
    await refuses.complete("x")
    assert endpoint.payload["max_tokens"] == 2000  # a host whose model caps output can opt out


# ─── the key: by NAME, never echoed ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_the_key_is_read_from_the_named_variable_and_sent_as_a_bearer(endpoint, monkeypatch):
    monkeypatch.setenv("TI_TEST_KEY", "sk-secret-value")
    model = OpenAICompatModel("https://api.example.test/v1", "m", api_key_env="TI_TEST_KEY")
    await model.complete("x")
    assert endpoint.requests[-1].get_header("Authorization") == "Bearer sk-secret-value"


@pytest.mark.asyncio
async def test_no_key_means_no_authorization_header(endpoint, monkeypatch):
    monkeypatch.delenv("TI_TEST_KEY", raising=False)
    model = OpenAICompatModel("https://api.example.test/v1", "m", api_key_env="TI_TEST_KEY")
    await model.complete("x")
    assert endpoint.requests[-1].get_header("Authorization") is None


@pytest.mark.asyncio
async def test_a_rejected_key_is_reported_without_echoing_the_key(endpoint):
    """The module promises the key value is never logged or embedded in an error message."""
    endpoint.error = urllib.error.HTTPError(
        "https://api.example.test/v1/chat/completions", 401, "Unauthorized", {},
        io.BytesIO(b'{"error":{"message":"Authentication Fails"}}'))
    model = OpenAICompatModel("https://api.example.test/v1", "m", api_key="sk-secret-value")
    with pytest.raises(RuntimeError) as err:
        await model.complete("x")
    assert "401" in str(err.value) and "Authentication Fails" in str(err.value)
    assert "sk-secret-value" not in str(err.value)


# ─── what it refuses to hand back ───────────────────────────────────────────


@pytest.mark.asyncio
async def test_an_empty_answer_is_an_error_not_an_empty_string(endpoint):
    """The regression that stopped a live run: truncated mid-thought, content empty, read as "no ideas"."""
    endpoint.body = reply("", finish_reason="length")
    model = OpenAICompatModel("https://api.example.test/v1", "deepseek-flash")
    with pytest.raises(RuntimeError) as err:
        await model.complete("x")
    text = str(err.value)
    assert "empty answer" in text and "reasoning" in text and "deepseek-flash" in text


@pytest.mark.asyncio
async def test_an_empty_answer_is_an_error_even_when_nothing_was_truncated(endpoint):
    endpoint.body = reply("", finish_reason="stop")
    model = OpenAICompatModel("https://api.example.test/v1", "m")
    with pytest.raises(RuntimeError) as err:
        await model.complete("x")
    assert "empty answer" in str(err.value) and "stop" in str(err.value)


@pytest.mark.asyncio
async def test_a_null_content_field_is_also_an_error(endpoint):
    endpoint.body = reply(None)
    model = OpenAICompatModel("https://api.example.test/v1", "m")
    with pytest.raises(RuntimeError, match="empty answer"):
        await model.complete("x")


@pytest.mark.asyncio
async def test_a_response_with_no_choices_is_an_error(endpoint):
    endpoint.body = json.dumps({"choices": []}).encode()
    model = OpenAICompatModel("https://api.example.test/v1", "m")
    with pytest.raises(RuntimeError, match="no choices"):
        await model.complete("x")


@pytest.mark.asyncio
async def test_an_unreachable_endpoint_is_reported_not_raised_raw(endpoint):
    endpoint.error = urllib.error.URLError("connection refused")
    model = OpenAICompatModel("http://127.0.0.1:1/v1", "m")
    with pytest.raises(RuntimeError, match="cannot reach"):
        await model.complete("x")
