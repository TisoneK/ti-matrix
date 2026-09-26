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

from ti_matrix.adapters.openai_compat import OpenAICompatModel, describe_balance


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


# ─── token usage: a running total, not a billing record ─────────────────────


@pytest.mark.asyncio
async def test_usage_accumulates_across_calls(endpoint):
    endpoint.body = reply("hello")
    model = OpenAICompatModel("https://api.example.test/v1", "m")
    assert model.usage_snapshot() == {"calls": 0, "prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}

    endpoint.body = json.dumps({"choices": [{"message": {"content": "hi"}, "finish_reason": "stop"}],
                                "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}}).encode()
    await model.complete("x")
    assert model.usage_snapshot() == {"calls": 1, "prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}

    endpoint.body = json.dumps({"choices": [{"message": {"content": "hi again"}, "finish_reason": "stop"}],
                                "usage": {"prompt_tokens": 20, "completion_tokens": 8, "total_tokens": 28}}).encode()
    await model.complete("x")
    assert model.usage_snapshot() == {"calls": 2, "prompt_tokens": 30, "completion_tokens": 13, "total_tokens": 43}


@pytest.mark.asyncio
async def test_usage_snapshot_is_a_copy_not_a_live_reference(endpoint):
    model = OpenAICompatModel("https://api.example.test/v1", "m")
    snap = model.usage_snapshot()
    snap["calls"] = 999
    assert model.usage_snapshot()["calls"] == 0


@pytest.mark.asyncio
async def test_a_provider_that_omits_usage_still_counts_the_call(endpoint):
    """Not every OpenAI-compatible host sends a `usage` object back. A missing one is a silent gap in the
    token fields, not a reason to lose track that a call happened at all."""
    endpoint.body = reply("hello")  # no "usage" key
    model = OpenAICompatModel("https://api.example.test/v1", "m")
    await model.complete("x")
    assert model.usage_snapshot() == {"calls": 1, "prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}


@pytest.mark.asyncio
async def test_a_call_that_ends_in_an_empty_answer_still_records_usage(endpoint):
    """An empty completion is an error the caller sees (see the "what it refuses to hand back" tests
    above) — but tokens were spent reasoning toward it, and the run should still be charged for them."""
    endpoint.body = json.dumps({"choices": [{"message": {"content": ""}, "finish_reason": "length"}],
                                "usage": {"prompt_tokens": 4, "completion_tokens": 8192, "total_tokens": 8196}}).encode()
    model = OpenAICompatModel("https://api.example.test/v1", "m")
    with pytest.raises(RuntimeError):
        await model.complete("x")
    assert model.usage_snapshot() == {"calls": 1, "prompt_tokens": 4, "completion_tokens": 8192, "total_tokens": 8196}


# ─── balance: DeepSeek only, never a guess elsewhere ─────────────────────────


@pytest.mark.asyncio
async def test_fetch_balance_is_none_for_a_host_that_is_not_deepseek(endpoint):
    model = OpenAICompatModel("https://api.example.test/v1", "m")
    assert await model.fetch_balance() is None
    assert endpoint.requests == []  # no network call at all for a host with no known balance endpoint


@pytest.mark.asyncio
async def test_fetch_balance_hits_the_deepseek_endpoint_with_the_bearer_key(endpoint, monkeypatch):
    monkeypatch.setenv("TI_TEST_KEY", "sk-secret-value")
    endpoint.body = json.dumps({"is_available": True, "balance_infos": [
        {"currency": "USD", "total_balance": "12.34"}]}).encode()
    model = OpenAICompatModel("https://api.deepseek.com/v1", "deepseek-chat", api_key_env="TI_TEST_KEY")
    balance = await model.fetch_balance()
    assert balance == {"is_available": True, "balance_infos": [{"currency": "USD", "total_balance": "12.34"}]}
    req = endpoint.requests[-1]
    assert req.full_url == "https://api.deepseek.com/user/balance"
    assert req.method == "GET"
    assert req.get_header("Authorization") == "Bearer sk-secret-value"


@pytest.mark.asyncio
async def test_fetch_balance_reports_a_rejected_key_without_echoing_it(endpoint):
    endpoint.error = urllib.error.HTTPError(
        "https://api.deepseek.com/user/balance", 401, "Unauthorized", {},
        io.BytesIO(b'{"error":{"message":"Authentication Fails"}}'))
    model = OpenAICompatModel("https://api.deepseek.com/v1", "deepseek-chat", api_key="sk-secret-value")
    with pytest.raises(RuntimeError) as err:
        await model.fetch_balance()
    assert "401" in str(err.value) and "sk-secret-value" not in str(err.value)


def test_describe_balance_reads_deepseeks_own_shape():
    info = {"is_available": True, "balance_infos": [{"currency": "USD", "total_balance": "12.34"}]}
    assert describe_balance(info) == "12.34 USD"


def test_describe_balance_names_several_currencies():
    info = {"is_available": True, "balance_infos": [
        {"currency": "USD", "total_balance": "12.34"}, {"currency": "CNY", "total_balance": "88.00"}]}
    assert describe_balance(info) == "12.34 USD, 88.00 CNY"


def test_describe_balance_flags_an_unavailable_account():
    info = {"is_available": False, "balance_infos": [{"currency": "USD", "total_balance": "0.00"}]}
    assert describe_balance(info) == "0.00 USD (account not available for new calls)"


def test_describe_balance_on_an_unrecognised_shape_says_so_rather_than_guessing():
    assert describe_balance({}) == "(unrecognised balance response)"
    assert describe_balance({"balance_infos": []}) == "(unrecognised balance response)"


# ─── the model list: GET /models, every provider named above has one ────────


@pytest.mark.asyncio
async def test_list_models_returns_the_sorted_ids(endpoint):
    endpoint.body = json.dumps({"data": [
        {"id": "deepseek-reasoner"}, {"id": "deepseek-chat"}]}).encode()
    model = OpenAICompatModel("https://api.deepseek.com/v1", "m")
    assert await model.list_models() == ["deepseek-chat", "deepseek-reasoner"]
    req = endpoint.requests[-1]
    assert req.full_url == "https://api.deepseek.com/v1/models"
    assert req.method == "GET" or req.get_method() == "GET"


@pytest.mark.asyncio
async def test_list_models_sends_the_bearer_key(endpoint, monkeypatch):
    monkeypatch.setenv("TI_TEST_KEY", "sk-secret-value")
    endpoint.body = json.dumps({"data": []}).encode()
    model = OpenAICompatModel("https://api.example.test/v1", "m", api_key_env="TI_TEST_KEY")
    await model.list_models()
    assert endpoint.requests[-1].get_header("Authorization") == "Bearer sk-secret-value"


@pytest.mark.asyncio
async def test_list_models_on_a_response_with_no_data_list_is_empty_not_an_error(endpoint):
    endpoint.body = json.dumps({"object": "list"}).encode()
    model = OpenAICompatModel("https://api.example.test/v1", "m")
    assert await model.list_models() == []


@pytest.mark.asyncio
async def test_list_models_drops_entries_with_no_usable_id(endpoint):
    endpoint.body = json.dumps({"data": [{"id": "m1"}, {"no_id": True}, "not-a-dict", {"id": ""}]}).encode()
    model = OpenAICompatModel("https://api.example.test/v1", "m")
    assert await model.list_models() == ["m1"]


@pytest.mark.asyncio
async def test_list_models_reports_a_rejected_key_without_echoing_it(endpoint):
    endpoint.error = urllib.error.HTTPError(
        "https://api.example.test/v1/models", 401, "Unauthorized", {},
        io.BytesIO(b'{"error":{"message":"Authentication Fails"}}'))
    model = OpenAICompatModel("https://api.example.test/v1", "m", api_key="sk-secret-value")
    with pytest.raises(RuntimeError) as err:
        await model.list_models()
    assert "401" in str(err.value) and "sk-secret-value" not in str(err.value)
