# GA hyperparameter sweep

Module: `src/evaluation/ga_hyperparams.py`.

Controlled validation-only factorial comparison of mutation rates **0.10, 0.20, 0.35** and population sizes **48, 96**, holding generations at **350**, tournament size at 3, and using the same **five seeds (0–4)** and same stratified **24 validation scenarios** for every configuration.

The script instantiates the existing `GeneticPlanner` with `GAConfig` overrides and labels each result with its population, mutation rate, and seed. It does **not** change production GA defaults or the MILP, and it does not touch the held-out test split.

```bash
python -m pytest tests/evaluation/test_ga_hyperparams.py -q
python src/evaluation/ga_hyperparams.py --limit 24 --seeds 5 --generations 350
```

There are 6 configurations × 5 seeds × 24 scenarios = **720 GA plans**. Output includes mean/std across seeds for weighted fitness, food waste, grocery items and grams, pantry and expiring utilisation, nutrition, preference, safety, completion, and runtime. It writes raw, per-seed, and summary CSVs to `data/evaluation/v2/runs/`.

Select a configuration using a predeclared criterion balancing **fitness, safety, and runtime**, not only one favourable seed or a single metric. After selection, freeze the hyperparameters before final held-out testing. A mutation probability is a probability of replacing **one gene in a child**, not a per-gene mutation probability. Hyperparameter search on validation data can overfit validation scenarios, so avoid sweeping excessively.
