# Pantry-to-Plate

An intelligent nutrition, pantry and grocery planning system — the week's dinners are built around what's already in the kitchen first, starting with whatever expires soonest, and only the missing groceries get ordered.

Team: Aryan Chopra, Shreyash Sarade — NUS-ISS MTech in AI Systems, Intelligent Reasoning Systems practice module.

## What this is

Most planning tools solve one meal at a time. Pantry-to-Plate plans the whole week as one constraint problem: it has to use pantry and perishable items first, meet nutrition and diet/allergy constraints, respect preferences, and minimise extra groceries — all at once. Rules and a weekly optimiser make the decisions; the LLM only parses input and explains the output.

MVP scope: one user, one week, mainly dinners.

## Docs

| Doc | What's in it |
| --- | --- |
| [architecture.md](architecture.md) | The five-stage pipeline, components, design principle |
| [systemflow.md](systemflow.md) | Step-by-step flow for a planning request, plus mid-week replanning |
| [data.md](data.md) | Data sources, canonical ingredient schema, synthetic scenarios |
| [evaluation.md](evaluation.md) | Metrics, baselines, ablations, scenario families |
| [CLAUDE.md](../CLAUDE.md) | Non-negotiables, folder rules and code/documentation conventions (repo root) |
| [modules/README.md](modules/README.md) | **One doc per source and test file**, mirroring `src/` and `tests/` |
| [llm.md](llm.md) | LLM runtime decision: local Ollama + `qwen3:8b`, benchmark, schema rules |

The week-by-week build plan (with the subagent/skill setup) lives in the [implementation roadmap](https://claude.ai/code/artifact/076c7456-5243-4511-ac52-b8f4a7cca012).

## Status

Oct 2026 — implementation under way.

| Component | State |
| --- | --- |
| Data build + curated dataset (`data/canonical/`) | done |
| Knowledge store (`src/knowledge/store.py`) | done |
| NLP pantry parser (`src/nlp/`) | done (rules-based; optional LLM fallback) |
| Recipe catalogue, domain models, pantry conversion (`src/knowledge/recipes.py`, `src/domain/`) | done |
| Hard-rule filter, preference scorer, shortlist, inventory accounting (`src/preference/`, `src/optimizer/`) | done |
| Weekly optimiser (MILP; HiGHS default, OR-Tools CP-SAT as a second backend in a child process) and baselines | done; ≈ 6 s per plan; solver comparison in `evaluation.md` |
| Evaluation: benchmark v1 frozen (240 scenarios), metrics, runner | done; robustness metric and NLP labelled set pending |
| LLM runtime (Ollama + `qwen3:8b`) and client (`src/llm/`) | done; checked live |
| NLP LLM fallback (`src/nlp/llm_fallback.py`) | done; validated against the user's words; not yet scored on a labelled set |
| Explainer (`src/explain/`): facts → templates → optional validated LLM paraphrase | done; template text complete without an LLM; paraphrase 30/32 sections accepted live |
| App service layer (`src/app/`): pantry review, profile, plan, grocery box, steps | done |
| Mid-week replanning (`optimizer/replan.py`; reject / skip a dinner, roll the pantry forward) | done (alternatives-with-trade-offs and counterfactual diffs not built) |
| UI prototype (`src/ui/`, Streamlit) | done: pantry review, profile, week, shopping list, re-plan; run with `streamlit run src/ui/streamlit_app.py` |

