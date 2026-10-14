# `src/evaluation/build_benchmark.py`

## Purpose

One-shot script that generates the benchmark scenarios and **freezes** them into `data/evaluation/`.

```bash
python src/evaluation/build_benchmark.py                 # 30 per family x 8 = 240 scenarios, writes *_v1.* + FROZEN.json
python src/evaluation/build_benchmark.py --out some/dir  # a different folder (e.g. a draft)
```

It prints, for every family, the number of recipes that pass the hard rules (min / median / max, and how many scenarios
have fewer than seven) so a family that accidentally became infeasible is visible immediately.

## Rules

* It **refuses to overwrite** a frozen benchmark (`FileExistsError` from `freeze_benchmark`).
* To change the generator: bump `BENCHMARK_VERSION` in `scenarios.py`, regenerate, and re-run every comparison — old
  numbers no longer apply.
* Freeze **before** any weight tuning.

## State

v1 frozen on 2026-10-12: 240 scenarios (120 validation / 120 test); `FROZEN.json` also records the SHA-256 of the
dataset `MANIFEST.json` the scenarios were generated from.

## Tests

No dedicated test: the functions it calls (`build_benchmark`, `freeze_benchmark`, `load_split`) are covered in
[`tests/evaluation/test_scenarios.py`](../tests/evaluation/test_scenarios.md), including a check that the committed
benchmark loads and is balanced.

## Logging

`main()` calls `configure_logging()`, so the dataset and catalogue loads are visible. The summary stays `print`.

## Change log

- 2026-10-12 — Created; ran once to freeze v1.
- 2026-10-14 — Configures logging at start-up.
