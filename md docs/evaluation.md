# Evaluation

> **Results package:** [`Evaluation/`](../Evaluation/README.md) has one folder per evaluation, each with its tables,
> the command that produced them and the per-scenario CSV. This page is the design and the running record. The
> folder is what to read, or copy, for the report.

## Metrics

| # | Metric | Checks |
| --- | --- | --- |
| 1 | Pantry utilisation | How much of the pantry gets used before it expires |
| 2 | Food waste | Grams unused at expiry |
| 3 | Extra groceries | What the plan needs beyond the pantry |
| 4 | Constraint safety | Diet/allergy violations — must be zero |
| 5 | Nutrition adherence | Intake vs. the user's target range |
| 6 | Preference quality | Preference score, disliked-meal rate |
| 7 | Ingredient NLP | Precision, recall, F1 on the labelled set (2026-10-21: measured on a synthetic, generator-labelled set; see `Evaluation/08`) |
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

> **Note (2026-10-13):** the tables below, up to "Weight sweep", were produced with the original hand-set weights
> (preference 1.0, kcal 4.0, protein 2.0). The optimiser now defaults to preference 6.0, kcal 8.0, protein 4.0
> (see "Weight sweep"), so re-running them gives different optimiser rows. **The current reference is the next
> section.**

### Final result: held-out test split, run once (2026-10-16)

*Frozen benchmark v2 · **test split** (n = 120, 15 per family; robustness n = 48) · weights frozen beforehand
(preference 6.0, kcal 8.0, protein 4.0, waste 1.0; the waste ×2 candidate was not adopted) · current code. Every table,
per-family result and CSV: [`Evaluation/`](../Evaluation/README.md) (01 planners, 02 ablations, 03 robustness). This is
the single unbiased estimate; any later change of method or weights needs a new benchmark version.*

| Method | Waste (g) | Extra grocery items | Pantry utilisation % | Expiring stock used % | Dinners in kcal band % | Protein ok % | Preference (0–1) | Weekday overtime % | Violations | s / plan |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Random | 859 | 44.8 | 6.9 | 2.7 | 14.9 | 31.0 | 0.53 | 48 | 0 | 0.01 |
| Greedy | 771 | 23.7 | **27.0** | 14.8 | 3.5 | 13.7 | 0.53 | 37 | 0 | 0.08 |
| Genetic (GA) | 724 | 15.4 | 18.1 | 20.5 | 65.8 | **57.6** | **0.59** | 20 | 0 | 0.58 |
| **MILP (HiGHS)** | **710** | **15.3** | 18.9 | **22.5** | **68.2** | **57.6** | **0.59** | **16** | 0 | 3.95 |

Paired, 95 % bootstrap CI (n = 120):
- MILP − greedy: waste **−61.5 g** [−83.3, −40.5], groceries **−8.4 items** [−9.6, −7.0], expiring stock used
  **+7.7 pts**, kcal-in-band **+64.8 pts**, protein **+43.9 pts**, preference **+0.065**, weekday overtime **−21 pts**.
- GA − greedy: waste **−47.1 g** [−67.9, −28.5], groceries **−8.3 items**, kcal-in-band **+62.4 pts**.
- MILP − GA: waste **−14.3 g** [−22.2, −6.7], kcal-in-band **+2.4 pts** [+0.2, +4.6], groceries −0.1 [−0.4, +0.3].

GA over 5 seeds: waste 729.7 ± 2.6 g, so the MILP's edge holds against every seed (−16 to −22 g). Validation (below)
agrees in every direction, and the waste gains are larger on test.

- **Ablations (test, variant − full MILP):**
  - no expiry: waste **+36.5 g** [+25.4, +48.8];
  - no nutrition: kcal-in-band **−46.1 pts**, groceries −4.2 items;
  - no preference: preference **−0.034** [−0.043, −0.028], disliked dinners 0.5 % → 1.7 %, groceries −0.6 items.
