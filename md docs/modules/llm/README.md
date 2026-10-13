# `src/llm/` — talking to the language model (transport only)

## Purpose

The LLM is **optional** and may only (1) re-read pantry text the rules could not understand and (2) paraphrase
explanation facts the optimiser already produced (`CLAUDE.md` non-negotiable; decision record in
[`md docs/llm.md`](../../llm.md)). This package is the *transport*: send messages, ask for schema-constrained JSON,
return what came back. It knows nothing about pantries or plans — callers validate every answer.

## Files

| File | Role | Doc |
| --- | --- | --- |
| `client.py` | `LlmClient`, `LlmConfig`, `LlmError`: Ollama-native and OpenAI-compatible providers | [client.md](client.md) |

Users of the client: [`nlp/llm_fallback.py`](../nlp/llm_fallback.md) (pantry re-read) and
[`explain/paraphrase.py`](../explain/paraphrase.md) (reword explanation facts; every answer validated, template
fallback). Both use only `complete_json` / `complete_text` and treat `LlmError` as "no LLM".

## Rules

1. **Any failure is `LlmError`** and means "no LLM": the caller keeps the rules-based result.
2. **Deterministic by default** (temperature 0, fixed seed) so evaluations are reproducible.
3. **Schema-constrained output** — never "please reply in JSON".
4. **Provider is configuration** (`PTP_LLM_PROVIDER`, `PTP_LLM_BASE_URL`, `PTP_LLM_MODEL`, `PTP_LLM_API_KEY`); no key is
   needed for a local Ollama.

## Change log

- 2026-10-12 — Package created.
- 2026-10-13 — The explainer (`explain/paraphrase.py`) became the second user of the client.
