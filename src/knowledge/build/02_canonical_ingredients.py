"""Step 02 - canonical ingredient layer.

raw Food.com ingredient string
   -> Food.com canonical name (ingr_map.pkl, lemmatiser typos repaired)
   -> core name (prep/size words stripped)           [ingredient_names.core_name]
   -> synonym / split resolution                      [reference/ingredient_synonyms.csv]
   -> USDA FoodData Central food                      [reference/ingredient_usda_overrides.csv, else scored match]
   -> nutrition per 100 g, household-unit weights, food group, allergen/diet flags

Outputs (data/canonical/ingredients/ and nutrition/):
  ingredient.parquet                    one row per canonical ingredient (the master table)
  ingredient_alias.parquet              every spelling we have seen -> ingredient_id
  ingredient_nutrition_per100g.parquet  USDA nutrients per 100 g, joined via fdc_id
  ingredient_unit_weight.parquet        grams per cup / tbsp / each / ... for pantry parsing
"""
import ast
import csv
import pickle
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))          # sibling build modules (config, matcher, ...)
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))       # src/  -> `knowledge.*` shared modules
from config import (NUTRIENT_OUTPUT_ORDER, OUT_INGREDIENTS, OUT_META, OUT_NUTRITION, OUT_REFERENCE,  # noqa: E402
                    RAW_RECIPES, write_parquet)
from ingredient_flags import classify  # noqa: E402
from knowledge.ingredient_names import core_name  # noqa: E402  (shared with the runtime NLP layer)
from matcher import UsdaIndex  # noqa: E402

# ------------------------------------------------------------------ inputs ---
class _Unpickler(pickle.Unpickler):  # ingr_map.pkl was written by pandas 0.2x
    def find_class(self, module, name):
        if module.startswith("pandas.core.indexes.numeric"):
            return pd.Index
        return super().find_class(module, name)


with open(RAW_RECIPES / "ingr_map.pkl", "rb") as fh:
    ingr_map = _Unpickler(fh).load()
raw_to_foodcom = dict(zip(ingr_map.raw_ingr, ingr_map.replaced))

recipes = pd.read_csv(RAW_RECIPES / "RAW_recipes.csv", usecols=["id", "ingredients"])
recipes["ingredients"] = recipes.ingredients.map(ast.literal_eval)
print(f"recipes: {len(recipes):,}")

synonyms = {}
for r in csv.DictReader(open(OUT_REFERENCE / "ingredient_synonyms.csv", encoding="utf-8")):
    synonyms[core_name(r["name"])] = r["canonical_name"].strip()
overrides = {}
for r in csv.DictReader(open(OUT_REFERENCE / "ingredient_usda_overrides.csv", encoding="utf-8")):
    overrides[r["canonical_name"].strip()] = (r["usda_description"].strip(), r.get("note", "").strip())

foods = pd.read_parquet(OUT_NUTRITION / "usda_food_nutrient_per100g.parquet")
portions = pd.read_parquet(OUT_NUTRITION / "usda_food_portion_weight.parquet")

# ---------------------------------------------------------- name resolution ---
BASE_SUFFIXES = ("leaf", "floret", "spear", "wedge", "half", "piece", "chunk", "sprig", "stalk", "rib", "slice", "cube")


# "all purpose flour" and "all-purpose flour" are the same ingredient: fold hyphen-less spellings onto curated names
HYPHEN_FOLD = {k.replace("-", " "): k for k in list(overrides) + list(synonyms.values()) if "-" in k}


def resolve(name: str) -> list[str]:
    """core name -> list of canonical names (usually one; 'salt + black pepper' style splits give two)."""
    n = re.sub(r"\s+of$", "", name)
    n = re.sub(r"^of\s+", "", n)
    n = HYPHEN_FOLD.get(n, n)
    n = synonyms.get(n, n)
    out = []
    for p in n.split(" + "):
        p = synonyms.get(p, p)
        for suf in BASE_SUFFIXES:
            if p.endswith(" " + suf):
                base = p[: -len(suf) - 1]
                if base in overrides or base in synonyms:
                    p = synonyms.get(base, base)
                    break
        out.append(p)
    return [p for p in out if p]


# raw string -> canonical names, plus occurrence statistics
raw_strings = Counter()
recipe_sets = defaultdict(set)
for rid, ings in zip(recipes.id, recipes.ingredients):
    for s in ings:
        raw_strings[s] += 1
raw_resolution = {}
name_occ = Counter()
for s, c in raw_strings.items():
    base = raw_to_foodcom.get(s)
    source = "foodcom_map" if base else "raw_fallback"
    names = resolve(core_name(base if base else s))
    raw_resolution[s] = (names, source)
    for n in names:
        name_occ[n] += c
