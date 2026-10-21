"""Ingredient NLP evaluation (measure 7): score the pantry parser on the frozen synthetic pantry messages.

What is scored
--------------
Each message (``evaluation.pantry_messages``) is parsed exactly as the app parses user text (``nlp.PantryParser``,
rules only unless ``--llm`` is given and a model answers), with the message's own ``today`` so weekday cues resolve
to the intended day. Parsed items are aligned to the answer key by ingredient:

* **Ingredient precision / recall / F1** (micro over items). A gold item is found (TP) when the parser *confidently*
  resolved some fragment to the same canonical ingredient. A confident item with no gold partner is a false positive
  (wrong ingredient, a split item, or chatter read as food). Items the parser marked *ambiguous* (it asks the user) are
  not counted as found; they are reported separately because asking is better than guessing wrong.
* **Quantity accuracy** on found items: the amount the text states, read correctly - metric mass within 1 %, metric
  volume within 2 %, counts and containers by value *and* unit, and "no amount given" recognised as such.
* **Urgency accuracy** on found items (none / soon / urgent), plus the share of stated dates read to the right day.
* **Message exact match**: every item found, nothing spurious, every quantity and urgency right.

Misses are classified by what the parser did with the item's own phrase: resolved it to a *different* ingredient,
asked the user (ambiguous), did not recognise it, or produced no item for it. Results are broken down by name variant,
quantity form and cue kind, with 95 % bootstrap CIs over messages for the headline numbers.

Optional ``--plan``: parse-then-plan. Each kitchen is planned twice with the same planner - once from its frozen
structured pantry, once from the parser's reading of its message - and both plans are judged against the *same* frozen
kitchen (``evaluation.metrics.evaluate_plan``). The paired difference is what reading the user's words costs the week.

Usage::

    python src/evaluation/nlp_eval.py --eval-dir data/evaluation/v3 --save
    python src/evaluation/nlp_eval.py --eval-dir data/evaluation/v3 --plan optimiser --save
"""
from __future__ import annotations

import argparse
import logging
import sys
import time
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path

if __name__ == "__main__":                       # allow `python src/evaluation/nlp_eval.py`
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
import pandas as pd

from evaluation.pantry_messages import load_messages
from knowledge.store import KnowledgeStore
from nlp.schemas import GramsSource, MatchStatus, ParsedItem, ParseResult

logger = logging.getLogger(__name__)

MASS_TOLERANCE = 0.01          # metric mass read to within 1 %
VOLUME_TOLERANCE = 0.02        # metric volume within 2 % (unit rounding)
COUNT_UNITS = frozenset({None, "each", "piece", "whole", "item"})
UNIT_SYNONYMS = {"pack": "package", "packet": "package", "packs": "package", "packets": "package", "tin": "can"}


# ================================================================================================================
# per-item scoring
# ================================================================================================================
def _norm_unit(unit: str | None) -> str | None:
    if unit is None:
        return None
    u = unit.lower().strip()
    return UNIT_SYNONYMS.get(u, u)


def _volume_ml(item: ParsedItem, store: KnowledgeStore) -> float | None:
    if item.quantity_value is None or item.quantity_unit is None:
        return None
    unit = store.unit_definitions.get(item.quantity_unit.lower())
    if unit is None or unit.kind != "volume":
        return None
    return item.quantity_value * unit.to_base


def quantity_correct(gold: dict, item: ParsedItem, store: KnowledgeStore) -> bool:
    """Did the parser read the amount the text states? (``gold`` is the answer key's ``quantity``.)"""
    form = gold["form"]
    if form == "none":
        return item.quantity_value is None
    if form == "mass":
        return (item.grams_source is GramsSource.EXPLICIT_MASS and item.grams is not None
                and abs(item.grams - gold["grams"]) <= max(1.0, MASS_TOLERANCE * gold["grams"]))
    if form == "volume":
        ml = _volume_ml(item, store)
        return ml is not None and abs(ml - gold["ml"]) <= VOLUME_TOLERANCE * gold["ml"]
    if item.quantity_value is None or abs(item.quantity_value - gold["value"]) > 0.01:
        return False
    pred_unit, gold_unit = _norm_unit(item.quantity_unit), _norm_unit(gold["unit"])
    if form == "count" and gold_unit is None:
        # a bare count ("2 chicken breasts"): fine whether the parser calls it a count or names the item's own unit
        return pred_unit in COUNT_UNITS or (pred_unit is not None and pred_unit in item.raw_text.lower())
    return pred_unit == gold_unit


