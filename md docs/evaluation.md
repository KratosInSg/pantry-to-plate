# Evaluation

## Metrics

| # | Metric | Checks |
| --- | --- | --- |
| 1 | Pantry utilisation | How much of the pantry gets used before it expires |
| 2 | Food waste | Grams unused at expiry |
| 3 | Extra groceries | What the plan needs beyond the pantry |
| 4 | Constraint safety | Diet/allergy violations — must be zero |
| 5 | Nutrition adherence | Intake vs. the user's target range |
| 6 | Preference quality | Preference score, disliked-meal rate |
| 7 | Ingredient NLP | Precision, recall, F1 on the labelled set |
| 8 | Robustness | How much the plan degrades under perturbed expiry/quantities |

All eight are measured on the same frozen held-out scenarios, for every method, baselines included.

## Baselines

- **Greedy** — matches recipes to pantry ingredients one at a time; this is how most recipe apps work today, so it's the fair comparison for the joint-planning claim.
- **Random** — a lower bound.
- **Ablations of our own system** — drop expiry awareness, nutrition optimisation, or preference scoring one at a time, to see what each contributes.
- **LLM-only planner** (stretch) — an LLM asked to write the week's plan directly, with no rules/optimiser — only if the team takes this on; see the Q&A prep.

## Process

1. **Gate the data** — coverage and consistency checks before any modelling (see [data.md](data.md)).
2. **Compare against baselines** — identical scenarios, all 8 metrics.
3. **Ablate** — remove one component at a time to attribute the gain.

## Statistical comparison

All methods run on the same scenarios, so comparisons are paired: mean difference with 95% bootstrap confidence intervals, or a Wilcoxon signed-rank test, reported per scenario family (not pooled).

## Results so far

*Frozen benchmark v1 · **validation split only** (120 scenarios, 15 per family) · default optimiser weights, **not
tuned** · run on 2026-10-12 with `python src/evaluation/runner.py --split validation --planners
random,greedy,optimiser --baseline greedy --save`. The test split has not been run.*

| Method | Waste (g) | Extra grocery items | Pantry utilisation % | Dinners in kcal band % | Preference (0–1) | Weekday overtime | Violations | s / plan |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Random | 852 | 44.2 | 7.3 | 14.2 | 0.54 | 0.42 | 0 | 0.02 |
| Greedy | 764 | 23.6 | **26.4** | 3.6 | 0.52 | 0.30 | 0 | 0.16 |
| **Optimiser** | **709** | **13.0** | 17.7 | **56.7** | **0.57** | **0.11** | 0 | 7.0 |

Paired difference, optimiser − greedy, 95 % bootstrap CI (n = 120): waste **−55 g** [−77, −34] · groceries **−10.5
items** [−12.0, −9.1] · utilisation **−8.7 pts** [−10.9, −6.5] (worse) · kcal-in-band **+53 pts** [+48, +58] ·
preference **+0.04** [+0.03, +0.06].

Per family (optimiser − greedy; CI over 15 scenarios, so wide):

| Family | Waste (g) | Grocery items | kcal-in-band (pts) |
| --- | --- | --- | --- |
| expiry_heavy | **−96** [−141, −57] | −9.5 [−13.4, −5.5] | +58 [+45, +71] |
| well_stocked | **−122** [−163, −80] | −2.9 [−5.0, −0.8] | +51 [+39, +61] |
| nutrition_pressure | **−75** [−132, −28] | −8.8 [−11.0, −6.5] | +55 [+49, +63] |
| tight_time | **−77** [−158, −5] | −8.9 [−12.3, −4.9] | +53 [+35, +71] |
| conflicting_preferences | −65 [−137, +1] | −9.9 [−13.9, −6.1] | +50 [+34, +65] |
| sparse_pantry | −55 [−138, +11] | −11.4 [−15.1, −8.1] | +68 [+55, +79] |
| restrictive_diet | +21 [−21, +65] | −14.9 [−19.6, −10.3] | +68 [+58, +78] |
| infeasible_combo | **+30** [+5, +64] | −18.1 [−20.7, −15.6] | +23 [+15, +31] |

### Ablations (same split; each variant minus the full optimiser, paired, n = 120)

Run with `--planners opt_no_expiry,opt_no_nutrition,opt_no_preference --save`; paired against the full optimiser's rows
from the run above. `*` = the 95 % CI excludes 0.