- **Robustness (test, n = 48):** the expiry-aware MILP degrades the most (+15 to +19 g vs `opt_no_expiry` under
  early spoilage or less stock, significant in 5 of 7 perturbations), so the proposal's expectation is not supported.
  It still has the lowest real waste in every perturbed kitchen.

The cost to state with these results: the optimisers buy fewer distinct items but about 0.9 kg more food by weight
than greedy, and they waste more than greedy in `restrictive_diet` and `infeasible_combo`.

### Current reference run: Greedy vs Genetic vs MILP (validation, 2026-10-16)

*Frozen benchmark v2 · **validation split** (n = 120, 15 per family) · adopted weights · current code ·
`python src/evaluation/runner.py --split validation --planners random,greedy,genetic,optimiser --baseline greedy
--save`. Full tables, per-family results and the 5-seed GA check:
[`Evaluation/01_planner_comparison`](../Evaluation/01_planner_comparison/README.md). The test split was run
once afterwards (see above).*

| Method | Waste (g) | Extra grocery items | Pantry utilisation % | Dinners in kcal band % | Protein ok % | Preference (0–1) | Weekday overtime % | Violations | s / plan |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Random | 854 | 44.1 | 7.2 | 13.8 | 30.6 | 0.54 | 42 | 0 | 0.01 |
| Greedy | 763 | 23.7 | **26.3** | 3.6 | 12.3 | 0.52 | 31 | 0 | 0.09 |
| Genetic (GA) | 734 | **15.4** | 16.3 | 69.5 | **59.6** | 0.61 | 16 | 0 | 0.61 |
| **MILP (HiGHS)** | **723** | **15.4** | 17.3 | **70.6** | 59.4 | **0.62** | **13** | 0 | 4.67 |

Paired, 95 % bootstrap CI (n = 120):
- MILP − greedy: waste **−40 g** [−64, −17], groceries **−8.3 items** [−9.8, −6.8], kcal-in-band **+67 pts**.
- GA − greedy: waste **−30 g** [−52, −8], groceries **−8.3 items**, kcal-in-band **+66 pts**.
- MILP − GA: waste **−10 g** [−17, −3], groceries +0.0 [−0.2, +0.3], kcal-in-band +1.1 [−1.0, +3.5].

The GA is stable across 5 seeds (waste 728.8 ± 1.9 g), so it is a near-equal, 7.7× faster alternative to the MILP. The
optimisers buy fewer distinct items but about 0.9 kg more food by weight than greedy. Greedy and the MILP match the
2026-10-14 run below (greedy exactly; the MILP within the time-limit noise).

### Ablations re-run with the adopted weights (2026-10-16)

*Same split, n = 120; each variant minus the full MILP. Details:
[`Evaluation/02_ablations`](../Evaluation/02_ablations/README.md).*

| Variant | Waste (g) | Expiring stock used (pts) | Grocery items | kcal-in-band (pts) | Protein ok (pts) | Preference | Disliked dinners (pts) |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `no_expiry` | **+32 \*** [+21, +44] | **−4.3 \*** | **−0.4 \*** | −0.5 | −1.0 | +0.003 | −0.1 |
| `no_nutrition` | −8 [−20, +3] | +0.7 | **−3.8 \*** | **−45 \*** [−49, −41] | **−26 \*** | +0.002 | −0.5 |
| `no_preference` | **−15 \*** [−26, −7] | **+1.8 \*** | **−1.0 \*** | −1.1 | −0.7 | **−0.050 \*** [−0.061, −0.040] | **+1.3 \*** |

With the tuned weights the preference term is now a real lever: −0.050 when switched off, where the 2026-10-12 run
below found −0.01. Its price is about 15 g of waste and one grocery item per week.

### Earlier reference run: adopted weights + vegetarian without eggs (2026-10-14)

