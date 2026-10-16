# `src/evaluation/ga_objective_audit.py`

Validation-only objective audit. For each GA plan, rebuilds the normal weekly MILP, fixes recipe/day binary variables to that GA chromosome, solves remaining variables using HiGHS, and prints the difference between GA replay fitness and the MILP fixed-plan objective. No hidden ground truth is used. Nonzero deltas must be investigated and documented, not ignored. Usage: `python src/evaluation/ga_objective_audit.py --limit 3 --planner genetic_35_s0`.
