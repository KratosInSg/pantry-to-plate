"""Run the whole data build, in order, from the raw downloads to data/canonical/.

    python src/knowledge/build/run_all.py

Raw inputs (read-only):  data/FoodData_Central_csv_2026-04-30/, data/recipes/, data/foodkeeper/
Curated inputs:          data/canonical/reference/*.csv   (synonyms, USDA overrides, FoodKeeper overrides, ...)
Output:                  data/canonical/                  (see data/canonical/README.md)
"""
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
STEPS = ["01_usda_nutrition.py", "02_canonical_ingredients.py", "03_recipes.py", "04_estimate_grams.py",
         "05_shelf_life.py", "06_finalize.py", "07_write_readme.py"]

t_all = time.time()
for step in STEPS:
    path = HERE / step
    if not path.exists():
        print(f"[skip] {step} (not found)")
        continue
    t = time.time()
    print(f"\n===== {step} =====", flush=True)
    r = subprocess.run([sys.executable, str(path)], cwd=HERE.parents[2])
    if r.returncode != 0:
        raise SystemExit(f"{step} failed with exit code {r.returncode}")
    print(f"[{step}] done in {time.time() - t:.0f}s", flush=True)
print(f"\nall steps finished in {time.time() - t_all:.0f}s")
