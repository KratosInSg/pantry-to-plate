# 09 · Expiry safety margin: making the plan hold up when food spoils early

**Problem (from 03).** The expiry-aware MILP plans estimated-expiry food right up to its estimated last day, so when the
food turns a day or two early it is wasted. On the v2 test split it degraded *more* than the MILP without the expiry
term (+18.6 g and +15.7 g), and measure 8 of the proposal ("less degradation than the planner without expiry
awareness") was not met.

**Remedy.** `estimate_margin_days` in `src/optimizer/weekly.py`: the planner treats every *estimated* deadline inside the
week as `m` days earlier (never before tonight). Known use-by dates are facts and are not moved; the evaluation, the
explanations and the user still see the real estimate. Variants `opt_margin1`, `opt_margin2`. The deployed default is
unchanged (`m = 0`).

| | |
| --- | --- |
| Protocol | [`PROTOCOL.md`](PROTOCOL.md), written before any run: selection rule on validation, then one run on fresh data |
| Step 1 data | Frozen benchmark v2, **validation split** (all 120 scenarios) |
| Step 2 data | Frozen benchmark **v3**: 120 *new* kitchens (new seeds, test only, never used before) |
| Perturbations | As in 03 (1 and 2 days early, ±2-day jitter, ±30 % stock, 30 % noise, combined), seed 0 |
| Date / code | 2026-10-21 · `src/evaluation/robustness.py` |
| Commands | `python src/evaluation/robustness.py --split validation --planners greedy,optimiser,opt_margin1,opt_margin2,opt_no_expiry --save` · `python src/evaluation/robustness.py --eval-dir data/evaluation/v3 --split test --planners greedy,optimiser,opt_margin2,opt_no_expiry --save` |
| Rows | [`robustness_validation_v2.csv`](robustness_validation_v2.csv) · [`robustness_test_v3.csv`](robustness_test_v3.csv) |

## Step 1: choosing the margin (validation)

| Candidate | Nominal waste | Grocery items | Calorie band | Guards | Mean waste degradation (1 d, 2 d early) |
| --- | --- | --- | --- | --- | --- |
| `optimiser` (m = 0) | 723.1 g | 15.69 | 72.0 % | – | 14.4 g (10.1, 18.6) |
| `opt_margin1` | 723.6 g | 15.42 | 70.8 % | pass | 10.3 g (8.7, 11.8) |
| **`opt_margin2`** | 721.6 g | 15.63 | 70.2 % | pass | **8.4 g** (6.4, 10.4) |
| `opt_no_expiry` | 752.8 g | 15.33 | 70.6 % | – | 9.3 g (7.2, 11.4) |

Chosen by the pre-written rule: **`opt_margin2`**.

## Step 2: the single run on the fresh v3 benchmark (120 new kitchens)

**Measure 8 (the proposal's test):** waste degradation of `opt_margin2` minus `opt_no_expiry`, paired, 95 % CI.

| Perturbation | `opt_margin2` − `opt_no_expiry` | (for reference) `optimiser` − `opt_no_expiry` |
| --- | --- | --- |
| Spoils 1 day early | **−5.4 g** [−11.6, +0.0] | +2.2 g [−0.4, +5.3] |
| Spoils 2 days early | **−4.4 g** [−12.5, +2.8] | +5.1 g [+0.1, +10.2] |
| ±2 days jitter | −5.3 g [−14.0, +2.5] | −4.8 g [−11.1, +0.8] |
| 30 % less stock | +5.7 g [+0.6, +10.4] | +4.1 g [−0.7, +8.6] |
| 30 % more stock | −3.7 g [−6.6, −0.8] | −0.6 g [−3.4, +2.6] |
| 30 % noise | −1.0 g [−5.8, +3.2] | −0.7 g [−4.9, +2.7] |
| Combined | +4.7 g [−1.6, +11.1] | +9.2 g [+2.1, +16.1] |

**Met** by the protocol's rule: with the margin, the expiry-aware planner degrades *no more* than the planner without
expiry awareness when food spoils early (mean differences −5.4 g and −4.4 g; both CIs touch or include 0, so "no
worse, probably better" rather than a proven advantage). Without the margin, the v3 run reproduces the original problem
(+5.1 g at two days early, CI above 0).

**The margin against today's planner** (`opt_margin2` − `optimiser`, degradation): −7.7 g [−14.0, −1.7] at one day
early and −9.5 g [−18.4, −2.4] at two days early, i.e. it removes about 70 % and 38 % of the extra spoilage.

**Cost on the nominal kitchen** (`opt_margin2` − `optimiser`, v3): waste −5.2 g [−15.2, +4.6], grocery items +0.08
[−0.28, +0.46], dinners in the calorie band +0.5 points [−1.5, +2.6], preference −0.000 [−0.004, +0.003]. No measurable
price. 0 violations and complete weeks for every planner.

**Real waste in each kitchen (g/week, v3 means):**

| Reality | Greedy | MILP (m = 0) | **MILP, margin 2** | MILP, no expiry term |
| --- | --- | --- | --- | --- |
| As told (nominal) | 729.8 | 697.7 | **692.5** | 729.9 |
| Spoils 1 day early | 750.5 | 708.7 | **695.9** | 738.6 |
| Spoils 2 days early | 767.9 | 722.7 | **708.1** | 749.8 |
| Combined | 805.7 | 770.6 | **761.0** | 793.6 |

The margin version wastes the least in every reality tested.

## Caveats

- One fresh benchmark (120 synthetic kitchens), one perturbation seed. The early-spoilage advantage over the no-expiry
  planner is small and its CIs reach 0; the advantage over today's planner is clearer.
- With 30 % less stock than stated, both expiry-aware versions degrade a little more than the no-expiry planner.
- **Not yet the app's default.** `DEFAULT_WEIGHTS.estimate_margin_days` is still 0, so the results in 01–03 describe the
  deployed planner. Adopting the margin is a one-line change; it would apply to the app from then on, and 01–03 would
  then describe the previous default.
