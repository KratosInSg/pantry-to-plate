# `tests/llm/test_client.py`

Tests [`llm/client.py`](../../llm/client.md) with a faked HTTP server (`httpx.MockTransport`): no LLM, no network.

| Test | Pins |
| --- | --- |
| `test_ollama_request_is_schema_constrained_deterministic_and_not_thinking` | `/api/chat`, schema in `format`, `think: false`, temperature 0, fixed seed |
| `test_openai_request_shape_and_auth_header` | `/v1/chat/completions`, bearer key, `response_format` json_schema, no `think` |
| `test_complete_text_sends_no_schema` | text mode has no `format` |
| `test_every_failure_is_an_llm_error` | HTTP 500, non-JSON body, wrong shape, empty content, non-JSON content, JSON array |
| `test_unreachable_server_is_an_llm_error_and_not_available` | connection refused → `LlmError`; `is_available()` is False |
| `test_is_available_probes_the_version_endpoint` | |
| `test_config_from_environment` | defaults, hosted provider URL, `OPENAI_API_KEY` |
| `test_unknown_provider_is_rejected` | |
| `test_with_model_changes_only_the_model` | |

A *live* check against the real Ollama server is deliberately not in the suite (cold start ~30 s, depends on the
machine); it is described in `md docs/llm.md`.

## Change log

- 2026-10-12 — Created.
