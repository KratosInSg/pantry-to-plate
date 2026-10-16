# Frozen benchmark v2 — integrity rebaseline

This directory contains **byte-for-byte copies** of the original committed v1 scenario and split files, under v2 names. Both v1 files were already inconsistent with their FROZEN.json SHA-256 hashes in the original commit `29d1bff`. The original files and their mismatching manifest remain untouched for audit.

This is an **integrity rebaseline**, not a newly sampled benchmark. It does **not** create independent scenarios or undo prior validation-based weight tuning. All existing 240 scenarios and 120/120 validation/test memberships remain identical. No held-out test results should be used to tune the model.

The v2 FROZEN.json records the actual SHA-256 of these committed bytes. The loader refuses any subsequent changes. For a genuinely new independent benchmark, generate new scenarios with a new seed and a new version, freeze them before tuning, and document that process separately.
