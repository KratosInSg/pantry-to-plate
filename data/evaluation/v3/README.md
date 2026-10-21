# Frozen benchmark v3: 120 new test-only kitchens (2026-10-21)

**What.** 120 synthetic kitchens (15 per family) from the *same* generator as v1/v2 (`src/evaluation/scenarios.py`,
generator v1) with **new seeds** (20261100–20261114 per family; v1/v2 used 20261012–20261041), so none of them is a v2
kitchen. Every scenario is in the **test** split; there is no validation split.

**Why.** The v2 test split was used once on 2026-10-16. Methods chosen after that (the expiry safety margin, chosen on
the v2 *validation* split) need data nobody has looked at to be tested fairly. v3 is that data.

**Also here.** `pantry_messages_m1.jsonl` + `MESSAGES_FROZEN.json`: each v3 kitchen written as a pantry message with an
answer key (`src/evaluation/pantry_messages.py`), the synthetic set for the ingredient-NLP measure. Its labels come from
the generator, not from people.

**Command.**

```bash
python src/evaluation/build_benchmark.py --out data/evaluation/v3 --version v3 --n-per-family 15 --seed 20261100 --validation-share 0
python src/evaluation/pantry_messages.py --eval-dir data/evaluation/v3
```

`FROZEN.json` also records the SHA-256 of the dataset `MANIFEST.json` at generation time (it differs from v2's: the
dataset has been rebuilt since 2026-10-12). Rules: never edit by hand, never tune on it; a new comparison needs a new
version.