for rid, ings in zip(recipes.id, recipes.ingredients):
    seen = set()
    for s in ings:
        seen.update(raw_resolution[s][0])
    for n in seen:
        recipe_sets[n].add(rid)
n_recipes = {n: len(v) for n, v in recipe_sets.items()}
print(f"distinct raw strings: {len(raw_strings):,} -> canonical names: {len(name_occ):,}")

# --------------------------------------------------------------- USDA match ---
usable = foods[(foods.qc_flag == "ok")]
idx = UsdaIndex(usable[["fdc_id", "description", "data_type", "category"]])
rank = {"sr_legacy": 0, "foundation": 1, "survey_fndds": 2}
by_desc = defaultdict(list)
for r in usable.itertuples():
    by_desc[r.description].append((rank[r.data_type], r.fdc_id))
desc_list = sorted(by_desc, key=len)


def resolve_description(desc: str):
    if desc in by_desc:
        return min(by_desc[desc])[1], desc
    for d in desc_list:  # shortest description that starts with the given prefix
        if d.startswith(desc):
            return min(by_desc[d])[1], d
    return None, None


records = []
missing_forced = []
for name, occ in name_occ.most_common():
    fdc_id, desc, method, score = None, None, "none", None
    if name in overrides:
        fdc_id, desc = resolve_description(overrides[name][0])
        if fdc_id is None:
            missing_forced.append((name, overrides[name][0]))
        else:
            method, score = "curated", 2.0
    if fdc_id is None and name not in overrides:
        res = idx.match(name, topk=1)
        if res and res[0]["score"] >= 0.80:
            fdc_id, desc, score, method = res[0]["fdc_id"], res[0]["description"], res[0]["score"], "auto"
    records.append({"canonical_name": name, "fdc_id": fdc_id, "usda_description": desc, "match_method": method,
                    "match_score": score, "n_occurrences": occ, "n_recipes": n_recipes.get(name, 0)})
if missing_forced:
    raise SystemExit(f"override descriptions not found in USDA data: {missing_forced}")
ing = pd.DataFrame(records)


def confidence(row):
    if row.match_method == "curated":
        return 1.0
    if row.match_method == "auto":
        return 0.85 if row.match_score >= 1.2 else 0.75 if row.match_score >= 1.0 else 0.55
    return 0.0


ing["match_confidence"] = ing.apply(confidence, axis=1)
ing = ing.merge(foods[["fdc_id", "data_type", "category"]].rename(columns={"data_type": "usda_data_type",
                                                                            "category": "usda_category"}),
                on="fdc_id", how="left")

# ------------------------------------------------------- group + flags --------
_none = lambda v: None if pd.isna(v) else v  # noqa: E731
flags = [classify(r.canonical_name, _none(r.usda_description), _none(r.usda_category)) for r in ing.itertuples()]
flags = pd.DataFrame(flags)
ing = pd.concat([ing, flags], axis=1)
ing["is_assumed_available"] = ing.canonical_name.isin(["water", "salt", "black pepper"])  # default pantry staples
NON_FOOD = re.compile(r"(?:aluminum foil|foil|toothpicks?|skewers?|tea bags?|parchment|wax paper|cheesecloth|twine|"
                      r"cupcake liners?|paper towels?|plastic wrap)")
ing["is_non_food"] = ing.canonical_name.str.contains(NON_FOOD)  # cooking equipment that leaked into ingredient lists

ing = ing.sort_values(["n_occurrences", "canonical_name"], ascending=[False, True]).reset_index(drop=True)
ing["ingredient_id"] = np.arange(1, len(ing) + 1, dtype="int32")
name_to_id = dict(zip(ing.canonical_name, ing.ingredient_id))

cols = ["ingredient_id", "canonical_name", "food_group", "fdc_id", "usda_description", "usda_data_type",
        "match_method", "match_score", "match_confidence", "n_occurrences", "n_recipes", "is_assumed_available",
        "is_non_food",
        "contains_dairy", "contains_egg", "contains_gluten", "contains_peanut", "contains_tree_nut", "contains_soy",
        "contains_sesame", "contains_fish", "contains_shellfish", "contains_meat", "contains_poultry",
        "contains_pork", "contains_alcohol", "contains_honey", "contains_gelatin", "is_vegetarian", "is_vegan"]
master = ing[cols].copy()
master["fdc_id"] = master.fdc_id.astype("Int64")
master["match_score"] = master.match_score.astype("float32").round(3)
master["match_confidence"] = master.match_confidence.astype("float32")
write_parquet(master, OUT_INGREDIENTS / "ingredient.parquet")

