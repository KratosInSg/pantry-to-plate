"""Tests for ``evaluation/pantry_messages.py``: the synthetic pantry messages and their answer key."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from evaluation.pantry_messages import (REGIONAL_NAMES, _Names, _typo, build_messages, freeze_messages, load_messages,
                                        message_today, pluralise, render_message)
from evaluation.scenarios import generate_scenario, load_split

V3 = Path(__file__).resolve().parents[2] / "data" / "evaluation" / "v3"


@pytest.fixture(scope="module")
def kitchen(catalog, store):
    return generate_scenario("expiry_heavy", 777, catalog, store)


@pytest.fixture(scope="module")
def message(kitchen, store):
    return render_message(kitchen, store, seed=1)


def test_rendering_is_a_pure_function_of_kitchen_and_seed(kitchen, store, message):
    assert render_message(kitchen, store, seed=1) == message
    assert render_message(kitchen, store, seed=2)["text"] != message["text"]


def test_answer_key_covers_every_pantry_item_once(kitchen, message):
    assert sorted(i["ingredient_id"] for i in message["items"]) == sorted(p.ingredient_id for p in kitchen.pantry)
    for item in message["items"]:
        assert item["phrase"] in message["text"]                       # what was written is in the text
        assert item["urgency"] in ("none", "soon", "urgent")


def test_stated_dates_and_cues_follow_the_kitchen(kitchen, message):
    by_id = {p.ingredient_id: p for p in kitchen.pantry}
    for item in message["items"]:
        stock = by_id[item["ingredient_id"]]
        if item["cue_kind"] == "explicit":
            assert stock.expiry_known and item["days_left"] == stock.last_use_day
            assert item["urgency"] == ("urgent" if stock.last_use_day <= 1 else
                                       "soon" if stock.last_use_day <= 4 else "none")
        elif item["cue_kind"] == "qualitative":
            assert not stock.expiry_known and stock.last_use_day is not None and stock.last_use_day <= 1
        else:
            assert item["urgency"] == "none"


def test_quantity_key_is_self_consistent(kitchen, message):
    for item in message["items"]:
        q = item["quantity"]
        if q["form"] == "mass":
            assert q["unit"] == "g" and q["grams"] == q["value"] > 0
        elif q["form"] == "volume":
            assert q["unit"] in ("ml", "cup") and q["ml"] > 0
        elif q["form"] == "none":
            assert q["value"] is None
        else:
            assert q["value"] > 0


def test_today_has_the_kitchen_start_weekday(kitchen):
    assert message_today(kitchen).weekday() == kitchen.start_weekday


def test_spelling_helpers():
    assert pluralise("tomato") == "tomatoes" and pluralise("chicken breast") == "chicken breasts"
    assert pluralise("berry") == "berries" and pluralise("peach") == "peaches" and pluralise("eggs") == "eggs"
    rng = np.random.default_rng(0)
    typed = _typo("cauliflower", rng)
    assert typed != "cauliflower" and typed[0] == "c" and abs(len(typed) - len("cauliflower")) <= 1
    assert _typo("egg", rng) == "egg"                                    # too short to mistype believably


def test_names_come_from_the_vocabulary_or_the_regional_list(store, kitchen, message):
    names = _Names(store)
    for item in message["items"]:
        if item["name_variant"] == "regional":
            assert item["surface"] in REGIONAL_NAMES[item["canonical_name"]]
        elif item["name_variant"] in ("top", "variant"):
            assert store.lookup_alias(item["surface"]) == (item["ingredient_id"],) or \
                item["surface"] == store.ingredient(item["ingredient_id"]).canonical_name
    assert names.top(store.ingredient_by_name("onion").ingredient_id) == "onion"


def test_freeze_and_load_verify_the_hash(kitchen, store, tmp_path):
    msgs = build_messages([kitchen], store, seed=3)
    freeze_messages(msgs, tmp_path, seed=3)
    assert load_messages(tmp_path) == msgs
    with pytest.raises(FileExistsError):
        freeze_messages(msgs, tmp_path, seed=3)
    path = next(tmp_path.glob("pantry_messages_*.jsonl"))
    path.write_text(path.read_text(encoding="utf-8").replace("g", "kg", 1), encoding="utf-8")
    with pytest.raises(RuntimeError, match="modified"):
        load_messages(tmp_path)


def test_committed_message_set_matches_the_v3_kitchens():
    msgs = load_messages(V3)
    kitchens = {s.scenario_id: s for s in load_split("test", V3)}
    assert len(msgs) == 120 and {m["scenario_id"] for m in msgs} == set(kitchens)
    meta = json.loads((V3 / "MESSAGES_FROZEN.json").read_text(encoding="utf-8"))
    assert meta["n_items"] == sum(len(m["items"]) for m in msgs) == sum(len(s.pantry) for s in kitchens.values())
    assert "synthetic" in meta["labels"]
