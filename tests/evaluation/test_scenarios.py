"""Tests for ``evaluation/scenarios.py``: determinism, planner-visible vs hidden truth, and the freeze discipline."""
from __future__ import annotations

import json

import numpy as np
import pytest

from evaluation.scenarios import (DEFAULT_EVAL_DIR, FAMILIES, SPECS, build_benchmark, freeze_benchmark,
                                  generate_scenario, load_split, split_benchmark)
from optimizer.hard_rules import feasible_mask

SEED = 12345


@pytest.fixture(scope="module")
def small_benchmark(catalog, store):
    return build_benchmark(catalog, store, n_per_family=2, base_seed=SEED)


def test_generation_is_a_pure_function_of_family_and_seed(catalog, store):
    a = generate_scenario("expiry_heavy", SEED, catalog, store)
    b = generate_scenario("expiry_heavy", SEED, catalog, store)
    c = generate_scenario("expiry_heavy", SEED + 1, catalog, store)
    assert a.model_dump_json() == b.model_dump_json()
    assert a.model_dump_json() != c.model_dump_json()


@pytest.mark.parametrize("family", FAMILIES)
def test_every_family_yields_a_valid_scenario(family, catalog, store, ctx):
    spec = SPECS[family]
    for seed in range(SEED, SEED + 5):
        sc = generate_scenario(family, seed, catalog, store)
        assert sc.family == family and sc.scenario_id.startswith(family)
        assert len(sc.pantry) > 0
        assert not {p.ingredient_id for p in sc.pantry} & set(ctx.ignore_ids)          # staples are never stocked
        assert not {p.ingredient_id for p in sc.pantry} & sc.profile.excluded_ingredient_ids
        assert sum(p.grams for p in sc.pantry) <= spec.pantry_cap_g * 1.15             # rounding slack only
        assert set(sc.true_last_use_day) == {p.ingredient_id for p in sc.pantry}


def test_known_dates_are_the_truth_and_estimates_are_flagged(catalog, store):
    seen_known = seen_estimate = False
    for seed in range(SEED, SEED + 10):
        sc = generate_scenario("expiry_heavy", seed, catalog, store)
        for item in sc.pantry:
            if item.expiry_known:
                seen_known = True
                assert item.last_use_day == sc.true_last_use_day[item.ingredient_id]     # the user stated the truth
                assert item.expiry_confidence == 1.0
            elif item.last_use_day is not None:
                seen_estimate = True
                assert item.expiry_confidence < 1.0
    assert seen_known and seen_estimate


def test_the_pool_of_infeasible_combo_is_small_but_a_week_is_still_possible(catalog, store):
    counts = [int(feasible_mask(catalog, generate_scenario("infeasible_combo", s, catalog, store).profile).sum())
              for s in range(SEED, SEED + 8)]
    assert min(counts) >= 7                                  # "very few", not "none": graceful degradation, not failure
    assert np.median(counts) < catalog.n * 0.05


def test_benchmark_has_every_family_in_equal_numbers(small_benchmark):
    assert len(small_benchmark) == 2 * len(FAMILIES)
    assert len({s.scenario_id for s in small_benchmark}) == len(small_benchmark)
    for fam in FAMILIES:
        assert sum(s.family == fam for s in small_benchmark) == 2


def test_split_is_stratified_disjoint_and_deterministic(small_benchmark):
    split = split_benchmark(small_benchmark)
    assert not set(split["validation"]) & set(split["test"])
    assert set(split["validation"]) | set(split["test"]) == {s.scenario_id for s in small_benchmark}
    by_id = {s.scenario_id: s.family for s in small_benchmark}
    for fam in FAMILIES:
        assert sum(by_id[i] == fam for i in split["validation"]) == 1       # 2 per family -> 1 + 1
    assert split == split_benchmark(small_benchmark)


def test_freeze_writes_hashes_refuses_overwrite_and_detects_tampering(small_benchmark, tmp_path):
    path = freeze_benchmark(small_benchmark, tmp_path)
    meta = json.loads(path.read_text(encoding="utf-8"))
    assert meta["n_scenarios"] == len(small_benchmark) and len(meta["files"]) == 2

    with pytest.raises(FileExistsError):                      # frozen means frozen
        freeze_benchmark(small_benchmark, tmp_path)

    val, test = load_split("validation", tmp_path), load_split("test", tmp_path)
    assert len(val) == len(test) == len(FAMILIES)
    assert not {s.scenario_id for s in val} & {s.scenario_id for s in test}

    scenarios_file = next(tmp_path.glob("scenarios_*.jsonl"))
    scenarios_file.write_text(scenarios_file.read_text(encoding="utf-8") + " ", encoding="utf-8")
    with pytest.raises(RuntimeError, match="FROZEN"):
        load_split("validation", tmp_path)


def test_load_split_rejects_an_unknown_split(tmp_path):
    with pytest.raises(ValueError):
        load_split("train", tmp_path)


def test_repository_benchmark_is_intact_and_balanced():
    """The committed benchmark loads (hashes verified) and holds 15 + 15 scenarios per family."""
    val, test = load_split("validation", DEFAULT_EVAL_DIR), load_split("test", DEFAULT_EVAL_DIR)
    assert len(val) == len(test) == 120
    assert not {s.scenario_id for s in val} & {s.scenario_id for s in test}
    for fam in FAMILIES:
        assert sum(s.family == fam for s in val) == sum(s.family == fam for s in test) == 15


def test_freeze_can_name_a_new_version_and_make_a_test_only_benchmark(small_benchmark, tmp_path):
    """A new independent sample gets its own file names, can be all-test, and records where it came from."""
    path = freeze_benchmark(small_benchmark, tmp_path, version="v9", validation_share=0.0,
                            provenance={"base_seed": SEED})
    meta = json.loads(path.read_text(encoding="utf-8"))
    assert meta["version"] == "v9" and meta["provenance"] == {"base_seed": SEED}
    assert set(meta["files"]) == {"scenarios_v9.jsonl", "split_v9.json"}
    assert load_split("validation", tmp_path) == []
    assert len(load_split("test", tmp_path)) == len(small_benchmark)


def test_repository_v3_benchmark_is_fresh_test_only_and_disjoint_from_v2():
    """v3 = 120 new kitchens, all held out, none of them a v2 kitchen (new seeds)."""
    from pathlib import Path
    v3_dir = Path(__file__).resolve().parents[2] / "data" / "evaluation" / "v3"
    v3 = load_split("test", v3_dir)
    assert len(v3) == 120 and load_split("validation", v3_dir) == []
    assert {fam: sum(s.family == fam for s in v3) for fam in FAMILIES} == {fam: 15 for fam in FAMILIES}
    v2_ids = {s.scenario_id for split in ("validation", "test") for s in load_split(split, DEFAULT_EVAL_DIR)}
    assert not v2_ids & {s.scenario_id for s in v3}
