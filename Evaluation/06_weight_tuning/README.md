# 06 · Weight tuning: how the optimiser's weights were chosen (validation only)

The MILP minimises a weighted sum of waste, extra groceries, nutrition deviation, preference, cooking time and variety.
The weights were tuned **on the validation split only**, against criteria written before each run
(`src/evaluation/weight_sweep.py`). The test split was never used.

| | |
| --- | --- |
| Data | Frozen benchmark v1 (same scenarios as v2) · validation split |
| Date / code | 2026-10-13 – 2026-10-14 · `src/evaluation/weight_sweep.py` |
| Rows | [`1_preference_nutrition_sweep_48.csv`](1_preference_nutrition_sweep_48.csv) · [`2_confirmation_120.csv`](2_confirmation_120.csv) · [`3_variety_sweep_120.csv`](3_variety_sweep_120.csv) · [`4_waste_sweep_120.csv`](4_waste_sweep_120.csv) |

## 1 · Making preferences and nutrition count (48 scenarios)

Why: real explanations showed the preference term had almost no effect, so stating "I like Italian food" changed
nothing. Paired difference vs the starting weights (preference 1.0, kcal 4.0, protein 2.0), 95 % CI:

| Candidate | Liked-cuisine dinners (pts) | Preference score | Dinners in kcal band (pts) | Extra grocery items | Waste (g) | Guardrails |
| --- | --- | --- | --- | --- | --- | --- |
| pref ×3 | +7.1 [+3.9, +10.7] | +0.023 | −1.2 | +0.40 | +2 | pass |
| pref ×6 | +17.0 [+12.5, +21.7] | +0.056 | −3.0 | +1.15 | +5 | fails groceries |
| nutrition ×2 | +0.6 | +0.003 | +12.8 [+8.6, +17.6] | +1.94 | −3 | fails groceries |
| pref ×6 + nutrition ×2 | +17.0 | +0.050 | +11.3 | +2.65 | +19 | fails groceries |

The stronger settings failed the 0.5-item grocery guardrail, which is a product limit rather than a modelling one.
The project owner decided the trade was worth it, so the combination was re-measured on all 120 scenarios.

## 2 · Confirmation on all 120 validation scenarios: preference ×6 + nutrition ×2 (**adopted**)

| Measure | Start | Adopted | Difference [95 % CI] | Criterion | Met |
| --- | --- | --- | --- | --- | --- |
| Dinners in a liked cuisine | 12.6 % | 27.6 % | +15.0 pts [+11.8, +18.2] | ≥ +10 | yes |
| Dinners in the calorie band | 57.0 % | 70.7 % | +13.7 pts [+10.5, +17.1] | ≥ +8 | yes |
| Dinners reaching the protein minimum | 52.7 % | 59.4 % | +6.7 pts [+4.0, +9.3] | – | – |
| Extra grocery items | 12.9 | 15.7 | +2.78 [+2.33, +3.27] | ≤ +3.5 | yes |
| Waste (g) | 710 | 722 | +11.9 [+3.1, +22.1] (+1.7 %) | ≤ +5 % | yes |
| Disliked meals | 2.3 % | 1.0 % | −1.3 pts [−3.1, −0.1] | ≤ +2 | yes |
| Rule violations / shorter weeks | 0 / 0 | 0 / 0 | – | none | yes |

Adopted as `OptimizerWeights`: preference 6.0, kcal 8.0, protein 4.0. These are the weights every other result in
this folder uses.

## 3 · Variety: one protein all week (120 scenarios)

Share of weeks with **5 or more dinners of one protein type**:

| Setting | One-protein weeks | Mean max same-type dinners | Extra grocery items | Liked-cuisine dinners |
| --- | --- | --- | --- | --- |
| Start weights | 84 % | 6.1 | 12.9 | 12.4 % |
| Adopted (pref ×6, nutrition ×2) | 83 % | 6.1 | 15.7 | 27.4 % |
| + variety ×3 | 64 % | 5.6 | 16.3 | 21.5 % |
| + cap 3 | 83 % | 6.0 | 15.7 | 27.4 % |
| + variety ×3, cap 3 | 62 % | 5.5 | 16.4 | 21.1 % |
| + variety ×6, cap 3 | 53 % | 5.2 | 17.3 | 20.7 % |

No candidate met the pre-declared criteria, so the adopted weights stand. The problem is structural, not a weight: the
objective counts *distinct* grocery items, so one protein bought once and used all week is cheap. A structural fix (a
per-main-ingredient cap) is open work.

## 4 · Waste weight (120 scenarios, 2026-10-14) — **decision pending**

| Setting | Waste (g) | Avoidable waste (g) | Extra grocery items | Dinners in kcal band % | Preference |
| --- | --- | --- | --- | --- | --- |
| Start weights | 709.3 | 403.9 | 12.8 | 56.6 | 0.57 |
| Adopted (pref ×6, nutrition ×2) | 723.4 | 418.0 | 15.5 | 70.2 | 0.62 |
| + waste ×2 | 698.0 | 392.6 | 16.0 | 68.9 | 0.61 |
| + waste ×3 | 682.2 | 376.8 | 16.5 | 68.9 | 0.61 |

The pre-declared rule (avoidable waste at least 5 % lower, at most +1.0 grocery item, at most 3 points less calorie fit)
picks **waste ×2**: avoidable waste −6 % for +0.54 items. Waste ×3 fails the grocery limit by 0.05 items. **Not
adopted yet:** it needs the project owner's decision, and adopting it would change the optimiser rows in
01_planner_comparison.

## Caveats

Runs 1–3 predate the 2026-10-14 vegetarian-rule change. Its effect on the adopted weights was measured to be within
noise (`md docs/evaluation.md`).
