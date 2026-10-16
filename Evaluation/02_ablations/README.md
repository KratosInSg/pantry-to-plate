# 02 · Ablations: what does each part of the MILP contribute?

The proposal's third evaluation stage: switch off one reasoning component at a time and measure what changes.
Each variant is the full MILP with one cost term's weight set to zero, so nothing else can change by accident
(`ABLATIONS` in `src/optimizer/weekly.py`).

| | |
| --- | --- |
| Data | Frozen synthetic benchmark v2 · **validation split** · 120 scenarios (15 per family) |
| Weights | The adopted defaults; each variant zeroes one term |
| Date | 2026-10-16, current code (supersedes the 2026-10-12 run, which used the old, untuned weights) |
| Command | `python src/evaluation/runner.py --split validation --planners optimiser,opt_no_expiry,opt_no_nutrition,opt_no_preference --baseline optimiser --save` |
| Rows | [`ablations_validation.csv`](ablations_validation.csv): the full MILP plus the three variants, one row per scenario × planner |

## Means (120 scenarios)

| Planner | Waste (g) | Expiring stock used % | Extra grocery items | Dinners in kcal band % | Protein minimum met % | Preference (0–1) | Dinners with a disliked food % |
| --- | --- | --- | --- | --- | --- | --- | --- |
| **Full MILP** | 723.2 | 19.8 | 15.4 | 70.6 | 59.4 | 0.615 | 1.0 |
| Without expiry term | 755.3 | 15.6 | 15.0 | 70.1 | 58.5 | 0.619 | 0.8 |
| Without nutrition term | 715.1 | 20.6 | 11.6 | 25.6 | 33.7 | 0.617 | 0.5 |
| Without preference term | 707.9 | 21.6 | 14.5 | 69.5 | 58.7 | 0.566 | 2.3 |

## Variant minus full MILP (paired, 95 % bootstrap CI, n = 120)

✓ = the variant is significantly better on that measure, ✗ = significantly worse, no mark = CI includes 0.

| Term switched off | Waste (g) | Expiring stock used (pts) | Extra grocery items | Dinners in kcal band (pts) | Protein minimum met (pts) | Preference (0–1) | Disliked-food dinners (pts) |
| --- | --- | --- | --- | --- | --- | --- | --- |
| **Expiry (waste)** | +32.1 [+20.8, +43.5] ✗ | −4.3 [−5.9, −2.7] ✗ | −0.4 [−0.6, −0.2] ✓ | −0.5 [−2.3, +1.2] | −1.0 [−2.5, +0.4] | +0.003 [−0.000, +0.008] | −0.1 [−0.4, +0.0] |
| **Nutrition** | −8.2 [−20.0, +3.3] | +0.7 [−0.6, +2.2] | −3.8 [−4.4, −3.2] ✓ | −45.0 [−48.9, −40.8] ✗ | −25.7 [−30.1, −21.5] ✗ | +0.002 [−0.007, +0.011] | −0.5 [−1.3, +0.0] |
| **Preference** | −15.3 [−26.1, −6.7] ✓ | +1.8 [+0.6, +3.1] ✓ | −1.0 [−1.4, −0.6] ✓ | −1.1 [−3.5, +1.2] | −0.7 [−2.5, +1.1] | −0.050 [−0.061, −0.040] ✗ | +1.3 [+0.4, +2.6] ✗ |

## How to read it

- **Every term does its job, and each costs something elsewhere.** This is the trade-off the weights encode:
  - **Expiry term:** without it, 32 g more food spoils per week (+4 %) and 4 points less expiring stock is used. It
    costs about 0.4 grocery items.
  - **Nutrition term:** the biggest lever. Without it, dinners in the calorie band fall from 71 % to 26 % and dinners
    meeting the protein minimum from 59 % to 34 %. Hitting the targets costs about 3.8 extra grocery items a week.
  - **Preference term:** without it, the taste match drops (0.615 → 0.566) and dinners containing a disliked food more
    than double (1.0 % → 2.3 %). Honouring tastes costs about 15 g of waste and 1 grocery item.
- **The preference term now matters.** In the first ablation (2026-10-12, untuned weights), switching it off changed
  the taste match by only 0.01. The weight tuning in [06](../06_weight_tuning/README.md) raised it 6×, which made the
  stated likes and dislikes count.

## Caveats

- Synthetic scenarios.
- The preference and nutrition measures use the same definitions the MILP optimises, so their own ablations are the
  expected direction. The informative part is what each term costs on the *other* measures.
- Validation split only. The MILP's 8 s time limit causes small run-to-run noise.
