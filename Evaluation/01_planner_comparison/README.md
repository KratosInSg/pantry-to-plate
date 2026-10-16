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
| Data | Frozen synthetic benchmark v2: **test split, run once** (120 scenarios, 15 in each of 8 families), plus the validation split where the methods were developed (120 more) |
| Weights | The adopted defaults (preference 6.0, kcal 8.0, protein 4.0), frozen before the test run; the GA uses the same weights |
| Date | 2026-10-16, current code |
| Commands | `python src/evaluation/runner.py --split test --planners random,greedy,genetic,optimiser --baseline greedy --save` (and `--split validation`) |
| Rows | [`results_test.csv`](results_test.csv) · [`genetic_5_seeds_test.csv`](genetic_5_seeds_test.csv) · [`results_validation.csv`](results_validation.csv) · [`genetic_5_seeds_validation.csv`](genetic_5_seeds_validation.csv) (one row per scenario × planner) |

## Final result: test split (single run, 120 scenarios)

| Planner | Waste (g) | Extra grocery items | Extra groceries (g) | Pantry used % | Expiring stock used % | Dinners in kcal band % | Protein minimum met % | Preference (0–1) | Weekday overtime % | Violations | s / plan |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Random (floor) | 859.0 | 44.8 | 1,782 | 6.9 | 2.7 | 14.9 | 31.0 | 0.532 | 48.3 | 0 | 0.01 |
| Greedy | 771.2 | 23.7 | **548** | **27.0** | 14.8 | 3.5 | 13.7 | 0.529 | 36.8 | 0 | 0.08 |
| Genetic (GA) | 724.1 | 15.4 | 1,440 | 18.1 | 20.5 | 65.8 | **57.6** | **0.594** | 19.8 | 0 | 0.58 |
| **MILP (HiGHS)** | **709.8** | **15.3** | 1,442 | 18.9 | **22.5** | **68.2** | **57.6** | **0.594** | **16.3** | 0 | 3.95 |

Every planner produced a complete 7-day week in all 120 test scenarios, with zero hard-rule violations (allergies, diet,
exclusions).

**Paired differences** (same scenarios; mean difference [95 % bootstrap CI], n = 120). ✓ = the first planner is
significantly better, ✗ = significantly worse, no mark = the CI includes 0.

| Metric | GA − Greedy | MILP − Greedy | MILP − GA |
| --- | --- | --- | --- |
| Waste (g) | −47.1 [−67.9, −28.5] ✓ | −61.5 [−83.3, −40.5] ✓ | −14.3 [−22.2, −6.7] ✓ |
| Extra grocery items | −8.3 [−9.5, −7.0] ✓ | −8.4 [−9.6, −7.0] ✓ | −0.1 [−0.4, +0.3] |
| Extra groceries (g) | +892 [+830, +958] ✗ | +894 [+832, +962] ✗ | +2 [−22, +25] |
| Pantry used (pts) | −9.0 [−11.1, −6.8] ✗ | −8.1 [−10.4, −5.8] ✗ | +0.9 [+0.2, +1.6] ✓ |
| Expiring stock used (pts) | +5.7 [+2.9, +8.9] ✓ | +7.7 [+4.8, +11.0] ✓ | +2.0 [+1.0, +3.0] ✓ |
| Dinners in kcal band (pts) | +62.4 [+57.5, +66.9] ✓ | +64.8 [+60.0, +69.3] ✓ | +2.4 [+0.2, +4.6] ✓ |
| Protein minimum met (pts) | +43.9 [+38.9, +49.2] ✓ | +43.9 [+38.8, +49.4] ✓ | +0.0 [−1.9, +2.0] |
| Preference (0–1) | +0.065 [+0.051, +0.081] ✓ | +0.065 [+0.051, +0.081] ✓ | −0.000 [−0.004, +0.003] |
| Weekday overtime (pts) | −17 [−22, −12] ✓ | −21 [−26, −15] ✓ | −3 [−6, −1] ✓ |

**By scenario family (test; mean per planner):**

