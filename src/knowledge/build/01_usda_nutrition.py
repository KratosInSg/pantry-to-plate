"""Step 01 - USDA FoodData Central -> compact nutrition + portion-weight tables.

Keeps only the three non-branded data types (SR Legacy, Foundation, FNDDS survey
foods = ~13.7K foods) and only the nutrients the planner uses. Branded foods are
out of scope for the MVP (see docs: hidden allergens in packaged foods).

Outputs (data/canonical/nutrition/):
  usda_food_nutrient_per100g.parquet   one row per FDC food, nutrients per 100 g
  usda_food_portion_weight.parquet     household-unit -> grams, cleaned
"""
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import (ATWATER, CORE_DATA_TYPES, ENERGY_IDS_PRIORITY, NUTRIENT_COLUMNS,  # noqa: E402
                    NUTRIENT_OUTPUT_ORDER, OUT_NUTRITION, RAW_FDC, write_parquet)

# ---------------------------------------------------------------- foods ------
food = pd.read_csv(RAW_FDC / "food.csv", usecols=["fdc_id", "data_type", "description", "food_category_id"],
                   dtype={"fdc_id": "int64", "food_category_id": "string"})
food = food[food.data_type.isin(CORE_DATA_TYPES)].copy()

usda_cat = pd.read_csv(RAW_FDC / "food_category.csv", dtype={"id": "string"}).set_index("id").description
wweia = pd.read_csv(RAW_FDC / "wweia_food_category.csv", dtype={"wweia_food_category": "string"}
                    ).set_index("wweia_food_category").wweia_food_category_description
food["category"] = np.where(food.data_type == "survey_fndds_food",
                            food.food_category_id.map(wweia), food.food_category_id.map(usda_cat))
food["description"] = food.description.str.strip().str.replace(r"\s+", " ", regex=True)
food = food.drop(columns="food_category_id")
core_ids = set(food.fdc_id)
print(f"core foods: {len(food):,}", food.data_type.value_counts().to_dict())

# ------------------------------------------------------------- nutrients -----
wanted = set(NUTRIENT_COLUMNS) | set(ENERGY_IDS_PRIORITY)
parts = []
for chunk in pd.read_csv(RAW_FDC / "food_nutrient.csv", usecols=["fdc_id", "nutrient_id", "amount"],
                         dtype={"fdc_id": "int64", "nutrient_id": "int32", "amount": "float32"}, chunksize=3_000_000):
    chunk = chunk[chunk.nutrient_id.isin(wanted) & chunk.fdc_id.isin(core_ids)]
    if len(chunk):
        parts.append(chunk)
fn = pd.concat(parts, ignore_index=True)
print(f"kept food_nutrient rows: {len(fn):,}")
fn = fn.groupby(["fdc_id", "nutrient_id"], as_index=False).amount.mean()
wide = fn.pivot(index="fdc_id", columns="nutrient_id", values="amount")

out = pd.DataFrame(index=wide.index)
# Energy: 1008 -> Atwater general (2047) -> Atwater specific (2048) -> computed 4/4/9
out["energy_kcal"] = np.nan
out["energy_source"] = pd.Series(pd.NA, index=wide.index, dtype="string")
for nid in ENERGY_IDS_PRIORITY:
    if nid in wide:
        fill = out.energy_kcal.isna() & wide[nid].notna()
        out.loc[fill, "energy_kcal"] = wide.loc[fill, nid]
        out.loc[fill, "energy_source"] = {1008: "usda_energy", 2047: "usda_atwater_general", 2048: "usda_atwater_specific"}[nid]
# Other nutrients (ids sharing a column are used in dict order: first present wins)
for nid, col in NUTRIENT_COLUMNS.items():
    if nid not in wide:
        continue
    if col not in out:
        out[col] = np.nan
    fill = out[col].isna() & wide[nid].notna()
    out.loc[fill, col] = wide.loc[fill, nid]