def days_correct(gold: dict, item: ParsedItem) -> bool:
    return item.days_left_explicit and item.days_left_hint == gold["days_left"]


def _confident(item: ParsedItem) -> bool:
    return item.match_status is MatchStatus.MATCHED and item.ingredient_id is not None


def _same_phrase(gold_phrase: str, item: ParsedItem) -> bool:
    a, b = gold_phrase.lower(), item.raw_text.lower().strip(" ,;.-")
    return bool(b) and (b in a or a in b)


@dataclass
class ItemRow:
    """One gold item (or one spurious parsed item) after alignment."""

    scenario_id: str
    gold_ingredient_id: int | None
    gold_name: str | None
    surface: str | None
    name_variant: str | None
    quantity_form: str | None
    cue_kind: str | None
    gold_urgency: str | None
    outcome: str                      # found | wrong_ingredient | asked_user | not_recognised | no_item | spurious
    pred_ingredient_id: int | None
    pred_name: str | None
    pred_raw_text: str | None
    quantity_ok: bool | None
    urgency_ok: bool | None
    pred_urgency: str | None
    days_ok: bool | None


def score_message(message: dict, result: ParseResult, store: KnowledgeStore) -> list[ItemRow]:
    """Align one parse to its answer key; one row per gold item plus one per spurious confident item."""
    preds = list(result.items)
    used: set[int] = set()
    rows: list[ItemRow] = []
    for gold in message["items"]:
        k = next((j for j, p in enumerate(preds) if j not in used and _confident(p)
                  and p.ingredient_id == gold["ingredient_id"]), None)
        base = dict(scenario_id=message["scenario_id"], gold_ingredient_id=gold["ingredient_id"],
                    gold_name=gold["canonical_name"], surface=gold["surface"], name_variant=gold["name_variant"],
                    quantity_form=gold["quantity"]["form"], cue_kind=gold["cue_kind"], gold_urgency=gold["urgency"])
        if k is not None:
            used.add(k)
            p = preds[k]
            rows.append(ItemRow(**base, outcome="found", pred_ingredient_id=p.ingredient_id,
                                pred_name=p.canonical_name, pred_raw_text=p.raw_text,
                                quantity_ok=quantity_correct(gold["quantity"], p, store),
                                urgency_ok=p.urgency.value == gold["urgency"], pred_urgency=p.urgency.value,
                                days_ok=days_correct(gold, p) if gold["cue_kind"] == "explicit" else None))
            continue
        # a miss: what did the parser do with this item's phrase?
        j = next((j for j, p in enumerate(preds) if j not in used and _same_phrase(gold["phrase"], p)), None)
        if j is None:
            outcome, p = "no_item", None
        else:
            p = preds[j]
            if _confident(p):
                outcome = "wrong_ingredient"
                used.add(j)                      # its error is this miss; do not count it again as spurious
            else:
                outcome = "asked_user" if p.match_status is MatchStatus.AMBIGUOUS else "not_recognised"
        rows.append(ItemRow(**base, outcome=outcome, pred_ingredient_id=p.ingredient_id if p else None,
                            pred_name=p.canonical_name if p else None, pred_raw_text=p.raw_text if p else None,
                            quantity_ok=None, urgency_ok=None, pred_urgency=None, days_ok=None))
    for j, p in enumerate(preds):
        if j not in used and _confident(p):
            rows.append(ItemRow(scenario_id=message["scenario_id"], gold_ingredient_id=None, gold_name=None,
                                surface=None, name_variant=None, quantity_form=None, cue_kind=None, gold_urgency=None,
                                outcome="spurious", pred_ingredient_id=p.ingredient_id, pred_name=p.canonical_name,
                                pred_raw_text=p.raw_text, quantity_ok=None, urgency_ok=None,
                                pred_urgency=p.urgency.value, days_ok=None))
    return rows