| Family | Waste (g): Greedy / GA / MILP | Grocery items: Greedy / GA / MILP | Dinners in kcal band %: Greedy / GA / MILP |
| --- | --- | --- | --- |
| `conflicting_preferences` | 674 / 612 / **603** | 18.7 / **12.3** / 12.7 | 2.9 / 63.8 / **64.8** |
| `expiry_heavy` | 1,111 / 1,085 / **1,072** | 24.9 / 14.7 / **14.5** | 1.9 / **79.0** / 78.1 |
| `infeasible_combo` | **795** / 812 / 805 | 32.9 / **22.2** / 22.5 | 6.7 / **31.4** / 29.5 |
| `nutrition_pressure` | 741 / 633 / **600** | 18.9 / 14.4 / **13.9** | 4.8 / 60.0 / **68.6** |
| `restrictive_diet` | **668** / 711 / 699 | 28.3 / 18.2 / **17.3** | 1.9 / 73.3 / **74.3** |
| `sparse_pantry` | 332 / 314 / **308** | 27.1 / 14.7 / **14.5** | 0.0 / 72.4 / **79.0** |
| `tight_time` | 652 / 574 / **563** | 21.5 / **13.7** / 14.0 | 5.7 / **76.2** / 74.3 |
| `well_stocked` | 1,196 / 1,052 / **1,029** | 17.4 / **13.1** / 13.3 | 3.8 / 70.5 / **77.1** |

MILP − GA per family (95 % CI, 15 scenarios each) is mostly within noise. The MILP is significantly better on waste in
`expiry_heavy` (−13 g [−28, −3]) and `nutrition_pressure` (−33 g [−62, −9], where it also fits calories better,
+8.6 pts [+3.8, +13.3]), and on grocery items in `restrictive_diet` (−0.9 [−1.9, −0.1]).

**Is the GA result luck? Five seeds on the test split:**

| GA seed | Waste (g) | Grocery items | Dinners in kcal band % | Preference | Expiring used % |
| --- | --- | --- | --- | --- | --- |
| 0 | 731.5 | 15.4 | 68.0 | 0.595 | 19.9 |
| 1 | 732.0 | 15.2 | 66.9 | 0.592 | 20.0 |
| 2 | 725.9 | 15.4 | 67.3 | 0.592 | 20.4 |
| 3 | 731.0 | 15.3 | 67.7 | 0.595 | 20.1 |
| 4 | 728.2 | 15.2 | 67.9 | 0.591 | 20.3 |
| **Mean ± sd** | **729.7 ± 2.6** | **15.30 ± 0.12** | **67.5 ± 0.5** | **0.593 ± 0.002** | **20.1 ± 0.2** |
| MILP, for reference | 709.8 | 15.3 | 68.2 | 0.594 | 22.5 |

The GA is very stable across seeds. Against every seed, the MILP's mean waste is 16–22 g lower, with grocery items,
calorie fit and preference level.

## How to read it

- **Planning the week jointly clearly beats greedy, on held-out test scenarios, with both the GA and the MILP.**
  - Extra grocery items fall by a third (23.7 → 15.3).
  - Food waste falls by 47 g (GA) and 61 g (MILP) a week, 6–8 %.
  - Dinners inside the calorie band rise from 3.5 % to about 66–68 %, and dinners meeting the protein minimum from
    14 % to 58 %.
  - Weekday dinners over the time limit fall from 37 % to 16–20 %.
  - All with zero rule violations.
- **MILP vs GA: the MILP is slightly better, the GA about 7× faster.** The MILP wastes 14 g less per week (about 2 %),
  uses 2 points more expiring stock, and puts 2.4 points more dinners in the calorie band. On groceries, protein and
  preference the two are level. The GA plans in 0.6 s; the MILP takes 4.0 s on an 8 s limit. The MILP stays the app's
  planner; the GA is a credible fast alternative.
- **Validation and test agree.** Every direction above was already seen on the validation split (below); the waste
  gains are larger on test.
