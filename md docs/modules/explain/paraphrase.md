# `src/explain/paraphrase.py`

## Purpose

Let the language model reword a section of the template explanation — **and accept its answer only if it adds nothing
and drops nothing that can be checked**. This is the "LLM writes explanations, validated against the solver's facts"
rule from `CLAUDE.md` made executable.

## Public API

| Name | What |
| --- | --- |
| `Paraphraser(client, vocabulary, max_tokens=400).rewrite(section) -> Paraphrase` | One LLM call + validation. `Paraphrase.text` is `None` when rejected, with `problems` |
| `paraphrase_explanation(explanation, paraphraser) -> Explanation` | Rewrites `overview` and `day:*` sections; rejected ones keep their template text and get a `note` |
| `check_paraphrase(candidate, title, facts_text, vocabulary) -> list[str]` | The validator; `[]` means usable |
| `ingredient_vocabulary(store)` | Stemmed single-word ingredient names whose presence is checked |
| `build_paraphraser(client, store)` | `None` when the client is `None` or not reachable |
| `TextLlm` | Protocol: `complete_text(messages, max_tokens) -> str` (`llm.LlmClient` satisfies it) |

## The validator

A rewrite is used only if **all** hold (against the section's own facts):

| Check | Catches |
| --- | --- |
| numbers | an invented number, or a dropped one (so a shortfall or quantity cannot vanish). Number words count; "no/none" may satisfy a `0`, "one" a `1`, but are never counted as invented |
| foods | an ingredient not in the facts, or one in the facts that was dropped |
| weekdays | a day the facts do not name; a deadline day that was dropped; relative days (`today`, `tomorrow`) are never allowed |
| warnings | `below` / `above` / `short` / `longer` / `dislike` / `unused` / `estimated` with no synonym left |
| claims | `healthy`, `delicious`, … not present in the facts |
| form | markup, line breaks, or much longer than the facts |

`rules` and `caveats` are safety statements: **never sent to the model**.

## Measured (qwen3:8b via Ollama, 2026-10-13, live)

| Setup | Sections accepted |
| --- | --- |
| prompt "rewrite as 2 to 4 short sentences" | **0 / 8** — the model summarised and dropped numbers every time |
| prompt "every fact must stay; you may join sentences" (shipped), final code | **30 / 32** (94 %) over four scenario families, stable across re-runs |

The 2 rejections are the validator doing its job: the model dropped an "estimated" caveat once, and a calorie range
once. Those sections keep their template text. Two *false* rejections were found and fixed on the way: the word *meal*
is also an ingredient name (`GENERIC_WORDS`), and a template bug the live run exposed — "17.6 g protein is **0 g**
short of your 18 g minimum" — now prints "0.4 g short" (`render._gap`; gaps below float noise are not misses).
Cost: ~2.5 s per section, ~20 s for a full explanation on the dev GPU, so treat the paraphrase as background /
on-demand; the templates are instant. A retry-with-feedback pass could lift acceptance further; not built — a rejected
section already falls back safely and the gain is small.

**Lessons:** (1) the prompt must ask for completeness because the validator demands it — asking for brevity guarantees
rejection; (2) running the real model found a defect in *our own* template that unit tests with a stub never could.
Both found live, not by the stub tests.

## Limits (be honest about these)

* It checks **content words and numbers, not meaning**. A rewrite could attach a true number to the wrong noun
  *within one section*. Sections are small and only their own facts are allowed, which bounds this; it does not
  eliminate it.
* The food check covers the ~530 single-word canonical names. A multi-word ingredient is checked through its head
  word ("chicken" in "chicken breast").
* Weekday and claim lists are fixed vocabularies; a new kind of unsupported claim is not caught until added.
* Acceptance depends on the model; a different model needs the live check repeated.

## Failure model

Any exception from the client ⇒ the template is kept; after the first failure the model is not called again in that
explanation (an unreachable server costs one timeout, not eight).

## Tests

[`tests/explain/test_paraphrase.py`](../tests/explain/test_paraphrase.md) — validator cases, the paraphraser against a
stub, safety sections never sent, circuit breaker. The live acceptance rate above is a measurement, not a test (it
needs a running model).

## Change log

- 2026-10-13 — Created. Prompt, vocabulary exclusions and zero-word handling all tuned against the real model.