*Frozen benchmark v1 · **validation split only** (n = 120) · adopted weights (preference 6.0, kcal 8.0, protein 4.0) ·
vegetarian = no meat, fish **or eggs** (rule changed 2026-10-14, dataset rebuilt) · `python src/evaluation/runner.py
--split validation --planners random,greedy,optimiser --baseline greedy --save` → `data/evaluation/runs/
20261014_153425_validation.csv`. The test split has still not been run.*

| Method | Waste (g) | Extra grocery items | Pantry utilisation % | Dinners in kcal band % | Preference (0–1) | Weekday overtime | Violations | s / plan |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Random | 854 | 44.1 | 7.2 | 13.8 | 0.54 | 0.42 | 0 | 0.02 |
| Greedy | 763 | 23.7 | **26.3** | 3.6 | 0.52 | 0.31 | 0 | 0.14 |
| **Optimiser** | **722** | **15.6** | 17.6 | **71.6** | **0.61** | **0.13** | 0 | 5.8 |

Optimiser − greedy, 95 % bootstrap CI (n = 120): waste **−41 g** [−65, −18] · groceries **−8.1 items** [−9.7, −6.6] ·
utilisation −8.8 pts [−11.1, −6.4] (worse) · kcal-in-band **+68 pts** [+64, +72] · preference **+0.09** [+0.08, +0.11].
Every week complete, zero violations. Per family, waste is clearly lower in `expiry_heavy`, `sparse_pantry` and
`well_stocked`, indistinguishable in three families, and **higher than greedy in `restrictive_diet` (+48 g [+4, +95])
and `infeasible_combo` (+39 g [+10, +76])**. With few allowed recipes, the weights favour nutrition and fewer
groceries over using up stock.

**What the vegetarian rule changed** (optimiser, same weights; before = the `pref x6, nutrition x2` rows of the
2026-10-13 confirmation run; paired by scenario):

| Group | Waste (g) | Grocery items | kcal-in-band (pts) | Protein ok (pts) |
| --- | --- | --- | --- | --- |
| Vegetarian scenarios (n = 30) | +4.8 [−5.4, +15.6] | −0.67 [−1.30, −0.17] | −1.9 [−6.2, +1.9] | 0.0 [−3.8, +4.8] |
| Control: all other diets (n = 90) | −1.3 [−8.9, +4.7] | +0.12 [−0.03, +0.31] | +1.75 [+0.32, +3.65] | +0.5 [−0.6, +1.8] |

* **The effect is small.** The vegetarian pool shrank by about a fifth (8,898 → 6,990 recipes) but is still large.
  Only 5 of the 30 vegetarian scenarios had eggs in the pantry (21 g on average), so little stock became unusable.
  Waste, calorie fit and protein are unchanged within the CIs. The one CI that excludes zero, −0.7 grocery items, is
  small and is not explained here.
* **The control moved slightly** (+1.75 in-band pts), although nothing changed for those users. The optimiser stops
  at an 8 s wall-clock limit, so a busier or quieter machine finds slightly different plans. Treat differences of this
  size as run-to-run noise. Greedy, which is deterministic, is identical on every control scenario that both runs share
  (36 of 36), confirming the dataset rebuild changed nothing except the vegetarian flag.
* Not re-run under the new rule: ablations, solver comparison and the weight sweeps below. The rule only touches 25 %
  of scenarios and moved none of the headline measures, so their conclusions are not expected to change.

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

### Ablations, first run with the untuned weights (2026-10-12; superseded by the re-run above)

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

*Exploration: frozen benchmark v1 · **validation split only** · 48 scenarios (6 per family), all of which state a liked cuisine ·
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

* **First adoption: preference ×3**, by the pre-declared rule (liked-cuisine dinners +7 pts for +0.4 grocery
  items). It was later superseded; see the confirmation below.
* **Stronger settings failed the 0.5-item grocery guardrail**, which is a *product* limit, not a modelling one.
  Preference ×6 gives about 1.9 liked-cuisine dinners a week for about one extra item; nutrition ×2 lifts
  dinners-in-band from 58 % to 71 % for about two. The project owner decided both were worth it (2026-10-13), and
  the combination was re-measured as below.