- **Honest costs:**
  - **Grams bought:** the optimisers buy *fewer distinct items* but about **0.9 kg more food by weight** than greedy
    (1.44 kg vs 0.55 kg a week). Greedy cooks whatever matches the pantry; the optimisers buy what makes the dinners
    fit the calorie and protein targets.
  - **Pantry share:** they use a *smaller share* of the whole pantry (19 % vs 27 %), though *more* of what is about to
    expire (22.5 % vs 14.8 %).
  - **Small allowed pools:** in `restrictive_diet` and `infeasible_combo`, where few recipes are allowed, both
    optimisers waste more than greedy (test: +31 to +43 g and +10 to +17 g).
- **Absolute waste is high for every method** (about 700–860 g). A week of dinners cannot absorb a whole pantry, so
  compare methods, not the number.

## Validation split (where the methods were developed; 120 other scenarios)

| Planner | Waste (g) | Extra grocery items | Extra groceries (g) | Pantry used % | Expiring stock used % | Dinners in kcal band % | Protein minimum met % | Preference (0–1) | Weekday overtime % | Violations | s / plan |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Random (floor) | 854.3 | 44.1 | 1,724 | 7.2 | 2.6 | 13.8 | 30.6 | 0.541 | 42.2 | 0 | 0.01 |
| Greedy | 763.2 | 23.7 | **530** | **26.3** | 15.5 | 3.6 | 12.3 | 0.524 | 30.7 | 0 | 0.09 |
| Genetic (GA) | 733.5 | **15.4** | 1,429 | 16.3 | 18.3 | 69.5 | **59.6** | 0.612 | 16.2 | 0 | 0.61 |
| **MILP (HiGHS)** | **723.2** | **15.4** | 1,416 | 17.3 | **19.8** | **70.6** | 59.4 | **0.615** | **13.3** | 0 | 4.67 |

| Metric (validation, n = 120) | GA − Greedy | MILP − Greedy | MILP − GA |
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

**By family (validation; Greedy / GA / MILP):**

| Family | Waste (g) | Grocery items | Dinners in kcal band % |
| --- | --- | --- | --- |
| `conflicting_preferences` | 638 / 606 / **591** | 21.7 / 16.1 / **15.5** | 5.7 / 72.4 / **74.3** |
| `expiry_heavy` | 974 / 892 / **887** | 22.0 / 15.3 / **15.1** | 1.0 / 64.8 / **71.4** |
| `infeasible_combo` | **644** / 684 / 683 | 33.3 / **18.2** / 18.7 | 8.6 / **47.6** / 45.7 |
| `nutrition_pressure` | 674 / **654** / 659 | 20.9 / **14.1** / **14.1** | 3.8 / **74.3** / 73.3 |
| `restrictive_diet` | **670** / 717 / 717 | 28.1 / 15.2 / **15.0** | 1.0 / **80.0** / 78.1 |
| `sparse_pantry` | 320 / 276 / **260** | 25.1 / **14.7** / 15.0 | 1.9 / **81.9** / 81.0 |
| `tight_time` | 873 / 817 / **798** | 21.7 / **14.6** / **14.6** | 3.8 / 65.7 / **67.6** |
| `well_stocked` | 1,311 / 1,223 / **1,192** | 16.9 / **15.0** / 15.5 | 2.9 / 69.5 / **73.3** |

GA with 5 seeds on validation: waste 728.8 ± 1.9 g, grocery items 15.49 ± 0.08, kcal band 69.9 ± 0.8 %, preference
0.612 ± 0.002. The MILP's mean waste is 3.7–8.1 g lower against every seed.

## Caveats

- **Synthetic scenarios:** a seeded generator, no real households (see `md docs/data.md`).
- **Built-in advantage:** calorie fit, protein, preference and cooking time are measured with the same definitions
  the optimisers minimise, so they favour the optimisers by construction. Waste and groceries are replayed against the
  *hidden true* expiry dates, which is the independent check.
- **The test split has now been used once.** Any later change of weights or method needs a new benchmark version to
  give an unbiased number again.
- **Timing:** seconds per plan were measured with several evaluation runs in parallel on a 32-core machine. The
  MILP's 8 s wall-clock limit makes its results vary slightly from run to run (about ±2 points on calorie fit).
