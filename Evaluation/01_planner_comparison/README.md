# 01 · Planner comparison: Greedy vs Genetic algorithm vs MILP

The proposal's core claim is that **planning the whole week jointly beats one-meal-at-a-time planning**. Three ways of
choosing 7 dinners are compared on identical scenarios, all judged by the same pantry replay:

| Planner | How it chooses | Code |
| --- | --- | --- |
| **Greedy** | One dinner at a time: each day, the allowed recipe that uses the most pantry stock. Never looks ahead. This is how most recipe apps work | `src/optimizer/baselines.py` |
| **Genetic algorithm (GA)** | Evolves whole weeks (population 48, 350 generations, mutation 0.20, seed 42) against the same six cost terms as the MILP | `src/optimizer/genetic.py` |
| **MILP** | Mixed-integer linear model of the whole week, solved with HiGHS (8 s limit, 2 % gap): minimises waste, extra groceries, nutrition deviation, preference, cooking time and variety | `src/optimizer/weekly.py` |
| Random (floor) | A random allowed week: the lower bound | `src/optimizer/baselines.py` |

| | |
| --- | --- |
| Data | Frozen synthetic benchmark v2 · **validation split** · 120 scenarios (15 in each of 8 families) |
| Weights | The adopted defaults (preference 6.0, kcal 8.0, protein 4.0); GA uses the same weights |
| Date | 2026-10-16, current code |
| Command | `python src/evaluation/runner.py --split validation --planners random,greedy,genetic,optimiser --baseline greedy --save` |
| Rows | [`results_validation.csv`](results_validation.csv) (one row per scenario × planner) · [`genetic_5_seeds_validation.csv`](genetic_5_seeds_validation.csv) (GA, seeds 0–4) |

## Overall (mean over 120 scenarios)

| Planner | Waste (g) | Extra grocery items | Extra groceries (g) | Pantry used % | Expiring stock used % | Dinners in kcal band % | Protein minimum met % | Preference (0–1) | Weekday overtime % | Violations | s / plan |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Random (floor) | 854.3 | 44.1 | 1,724 | 7.2 | 2.6 | 13.8 | 30.6 | 0.541 | 42.2 | 0 | 0.01 |
| Greedy | 763.2 | 23.7 | **530** | **26.3** | 15.5 | 3.6 | 12.3 | 0.524 | 30.7 | 0 | 0.09 |
| Genetic (GA) | 733.5 | **15.4** | 1,429 | 16.3 | 18.3 | 69.5 | **59.6** | 0.612 | 16.2 | 0 | 0.61 |
| **MILP (HiGHS)** | **723.2** | **15.4** | 1,416 | 17.3 | **19.8** | **70.6** | 59.4 | **0.615** | **13.3** | 0 | 4.67 |

Every planner produced a complete 7-day week in all 120 scenarios, with zero hard-rule violations (allergies, diet,
exclusions).

## Paired differences (same scenarios; mean difference [95 % bootstrap CI], n = 120)

✓ = the first planner is significantly better, ✗ = significantly worse, no mark = the CI includes 0.

| Metric | GA − Greedy | MILP − Greedy | MILP − GA |
| --- | --- | --- | --- |
| Waste (g) | −29.7 [−52.1, −7.7] ✓ | −40.0 [−63.7, −17.0] ✓ | −10.3 [−17.2, −3.0] ✓ |
| Extra grocery items | −8.3 [−9.8, −6.8] ✓ | −8.3 [−9.8, −6.8] ✓ | +0.0 [−0.2, +0.3] |
| Extra groceries (g) | +899 [+829, +968] ✗ | +887 [+818, +957] ✗ | −12 [−33, +10] |
| Pantry used (pts) | −10.0 [−12.2, −7.7] ✗ | −9.0 [−11.2, −6.7] ✗ | +1.0 [+0.5, +1.6] ✓ |
| Expiring stock used (pts) | +2.8 [−0.4, +5.9] | +4.3 [+1.4, +7.4] ✓ | +1.5 [+0.4, +2.7] ✓ |
| Dinners in kcal band (pts) | +66.0 [+61.7, +70.2] ✓ | +67.0 [+62.9, +71.1] ✓ | +1.1 [−1.0, +3.5] |
| Protein minimum met (pts) | +47.4 [+42.3, +53.2] ✓ | +47.1 [+42.0, +53.0] ✓ | −0.2 [−1.9, +1.4] |
| Preference (0–1) | +0.088 [+0.073, +0.102] ✓ | +0.091 [+0.077, +0.106] ✓ | +0.004 [−0.000, +0.007] |
| Weekday overtime (pts) | −15 [−19, −10] ✓ | −17 [−22, −13] ✓ | −3 [−5, −1] ✓ |

## By scenario family (mean per planner)