#### Confirmation on all 120 validation scenarios (preference ×6 with nutrition ×2)

The owner's decision came *after* the 48-scenario sweep had been seen, so the exact candidate was re-measured on
every validation scenario (72 of which the sweep never used) against criteria fixed in `weight_sweep.py` *before* the
run. `python src/evaluation/weight_sweep.py --limit 0 --candidates "3:1,6:2" --confirm 6:2 --workers 3 --save`;
rows in `data/evaluation/runs/20261013_124746_weight_sweep_validation.csv`. Paired difference vs the start, 95 %
bootstrap CI (n = 120):

| Measure | Start | Preference ×6 + nutrition ×2 | Difference | Criterion | Met |
| --- | --- | --- | --- | --- | --- |
| Dinners in a liked cuisine | 12.6 % | 27.6 % | **+15.0 pts** [+11.8, +18.2] | ≥ +10 | yes |
| Dinners in the calorie band | 57.0 % | 70.7 % | **+13.7 pts** [+10.5, +17.1] | ≥ +8 | yes |
| Dinners reaching the protein minimum | 52.7 % | 59.4 % | +6.7 pts [+4.0, +9.3] | – | – |
| Extra grocery items | 12.9 | 15.7 | **+2.78** [+2.33, +3.27] | ≤ +3.5 | yes |
| Waste (g) | 710 | 722 | +11.9 [+3.1, +22.1] (+1.7 %) | ≤ +5 % | yes |
| Disliked meals | 2.3 % | 1.0 % | −1.3 pts [−3.1, −0.1] | ≤ +2 | yes |
| Rule violations / shorter weeks | 0 / 0 | 0 / 0 | – | none | yes |

