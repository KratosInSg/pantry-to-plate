# 03 · Robustness: does the plan hold up when the kitchen is not what we were told?

Evaluation measure 8 of the proposal. Each plan is made once from what the planner is told, then replayed against
*perturbed realities*:

- estimated use-by dates 1 or 2 days earlier than expected, or ±2 days at random;
- 30 % less or 30 % more stock than stated, or ±30 % noise per item;
- a combination (1 day early ±1, plus 30 % noise).

Known use-by dates are never perturbed. **Degradation** = perturbed minus nominal, signed so that **positive = worse**.
Planners are compared by paired bootstrap against `opt_no_expiry`, the planner without expiry awareness, as the
proposal specifies.

| | |
| --- | --- |
| Data | Frozen benchmark v2 · **validation split** · 48 scenarios (6 per family) |
| Planners | greedy, MILP optimiser (HiGHS), `opt_no_expiry` (MILP with the waste term off) |
| Date / code | 2026-10-16 · `src/evaluation/robustness.py` |
| Command | `python src/evaluation/robustness.py --split validation --planners greedy,optimiser,opt_no_expiry --baseline opt_no_expiry --limit 48 --save` |
| Rows | [`robustness_validation.csv`](robustness_validation.csv): one row per scenario × planner × perturbation |

## Nominal kitchen (no perturbation)

| Planner | Waste (g) | Avoidable waste (g) | Grocery items | Grocery (g) | Expiring stock used % | Pantry used % |
| --- | --- | --- | --- | --- | --- | --- |
| Greedy | 735.4 | 438.3 | 24.4 | 585.9 | 16.8 | 26.2 |
| MILP optimiser | 702.0 | 405.0 | 15.6 | 1,428.3 | 19.1 | 15.7 |
| `opt_no_expiry` | 734.5 | 437.4 | 15.4 | 1,439.7 | 14.7 | 12.8 |

## Mean degradation (positive = worse)

**Extra waste (g):**

| Perturbation | Greedy | MILP optimiser | `opt_no_expiry` |
| --- | --- | --- | --- |
| Spoils 1 day early | +18.1 | +9.8 | +10.8 |
| Spoils 2 days early | +34.9 | +21.6 | +10.8 |
| ±2 days jitter | −31.5 | −24.3 | −19.0 |
| 30 % less stock | −239.4 | −224.0 | −235.7 |
| 30 % more stock | +250.5 | +242.4 | +245.1 |
| ±30 % quantity noise | +28.1 | +31.1 | +28.0 |
| Combined | +55.0 | +45.7 | +43.5 |

**Extra groceries (g):**

| Perturbation | Greedy | MILP optimiser | `opt_no_expiry` |
| --- | --- | --- | --- |
| Spoils 1 day early | +18.1 | +9.8 | +10.8 |
| Spoils 2 days early | +34.9 | +21.6 | +10.8 |
| ±2 days jitter | −23.2 | −10.5 | −4.0 |
| 30 % less stock | +80.8 | +50.3 | +35.0 |
| 30 % more stock | −20.3 | −26.9 | −21.9 |
| ±30 % quantity noise | +14.4 | +5.1 | +0.1 |
| Combined | +46.6 | +21.1 | +17.9 |

## Paired difference in degradation vs `opt_no_expiry` (95 % bootstrap CI, n = 48; negative = more robust)

**MILP optimiser − `opt_no_expiry`:**

| Perturbation | Waste (g) | Grocery items | Grocery (g) |
| --- | --- | --- | --- |
| Spoils 1 day early | −0.9 [−7.3, +5.0] | +0.0 [−0.1, +0.1] | −0.9 [−7.3, +5.0] |
| Spoils 2 days early | +10.8 [−0.9, +25.5] | +0.1 [−0.0, +0.2] | +10.8 [−0.9, +25.5] |
| ±2 days jitter | −5.3 [−15.0, +3.2] | −0.0 [−0.1, +0.1] | −6.5 [−16.3, +1.4] |
| 30 % less stock | **+11.7 [+5.7, +18.7]** | +0.1 [−0.0, +0.3] | **+15.2 [+8.4, +23.0]** |
| 30 % more stock | **−2.8 [−5.7, −0.3]** | −0.1 [−0.2, +0.0] | **−5.0 [−9.0, −1.7]** |
| ±30 % quantity noise | +3.1 [−2.7, +8.9] | +0.1 [−0.0, +0.2] | +5.0 [−1.5, +11.4] |
| Combined | +2.2 [−3.1, +8.2] | +0.0 [−0.1, +0.1] | +3.2 [−2.2, +9.2] |

**Greedy − `opt_no_expiry`:**

| Perturbation | Waste (g) | Grocery items | Grocery (g) |
| --- | --- | --- | --- |
| Spoils 1 day early | +7.3 [−3.1, +18.5] | +0.1 [−0.0, +0.2] | +7.3 [−3.1, +18.5] |
| Spoils 2 days early | **+24.0 [+8.1, +42.6]** | **+0.2 [+0.0, +0.3]** | **+24.0 [+8.1, +42.6]** |
| ±2 days jitter | −12.5 [−30.2, +2.8] | −0.1 [−0.2, +0.1] | **−19.3 [−36.3, −4.6]** |
| 30 % less stock | −3.7 [−11.8, +4.4] | **+1.0 [+0.7, +1.3]** | **+45.8 [+31.7, +59.2]** |
| 30 % more stock | +5.4 [−0.3, +11.1] | **−0.8 [−1.1, −0.5]** | +1.6 [−6.8, +9.8] |
| ±30 % quantity noise | +0.1 [−4.6, +4.4] | +0.1 [−0.3, +0.4] | **+14.4 [+2.0, +29.2]** |
| Combined | +11.6 [−2.5, +25.6] | +0.2 [−0.0, +0.5] | **+28.7 [+13.9, +44.0]** |

Bold = the 95 % CI excludes 0.

## How to read it

- **The expiry term does not make the plan more robust; it makes it slightly less robust.** The optimiser schedules
  stock close to its *estimated* deadline. When food really spoils earlier, or there is less of it, more of that plan
  breaks. The proposal's expectation ("less degradation than the planner without expiry awareness") is **not
  supported**.
- **It still ends ahead in absolute terms.** Even with food spoiling 2 days early, the optimiser's real waste
  (702 + 22 ≈ 724 g) stays below `opt_no_expiry` (≈ 745 g) and greedy (≈ 770 g).
- **Greedy degrades most** under early spoilage and when there is less stock, because it cooks most from the pantry.
- With less stock, waste *falls* for every plan simply because there is less food to waste. Compare planners, and use
  the grocery columns for quantity perturbations.
- The remedy is re-planning once the user reports what spoiled (`optimizer/replan.py`), or discounting estimated
  deadlines more strongly. Neither is measured here.

## Caveats

Synthetic scenarios and perturbations. Validation split only. The test split has not been run.