| Variant (term switched off) | Waste (g) | Expiring stock used (pts) | Grocery items | kcal-in-band (pts) | Protein ok (pts) | Preference |
| --- | --- | --- | --- | --- | --- | --- |
| `no_expiry` | **+35 \*** [+24, +47] | **−4.2 \*** [−5.6, −3.0] | −0.35 \* | +1 [−1, +3] | +0.6 | 0.00 |
| `no_nutrition` | +2 [−7, +11] | −0.4 | **−2.5 \*** [−3.0, −2.1] | **−32 \*** [−36, −28] | **−19 \*** [−23, −15] | 0.00 |
| `no_preference` | −5 [−9, 0] | +0.4 | −0.2 \* | −0.7 | −1.0 | **−0.01 \*** [−0.01, −0.00] |

* **Expiry term:** real but small — without it 35 g more food spoils (waste 76 % → 80 % of expiring stock).
* **Nutrition term:** large and clean — it buys +32 points of in-band dinners and +19 points of protein-ok dinners for
  about 2.5 extra grocery items per week, and does not change waste.
* **Preference term: almost no effect.** Removing it moves mean preference by 0.01. With the current weight and
  score spread (scores cluster near 0.5) it is a weak lever, so **the preference gain over greedy (+0.04) is mostly a
  by-product of other terms, not evidence that the preference term works.** Treat "preference quality" as unproven
  until the term is re-scaled and re-tested on validation.

### Solver backends: HiGHS vs CP-SAT (same model, same weights)

