"""Tests for ``llm/client.py`` with a faked HTTP server (``httpx.MockTransport``): no LLM, no network."""
from __future__ import annotations

import json

import httpx
import pytest

from llm.client import LlmClient, LlmConfig, LlmError

SCHEMA = {"type": "object", "properties": {"x": {"type": "number"}}, "required": ["x"]}
MESSAGES = [{"role": "user", "content": "hi"}]


def _client(handler, **config) -> tuple[LlmClient, list[httpx.Request]]:
    seen: list[httpx.Request] = []

    def recording(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return handler(request)

    return LlmClient(LlmConfig(**config), transport=httpx.MockTransport(recording)), seen


def _ollama_reply(content: str) -> httpx.Response:
    return httpx.Response(200, json={"message": {"role": "assistant", "content": content}})


def test_ollama_request_is_schema_constrained_deterministic_and_not_thinking():
    client, seen = _client(lambda r: _ollama_reply('{"x": 1.5}'))
    assert client.complete_json(MESSAGES, SCHEMA) == {"x": 1.5}
    req = seen[0]
    assert req.url.path == "/api/chat"
    body = json.loads(req.content)
    assert body["format"] == SCHEMA and body["think"] is False and body["stream"] is False
    assert body["options"]["temperature"] == 0.0 and body["options"]["seed"] == 7
    assert body["model"] == "qwen3:8b"


def test_openai_request_shape_and_auth_header():
    def handler(request):
        return httpx.Response(200, json={"choices": [{"message": {"content": '{"x": 2}'}}]})

    client, seen = _client(handler, provider="openai", base_url="http://llm.test/v1", api_key="sk-test",
                           model="some-model")
    assert client.complete_json(MESSAGES, SCHEMA) == {"x": 2}
    req = seen[0]
    assert req.url.path == "/v1/chat/completions"
    assert req.headers["authorization"] == "Bearer sk-test"
    body = json.loads(req.content)
    assert body["response_format"]["type"] == "json_schema"
    assert body["response_format"]["json_schema"]["schema"] == SCHEMA
    assert "think" not in body


def test_complete_text_sends_no_schema():
    client, seen = _client(lambda r: _ollama_reply("  A short sentence.  "))
    assert client.complete_text(MESSAGES) == "A short sentence."
    assert "format" not in json.loads(seen[0].content)


@pytest.mark.parametrize("reply", [
    httpx.Response(500, text="boom"),
    httpx.Response(200, text="<html>not json</html>"),
    httpx.Response(200, json={"unexpected": "shape"}),
    httpx.Response(200, json={"message": {"content": "   "}}),
    httpx.Response(200, json={"message": {"content": "not json at all"}}),
    httpx.Response(200, json={"message": {"content": "[1, 2, 3]"}}),
])
def test_every_failure_is_an_llm_error(reply):
    client, _ = _client(lambda r: reply)
    with pytest.raises(LlmError):
        client.complete_json(MESSAGES, SCHEMA)


def test_unreachable_server_is_an_llm_error_and_not_available():
    def refuse(request):
        raise httpx.ConnectError("connection refused")

    client, _ = _client(refuse)
    assert client.is_available() is False
    with pytest.raises(LlmError):
        client.complete_json(MESSAGES, SCHEMA)


def test_is_available_probes_the_version_endpoint():
    client, seen = _client(lambda r: httpx.Response(200, json={"version": "0.40.3"}))
    assert client.is_available() is True
    assert seen[0].url.path == "/api/version"


def test_config_from_environment():
    default = LlmConfig.from_env({})
    assert (default.provider, default.model, default.api_key) == ("ollama", "qwen3:8b", None)
    assert default.base_url == "http://127.0.0.1:11434"

    hosted = LlmConfig.from_env({"PTP_LLM_PROVIDER": "openai", "PTP_LLM_MODEL": "m", "OPENAI_API_KEY": "sk-1"})
    assert (hosted.provider, hosted.model, hosted.api_key) == ("openai", "m", "sk-1")
    assert hosted.base_url == "https://api.openai.com/v1"


def test_unknown_provider_is_rejected():
    with pytest.raises(ValueError):
        LlmConfig(provider="carrier-pigeon")


def test_with_model_changes_only_the_model():
    client, seen = _client(lambda r: _ollama_reply('{"x": 1}'))
    other = client.with_model("qwen2.5:7b")
    other.complete_json(MESSAGES, SCHEMA)
    assert json.loads(seen[0].content)["model"] == "qwen2.5:7b"
    assert other.config.temperature == client.config.temperature
