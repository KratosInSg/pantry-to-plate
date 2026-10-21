# Pantry-to-Plate
### Intelligent Nutrition, Pantry & Grocery Planning System

**NUS-ISS · MTech in AI Systems · Intelligent Reasoning Systems (IRS) Practice Module**

**Team:** Aryan Chopra and Shreyash Sarade  
**Project status:** Completed prototype and recorded held-out evaluation (October 2026). This repository is for academic assessment, not a deployed grocery subscription service.

Pantry-to-Plate converts pantry descriptions written in ordinary language into a **seven-day dinner plan** and a list of **additional ingredients needed**. It accounts for dietary and allergen restrictions, estimated or known use-by dates, nutrition targets, preferences, weekday cooking time, and available pantry stock. Each dinner includes traceable explanations. The application supports mid-week replanning and a “Loved it” feedback signal.

> **Scope:** One household profile; dinners only; academic prototype. No payment, grocery delivery, clinical dietary advice, packaged-food allergen verification, or real-household food-waste trial.

## Quick start

Use a supported Python environment and install the project dependencies:

```bash
git clone https://github.com/KratosInSg/pantry-to-plate.git
cd pantry-to-plate
python -m venv .venv
source .venv/bin/activate            # Windows PowerShell: .venv\\Scripts\\Activate.ps1
python -m pip install -r requirements.txt
python -m streamlit run src/ui/streamlit_app.py
```

The optional local LLM uses Ollama and `qwen3:8b`; it is **not required** to run the rule-based pantry parser, optimisation engine, or deterministic explanations. The UI works without an LLM. Refer to [LLM setup](md%20docs/llm.md) for optional configuration.

## User workflow

1. Enter pantry ingredients, quantities, and expiry information in natural language.
2. Review or correct the parsed ingredient rows and any assumed amounts/dates.
3. Select diet, allergens, exclusions, preferred foods/cuisines, calorie and protein targets, and cooking-time limits.
4. Generate a seven-dinner plan, view ingredients and cooking steps, and inspect the eight XAI evidence cards.
5. Download the additional-groceries list; mark meals cooked, skipped, rejected or loved and replan.

## Intelligent reasoning techniques

| NUS-ISS area | Implementation |
| --- | --- |
| **Machine Reasoning (MR)** | Knowledge-based dietary and allergen hard-rule filtering; ingredient ontology/flags; expiry knowledge; rule-based substitutions from safe, spare pantry stock |
| **Reasoning Systems (RS)** | Seven-day multi-objective MILP via SciPy/HiGHS; OR-Tools CP-SAT cross-check; evolutionary genetic algorithm and greedy/random baselines; ablation and robustness studies |
| **Knowledge discovery / recommendation** | Content-based preferences and similarity to previously liked dishes; offline evaluation using 100 MealRec users |
| **Cognitive Systems (CGS)** | Rules-first pantry language parsing, optional checked local LLM fallback, evidence-backed explanations and checked paraphrasing |

The optimiser weighs **expiring waste, additional groceries, calorie/protein deviations, taste, weekday overtime, and variety**. Hard safety exclusions are enforced before optimisation and are never soft objective penalties. Ingredient substitutions are applied after planning, not jointly optimised, and nutrition is not recomputed for a swapped ingredient.

## Recorded experimental results

The frozen synthetic benchmark has **240 scenarios** across eight household families, divided into **120 validation and 120 held-out test** scenarios. These are simulated kitchens, not observations of real households. The held-out planner test was run once on **16 October 2026**.

| Metric — mean over 120 test scenarios | Greedy | GA | MILP (HiGHS) |
| --- | ---: | ---: | ---: |
| Simulated food waste (g/week) ↓ | 771.2 | 724.1 | **709.8** |
| Distinct additional grocery items ↓ | 23.7 | 15.4 | **15.3** |
| Additional grocery mass (g/week) ↓ | **548** | 1,440 | 1,442 |
| Starting pantry used (%) ↑ | **27.0** | 18.1 | 18.9 |
| Expiring pantry used (%) ↑ | 14.8 | 20.5 | **22.5** |
| Dinners within calorie band (%) ↑ | 3.5 | 65.8 | **68.2** |
| Weekday overtime (%) ↓ | 36.8 | 19.8 | **16.3** |
| Runtime (s/plan; recorded benchmark) ↓ | **0.08** | 0.58 | 3.95 |

All three planners produced complete seven-dinner plans with **zero recorded hard-rule violations** on these test scenarios. MILP reduced mean simulated waste by approximately **61 g/week** relative to greedy (paired 95% bootstrap CI approximately **−83 to −41 g**). The GA was approximately **7× faster** than MILP on the recorded benchmark, with slightly lower plan quality.

**Trade-offs matter:** Greedy bought less food by mass and consumed more starting pantry inventory. The optimisers preferentially used expiring stock and improved nutrition adherence, but bought more grocery mass. The original expiry-aware optimiser degraded more when expiry estimates were wrong. A subsequent **two-day estimated-expiry safety margin** improved early-spoilage robustness on 120 fresh v3 synthetic kitchens: 7.7 g and 9.5 g less degradation than the original MILP at one and two days early, respectively. This is an **experimental variant**, not the application's default. See [09 — Expiry safety margin](Evaluation/09_expiry_safety_margin/README.md).

