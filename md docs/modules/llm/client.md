# `src/llm/client.py`

## Purpose

A small, synchronous, provider-neutral client. Default: `qwen3:8b` served locally by Ollama.

## Public API

| Name | What |
| --- | --- |
| `LlmConfig` | `provider` (`ollama` \| `openai`), `base_url`, `model`, `api_key`, `temperature=0`, `seed=7`, `num_ctx=4096`, `max_tokens=400`, `timeout_s=60`. `LlmConfig.from_env()` reads `PTP_LLM_*` (`OPENAI_API_KEY` accepted) |
| `LlmClient(config=None, transport=None)` | `complete_json(messages, schema) -> dict`, `complete_text(messages, max_tokens=None) -> str`, `is_available() -> bool`, `with_model(name)`, `close()`. Pass an `httpx` transport to fake the server in tests |
| `LlmError` | Every failure: server down, timeout, HTTP error, non-JSON, non-object, empty answer |

## Providers

| Provider | Endpoint | Schema goes in | Notes |
| --- | --- | --- | --- |
| `ollama` (default) | `POST /api/chat` | `format` | Sends `think: false` — a reasoning model otherwise spends the whole token budget thinking (measured: 13 s, empty answer) |
| `openai` | `POST {base_url}/chat/completions` | `response_format` (`json_schema`, strict) | Hosted OpenAI, vLLM, LM Studio, llama.cpp server. No `think` switch: use a non-reasoning model |

## Decisions

* **Native Ollama endpoint, not only the OpenAI-compatible one.** The benchmarked configuration (schema in `format`,
  `think: false`) is native; the decision record's "OpenAI-compatible" goal is met by the second provider.
* **No SDK dependency.** `httpx` only; two request shapes are ~25 lines each.
* **`is_available()` never raises** and uses a 2 s timeout, so the app can decide at start-up whether to attach the LLM.

## Limits

* Synchronous; no streaming, no retries (a retry loop would hide a server that is down; the caller already has a
  complete fallback).
* A cold model load takes ~30 s on the dev laptop; the default 60 s timeout covers it.

## Tests

[`tests/llm/test_client.py`](../tests/llm/test_client.md)

## Change log

- 2026-10-12 — Created.