# ================================================================================================================
# aggregate
# ================================================================================================================
def prf(df: pd.DataFrame) -> dict[str, float]:
    """Micro precision / recall / F1 over the rows of ``df``.

    TP = found; FN = every other gold row; FP = spurious rows plus misses resolved to a *different* ingredient (a
    confident wrong answer is both a miss and a false alarm).
    """
    tp = int((df.outcome == "found").sum())
    fn = int(df.gold_ingredient_id.notna().sum()) - tp
    fp = int((df.outcome == "spurious").sum() + (df.outcome == "wrong_ingredient").sum())
    p = tp / (tp + fp) if tp + fp else 0.0
    r = tp / (tp + fn) if tp + fn else 0.0
    return {"tp": tp, "fp": fp, "fn": fn, "precision": p, "recall": r, "f1": 2 * p * r / (p + r) if p + r else 0.0}


def message_exact(df: pd.DataFrame) -> pd.Series:
    """Per message: True when every gold item is found with the right amount and urgency and nothing is spurious."""
    def ok(g: pd.DataFrame) -> bool:
        gold = g[g.gold_ingredient_id.notna()]
        return bool((gold.outcome == "found").all() and gold.quantity_ok.fillna(False).astype(bool).all()
                    and gold.urgency_ok.fillna(False).astype(bool).all() and not (g.outcome == "spurious").any())
    return df.groupby("scenario_id").apply(ok, include_groups=False)


def _per_message_counts(df: pd.DataFrame) -> pd.DataFrame:
    """Per message: the counts every headline ratio is built from (so a bootstrap only resamples rows of this)."""
    gold = df.gold_ingredient_id.notna()
    found = df.outcome == "found"
    frame = pd.DataFrame({
        "scenario_id": df.scenario_id, "tp": found, "gold": gold,
        "fp": (df.outcome == "spurious") | (df.outcome == "wrong_ingredient"),
        "q_ok": found & df.quantity_ok.fillna(False).astype(bool),
        "u_ok": found & df.urgency_ok.fillna(False).astype(bool)})
    return frame.groupby("scenario_id").sum()


def _ratios(c: np.ndarray) -> dict[str, float]:
    """``c`` columns: tp, gold, fp, q_ok, u_ok (summed over the sampled messages)."""
    tp, gold, fp, q_ok, u_ok = c
    p = tp / (tp + fp) if tp + fp else 0.0
    r = tp / gold if gold else 0.0
    return {"precision": p, "recall": r, "f1": 2 * p * r / (p + r) if p + r else 0.0,
            "quantity": q_ok / tp if tp else float("nan"), "urgency": u_ok / tp if tp else float("nan")}


def bootstrap_cis(df: pd.DataFrame, n_boot: int = 2000, seed: int = 0) -> dict[str, tuple[float, float]]:
    """95 % CIs of the headline ratios, resampling whole messages (items in one message are not independent)."""
    counts = _per_message_counts(df)[["tp", "gold", "fp", "q_ok", "u_ok"]].to_numpy(dtype=float)
    rng = np.random.default_rng(seed)
    picks = rng.integers(0, len(counts), (n_boot, len(counts)))
    sums = counts[picks].sum(axis=1)                                  # (n_boot, 5)
    samples = [_ratios(row) for row in sums]
    return {k: (float(np.nanpercentile([s[k] for s in samples], 2.5)),
                float(np.nanpercentile([s[k] for s in samples], 97.5))) for k in samples[0]}


def _found(df: pd.DataFrame) -> pd.DataFrame:
    return df[df.outcome == "found"]


def summary(df: pd.DataFrame, n_boot: int = 2000) -> dict:
    """Headline numbers (with CIs) - what the report quotes."""
    out = prf(df)
    cis = bootstrap_cis(df, n_boot)
    out["f1_ci"], out["precision_ci"], out["recall_ci"] = cis["f1"], cis["precision"], cis["recall"]
    found = _found(df)
    out["quantity_accuracy"] = float(found.quantity_ok.mean())
    out["quantity_ci"] = cis["quantity"]
    out["urgency_accuracy"] = float(found.urgency_ok.mean())
    out["urgency_ci"] = cis["urgency"]
    cued = found[found.cue_kind != "none"]
    out["urgency_accuracy_cued"] = float(cued.urgency_ok.mean()) if len(cued) else float("nan")
    explicit = found[found.cue_kind == "explicit"]
    out["stated_date_accuracy"] = float(explicit.days_ok.astype(bool).mean()) if len(explicit) else float("nan")
    out["asked_user"] = int((df.outcome == "asked_user").sum())
    exact = message_exact(df)
    out["message_exact"] = float(exact.mean())
    out["n_messages"] = int(df.scenario_id.nunique())
    out["n_gold_items"] = int(df.gold_ingredient_id.notna().sum())
    return out