# ---------------------------------------------------------------- aliases -----
alias_rows = defaultdict(lambda: {"n": 0, "source": None, "split": False})


def add_alias(alias, names, source, n=0):
    alias = re.sub(r"\s+", " ", alias.lower().strip())
    if not alias:
        return
    for nm in names:
        if nm not in name_to_id:
            continue
        key = (alias, name_to_id[nm])
        rec = alias_rows[key]
        rec["n"] = max(rec["n"], n)
        rec["source"] = rec["source"] or source
        rec["split"] = rec["split"] or len(names) > 1


for s, (names, src) in raw_resolution.items():
    add_alias(s, names, "foodcom_raw" if src == "foodcom_map" else "foodcom_raw_unmapped", raw_strings[s])
for foodcom_name in set(raw_to_foodcom.values()):
    add_alias(foodcom_name, resolve(core_name(foodcom_name)), "foodcom_canonical")
for syn_name, target in synonyms.items():
    add_alias(syn_name, resolve(core_name(target)), "synonym")
for nm in name_to_id:
    add_alias(nm, [nm], "canonical", int(master.loc[master.canonical_name == nm, "n_occurrences"].iloc[0]))
# generated spelling variants so the NLP lookup does not depend on punctuation or number:
# "all-purpose flour" -> "all purpose flour"; "tomato" -> "tomatoes"; "berry" -> "berries"
def _plural(word: str) -> str:
    if word.endswith("y") and len(word) > 2 and word[-2] not in "aeiou":
        return word[:-1] + "ies"
    if word.endswith(("s", "x", "z", "ch", "sh")):
        return word + "es"
    return word + "s"


existing = {k[0] for k in alias_rows}
for (a, iid), rec in list(alias_rows.items()):
    name_like = rec["source"] in ("canonical", "synonym", "foodcom_canonical") or a in name_to_id
    cands = set()
    if "-" in a:
        cands.add(a.replace("-", " "))            # every alias gets a hyphen-free twin
    toks = a.split(" ")
    if name_like and toks and toks[-1].isalpha() and len(toks[-1]) > 2:
        cands.add(" ".join(toks[:-1] + [_plural(toks[-1])]))   # plural only for names, not raw strings
    for c in cands:
        if c and c not in existing:
            alias_rows[(c, iid)] = {"n": 0, "source": "generated_variant", "split": rec["split"]}
            existing.add(c)
alias = pd.DataFrame([{"alias": k[0], "ingredient_id": k[1], "alias_source": v["source"], "n_occurrences": v["n"],
                       "is_split": v["split"]} for k, v in alias_rows.items()])
alias["ingredient_id"] = alias.ingredient_id.astype("int32")
alias = alias.sort_values(["alias", "ingredient_id"]).reset_index(drop=True)
write_parquet(alias, OUT_INGREDIENTS / "ingredient_alias.parquet")

# -------------------------------------------------- nutrition per 100 g -------
nut = ing[ing.fdc_id.notna() & ~ing.is_non_food][["ingredient_id", "fdc_id", "usda_data_type", "match_confidence"]].copy()
nut["fdc_id"] = nut.fdc_id.astype("int64")
nut = nut.merge(foods[["fdc_id"] + NUTRIENT_OUTPUT_ORDER + ["energy_source"]], on="fdc_id", how="left")
nut["basis"] = "per_100g"
nut["source"] = "USDA FoodData Central " + nut.usda_data_type.str.replace("_", " ") + " fdc_id=" + nut.fdc_id.astype(str)
nut = nut.drop(columns="usda_data_type").sort_values("ingredient_id").reset_index(drop=True)
write_parquet(nut, OUT_NUTRITION / "ingredient_nutrition_per100g.parquet")

# ------------------------------------------------------------ unit weights ----
# one grams_per_unit per (fdc_id, unit, size): plain portion preferred, else median over prep variants
port = portions.copy()
port["plain"] = port.prep.isna()
port["size"] = port["size"].fillna("")
rows = []
for (fid, unit, size), g in port.groupby(["fdc_id", "unit", "size"]):
    plain = g[g.plain]
    use = plain if len(plain) else g
    rows.append((fid, unit, size or None, float(np.median(use.grams_per_unit)),
                 None if len(plain) else (use.prep.mode().iloc[0] if use.prep.notna().any() else None)))
