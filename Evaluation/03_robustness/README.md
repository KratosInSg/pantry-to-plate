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
| Data | Frozen benchmark v2: **test split, run once** (48 scenarios, 6 per family), plus the validation split (48 other scenarios) |
| Planners | greedy, MILP optimiser (HiGHS), `opt_no_expiry` (MILP with the waste term off) |
| Date / code | 2026-10-16 · `src/evaluation/robustness.py` |
| Command | `python src/evaluation/robustness.py --split test --planners greedy,optimiser,opt_no_expiry --baseline opt_no_expiry --limit 48 --save` (and `--split validation`) |
| Rows | [`robustness_test.csv`](robustness_test.csv) · [`robustness_validation.csv`](robustness_validation.csv): one row per scenario × planner × perturbation |

## Final result: test split (single run, 48 scenarios)

**Nominal kitchen:**

| Planner | Waste (g) | Avoidable waste (g) | Grocery items | Grocery (g) | Expiring stock used % | Pantry used % |
| --- | --- | --- | --- | --- | --- | --- |
| Greedy | 780.9 | 475.3 | 23.4 | 574.0 | 11.7 | 26.3 |
| MILP optimiser | 698.5 | 392.9 | 16.1 | 1,517.2 | 22.6 | 19.9 |
| `opt_no_expiry` | 745.5 | 439.9 | 15.8 | 1,535.7 | 16.7 | 17.2 |

**Mean degradation, extra waste (g):**

| Perturbation | Greedy | MILP optimiser | `opt_no_expiry` | Real waste after perturbation (G / MILP / no-expiry) |
| --- | --- | --- | --- | --- |
| Spoils 1 day early | +19.3 | +35.0 | +16.3 | 800 / **734** / 762 |
| Spoils 2 days early | +28.7 | +39.3 | +23.6 | 810 / **738** / 769 |
| ±2 days jitter | −37.7 | −10.6 | −22.4 | 743 / **688** / 723 |
| 30 % less stock | −255.1 | −228.5 | −243.2 | 526 / **470** / 502 |
| 30 % more stock | +261.4 | +252.2 | +253.3 | 1,042 / **951** / 999 |
| ±30 % quantity noise | +49.1 | +52.6 | +48.2 | 830 / **751** / 794 |
| Combined | +25.5 | +43.0 | +26.8 | 806 / **742** / 772 |

**Paired difference in degradation vs `opt_no_expiry`** (95 % bootstrap CI, n = 48; negative = more robust; bold = CI
excludes 0):

| Perturbation | MILP − no-expiry: waste (g) | MILP − no-expiry: grocery (g) | Greedy − no-expiry: waste (g) | Greedy − no-expiry: grocery items |
| --- | --- | --- | --- | --- |
| Spoils 1 day early | **+18.6 [+5.4, +35.0]** | **+18.6 [+5.4, +35.0]** | +3.0 [−9.6, +14.5] | +0.0 [−0.1, +0.1] |
| Spoils 2 days early | **+15.7 [+5.8, +26.8]** | **+15.7 [+5.8, +26.8]** | +5.1 [−11.3, +19.2] | +0.0 [−0.1, +0.2] |
| ±2 days jitter | +11.8 [−1.2, +27.3] | +11.8 [−1.2, +27.3] | −15.3 [−36.9, +4.2] | −0.1 [−0.2, +0.1] |
| 30 % less stock | **+14.7 [+7.0, +23.1]** | **+15.4 [+7.5, +23.9]** | **−11.9 [−21.6, −2.8]** | **+0.8 [+0.5, +1.1]** |
| 30 % more stock | −1.1 [−5.9, +3.9] | +0.1 [−5.4, +5.9] | **+8.1 [+3.7, +13.2]** | **−0.9 [−1.2, −0.7]** |
| ±30 % quantity noise | **+4.5 [+0.5, +9.0]** | **+9.4 [+0.6, +24.7]** | +1.0 [−4.2, +6.3] | −0.2 [−0.5, +0.1] |
| Combined | **+16.1 [+7.3, +26.3]** | **+16.7 [+7.8, +27.1]** | −1.3 [−16.4, +12.2] | −0.0 [−0.3, +0.2] |

## How to read it

- **The expiry-aware plan is the least robust of the three, and the proposal's expectation is not supported.** The
  MILP schedules stock close to its *estimated* deadline. When food really spoils 1–2 days earlier, or there is less
  of it, more of that plan breaks: +15 to +19 g of extra waste and rebought food compared with the planner without
  expiry awareness. Validation showed the same direction more weakly; on test it is significant in 5 of 7
  perturbations.
- **It still wastes the least in every perturbed kitchen.** Its head start (698 g vs 746 g and 781 g) is larger than
  what it loses. With food spoiling 2 days early it still wastes 738 g, against 769 g without expiry awareness and
  810 g for greedy.
- **Greedy is not more robust than `opt_no_expiry` on test** for early spoilage (validation suggested it was worse).
  With wrong quantities it trades waste for groceries in both directions.
- **What would make the plan robust** is not more aggressive scheduling but re-planning once the user reports what
  spoiled (`optimizer/replan.py`, already in the app), or discounting estimated deadlines more strongly. Neither is
  measured here.

## Validation split (48 other scenarios)

| Perturbation | Degradation in waste (g): Greedy / MILP / no-expiry | MILP − no-expiry: waste (g) | Greedy − no-expiry: waste (g) |
| --- | --- | --- | --- |
| Spoils 1 day early | +18.1 / +9.8 / +10.8 | −0.9 [−7.3, +5.0] | +7.3 [−3.1, +18.5] |
| Spoils 2 days early | +34.9 / +21.6 / +10.8 | +10.8 [−0.9, +25.5] | **+24.0 [+8.1, +42.6]** |
| ±2 days jitter | −31.5 / −24.3 / −19.0 | −5.3 [−15.0, +3.2] | −12.5 [−30.2, +2.8] |
| 30 % less stock | −239.4 / −224.0 / −235.7 | **+11.7 [+5.7, +18.7]** | −3.7 [−11.8, +4.4] |
| 30 % more stock | +250.5 / +242.4 / +245.1 | **−2.8 [−5.7, −0.3]** | +5.4 [−0.3, +11.1] |
| ±30 % quantity noise | +28.1 / +31.1 / +28.0 | +3.1 [−2.7, +8.9] | +0.1 [−4.6, +4.4] |
| Combined | +55.0 / +45.7 / +43.5 | +2.2 [−3.1, +8.2] | +11.6 [−2.5, +25.6] |

Nominal (validation): waste greedy 735 g · MILP 702 g · `opt_no_expiry` 735 g.

## Caveats

- Synthetic scenarios and perturbations.
- With less stock, waste *falls* for every plan simply because there is less food to waste. Compare planners, and use
  the grocery columns for quantity perturbations.
- 48 scenarios per split (6 per family) gives wide intervals.
