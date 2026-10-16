# `src/evaluation/ga_objective_audit.py`

Validation-only objective audit. For each GA plan, rebuilds the normal weekly MILP, fixes recipe/day binary variables to that GA chromosome, solves remaining variables using HiGHS, and prints the difference between GA replay fitness and the MILP fixed-plan objective. No hidden ground truth is used. Nonzero deltas must be investigated and documented, not ignored. Usage: `python src/evaluation/ga_objective_audit.py --limit 3 --planner genetic_35_s0`.

## Term-by-term audit (2026-10-16)

The audit now reports `ga_terms`, `milp_terms`, and `term_deltas` for waste, groceries, nutrition, preference, cook time and variety, plus the total fitness discrepancy. Both decompositions are independently checked against their respective total objectives. This diagnoses *which* terms differ without modifying either optimiser. Fixed-plan MILP can optimise its inventory allocation, while GA replay uses first-available pantry stock. A mismatch is not silently declared equivalence. Run `python src/evaluation/ga_objective_audit.py --limit 3 --planner genetic_350_s0`.

## Change log

- 2026-10-16 — Created: fixed-plan MILP audit of GA fitness; term-by-term deltas added the same day.