for col in NUTRIENT_OUTPUT_ORDER:
    if col not in out:
        out[col] = np.nan
macros = out[list(ATWATER)]
computed = sum(out[c].fillna(0) * k for c, k in ATWATER.items())
n_macros = macros.notna().sum(axis=1)
fill = out.energy_kcal.isna() & (n_macros >= 2)          # tolerate one missing macro (treated as 0)
out.loc[fill, "energy_kcal"] = computed[fill]
out.loc[fill, "energy_source"] = np.where(n_macros[fill] == 3, "computed_atwater_4_4_9", "computed_atwater_partial")

out = out.reset_index().rename_axis(columns=None)
out = food.merge(out, on="fdc_id", how="left")

# ---- quality flags (informational; nothing is dropped silently) --------------
macro_sum = out.protein_g.fillna(0) + out.fat_g.fillna(0) + out.carbohydrate_g.fillna(0)
flag = pd.Series("ok", index=out.index, dtype="string")
flag[out.energy_kcal.isna()] = "no_energy"
flag[(out.energy_kcal > 925) | (out.energy_kcal < 0)] = "energy_out_of_range"  # pure fats are ~900
flag[(macro_sum > 105) & (flag == "ok")] = "macro_sum_gt_100g"
out["qc_flag"] = flag
out["data_type"] = out.data_type.str.replace("_food", "", regex=False)  # sr_legacy / foundation / survey_fndds

for col in NUTRIENT_OUTPUT_ORDER:
    out[col] = out[col].astype("float32").round(3)
cols = ["fdc_id", "data_type", "description", "category"] + NUTRIENT_OUTPUT_ORDER + ["energy_source", "qc_flag"]
out = out[cols].sort_values("fdc_id").reset_index(drop=True)
write_parquet(out, OUT_NUTRITION / "usda_food_nutrient_per100g.parquet")
print("energy_source:", out.energy_source.value_counts(dropna=False).to_dict())
print("qc_flag:", out.qc_flag.value_counts().to_dict())
print("non-null share:\n", out[NUTRIENT_OUTPUT_ORDER].notna().mean().round(3).to_string())

# --------------------------------------------------------------- portions ----
mu = pd.read_csv(RAW_FDC / "measure_unit.csv").set_index("id").name
fp = pd.read_csv(RAW_FDC / "food_portion.csv",
                 usecols=["fdc_id", "seq_num", "amount", "measure_unit_id", "portion_description", "modifier", "gram_weight"])
fp = fp[fp.fdc_id.isin(core_ids) & fp.gram_weight.gt(0)].copy()
fp["fdc_id"] = fp.fdc_id.astype("int64")
fp["unit_name"] = fp.measure_unit_id.map(mu)

SIZES = ["extra large", "extra small", "jumbo", "large", "medium", "small", "regular", "miniature"]
COUNT_NOUNS = ["slice", "piece", "clove", "stalk", "head", "bunch", "sprig", "ear", "fillet", "breast", "steak", "wedge",
               "stick", "link", "can", "jar", "package", "packet", "bag", "patty", "roll", "pod", "bulb", "cube", "ring",
               "spear", "floret", "half", "thigh", "leg", "drumstick", "wing", "loaf", "bottle", "pat", "sheet", "strip",
               "chop", "leaf", "bar", "container", "sandwich", "cookie", "tortilla"]
WHOLE_WORDS = {"each", "egg", "fruit", "whole", "unit", "item", "serving"}
VOLUME = [("fl_oz", r"^(fl\.? ?oz|fluid ounces?)\b"), ("cup", r"^cups?\b"), ("tbsp", r"^(tbsp|tbs|tablespoons?)\b"),
          ("tsp", r"^(tsp|teaspoons?)\b"), ("ml", r"^(ml|milliliters?)\b"), ("l", r"^(liters?|litres?)\b")]
