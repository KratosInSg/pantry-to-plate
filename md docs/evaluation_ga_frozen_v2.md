# GA frozen configuration — 2026-10-16

**Selected on validation data only** (24 scenarios × 5 seeds), prior to any held-out test evaluation:

- Population: **48**
- Generations: **350**
- Mutation probability: **0.20** (probability of changing one gene per child)
- Tournament size: **3**
- Elitism: **3**
- Default seed: **42** (other seeds supported for uncertainty analysis)
- Shortlist size: **120**
- Objective weights: `optimizer.weekly.DEFAULT_WEIGHTS`, unchanged.

Selection rationale: speed-oriented compromise with strong nutrition and food-waste performance; population 96 at 20% had marginally better weighted fitness (51.294 versus 51.536) but almost twice the runtime (0.884 versus 0.465 s per plan). Population 48 at 35% mutation had lower weighted fitness (51.383) but worse nutrition and waste; the selection prioritises these outcomes and latency over the minimum weighted score alone.

The default `genetic` planner now uses the frozen configuration. Explicit `genetic_35_sN` and `genetic_350_sN` variants remain available for experiments. No new hyperparameter tuning should use the held-out test split. Benchmark `data/evaluation/v2` is an integrity rebaseline of the original committed scenarios, not a newly sampled independent dataset.

Full validation comparison:

```bash
python src/evaluation/runner.py --split validation --planners greedy,optimiser,genetic --baseline greedy --save
```

Report all eight scenario families, paired bootstrap CIs, grocery grams as well as item counts, expiring and overall pantry utilisation, safety, completion, and runtime. This is a validation comparison, not a final held-out test claim.
