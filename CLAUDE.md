# Pantry-to-Plate

Read this first. It is the rulebook for anyone (human or Claude Code) changing this repo.
Design background lives in `md docs/` (architecture, systemflow, data, evaluation).

## Non-negotiables

- The LLM only parses input and writes explanations. It never decides what goes in the plan — rules and the optimiser do.
- Nutrition is always computed from grams × USDA per-100g values. Never estimate it.
- **Vegetarian means no meat, no fish, no eggs** (dairy is fine). Not the Western lacto-ovo convention. It is enforced
  through the dataset's `is_vegetarian` flag (`src/knowledge/build/ingredient_flags.py`). The UI defaults to it.
- Known use-by dates are hard constraints; FoodKeeper ranges are soft, weighted by confidence.
- Validation and test scenario splits are frozen before tuning weights. Never tune on the test set.
- Explanations must trace back to an actual solver cost term or fired rule — never a rationalisation.

## Stack

Python 3.14, pandas/pyarrow for data, rapidfuzz for fuzzy matching, pydantic for the typed objects that cross module
boundaries, pytest for tests.
Weekly optimiser: a mixed-integer *linear* model (`optimizer/linear_model.py`), solver-agnostic. Two backends:
HiGHS through `scipy.optimize.milp` (default, in-process) and OR-Tools CP-SAT (`solve_cpsat`, selected with the
`_cpsat` planner suffix). CP-SAT runs in a **child process** (`optimizer/cpsat_worker.py`) because on the Windows/conda
development machine OR-Tools and pyarrow cannot be loaded into one process (clashing `abseil`/`protobuf`/`re2` DLLs) -
never import `ortools` in the main process. See `md docs/modules/optimizer/backends.md`.
LLM: an open-source model served locally by Ollama (default `qwen3:8b`) through `src/llm/client.py` (Ollama's native
chat API; any OpenAI-compatible server is a config switch) - see `md docs/llm.md`. The LLM is optional; every feature
must work (more bluntly) without it, and every LLM answer is validated against the user's words or the solver's facts.

## Where things live

| Path | What | Rule |
| --- | --- | --- |
| `data/canonical/` | The curated dataset — single source of truth for ingredients, recipes, nutrition, shelf life | **Generated.** Never edit tables by hand. Edit `data/canonical/reference/*.csv` and rebuild |
| `data/FoodData_Central_*`, `data/recipes/`, `data/foodkeeper/` | Raw downloads | Read-only inputs to the build |
| `src/knowledge/` | Runtime access to the dataset (`KnowledgeStore`) + shared text normalisation | Read-only, no planning logic |
| `src/knowledge/build/` | The data build pipeline (steps 01-07, `run_all.py`) | Offline only; never imported at run time |
| `src/domain/` | Shared typed objects (`UserProfile`, `PantryItem`, `Scenario`, `WeekPlan`) and NLP→pantry conversion | Data shapes only; no planning logic |
| `src/nlp/` | Free text → structured pantry (parse, canonicalise, flag urgency) | Understands input; never plans |
| `src/preference/` | Content-based preference scoring | Scores; never filters safety |
| `src/llm/` | Transport to the language model (Ollama native / OpenAI-compatible) | Transport only; callers validate every answer; any failure is `LlmError` = "no LLM" |
| `src/optimizer/` | The only place that decides the weekly plan: hard rules, shortlist, inventory accounting, substitution rules, baselines, weekly MILP | Pure functions of their inputs |
| `src/explain/` | Turns solver output into plain English | Reads, never decides |
| `src/app/` | `PantryToPlateService`: the one object a UI calls (pantry review, profile, plan, grocery box, re-plan) | Orchestrates and presents; decides nothing |
| `src/ui/` | The Streamlit prototype (`streamlit run src/ui/streamlit_app.py`) | Layout and state only; every decision is the service's |
| `src/evaluation/` | Scenario generator, simulator-backed metrics, benchmark runner | Measures plans; never produces the app's plan |
| `src/logging_setup.py` | `configure_logging()` + `timed()`: where log lines go and how many | Only entry points call `configure_logging` |
| `data/evaluation/` | Frozen synthetic scenarios + split (+ SHA-256 freeze file) | Frozen: regenerate only by bumping the version |
| `tests/` | Mirrors `src/` (`tests/nlp/test_x.py` tests `src/nlp/x.py`) | Every module ships with tests |
| `md docs/` | Project-level design docs | Update when a design decision changes |
| `md docs/modules/` | **One doc per source/test file**, mirroring `src/` and `tests/` | See "Documentation rule" below |

Imports use `src/` as the root: `from knowledge.store import KnowledgeStore`, `from nlp.pantry_parser import PantryParser`.
(`pytest.ini` puts `src/` on the path; scripts under `src/knowledge/build/` add it themselves.)

## Documentation rule (important)

Every file under `src/` and `tests/` has a matching doc:

```
src/nlp/quantities.py        ->  md docs/modules/nlp/quantities.md
tests/nlp/test_quantities.py ->  md docs/modules/tests/nlp/test_quantities.md
```

- **Creating a file** → create its doc in the same change and add it to `md docs/modules/README.md`.
- **Changing a file** → update its doc in the same change: public API, behaviour, edge cases, and a dated line in its
  **Change log**. A code change without a doc change is an incomplete change.
- A doc says *what the file is for, how to use it, the decisions behind it, the known limits, and how it is tested*.
  It does not restate the code line by line.

## Code conventions

- **Comments explain *why*, not *what*.** Assume the reader is new to the project and to the domain. Each module starts
  with a docstring covering: purpose, where it sits in the pipeline, inputs/outputs, and the important design decisions.
- Every public function/class has a docstring with its contract (units, ranges, what `None` means, what it raises).
- Type hints everywhere. Data crossing a module boundary is a pydantic model or a dataclass, never a loose dict.
- Constants with a meaning (thresholds, default amounts, vocabularies) are named, grouped at the top of the module, and
  commented with *where the number came from*.
- Deterministic by default: anything random takes an explicit seed.
- No silent fallbacks. If the code guesses (assumed quantity, fuzzy match, category-level shelf life) it records that it
  guessed, in the returned object, so the explainer and the evaluation can see it.
- Keep functions small and pure where possible; I/O (reading parquet, calling an LLM) lives at the edges.
- Logging: each module does `logger = logging.getLogger(__name__)` and never configures handlers; only entry points
  call `logging_setup.configure_logging()`. DEBUG = detail inside a step, INFO = one line per user-visible step,
  WARNING = a degradation (LLM fallback, no plan). Use %-style arguments (`logger.info("x %d", n)`), not f-strings.
  Never log API keys, LLM prompts/answers, or the user's text above DEBUG. The log is for developers: anything the
  explainer or evaluation needs still goes in the returned object. See `md docs/modules/logging_setup.md`.

## Commands

```bash
python src/knowledge/build/run_all.py     # rebuild data/canonical from the raw downloads (~5 min)
streamlit run src/ui/streamlit_app.py    # the prototype UI (http://localhost:8501)
PTP_LOG_LEVEL=DEBUG streamlit run src/ui/streamlit_app.py   # same, with the step-by-step trace in the terminal
python -m pytest                          # run all tests
python -m pytest tests/nlp -q             # one package
python src/evaluation/build_benchmark.py  # freeze the synthetic benchmark (refuses if already frozen)
python src/evaluation/runner.py --split validation --planners random,greedy,optimiser --limit 24
```

## Git

Local repo, branch `main`. Raw downloads are git-ignored; `data/canonical/` is tracked so the team shares the same
dataset. Do not commit unless asked.