MASS = re.compile(r"^(oz|ounces?|lb|lbs|pounds?|g|grams?|kg)\b")
NUM = re.compile(r"^(\d+(?:\.\d+)?(?:\s+\d+/\d+)?|\d+/\d+)\s+(.*)$")


def _to_float(s: str) -> float:
    total = 0.0
    for tok in s.split():
        if "/" in tok:
            a, b = tok.split("/")
            total += float(a) / float(b)
        else:
            total += float(tok)
    return total


def parse_label(text: str, qty):
    """-> (qty, unit, size, prep) or None when the label is not a usable household unit."""
    t = text.lower().strip()
    if not t or "quantity not specified" in t:
        return None
    m = NUM.match(t)
    if m:
        qty, t = _to_float(m.group(1)), m.group(2)
    if qty is None or not np.isfinite(qty) or qty <= 0:
        return None
    t = t.replace("tbsp.", "tbsp").strip()
    unit = None
    for name, pat in VOLUME:
        mm = re.match(pat, t)
        if mm:
            unit, rest = name, t[mm.end():]
            break
    if unit is None and MASS.match(t):
        return None  # mass units are physical constants, not worth storing
    size = None
    if unit is None:
        for s in SIZES:
            if t.startswith(s):
                unit, size, rest = "each", s.replace("extra ", "x"), t[len(s):]
                break
    if unit is None:
        first = re.match(r"[a-z]+", t)
        w = first.group(0) if first else ""
        w1 = w[:-1] if w.endswith("s") and len(w) > 3 else w
        if w in WHOLE_WORDS or w1 in WHOLE_WORDS:
            unit, rest = "each", t[len(w):]
        elif w1 in COUNT_NOUNS:
            unit, rest = w1, t[len(w):]
    if unit is None:
        return None
    rest = rest.strip(" ,;")
    if size is None:
        for s in SIZES:
            if re.search(rf"\b{s}\b", rest):
                size = s.replace("extra ", "x")
                break
    prep = re.sub(r"\([^)]*\)", "", rest).strip(" ,;")
    prep = re.sub(r"\b(" + "|".join(SIZES) + r")\b", "", prep).strip(" ,;")
    return qty, unit, size, (prep or None)


rows = []
for r in fp.itertuples(index=False):
    # label source differs by FDC data type
    if isinstance(r.portion_description, str) and r.portion_description.strip():
        label, qty = r.portion_description, None             # FNDDS: "1 cup, cooked"
    elif isinstance(r.modifier, str) and r.modifier.strip():
        label, qty = r.modifier, r.amount                    # SR Legacy: "cup, chopped"
    elif isinstance(r.unit_name, str) and r.unit_name not in ("undetermined", ""):
        label = r.unit_name + (", " + r.modifier if isinstance(r.modifier, str) else "")  # Foundation
        qty = r.amount
    else:
        continue
    p = parse_label(label, qty)
    if p is None:
        continue
    q, unit, size, prep = p
    rows.append((r.fdc_id, int(r.seq_num) if pd.notna(r.seq_num) else 99, unit, size, prep, q, r.gram_weight,
                 r.gram_weight / q, label.strip()))
port = pd.DataFrame(rows, columns=["fdc_id", "seq_num", "unit", "size", "prep", "amount", "gram_weight",
                                   "grams_per_unit", "label_raw"])
port = port[port.grams_per_unit.between(0.05, 5000)]
port = port.drop_duplicates(["fdc_id", "unit", "size", "prep", "grams_per_unit"]).sort_values(
    ["fdc_id", "seq_num", "unit"]).reset_index(drop=True)
for c in ("amount", "gram_weight", "grams_per_unit"):
    port[c] = port[c].astype("float32").round(3)
port["size"] = port["size"].astype("string")
port["prep"] = port["prep"].astype("string")
write_parquet(port, OUT_NUTRITION / "usda_food_portion_weight.parquet")
print("unit counts:", port.unit.value_counts().head(15).to_dict())
print("foods with >=1 usable portion:", port.fdc_id.nunique(), "of", len(food))