**Adopted** (`OptimizerWeights`: preference 6.0, kcal 8.0, protein 4.0). It meets every criterion. Every one of the
eight families improved: dinners-in-band +10 to +20 pts, extra grocery items +2.1 to +3.9 (largest in
`conflicting_preferences` and `infeasible_combo`). Two things to keep in mind: the added waste is statistically
distinguishable from zero though small (+1.7 %), and the grocery cost is real (about 16 items a week instead of about
13, still roughly a third fewer than greedy's 24). This is a tuned-on-validation result; the test split has not been
run and remains the only unbiased estimate.

#### Variety: one protein all week (validation, n = 120, 2026-10-13)

Found by looking at the first real plan in the UI: seven chicken dinners for a pantry containing chicken. The sweeps
above never measured variety. Share of weeks with **5 or more dinners of one protein type**:

| Setting | One-protein weeks | Mean max same-type dinners | Extra grocery items | Liked-cuisine dinners |
| --- | --- | --- | --- | --- |
| Start weights | 84 % | 6.1 | 12.9 | 12.4 % |
| Adopted (pref x6, nutrition x2) | 83 % | 6.1 | 15.7 | 27.4 % |
| + variety x3 | 64 % | 5.6 | 16.3 | 21.5 % |
| + cap 3 | 83 % | 6.0 | 15.7 | 27.4 % |
| + variety x3, cap 3 | 62 % | 5.5 | 16.4 | 21.1 % |
| + variety x6, cap 3 | 53 % | 5.2 | 17.3 | 20.7 % |

**No candidate met the pre-declared criteria** (`VARIETY_CRITERIA`), so the adopted weights stand. The problem is
structural, not a weight: the objective counts *distinct* grocery items, so one protein bought once and used all week
is cheap, and the four-way protein taxonomy (poultry / meat / seafood / vegetarian) is coarse. A structural fix (a
per-main-ingredient cap, or charging repeated main ingredients) is open work. The new defaults did **not** cause it
(84 % vs 83 %). Rows: `data/evaluation/runs/20261013_131852_weight_sweep_validation.csv`.

### Robustness (measure 8, 2026-10-16)

*Frozen benchmark v2 (byte-exact rebaseline of v1) · **validation split only**, 48 scenarios (6 per family) · current
default weights · `python src/evaluation/robustness.py --split validation --planners greedy,optimiser,opt_no_expiry
--baseline opt_no_expiry --limit 48 --save` → rows in `Evaluation/03_robustness/robustness_validation.csv`.*

Each plan is made once from what the planner is told, then replayed against perturbed realities
(`evaluation/robustness.py`): estimated deadlines 1 or 2 days earlier, ±2-day jitter, 30 % less / more stock,
30 % per-item noise, and a combination. **Degradation** = perturbed − nominal, positive = worse.

Mean degradation (g of waste / g of groceries):

| Perturbation | Greedy | Optimiser | `opt_no_expiry` |
| --- | --- | --- | --- |
| spoils 1 day early | +18 / +18 | +10 / +10 | +11 / +11 |
| spoils 2 days early | +35 / +35 | +22 / +22 | +11 / +11 |
| 30 % less stock | −239 / +81 | −224 / +50 | −236 / +35 |
| combined (1 day early ± 1, 30 % noise) | +55 / +47 | +46 / +21 | +43 / +18 |

Paired difference in degradation, optimiser − `opt_no_expiry` (negative = optimiser more robust), 95 % CI, n = 48:
spoils 2 days early, waste **+10.8 g [−0.9, +25.5]**. 30 % less stock: waste **+11.7 g [+5.7, +18.7]**, groceries
**+15.2 g [+8.4, +23.0]**. All other perturbations are indistinguishable from zero, or small in the optimiser's favour
(30 % more stock: −2.8 g waste [−5.7, −0.3]).

* **The expiry term does not make the plan more robust; it makes it slightly less robust.** The optimiser schedules
  stock close to its *estimated* deadline, so when the food really spoils earlier, or there is less of it, more of that
  plan breaks. The planner without expiry awareness leans less on perishable stock, so it has less to lose. The slide's
  expectation ("less degradation than the planner without expiry awareness") is **not** supported.
* **It still ends ahead in absolute terms.** Even with food spoiling 2 days early, the optimiser's real waste
  (702 + 22 ≈ 724 g) stays below `opt_no_expiry`'s (734 + 11 ≈ 745 g) and greedy's (735 + 35 ≈ 770 g). The expiry
  term's advantage shrinks under wrong estimates, but within these perturbation sizes it does not reverse.
* **Greedy degrades most** under early spoilage (+24 g more than `opt_no_expiry` at 2 days [+8, +43]) and when there
  is less stock (+46 g more groceries [+32, +59]), because it cooks most from the pantry.
* With less stock, waste *falls* for every plan simply because there is less food to waste. Compare planners, and read
  the grocery columns for quantity perturbations.
* A natural remedy, not built: discount the expiry credit by the estimate's confidence more strongly, or re-plan
  mid-week (`optimizer/replan.py`) once the user reports what actually spoiled.

### Real-taste preference check: MealRec users (2026-10-16)

*Frozen real-taste set `data/evaluation/taste_v2` (100 MealRec users: 50 validation / 50 test; the same users as
`taste_v1`, plus dinner tags). The method and its settings were chosen on the validation users. The **test users were
then run once**, with nothing changed in between. `python src/evaluation/taste_eval.py --split validation|test`; per-user
rows in `Evaluation/04_real_taste_preferences/`.*

**Question.** The planning benchmark's likes are invented, so its preference metric only shows that the optimiser
follows them. Here the likes are real. For each user, the earliest 80 dinners they rated on Allrecipes play the part of
"dinners we suggested and they rated". Preferences built from those are checked against the dinners they rated
*later* (those that exist in our catalogue: about 24 per test user and 28 per validation user). No later rating is
used to build anything.

**Protocol** (the MealRec paper's own, Li et al. 2022, Section 5.1.1). Each held-out dinner is ranked against 99
recipes the user never rated, sampled at random with a fixed seed and shared by every method.
- **HR@K:** the dinner is in the top K of those 100. Chance is K/100, so HR@10 = 0.10.
- **NDCG@K:** also rewards a higher place.
- **AUC:** the stricter full-ranking counterpart (0.5 = chance), reported next to the sampled metrics because sampled
  metrics can flatter every method and even reorder them (Krichene & Rendle, KDD 2020).

**Methods** (none is trained):

| Method | What scores the catalogue |
| --- | --- |
| Popularity | Today's scorer for a user who states nothing: only the Food.com rating prior |
| Likes in the profile | Liked ingredients / cuisines derived from the history, put into today's scorer unchanged ("plug and play") |
| Average-dish similarity | Ingredient similarity to the user's *average* liked dinner |
| **Nearest dishes + tags** | Mean similarity to the user's **10 most similar** liked dinners, over ingredients and over tags (dish type, main protein, cuisine), mixed 50/50. Keeps mixed tastes (e.g. Mexican *and* Italian) apart |

**Results: test users, single run** (validation in brackets):

| Method | HR@10 | NDCG@10 | HR@5 | AUC |
| --- | --- | --- | --- | --- |
| Chance level | 0.100 | 0.045 | 0.050 | 0.500 |
| Popularity (today) | 0.119 (0.115) | 0.052 (0.058) | 0.055 (0.068) | 0.518 (0.531) |
| Likes in the profile | 0.140 (0.137) | 0.069 (0.071) | 0.074 (0.084) | 0.549 (0.539) |
| Average-dish similarity | 0.174 (0.204) | 0.085 (0.089) | 0.087 (0.100) | 0.587 (0.598) |
| **Nearest dishes + tags** | **0.202** (0.235) | **0.092** (0.116) | **0.107** (0.142) | **0.622** (0.643) |

Chance-level NDCG@10 is the expected value for a random rank among 100. The empirical `random` row that `taste_eval`
prints (test: HR@10 0.083, AUC 0.499) varies around those values.

Nearest dishes + tags minus popularity, paired over the 50 test users, 95 % bootstrap CI:
- HR@10 **+0.083 [+0.040, +0.127]**
- NDCG@10 **+0.040 [+0.020, +0.061]**
- AUC **+0.105 [+0.075, +0.134]**
- higher HR@10 for 64 % of users

**How to read it.**
* **Preferences learned from a person's past ratings predict what they choose later: about twice the chance hit
  rate** (HR@10 0.20 vs 0.10). They also beat today's popularity prior, with every confidence interval clear of zero
  on the held-out test users.
* **Plugging likes into the existing profile fields gives part of the gain** (test AUC +0.031 [+0.009, +0.053] over
  popularity, though not on HR@10). Keeping the whole history as nearest dishes with tags gives the largest gain.
* **The numbers stay well below the MealRec paper's** (HR@10 0.42–0.69). That is not a difference of metric. Those
  models are trained on the same site's own interaction data and rank whole meals; ours is content-only, works across
  sites (Allrecipes ratings → Food.com recipes), and needs no training. An exploratory diagnostic on the same
  validation users (scratch scripts, not in the repository) puts the gap in context. Inside MealRec, simple same-site
  popularity reaches HR@10 ≈ 0.45 and item-to-item collaborative filtering ≈ 0.46, while ingredient-only content stays
  at ≈ 0.19 there too. The limit is the missing behaviour data (who else liked what on *our* platform), which is slide
  4's "collaborative filtering once multi-user data exists".
* Food.com behaviour does not stand in for that data. On these users, Food.com rating counts (AUC 0.532) and
  Food.com item-to-item filtering (0.516) were no better than today's prior (validation, exploratory).
* **Now in the planner (2026-10-16):** the nearest-dishes score is the rating-history term of `preference.scorer`
  (dinners in `UserProfile.rated_dinners`, e.g. those marked "Loved it"). The integrated scorer was checked on the
  **validation users only** (`scorer_with_history`, added after the single test run): HR@10 0.240, NDCG@10 0.123,
  AUC 0.643, ahead of popularity by +0.125 HR@10 [+0.093, +0.159] for 82 % of users. That is the same as the method
  on its own, so wiring it in did not cost ranking quality. The test users were not run again.

<details><summary>First run on taste_v1 (validation only; superseded)</summary>

The first run, before tags and the paper's protocol existed, compared popularity (AUC 0.531), likes in the profile
(0.539) and average-dish similarity (0.598) on the same 50 validation users. An exploratory sweep of the like-derivation
thresholds reached at most 0.564 (about 23 likes per user, chosen on the users it is reported for). These numbers match
the AUC column above.
</details>

### How to read this

*(Numbers from the 2026-10-14 reference run; the 2026-10-16 Greedy vs GA vs MILP run above confirms them.)*

* **Supported:** planning the week jointly needs ~34 % fewer extra grocery items than greedy (15.6 vs 23.7), puts 72 %
  of dinners inside the calorie band (greedy: 4 %), cuts weekday over-time dinners from 31 % to 13 %, with **zero
  hard-rule violations**, in every family.
* **Modest, not uniform:** waste falls ~5 % on average (722 vs 763 g). It is clearly lower in 3 families,
  indistinguishable in 3, and **higher in `restrictive_diet` and `infeasible_combo`** (+48 g, +39 g): when the
  feasible pool is small the weights spend the plan on groceries and nutrition rather than on using up stock.
* **Worse on utilisation:** the optimiser cooks with *less* of the pantry overall (17.6 % vs 26.3 %) because it prefers
  recipes that need few new items; it is not using up more of what expires. Read it with waste and groceries, not alone.
* **Absolute waste is high for every method** (~700–850 g): a week of dinners cannot absorb a whole pantry. Compare
  methods, not the number.

### Caveats that matter

* The scenarios are **synthetic** (documented generator; no real households).
* The nutrition, preference and cook-time metrics use the **same definitions the optimiser minimises** — they favour it
  by construction. The independent checks are waste and groceries (replayed against *hidden* true expiry), the
  ablations, and robustness (see "Robustness").
* Weights are hand-set defaults. HiGHS reports loose proven gaps, but its plans were within ~0.4 % of the best objective
  found by any solver on 48 validation scenarios (see "Solver backends"); plans are good, not certified optimal.
* Seconds per plan were measured while the machine was also running other work.

## What's not proven

- Real taste satisfaction — there's no real user panel. Preference quality in the planning benchmark is measured against synthetic profiles with known likes/dislikes. The real-taste check above uses real people's past ratings (MealRec), but it is offline (ranking their later-rated dinners), positive-only, and not a study of people eating our plans.
- Constraint safety is relative to the knowledge base — hidden allergens in branded/packaged products aren't covered yet (see architecture.md → Out of scope).

## 2026-10-21 · Fresh benchmark v3, synthetic NLP set, expiry safety margin

* **v3** (`data/evaluation/v3/`): 120 new kitchens, new seeds, all test - fresh data for anything chosen after the v2
  test run.
* **Ingredient NLP** (`Evaluation/08_ingredient_nlp/`): 120 synthetic pantry messages from the v3 kitchens, labels from
  the generator. Rules-only parser: P 0.983, R 0.822, F1 0.895 [0.860, 0.922]; without the 10 " + "-separated
  messages R 0.890, F1 0.934. Parse-then-plan: +48.7 g waste [+30.5, +70.9] versus planning from the structured pantry.
  Do not tune the parser on m1; measure a fixed parser on a new message set.
* **Safety margin** (`Evaluation/09_expiry_safety_margin/`): `opt_margin2` chosen on v2 validation by a pre-written rule,
  run once on v3. Degradation versus `opt_no_expiry`: −5.4 g [−11.6, +0.0] (1 day early), −4.4 g [−12.5, +2.8]
  (2 days early) - measure 8 met; versus today's `optimiser`: −7.7 g and −9.5 g, CIs below 0; no nominal cost. Not yet the
  default.