def breakdown(df: pd.DataFrame, by: str) -> pd.DataFrame:
    """Recall, quantity and urgency accuracy per value of ``by`` (gold rows only)."""
    gold = df[df.gold_ingredient_id.notna()]
    rows = []
    for key, g in gold.groupby(by, dropna=False):
        found = g[g.outcome == "found"]
        rows.append({by: key, "n": len(g), "recall": (g.outcome == "found").mean(),
                     "quantity_ok": found.quantity_ok.mean() if len(found) else float("nan"),
                     "urgency_ok": found.urgency_ok.mean() if len(found) else float("nan"),
                     **{f"miss_{o}": int((g.outcome == o).sum()) for o in
                        ("wrong_ingredient", "asked_user", "not_recognised", "no_item")}})
    return pd.DataFrame(rows).set_index(by).round(3)


def urgency_confusion(df: pd.DataFrame) -> pd.DataFrame:
    found = _found(df)
    return pd.crosstab(found.gold_urgency, found.pred_urgency, rownames=["gold"], colnames=["parsed"])


# ================================================================================================================
# runs
# ================================================================================================================
def run_parse(eval_dir: Path, store: KnowledgeStore, use_llm: bool = False) -> tuple[pd.DataFrame, list[dict],
                                                                                     list[ParseResult]]:
    """Parse every frozen message; returns (item rows, messages, parse results)."""
    from nlp.pantry_parser import PantryParser
    fallback = None
    if use_llm:
        from llm.client import LlmClient
        from nlp.llm_fallback import LlmPantryFallback
        client = LlmClient()
        if not client.is_available():
            raise RuntimeError("--llm given but no language model answers at the configured address")
        fallback = LlmPantryFallback(client, PantryParser(store))      # the fallback re-reads with a rules parser
    parser = PantryParser(store, llm_fallback=fallback)
    messages = load_messages(eval_dir)
    rows: list[ItemRow] = []
    results: list[ParseResult] = []
    started = time.time()
    for m in messages:
        result = parser.parse(m["text"], today=date.fromisoformat(m["today"]))
        results.append(result)
        rows += score_message(m, result, store)
    logger.info("parsed %d messages in %.1f s", len(messages), time.time() - started)
    return pd.DataFrame([asdict(r) for r in rows]), messages, results


def run_parse_then_plan(eval_dir: Path, planner_name: str, messages: list[dict], results: list[ParseResult],
                        store: KnowledgeStore) -> pd.DataFrame:
    """Plan each kitchen from its frozen pantry and from the parsed message; judge both against the frozen kitchen."""
    from domain.pantry import pantry_from_parse
    from evaluation.metrics import evaluate_plan
    from evaluation.runner import build_planner
    from evaluation.scenarios import load_split
    from optimizer.planning import make_context, prepare

    ctx = make_context(store=store)
    planner = build_planner(planner_name, ctx)
    by_id = {s.scenario_id: s for s in load_split("test", eval_dir)}
    rows = []
    for k, (m, result) in enumerate(zip(messages, results)):
        gold = by_id[m["scenario_id"]]
        prepared = prepare(gold, ctx)
        parsed = pantry_from_parse(result, store, gold.horizon_days)
        typed = gold.model_copy(update={"pantry": parsed.items})
        for source, scenario in (("structured", gold), ("typed", typed)):
            plan = planner.plan(scenario)
            rows.append({**asdict(evaluate_plan(gold, plan, ctx, prepared)), "pantry_source": source,
                         "n_pantry_items": len(scenario.pantry)})
        if (k + 1) % 20 == 0:
            logger.info("%d/%d kitchens planned twice", k + 1, len(messages))
    return pd.DataFrame(rows)