*Validation split only · 48 scenarios (the runner's stratified head, 6 per family) · shortlist 120, 8 s limit, 2 % gap ·
run on 2026-10-13. Weights untuned. Test split not touched.*

**Solver-only comparison** on identical built models. "True gap" is measured against the best objective *any*
configuration found on that scenario (not against a solver's own bound). Produced by a one-off script that is **not kept
in the repo**; the numbers are recorded here, not reproducible from a command.

| Configuration | Proved optimal | Mean s | Mean true gap | p90 true gap | Within 0.5 % of best |
| --- | --- | --- | --- | --- | --- |
| HiGHS (default) | 62 % | 5.8 | 0.38 % | 1.3 % | 41 / 48 |
| CP-SAT, 8 workers | 60 % | 6.0 | 0.51 % | 1.4 % | 40 / 48 |
| CP-SAT, 1 worker | 2 % | 9.6 | 17.6 % | 31.5 % | 3 / 48 |
| CP-SAT, 8 workers, 30 s (reference) | 85 % | 10.6 | 0 | 0 | 48 / 48 |

HiGHS and 8-worker CP-SAT return the same objective on 34 / 48 scenarios; HiGHS is strictly better on 6, CP-SAT on 8.
No CP-SAT run was infeasible or errored. CP-SAT seconds include ~1–2 s of child-process start-up.

**Plan quality** (`python src/evaluation/runner.py --split validation --planners greedy,optimiser,optimiser_cpsat
--limit 48 --baseline greedy --save`, saved as `data/evaluation/runs/20261013_112653_validation.csv`):

| Method | Waste (g) | Extra grocery items | Pantry utilisation % | Dinners in kcal band % | Preference | Violations | s / plan |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Greedy | 736 | 24.2 | 26.2 | 4.5 | 0.53 | 0 | 0.08 |
| Optimiser (HiGHS) | 682 | 13.3 | 16.9 | 58.0 | 0.57 | 0 | 5.6 |
| Optimiser (CP-SAT) | 679 | 13.1 | 17.2 | 56.3 | 0.58 | 0 | 5.5 |

Paired, CP-SAT − HiGHS, 95 % bootstrap CI (n = 48): waste −3 g [−14, +7] · groceries −0.21 items [−0.42, 0.00] ·
kcal-in-band −1.8 pts [−4.5, +0.6] · preference 0.00. **No difference is distinguishable from zero**; waste is identical
in 31 / 48 scenarios. Both beat greedy by the same margins as in the n = 120 run above.

* **Reading:** at these settings the solver choice does not change the plans. HiGHS stays the default (in-process, no
  start-up cost, no parallelism needed). CP-SAT is kept as an independent cross-check — it already caught a modelling
  discrepancy (`backends.md`).
* **HiGHS's "loose proven gap" is a loose *bound*, not a loose plan:** its plans are within ~0.4 % of the best found
  even where it only proves 10–20 %.
* **CP-SAT's edge, if any, is parallelism.** With one worker it is far worse than HiGHS (17.6 % mean gap). On a machine
  with few cores do not expect the 8-worker numbers.
* **Not equal compute.** HiGHS is single-threaded; CP-SAT used 8 workers on a 32-core machine.
* With 6 scenarios per family, per-family solver differences (e.g. `well_stocked` favours HiGHS, `restrictive_diet`
  CP-SAT) are noise-level; do not read them.

### Weight sweep: making preferences visible (validation only)

*Frozen benchmark v1 · **validation split only** · 48 scenarios (6 per family), all of which state a liked cuisine ·
run on 2026-10-13 with `python src/evaluation/weight_sweep.py --limit 48 --workers 6 --save` (rows in
`data/evaluation/runs/20261013_121922_weight_sweep_validation.csv`). Test split not touched.*

Why: reading real explanations showed the preference term had almost no effect, so a user who says "I like Italian
food" would see no change. Candidates are multiples of the hand-set start (preference 1.0, kcal 4.0, protein 2.0).
The choice rule and guardrails are in `weight_sweep.py` and were fixed before the run.

Paired difference vs the start, 95 % bootstrap CI (n = 48):

| Candidate | Liked-cuisine dinners (pts) | Preference score | Dinners in kcal band (pts) | Extra grocery items | Waste (g) | Guardrails |
| --- | --- | --- | --- | --- | --- | --- |
| **pref ×3** (adopted) | **+7.1** [+3.9, +10.7] | +0.023 [+0.014, +0.034] | −1.2 [−3.3, +1.2] | +0.40 [+0.04, +0.77] | +2 [−7, +12] | pass |
| pref ×6 | +17.0 [+12.5, +21.7] | +0.056 [+0.043, +0.070] | −3.0 [−6.3, +0.3] | +1.15 [+0.65, +1.69] | +5 [−5, +16] | fails groceries |
| nutrition ×2 | +0.6 [−2.1, +3.3] | +0.003 | **+12.8** [+8.6, +17.6] | +1.94 [+1.38, +2.58] | −3 [−16, +9] | fails groceries |
| pref ×3 + nutrition ×2 | +3.0 | +0.020 | +13.7 | +2.15 | +1 | fails groceries |
| pref ×6 + nutrition ×2 | +17.0 | +0.050 | +11.3 | +2.65 | +19 | fails groceries |

Absolute at the start: 10.7 % of dinners in a liked cuisine, 58.0 % in the calorie band, 52.1 % reaching the protein
minimum, 13.3 extra grocery items.

* **Adopted: preference ×3** (`OptimizerWeights.preference` 1.0 → 3.0). Real and statistically clear, but modest:
  from about 0.7 to about 1.25 liked-cuisine dinners in a week. Waste, nutrition and rule violations are
  indistinguishable from unchanged.
* **Stronger taste matching is available at a price.** ×6 gives about 1.9 liked-cuisine dinners a week for about
  one extra grocery item a week; it failed the pre-declared 0.5-item guardrail, so it was not adopted. That is a
  *product* choice (a "how much should my tastes matter" setting), not a modelling one.
* **Nutrition is a separate trade-off.** Doubling the nutrition weights lifts dinners-in-band from 58 % to 71 % and
  protein-ok from 52 % to 58 %, for about two extra grocery items a week, with waste unchanged. It was not adopted
  because it failed the same guardrail; it is the single biggest lever on how "on target" the plans look.
* Results above in this document (n = 120 and n = 48 tables) were produced with preference 1.0.

### How to read this

* **Supported:** planning the week jointly needs ~45 % fewer extra grocery items than greedy, puts 57 % of dinners
  inside the calorie band (greedy: 4 %), cuts weekday over-time dinners from 30 % to 11 %, with **zero hard-rule
  violations** — in every family.
* **Modest, not uniform:** waste falls ~7 % on average. It is clearly lower in 4 families, indistinguishable in 3, and
  **higher in `infeasible_combo`** (+30 g): when the feasible pool is tiny the default weights spend the plan on
  groceries and nutrition rather than on using up stock.
* **Worse on utilisation:** the optimiser cooks with *less* of the pantry overall (17.7 % vs 26.4 %) because it prefers
  recipes that need few new items; it is not using up more of what expires. Read it with waste and groceries, not alone.
* **Absolute waste is high for every method** (~700–850 g): a week of dinners cannot absorb a whole pantry. Compare
  methods, not the number.

### Caveats that matter

* The scenarios are **synthetic** (documented generator; no real households).
* The nutrition, preference and cook-time metrics use the **same definitions the optimiser minimises** — they favour it
  by construction. The independent checks are waste and groceries (replayed against *hidden* true expiry), the
  ablations, and robustness (not yet implemented).
* Weights are hand-set defaults. HiGHS reports loose proven gaps, but its plans were within ~0.4 % of the best objective
  found by any solver on 48 validation scenarios (see "Solver backends"); plans are good, not certified optimal.
* Seconds per plan were measured while the machine was also running other work.

## What's not proven

- Real taste satisfaction — there's no real user panel. Preference quality is measured against synthetic profiles with known likes/dislikes, and optionally checked offline by seeing whether the preference score ranks Food.com users' higher-rated recipes above their lower-rated ones.
- Constraint safety is relative to the knowledge base — hidden allergens in branded/packaged products aren't covered yet (see architecture.md → Out of scope).