| Family | Waste (g): Greedy / GA / MILP | Grocery items: Greedy / GA / MILP | Dinners in kcal band %: Greedy / GA / MILP |
| --- | --- | --- | --- |
| `conflicting_preferences` | 638 / 606 / **591** | 21.7 / 16.1 / **15.5** | 5.7 / 72.4 / **74.3** |
| `expiry_heavy` | 974 / 892 / **887** | 22.0 / 15.3 / **15.1** | 1.0 / 64.8 / **71.4** |
| `infeasible_combo` | **644** / 684 / 683 | 33.3 / **18.2** / 18.7 | 8.6 / **47.6** / 45.7 |
| `nutrition_pressure` | 674 / **654** / 659 | 20.9 / **14.1** / **14.1** | 3.8 / **74.3** / 73.3 |
| `restrictive_diet` | **670** / 717 / 717 | 28.1 / 15.2 / **15.0** | 1.0 / **80.0** / 78.1 |
| `sparse_pantry` | 320 / 276 / **260** | 25.1 / **14.7** / 15.0 | 1.9 / **81.9** / 81.0 |
| `tight_time` | 873 / 817 / **798** | 21.7 / **14.6** / **14.6** | 3.8 / 65.7 / **67.6** |
| `well_stocked` | 1,311 / 1,223 / **1,192** | 16.9 / **15.0** / 15.5 | 2.9 / 69.5 / **73.3** |

MILP − GA per family (95 % CI, 15 scenarios each). Most differences are within noise. The MILP wastes less in
`sparse_pantry` (−16 g [−27, −6]), `tight_time` (−20 g [−41, −1]) and `well_stocked` (−31 g [−54, −11]). The GA
needs fewer grocery items in `infeasible_combo` (MILP +0.5 [+0.1, +1.0]).

## Is the GA result luck? Five seeds (120 scenarios each)

| GA seed | Waste (g) | Grocery items | Dinners in kcal band % | Preference | Expiring used % |
| --- | --- | --- | --- | --- | --- |
| 0 | 729.3 | 15.6 | 69.4 | 0.610 | 18.8 |
| 1 | 729.4 | 15.6 | 70.2 | 0.614 | 18.6 |
| 2 | 726.9 | 15.4 | 69.9 | 0.611 | 18.3 |
| 3 | 731.3 | 15.4 | 68.9 | 0.615 | 18.5 |
| 4 | 727.0 | 15.5 | 71.0 | 0.610 | 19.1 |
| **Mean ± sd** | **728.8 ± 1.9** | **15.49 ± 0.08** | **69.9 ± 0.8** | **0.612 ± 0.002** | **18.7 ± 0.3** |
| MILP, for reference | 723.2 | 15.4 | 70.6 | 0.615 | 19.8 |

The GA is very stable across seeds. Against every seed, the MILP's mean waste is 3.7–8.1 g lower, with grocery items
and calorie fit level.

## How to read it

- **Planning the week jointly clearly beats greedy, with both the GA and the MILP.** Against greedy they cut extra
  grocery items by a third (23.7 → 15.4) and food waste by 30–40 g a week. Dinners inside the calorie band rise from
  4 % to about 70 %, dinners meeting the protein minimum from 12 % to about 60 %, and weekday dinners over the time
  limit fall from 31 % to 13–16 %. All with zero rule violations.
- **MILP vs GA: the MILP is slightly better, the GA much faster.** The MILP wastes 10 g less per week (about 1.4 %) and
  uses a bit more expiring stock. On groceries, calorie fit, protein and preference the two are level. The GA plans in
  0.6 s; the MILP takes 4.7 s on the 8 s limit. The MILP stays the app's planner; the GA is a credible fast
  alternative.
- **Honest costs:**
  - **Grams bought:** the optimisers buy *fewer distinct items* but about **0.9 kg more food by weight** than greedy
    (1.4 kg vs 0.5 kg a week). Greedy cooks whatever matches the pantry; the optimisers buy what makes the dinners fit
    the calorie and protein targets.
  - **Pantry share:** they use a *smaller share* of the whole pantry (17 % vs 26 %), though *more* of what is about to
    expire. Read utilisation together with waste and groceries, not alone.
  - **Small allowed pools:** in `restrictive_diet` and `infeasible_combo`, where few recipes are allowed, both
    optimisers waste more than greedy (+39–47 g). They spend the plan on nutrition and fewer grocery items rather than
    on using up stock.
- **Absolute waste is high for every method** (about 700–850 g). A week of dinners cannot absorb a whole pantry, so
  compare methods, not the number.

## Caveats

- **Synthetic scenarios:** a seeded generator, no real households (see `md docs/data.md`).
- **Built-in advantage:** calorie fit, protein, preference and cooking time are measured with the same definitions
  the optimisers minimise, so they favour the optimisers by construction. Waste and groceries are replayed against the
  *hidden true* expiry dates, which is the independent check.
- **Validation split only.** The test split is reserved for one final run once the weights are frozen (a waste-weight
  decision is still open, see [06](../06_weight_tuning/README.md)).
- **Timing:** seconds per plan were measured with several evaluation runs in parallel on a 32-core machine. The
  MILP's 8 s wall-clock limit makes its results vary slightly from run to run (about ±2 points on calorie fit).
