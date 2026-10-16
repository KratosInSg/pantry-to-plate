# `src/evaluation/ga_multiseed.py`

Validation-only GA stability and budget comparison. Runs five independent seeds at 35 and 350 generations plus deterministic greedy/MILP on the same stratified 24 validation scenarios. Saves raw, per-seed, and across-seed summary CSV files under `data/evaluation/v2/runs/`; reports mean, standard deviation, minimum, maximum and runtime. Usage: `python src/evaluation/ga_multiseed.py --limit 24 --seeds 5 --generations 35,350`. Never tune on the test split.

## Change log

- 2026-10-16 — Created: five-seed 35-vs-350-generation validation experiment.