def compare_sources(df: pd.DataFrame, metrics=("waste_g", "grocery_items", "grocery_g", "nutrition_in_range_pct",
                                               "preference_mean", "violations", "complete")) -> pd.DataFrame:
    """Paired ``typed - structured`` difference per metric, 95 % bootstrap CI."""
    from evaluation.metrics import paired_bootstrap
    frame = df.copy()
    frame["planner"] = frame.pantry_source
    rows = []
    for m in metrics:
        r = paired_bootstrap(frame, m, "typed", "structured")
        rows.append({"metric": m, "structured": frame[frame.planner == "structured"][m].mean(),
                     "typed": frame[frame.planner == "typed"][m].mean(),
                     "diff": f"{r['mean_diff']:+.2f} [{r['ci_low']:+.2f}, {r['ci_high']:+.2f}]"})
    return pd.DataFrame(rows).set_index("metric")


def report(df: pd.DataFrame, s: dict) -> None:
    pd.set_option("display.width", 220)
    pd.set_option("display.max_columns", 30)
    print(f"\n=== ingredient NLP on {s['n_messages']} synthetic messages, {s['n_gold_items']} items ===")
    print(f"precision {s['precision']:.3f} [{s['precision_ci'][0]:.3f}, {s['precision_ci'][1]:.3f}]   "
          f"recall {s['recall']:.3f} [{s['recall_ci'][0]:.3f}, {s['recall_ci'][1]:.3f}]   "
          f"F1 {s['f1']:.3f} [{s['f1_ci'][0]:.3f}, {s['f1_ci'][1]:.3f}]   (TP {s['tp']}, FP {s['fp']}, FN {s['fn']})")
    print(f"quantity accuracy (found items) {s['quantity_accuracy']:.3f} [{s['quantity_ci'][0]:.3f}, "
          f"{s['quantity_ci'][1]:.3f}]   urgency accuracy {s['urgency_accuracy']:.3f} [{s['urgency_ci'][0]:.3f}, "
          f"{s['urgency_ci'][1]:.3f}] (cued items only {s['urgency_accuracy_cued']:.3f})   "
          f"stated dates {s['stated_date_accuracy']:.3f}")
    print(f"asked the user: {s['asked_user']} items   messages fully right: {s['message_exact']:.3f}")
    for by in ("name_variant", "quantity_form", "cue_kind"):
        print(f"\n--- by {by} ---")
        print(breakdown(df, by).to_string())
    print("\n--- urgency (found items) ---")
    print(urgency_confusion(df).to_string())
    print("\n--- outcomes ---")
    print(df.outcome.value_counts().to_string())


def main() -> None:
    from knowledge.store import get_default_store
    from logging_setup import configure_logging

    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--eval-dir", type=Path, required=True, help="folder with the frozen messages, e.g. data/evaluation/v3")
    ap.add_argument("--llm", action="store_true", help="use the LLM fallback (needs a reachable model)")
    ap.add_argument("--plan", default=None, help="also run parse-then-plan with this planner, e.g. optimiser")
    ap.add_argument("--save", action="store_true", help="write per-item (and per-plan) CSVs to <eval-dir>/runs/")
    ap.add_argument("--log-level", default=None)
    args = ap.parse_args()
    configure_logging(args.log_level)
    store = get_default_store()
    df, messages, results = run_parse(args.eval_dir, store, args.llm)
    s = summary(df)
    report(df, s)
    stamp = time.strftime("%Y%m%d_%H%M%S")
    out = args.eval_dir / "runs"
    if args.save:
        out.mkdir(parents=True, exist_ok=True)
        df.to_csv(out / f"{stamp}_nlp_items.csv", index=False)
        print("saved", out / f"{stamp}_nlp_items.csv")
    if args.plan:
        plans = run_parse_then_plan(args.eval_dir, args.plan, messages, results, store)
        print(f"\n=== parse-then-plan ({args.plan}): typed message vs structured pantry, judged on the same kitchen ===")
        print(compare_sources(plans).to_string())
        if args.save:
            plans.to_csv(out / f"{stamp}_parse_then_plan.csv", index=False)
            print("saved", out / f"{stamp}_parse_then_plan.csv")


if __name__ == "__main__":
    main()
