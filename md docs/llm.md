# LLM runtime — decision record

*Status: installed and benchmarked 2026-10-12; integration written the same day (`src/llm/client.py`, `nlp/llm_fallback.py`).*

## Decision

Use an **open-source model served locally by Ollama**, called over the standard OpenAI-compatible HTTP API.
Default model: **`qwen3:8b`** (Q4_K_M, 5.2 GB, Apache-2.0).

Why local: no per-call cost, no API key, data never leaves the machine, pinned weights give reproducible evaluation.
Why the OpenAI-compatible protocol: Ollama, llama.cpp server, LM Studio, vLLM **and** the hosted OpenAI API all speak
it, so switching provider is configuration (`base_url`, `model`, optional key), not code.

## What the LLM is allowed to do (non-negotiable, from `CLAUDE.md`)

1. Re-read a pantry fragment the rules could not understand → **schema-constrained JSON**, then validated.
2. Paraphrase explanation facts the solver/rules already produced → no new facts, validated, template fallback.

It never decides the plan.

## Environment (this project's laptop)

| Item | Value |
| --- | --- |
| GPU | NVIDIA RTX 5050 Laptop, 8 GB VRAM |
| RAM | 15 GB |
| Ollama | 0.40.3, installed with `winget install Ollama.Ollama`; server on `127.0.0.1:11434` (local only) |
| Model store | default `%USERPROFILE%\.ollama\models` (on `C:`, ~5.2 GB for `qwen3:8b`) |

## Benchmark (qwen3:8b, thinking off, temperature 0, 4096 context)

| Measure | Result |
| --- | --- |
| Placement | **100% GPU**; 5.9 GB VRAM in use (of 8 GB) |
| Cold load | ~27 s (first request after the model was unloaded; Ollama keeps it warm for 5 min) |
| Generation speed | **57–61 tokens/s** |
| Extraction (4 items → JSON, ~130 tokens) | 2.4 s |
| Grounded explanation (~40 tokens) | 0.6–0.9 s |

### Quality finding: the schema matters more than the prompt

Same model, same messy fragment (*"a tub of kimchi, ~2 lbs of that purple cabbage, six eggs (going off), and the
leftover rice from Sunday"*):

| Setup | Result |
| --- | --- |
| Nullable `quantity` + free-text `unit` | **Wrong**: quantities null for "2 lbs" and "six eggs", invented units (`lbs` for rice) |
| `has_quantity` flag + `quantity` number + **enum** `unit` | **Correct** on all four items (also without the few-shot example) |
| Free JSON mode (no schema), few-shot | Missed kimchi's quantity |
| Schema + thinking **on** | 13 s and an empty answer (thinking ate the token budget) |

**Rules for the integration:**

* Use schema-constrained output (`format` = JSON schema) — never "please reply in JSON".
* Prefer `has_quantity: bool` + `quantity: number` over `number | null`; constrain `unit` with an enum **built per call
  from the unit words that occur in the text** - *not* a fixed list of canonical names. A fixed enum of canonical
  units made the model answer `pint` for "2 pounds" (the nearest listed word), a silent error that turned 2 lb of
  potatoes into 600 g. Found by the first live run of the integration; regression-tested.
* Keep `think: false` and `temperature: 0`, fixed `seed`.
* Always validate against the *fragment that names the food*: name words must occur in it, the number must be derivable
  from it, the unit word must be written in it. On any failure keep the rules-based result.
* The model never produces ingredient ids, grams or urgency: its output is rebuilt into a plain sentence and re-parsed
  by the rules.
* Talk to Ollama through its **native** `/api/chat` (the benchmarked configuration: `format` = schema,
  `think: false`); the OpenAI-compatible endpoint is the second provider in `llm/client.py`.

## Operations

```bash
ollama list                 # installed models
ollama ps                   # what is loaded and whether it is on the GPU
ollama pull qwen3:8b        # (re)download
curl http://127.0.0.1:11434/api/version
```

The tray app starts the server at login; quit it from the tray to free the GPU. No Ollama account is needed (the
repeated `401 /api/me` lines in its log are the tray app's optional sign-in check).

## Alternatives considered

| Option | Verdict |
| --- | --- |
| `gpt-oss-20b` (OpenAI open-weight) | needs ~13 GB for weights; does not fit 8 GB VRAM / 15 GB RAM smoothly; reasoning overhead we do not need |
| `qwen3.5:9b` (6.6 GB) | too little VRAM headroom for context on 8 GB; `qwen3.5:4b` (3.3 GB) is a fast fallback |
| `qwen2.5:7b` (4.7 GB) | non-reasoning, Apache-2.0; candidate for an A/B on the labelled NLP set |
| Hosted OpenAI API | optional, via env config: quality ceiling for the evaluation and a fair "LLM-only planner" baseline |

Model choice should ultimately be settled by **F1 and latency on the frozen labelled NLP set**, not by leaderboards.

## Change log

- 2026-10-12 — Created. Installed Ollama 0.40.3, pulled `qwen3:8b`, benchmarked latency, GPU placement and
  extraction quality.
- 2026-10-12 — Integration written. Live run found the fixed-enum unit failure ("pounds" -> `pint`); rule above
  changed. Fallback limited to extraction (cannot fix vocabulary gaps); see `modules/nlp/llm_fallback.md`.
- 2026-10-13 — Explanation paraphrase written (`explain/paraphrase.py`) and measured live on `qwen3:8b`: asking for
  "2 to 4 short sentences" gave **0/8** accepted sections (the model summarises, dropping numbers); asking for "every
  fact must stay, you may join sentences" gave **30/32**. Rule: **when a validator demands completeness, the prompt must
  ask for completeness.** ~2.5 s per section. The live run also exposed a defect in our own template, which unit tests
  with a stub had not.
