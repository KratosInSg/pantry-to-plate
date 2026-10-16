# 02 · Ablations: what does each part of the MILP contribute?

The proposal's third evaluation stage: switch off one reasoning component at a time and measure what changes.
Each variant is the full MILP with one cost term's weight set to zero, so nothing else can change by accident
(`ABLATIONS` in `src/optimizer/weekly.py`).

| | |
| --- | --- |
| Data | Frozen synthetic benchmark v2: **test split, run once** (120 scenarios), plus the validation split (120 other scenarios) |
| Weights | The adopted defaults, frozen before the test run; each variant zeroes one term |
| Date | 2026-10-16, current code (supersedes the 2026-10-12 run, which used the old, untuned weights) |
| Command | `python src/evaluation/runner.py --split test --planners optimiser,opt_no_expiry,opt_no_nutrition,opt_no_preference --baseline optimiser --save` (and `--split validation`) |
| Rows | [`ablations_test.csv`](ablations_test.csv) · [`ablations_validation.csv`](ablations_validation.csv): the full MILP plus the three variants, one row per scenario × planner |

## Final result: test split (single run, 120 scenarios)

| Planner | Waste (g) | Expiring stock used % | Extra grocery items | Dinners in kcal band % | Protein minimum met % | Preference (0–1) | Dinners with a disliked food % |
| --- | --- | --- | --- | --- | --- | --- | --- |
| **Full MILP** | 709.8 | 22.5 | 15.3 | 68.2 | 57.6 | 0.594 | 0.5 |
| Without expiry term | 746.3 | 18.2 | 14.9 | 67.4 | 58.0 | 0.594 | 0.5 |
| Without nutrition term | 711.8 | 22.7 | 11.2 | 22.1 | 35.7 | 0.594 | 0.0 |
| Without preference term | 712.6 | 22.0 | 14.7 | 67.6 | 58.1 | 0.559 | 1.7 |

**Variant minus full MILP** (paired, 95 % bootstrap CI, n = 120). ✓ = the variant is significantly better on that
measure, ✗ = significantly worse, no mark = CI includes 0.

| Term switched off | Waste (g) | Expiring stock used (pts) | Extra grocery items | Dinners in kcal band (pts) | Protein minimum met (pts) | Preference (0–1) | Disliked-food dinners (pts) |
| --- | --- | --- | --- | --- | --- | --- | --- |
| **Expiry (waste)** | +36.5 [+25.4, +48.8] ✗ | −4.3 [−5.8, −3.0] ✗ | −0.4 [−0.7, −0.2] ✓ | −0.8 [−2.7, +1.1] | +0.4 [−1.0, +1.7] | −0.000 [−0.003, +0.002] | +0.0 |
| **Nutrition** | +2.0 [−8.4, +13.4] | +0.2 [−1.1, +1.5] | −4.2 [−4.9, −3.5] ✓ | −46.1 [−50.7, −41.7] ✗ | −21.9 [−26.4, −18.0] ✗ | +0.001 [−0.008, +0.008] | −0.5 [−1.2, +0.0] |
| **Preference** | +2.9 [−5.8, +12.1] | −0.5 [−1.5, +0.5] | −0.6 [−1.0, −0.3] ✓ | −0.6 [−3.0, +1.8] | +0.5 [−1.3, +2.1] | −0.034 [−0.043, −0.028] ✗ | +1.2 [+0.5, +2.3] ✗ |

## How to read it

- **Every term does its job, on held-out scenarios, and each costs something elsewhere:**
  - **Expiry term:** without it, 37 g more food spoils per week (+5 %) and 4 points less of the expiring stock is
    used. It costs about 0.4 grocery items.
  - **Nutrition term:** the biggest lever. Without it, dinners in the calorie band fall from 68 % to 22 % and dinners
    meeting the protein minimum from 58 % to 36 %. Hitting the targets costs about 4 extra grocery items a week.
  - **Preference term:** without it, the taste match drops (0.594 → 0.559) and dinners containing a disliked food rise
    from 0.5 % to 1.7 %. Honouring tastes costs about 0.6 grocery items. On test it costs no waste, while validation
    showed about 15 g.
- **The preference term matters because of the weight tuning.** In the first ablation (2026-10-12, untuned weights),
  switching it off changed the taste match by only 0.01. The tuning in [06](../06_weight_tuning/README.md) raised it
  6×, which made stated likes and dislikes count.

## Validation split (120 other scenarios)

| Planner | Waste (g) | Expiring stock used % | Extra grocery items | Dinners in kcal band % | Protein minimum met % | Preference (0–1) | Dinners with a disliked food % |
| --- | --- | --- | --- | --- | --- | --- | --- |
| **Full MILP** | 723.2 | 19.8 | 15.4 | 70.6 | 59.4 | 0.615 | 1.0 |
| Without expiry term | 755.3 | 15.6 | 15.0 | 70.1 | 58.5 | 0.619 | 0.8 |
| Without nutrition term | 715.1 | 20.6 | 11.6 | 25.6 | 33.7 | 0.617 | 0.5 |
| Without preference term | 707.9 | 21.6 | 14.5 | 69.5 | 58.7 | 0.566 | 2.3 |

| Term switched off (validation) | Waste (g) | Expiring stock used (pts) | Extra grocery items | Dinners in kcal band (pts) | Protein minimum met (pts) | Preference (0–1) | Disliked-food dinners (pts) |
| --- | --- | --- | --- | --- | --- | --- | --- |
| **Expiry (waste)** | +32.1 [+20.8, +43.5] ✗ | −4.3 [−5.9, −2.7] ✗ | −0.4 [−0.6, −0.2] ✓ | −0.5 [−2.3, +1.2] | −1.0 [−2.5, +0.4] | +0.003 [−0.000, +0.008] | −0.1 [−0.4, +0.0] |
| **Nutrition** | −8.2 [−20.0, +3.3] | +0.7 [−0.6, +2.2] | −3.8 [−4.4, −3.2] ✓ | −45.0 [−48.9, −40.8] ✗ | −25.7 [−30.1, −21.5] ✗ | +0.002 [−0.007, +0.011] | −0.5 [−1.3, +0.0] |
| **Preference** | −15.3 [−26.1, −6.7] ✓ | +1.8 [+0.6, +3.1] ✓ | −1.0 [−1.4, −0.6] ✓ | −1.1 [−3.5, +1.2] | −0.7 [−2.5, +1.1] | −0.050 [−0.061, −0.040] ✗ | +1.3 [+0.4, +2.6] ✗ |

## Caveats

- Synthetic scenarios.
- The preference and nutrition measures use the same definitions the MILP optimises, so their own ablations are the
  expected direction. The informative part is what each term costs on the *other* measures.
- The MILP's 8 s time limit causes small run-to-run noise.
