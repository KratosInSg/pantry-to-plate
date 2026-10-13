"""A small, provider-neutral client for the project's LLM (default: ``qwen3:8b`` served locally by Ollama).

Where it sits
-------------
The LLM is optional and may only (1) re-read pantry text the rules could not understand and (2) paraphrase explanation
facts the optimiser already produced (``md docs/llm.md``, ``CLAUDE.md``). This module is the *transport only*: it sends
messages, asks for schema-constrained JSON, and returns what came back. It knows nothing about pantries or plans; the
callers (``nlp/llm_fallback.py``, later ``explain/``) validate every answer before using it.

Providers
---------
``ollama``  Ollama's native ``/api/chat``. This is what was benchmarked: it accepts a JSON schema in ``format`` and
            ``think: false`` (a reasoning model otherwise spends the whole token budget "thinking").
``openai``  Any OpenAI-compatible ``/v1/chat/completions`` server (hosted OpenAI, vLLM, LM Studio, llama.cpp). The
            schema goes in ``response_format``; there is no ``think`` switch, so use a non-reasoning model.

Switching provider is configuration (``LlmConfig`` / environment variables), not code.

Failure model
-------------
Every failure - server down, timeout, HTTP error, reply that is not JSON - raises :class:`LlmError`. Callers treat that
as "no LLM": the rules-based result is kept and the feature degrades, never the application.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, replace
from typing import Any

import httpx

DEFAULT_OLLAMA_URL = "http://127.0.0.1:11434"
DEFAULT_MODEL = "qwen3:8b"

# Environment variables read by ``LlmConfig.from_env``. A local Ollama needs none of them.
ENV_PROVIDER = "PTP_LLM_PROVIDER"
ENV_BASE_URL = "PTP_LLM_BASE_URL"
ENV_MODEL = "PTP_LLM_MODEL"
ENV_API_KEY = "PTP_LLM_API_KEY"


class LlmError(RuntimeError):
    """The LLM could not be reached or did not return a usable answer. Callers fall back to the rules."""


@dataclass(frozen=True, slots=True)
class LlmConfig:
    """Everything needed to talk to one model. Deterministic by default (temperature 0, fixed seed)."""

    provider: str = "ollama"                 # "ollama" | "openai"
    base_url: str = DEFAULT_OLLAMA_URL       # for "openai" include the version prefix, e.g. https://api.openai.com/v1
    model: str = DEFAULT_MODEL
    api_key: str | None = None               # only the hosted / authenticated providers need it
    temperature: float = 0.0
    seed: int = 7                            # fixed so the evaluation is reproducible
    num_ctx: int = 4096                      # Ollama context window; keeps the 8 GB GPU comfortable
    max_tokens: int = 400                    # a pantry fragment's JSON is ~130 tokens; this is generous headroom
    timeout_s: float = 60.0                  # first request after a cold start can take ~30 s to load the model

    def __post_init__(self) -> None:
        if self.provider not in ("ollama", "openai"):
            raise ValueError(f"unknown provider {self.provider!r}; expected 'ollama' or 'openai'")

    @classmethod
    def from_env(cls, environ: dict[str, str] | None = None) -> "LlmConfig":
        """Build a config from ``PTP_LLM_*`` variables (``OPENAI_API_KEY`` is accepted for the key)."""
        env = os.environ if environ is None else environ
        provider = env.get(ENV_PROVIDER, "ollama")
        default_url = "https://api.openai.com/v1" if provider == "openai" else DEFAULT_OLLAMA_URL
        return cls(provider=provider, base_url=env.get(ENV_BASE_URL, default_url),
                   model=env.get(ENV_MODEL, DEFAULT_MODEL),
                   api_key=env.get(ENV_API_KEY) or env.get("OPENAI_API_KEY") or None)


class LlmClient:
    """Synchronous client. Cheap to create; holds one ``httpx.Client`` (pass ``transport`` to fake the server in tests)."""

    def __init__(self, config: LlmConfig | None = None, transport: httpx.BaseTransport | None = None) -> None:
        self.config = config or LlmConfig.from_env()
        headers = {"Authorization": f"Bearer {self.config.api_key}"} if self.config.api_key else {}
        self._transport = transport
        self._http = httpx.Client(base_url=self.config.base_url.rstrip("/"), headers=headers,
                                  timeout=self.config.timeout_s, transport=transport)

    # ------------------------------------------------------------------------------------------------ public API
    def is_available(self, timeout_s: float = 2.0) -> bool:
        """Cheap liveness probe (never raises). Use it to decide whether to attach the LLM at all."""
        path = "/api/version" if self.config.provider == "ollama" else "/models"
        try:
            return self._http.get(path, timeout=timeout_s).status_code < 400
        except httpx.HTTPError:
            return False

    def complete_json(self, messages: list[dict[str, str]], schema: dict[str, Any]) -> dict[str, Any]:
        """Ask for a JSON object that conforms to ``schema`` and return it parsed.

        Args:
            messages: chat messages (``system`` / ``user`` / optional few-shot ``assistant`` turns).
            schema: a JSON Schema. Use ``has_quantity: bool`` + ``quantity: number`` rather than a nullable number, and
                enums for closed vocabularies - small models follow that far more reliably (``md docs/llm.md``).

        Raises:
            LlmError: transport/HTTP failure, or the reply is not a JSON object.
        """
        content = self._chat(messages, schema)
        try:
            parsed = json.loads(content)
        except json.JSONDecodeError as exc:
            raise LlmError(f"model did not return JSON: {content[:120]!r}") from exc
        if not isinstance(parsed, dict):
            raise LlmError(f"expected a JSON object, got {type(parsed).__name__}")
        return parsed

    def complete_text(self, messages: list[dict[str, str]], max_tokens: int | None = None) -> str:
        """Plain text completion (used by the explainer to paraphrase facts it already holds)."""
        return self._chat(messages, None, max_tokens).strip()

    def with_model(self, model: str) -> "LlmClient":
        """A client for another model on the same server (e.g. an A/B on the labelled NLP set)."""
        return LlmClient(replace(self.config, model=model), transport=self._transport)

    def close(self) -> None:
        self._http.close()

    # ------------------------------------------------------------------------------------------------ transport
    def _chat(self, messages: list[dict[str, str]], schema: dict[str, Any] | None, max_tokens: int | None = None) -> str:
        cfg = self.config
        limit = max_tokens or cfg.max_tokens
        if cfg.provider == "ollama":
            path = "/api/chat"
            body: dict[str, Any] = {
                "model": cfg.model, "messages": messages, "stream": False, "think": False,
                "options": {"temperature": cfg.temperature, "seed": cfg.seed, "num_ctx": cfg.num_ctx,
                            "num_predict": limit}}
            if schema is not None:
                body["format"] = schema
        else:
            path = "/chat/completions"
            body = {"model": cfg.model, "messages": messages, "temperature": cfg.temperature, "seed": cfg.seed,
                    "max_tokens": limit}
            if schema is not None:
                body["response_format"] = {"type": "json_schema",
                                           "json_schema": {"name": "answer", "schema": schema, "strict": True}}
        try:
            response = self._http.post(path, json=body)
            response.raise_for_status()
            data = response.json()
        except httpx.HTTPError as exc:
            raise LlmError(f"LLM request failed ({type(exc).__name__}): {exc}") from exc
        except ValueError as exc:                                  # body was not JSON at all
            raise LlmError("LLM server returned a non-JSON body") from exc
        try:
            content = data["message"]["content"] if cfg.provider == "ollama" else data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise LlmError(f"unexpected LLM response shape: {str(data)[:120]}") from exc
        if not isinstance(content, str) or not content.strip():
            raise LlmError("LLM returned an empty answer")
        return content