**Real-user taste check:** On 50 held-out MealRec users, nearest-liked-dish content scoring reached **HR@10 0.202** and **AUC 0.622**, compared with a chance HR@10 of 0.100 and a popularity-prior HR@10 of 0.119. This is **content-based recommendation, not a newly trained ML model**, and does not demonstrate real household meal adoption.

**Ingredient NLP evaluation (v3):** On 120 **synthetic, generator-labelled** pantry messages (1,718 items), the rules-only parser achieved precision **0.983** (95% CI [0.975, 0.989]), recall **0.822** ([0.765, 0.867]) and F1 **0.895** ([0.860, 0.922]). Amount accuracy on found items was 0.999 and urgency accuracy 0.989; only 19% of whole messages were completely correct. Planning from parsed messages increased simulated waste by **48.7 g/week** ([30.5, 70.9]) versus structured input. These are **not hand-labelled data**; the optional LLM fallback was not evaluated. See [08 — Ingredient NLP](Evaluation/08_ingredient_nlp/README.md).

## Evaluation and documentation

| Resource | Contents |
| --- | --- |
| [Evaluation results index](Evaluation/README.md) | Seven experiment families, raw CSVs, confidence intervals and caveats |
| [01 — Planner comparison](Evaluation/01_planner_comparison/README.md) | Random, greedy, GA, MILP, test/validation and GA seeds |
| [02 — Ablations](Evaluation/02_ablations/README.md) | Expiry, nutrition and preference objective contributions |
| [03 — Robustness](Evaluation/03_robustness/README.md) | Earlier expiry and incorrect pantry quantities; negative findings reported |
| [04 — Real taste](Evaluation/04_real_taste_preferences/README.md) | MealRec user evaluation and ranking metrics |
| [05 — Solver backends](Evaluation/05_solver_backends/README.md) | HiGHS versus CP-SAT |
| [06 — Weight tuning](Evaluation/06_weight_tuning/README.md) | Validation-only objective-weight selection |
| [07 — GA configuration](Evaluation/07_ga_configuration/README.md) | Five-seed GA population, mutation and generation experiments |
| [08 — Ingredient NLP](Evaluation/08_ingredient_nlp/README.md) | Synthetic parser precision/recall/F1 and parse-then-plan effects |
| [09 — Expiry safety margin](Evaluation/09_expiry_safety_margin/README.md) | v3 robustness study of a two-day estimated-expiry margin |
| [Architecture](md%20docs/architecture.md) | Five-stage system design |
| [Data preparation](data/canonical/README.md) | Canonical ingredients, data quality gates and sources |
| [Installation / technical documentation](md%20docs/README.md) | Implementation and module-level documentation |
| [Security and deployment limitations](md%20docs/security.md) | Input limits, escaping, dependencies and deployment checklist |
| [Original project proposal](documentation/Pantry_to_Plate_IRS_Project_Proposal.docx) | Submitted project proposal |

### Run tests

```bash
python -m pytest -q
```

Reproduction commands for the published evaluation are in [Evaluation/README.md](Evaluation/README.md). **Do not retune using the already-used held-out test split.** For a new model version or newly labelled evaluation, document the protocol, version and separation from prior test results.

## Data and usage limitations

The recipe corpus comes from Food.com; nutrition is joined from USDA FoodData Central; shelf-life estimates use USDA FoodKeeper. The real-taste study uses MealRec (Allrecipes-derived ratings). Ingredient amounts for retained Food.com recipes were estimated against nutritional constraints, not directly observed. Some expiry dates are estimates. Dataset licensing and permission must be reviewed before commercial use; MealRec raw/derived user data is not redistributed here.

The app is a research prototype, not a clinically validated diet planner or an allergen certification tool. It has no persistent user accounts, payment processing or actual grocery fulfilment. See the security checklist before any public deployment.

## NUS-ISS submission

The IRS practice module briefing requires: a group report with business case, design, implementation, experiments and findings; the original proposal, MR/RS/CGS mapping and installation/user-guide appendices; **two separate five-minute videos** (business promotion/demo/pricing and technical system design); a repository ZIP; and a `member-github.txt` file. The group leader uploads one combined ZIP to **[Group Leader] Project Deliverables (zip)** in Canvas. Each member separately submits the confidential individual reflection/peer evaluation to **[Individual] Project Peer Evaluation**. Verify exact naming and any template requirements in Canvas.

**Project team:** Aryan Chopra · Shreyash Sarade  
**Repository:** https://github.com/KratosInSg/pantry-to-plate

## Acknowledgements

NUS-ISS IRS course team; Food.com, USDA FoodData Central, USDA FoodKeeper and MealRec data providers; SciPy/HiGHS, OR-Tools, Streamlit, rapidfuzz, pandas and other open-source contributors. Any use of coding assistants or AI in the report and presentation should be disclosed accurately by the project team.