uw = pd.DataFrame(rows, columns=["fdc_id", "unit", "size", "grams_per_unit", "prep_basis"])
fdc_to_ing = ing[ing.fdc_id.notna() & ~ing.is_non_food][["ingredient_id", "fdc_id", "food_group"]].copy()
fdc_to_ing["fdc_id"] = fdc_to_ing.fdc_id.astype("int64")
uw = fdc_to_ing.merge(uw, on="fdc_id", how="left")
uw = uw[uw.unit.notna()].copy()
uw["source"] = "usda_portion"

# derive missing volume units from the ones we have (cup = 16 tbsp = 48 tsp = 8 fl oz)
VOL = {"cup": 1.0, "tbsp": 1 / 16, "tsp": 1 / 48, "fl_oz": 1 / 8}
derived = []
have = uw[uw.unit.isin(VOL) & uw["size"].isna()].groupby("ingredient_id")
per_ing = {}
for iid, g in have:
    cup_equiv = np.median([row.grams_per_unit / VOL[row.unit] for row in g.itertuples()])
    per_ing[iid] = cup_equiv
fg = fdc_to_ing.set_index("ingredient_id").food_group
group_cup = defaultdict(list)
for iid, c in per_ing.items():
    group_cup[fg.get(iid, "other")].append(c)
group_cup = {g: float(np.median(v)) for g, v in group_cup.items() if len(v) >= 5}
present = set(zip(uw.ingredient_id, uw.unit)) | set()
for r in fdc_to_ing.itertuples():
    cup = per_ing.get(r.ingredient_id)
    src = "derived_volume"
    if cup is None:
        cup, src = group_cup.get(r.food_group), "group_median"
    if cup is None:
        continue
    for unit, k in VOL.items():
        if (r.ingredient_id, unit) not in present and unit in ("cup", "tbsp", "tsp"):
            derived.append({"ingredient_id": r.ingredient_id, "fdc_id": r.fdc_id, "food_group": r.food_group,
                            "unit": unit, "size": None, "grams_per_unit": cup * k, "prep_basis": None, "source": src})
uw = pd.concat([uw, pd.DataFrame(derived)], ignore_index=True)
uw["grams_per_unit"] = uw.grams_per_unit.astype("float32").round(2)
uw["unit"] = uw.unit.astype("string")
uw["size"] = uw["size"].astype("string")
uw["prep_basis"] = uw.prep_basis.astype("string")
uw = uw[["ingredient_id", "unit", "size", "grams_per_unit", "prep_basis", "source"]].sort_values(
    ["ingredient_id", "unit", "size"]).reset_index(drop=True)
write_parquet(uw, OUT_INGREDIENTS / "ingredient_unit_weight.parquet")

# ------------------------------------------------------------------ report ----
tot = master.n_occurrences.sum()
mapped = master[master.fdc_id.notna() | master.is_non_food]
print("\n=== ingredient mapping summary ===")
print(f"canonical ingredients: {len(master):,} | mapped to USDA: {len(mapped):,} ({len(mapped)/len(master):.1%})")
print(f"occurrence coverage (mapped): {mapped.n_occurrences.sum()/tot:.2%}")
print("by method (occurrence share):",
      (master.groupby("match_method").n_occurrences.sum() / tot).round(3).to_dict())
print("by confidence (occurrence share):",
      (master.groupby("match_confidence").n_occurrences.sum() / tot).round(3).to_dict())
print("food groups (n ingredients):", master.food_group.value_counts().to_dict())
print(f"alias rows: {len(alias):,} | unit-weight rows: {len(uw):,} | ingredients with any unit weight: {uw.ingredient_id.nunique():,}")
import json  # noqa: E402
map_report = {
    "distinct_raw_strings": int(len(raw_strings)), "canonical_names": int(len(master)),
    "mapped_names": int(len(mapped)), "occurrences_total": int(tot),
    "occurrence_coverage_mapped": float(mapped.n_occurrences.sum() / tot),
    "occurrence_share_by_method": {k: float(v) for k, v in (master.groupby("match_method").n_occurrences.sum() / tot).items()},
    "occurrence_share_curated": float(master[master.match_method == "curated"].n_occurrences.sum() / tot),
}
OUT_META.mkdir(parents=True, exist_ok=True)
(OUT_META / "ingredient_mapping_report.json").write_text(json.dumps(map_report, indent=2), encoding="utf-8")
rep = master[(master.fdc_id.isna()) | (master.match_confidence < 0.8)].sort_values("n_occurrences", ascending=False)
OUT_META.mkdir(parents=True, exist_ok=True)
rep[["canonical_name", "n_occurrences", "n_recipes", "usda_description", "match_method", "match_score"]].head(1500).to_csv(
    OUT_META / "review_unmapped_or_low_confidence.csv", index=False)
print("review file written: _meta/review_unmapped_or_low_confidence.csv (top by frequency)")
