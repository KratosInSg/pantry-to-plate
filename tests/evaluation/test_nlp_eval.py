"""Tests for ``evaluation/nlp_eval.py``: alignment, the four kinds of miss, P/R/F1 and quantity/urgency scoring."""
from __future__ import annotations

from dataclasses import asdict
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from evaluation.nlp_eval import (bootstrap_cis, message_exact, prf, quantity_correct, score_message, summary)
from evaluation.pantry_messages import load_messages
from nlp.schemas import GramsSource, MatchStatus, ParsedItem, ParseResult, Urgency

V3 = Path(__file__).resolve().parents[2] / "data" / "evaluation" / "v3"


def _gold(iid, phrase, form="mass", value=200.0, unit="g", urgency="none", cue_kind="none", days=None, **extra):
    q = {"form": form, "value": value, "unit": unit, **extra}
    if form == "mass":
        q["grams"] = value
    return {"ingredient_id": iid, "canonical_name": f"food {iid}", "surface": f"food {iid}", "name_variant": "top",
            "quantity": q, "urgency": urgency, "cue_kind": cue_kind, "cue_text": None, "days_left": days,
            "phrase": phrase}


def _item(raw, iid=None, status=MatchStatus.MATCHED, **kw):
    return ParsedItem(raw_text=raw, name_text=raw, ingredient_id=iid, match_status=status, **kw)


def test_alignment_classifies_every_kind_of_miss_and_counts_false_alarms(store):
    message = {"scenario_id": "m", "items": [
        _gold(1, "200g food one"), _gold(2, "200g food two"), _gold(3, "200g food three"),
        _gold(4, "200g food four"), _gold(5, "200g food five")]}
    result = ParseResult(source_text="", items=[
        _item("200g food one", 1, grams=200.0, grams_source=GramsSource.EXPLICIT_MASS, quantity_value=200,
              quantity_unit="g"),
        _item("200g food two", 99),                                             # confident, wrong ingredient
        _item("200g food three", 3, status=MatchStatus.AMBIGUOUS),              # asks the user
        _item("200g food four", None, status=MatchStatus.UNKNOWN),              # not recognised
        _item("and that's it", 42)])                                            # chatter read as food
    rows = pd.DataFrame([asdict(r) for r in score_message(message, result, store)])
    outcomes = dict(zip(rows.gold_ingredient_id.fillna(-1).astype(int), rows.outcome))
    assert outcomes == {1: "found", 2: "wrong_ingredient", 3: "asked_user", 4: "not_recognised", 5: "no_item",
                        -1: "spurious"}
    s = prf(rows)
    assert (s["tp"], s["fp"], s["fn"]) == (1, 2, 4)
    assert s["precision"] == pytest.approx(1 / 3) and s["recall"] == pytest.approx(1 / 5)
    assert not message_exact(rows).iloc[0]


def test_quantity_scoring_per_form(store):
    mass = {"form": "mass", "value": 450.0, "unit": "g", "grams": 450.0}
    assert quantity_correct(mass, _item("x", 1, grams=452.0, grams_source=GramsSource.EXPLICIT_MASS), store)
    assert not quantity_correct(mass, _item("x", 1, grams=450.0, grams_source=GramsSource.ASSUMED_DEFAULT), store)
    vol = {"form": "volume", "value": 2.0, "unit": "cup", "ml": 2 * 236.588}
    assert quantity_correct(vol, _item("x", 1, quantity_value=2.0, quantity_unit="cup"), store)
    assert quantity_correct({"form": "volume", "value": 500.0, "unit": "ml", "ml": 500.0},
                            _item("x", 1, quantity_value=0.5, quantity_unit="l"), store)
    count = {"form": "count", "value": 2.0, "unit": None}
    assert quantity_correct(count, _item("2 chicken breasts", 1, quantity_value=2.0, quantity_unit=None), store)
    assert quantity_correct(count, _item("2 chicken breasts", 1, quantity_value=2.0, quantity_unit="breast"), store)
    assert not quantity_correct(count, _item("2 eggs", 1, quantity_value=3.0), store)
    can = {"form": "container", "value": 1.0, "unit": "can"}
    assert quantity_correct(can, _item("a tin of beans", 1, quantity_value=1.0, quantity_unit="tin"), store)
    assert not quantity_correct(can, _item("a tin of beans", 1, quantity_value=1.0, quantity_unit=None), store)
    none = {"form": "none", "value": None, "unit": None}
    assert quantity_correct(none, _item("spinach", 1, grams=250.0, quantity_is_assumed=True), store)


def test_urgency_and_stated_dates_are_scored_on_found_items(store):
    message = {"scenario_id": "m", "items": [
        _gold(1, "milk (use by friday)", form="none", value=None, unit=None, urgency="soon", cue_kind="explicit",
              days=3)]}
    right = ParseResult(source_text="", items=[_item("milk (use by friday)", 1, urgency=Urgency.SOON,
                                                     days_left_hint=3, days_left_explicit=True)])
    wrong = ParseResult(source_text="", items=[_item("milk (use by friday)", 1, urgency=Urgency.NONE)])
    r1, = score_message(message, right, store)
    r2, = score_message(message, wrong, store)
    assert (r1.urgency_ok, r1.days_ok) == (True, True)
    assert (r2.urgency_ok, r2.days_ok) == (False, False)


def test_parsing_the_committed_messages_end_to_end(store):
    """A smoke test on real messages: the parser runs, every gold item gets an outcome, the CIs bracket the estimate."""
    from nlp.pantry_parser import PantryParser
    parser = PantryParser(store)
    rows = []
    for m in load_messages(V3)[:12]:
        rows += score_message(m, parser.parse(m["text"], today=date.fromisoformat(m["today"])), store)
    df = pd.DataFrame([asdict(r) for r in rows])
    assert set(df.outcome) <= {"found", "wrong_ingredient", "asked_user", "not_recognised", "no_item", "spurious"}
    s = summary(df, n_boot=200)
    assert 0 < s["recall"] <= 1 and s["f1_ci"][0] <= s["f1"] <= s["f1_ci"][1]
    cis = bootstrap_cis(df, n_boot=200)
    assert set(cis) == {"precision", "recall", "f1", "quantity", "urgency"}
