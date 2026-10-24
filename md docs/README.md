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
| [security.md](security.md) | Security review (attack surface, findings, fixes) and the **deployment checklist** |

The week-by-week build plan (with the subagent/skill setup) lives in the [implementation roadmap](https://claude.ai/code/artifact/076c7456-5243-4511-ac52-b8f4a7cca012).

## Implemented system

The current application is deployed at [pantry-to-plate-369.streamlit.app](https://pantry-to-plate-369.streamlit.app). The project integrates the following components:

| Component | Implementation and evidence |
| --- | --- |
| Data and knowledge | Curated canonical ingredients, Food.com recipe catalogue, USDA nutrition and FoodKeeper shelf-life reference data |
| Natural-language pantry entry | Rules-first ingredient, quantity and urgency parsing with validated optional LLM fallback; rules-only parser evaluated in [Evaluation/08](../Evaluation/08_ingredient_nlp/README.md) |
| Safety and inventory reasoning | Dietary/allergen filtering, hard-rule-safe ingredient substitutions, inventory replay and expiry-aware feasibility |
| Weekly optimisation | SciPy/HiGHS MILP, OR-Tools CP-SAT cross-check, genetic algorithm, greedy and random baselines |
| Personalisation | Content-based preferences with session feedback from “Loved it”; evaluated on MealRec users |
| Explainable recommendations | Deterministic facts, eight evidence cards and optional validated LLM paraphrasing |
| Interactive application | Streamlit pantry review, user profile, seven-dinner planning, grocery list and mid-week replanning |
| Quantitative evaluation | [Nine studies](../Evaluation/README.md) covering held-out planning, ablations, robustness, preference ranking, NLP, solver comparison and GA tuning |

The two-day expiry safety margin is an independently evaluated experimental planner variant; the published application uses the original MILP default. Ingredient substitutions are applied after weekly optimisation. The optional LLM is not required for core planning.

## October 21 evaluation updates

- [Ingredient NLP](../Evaluation/08_ingredient_nlp/README.md): 120 synthetically generated, team-reviewed messages (1,718 ingredient mentions), rules-only precision 0.983, recall 0.822, F1 0.895. Initial labels were programmatically generated and reviewed by the team; optional LLM fallback not evaluated.
- [Expiry safety margin](../Evaluation/09_expiry_safety_margin/README.md): two-day margin selected on v2 validation and tested on fresh v3 kitchens. It improves robustness to early spoilage but is not yet the default planner.
- [Frozen v3 benchmark](../data/evaluation/v3/README.md): 120 new test-only kitchens plus synthetic pantry-message answer keys.
