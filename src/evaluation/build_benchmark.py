"""Generate and freeze the synthetic benchmark (scenarios + validation/test split + hashes).

Run once, from the repository root::

    python src/evaluation/build_benchmark.py                # writes data/evaluation/*_v1.* and FROZEN.json

The script refuses to overwrite a frozen benchmark. To change the generator, bump ``BENCHMARK_VERSION`` in
``scenarios.py`` (new files, new hashes) - and re-run every comparison, because old numbers no longer apply.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from evaluation.scenarios import (BENCHMARK_VERSION, DEFAULT_BASE_SEED, DEFAULT_EVAL_DIR, FAMILIES, build_benchmark,
                                  freeze_benchmark)
from knowledge.recipes import get_default_catalog
from knowledge.store import DEFAULT_DATA_DIR, get_default_store
from logging_setup import configure_logging
from optimizer.hard_rules import feasible_mask


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", type=Path, default=DEFAULT_EVAL_DIR)
    ap.add_argument("--n-per-family", type=int, default=30)
    ap.add_argument("--seed", type=int, default=DEFAULT_BASE_SEED)
    args = ap.parse_args()
    configure_logging()

    catalog, store = get_default_catalog(), get_default_store()
    scenarios = build_benchmark(catalog, store, args.n_per_family, args.seed)
    print(f"generated {len(scenarios)} scenarios ({args.n_per_family} x {len(FAMILIES)} families, version {BENCHMARK_VERSION})")
    for fam in FAMILIES:
        counts = [int(feasible_mask(catalog, s.profile).sum()) for s in scenarios if s.family == fam]
        print(f"  {fam:<24} feasible recipes: min {min(counts):>6}  median {sorted(counts)[len(counts)//2]:>6}  "
              f"max {max(counts):>6}  (<7: {sum(c < 7 for c in counts)})")
    path = freeze_benchmark(scenarios, args.out, DEFAULT_DATA_DIR / "MANIFEST.json")
    print("frozen:", path)


if __name__ == "__main__":
    main()
