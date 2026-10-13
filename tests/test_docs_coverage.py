"""Enforces the documentation rule from CLAUDE.md: one doc per source file and per test file.

    src/nlp/quantities.py        ->  md docs/modules/nlp/quantities.md
    tests/nlp/test_quantities.py ->  md docs/modules/tests/nlp/test_quantities.md

These tests do not check that the docs are *good* (that is what review is for) - they make the rule impossible to
forget: a new file without a doc, an unlisted doc, or a doc without a change log fails the suite.
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODULES_DOCS = ROOT / "md docs" / "modules"
INDEX = MODULES_DOCS / "README.md"


def _python_files(base: Path):
    for py in sorted(base.rglob("*.py")):
        if "__pycache__" in py.parts or py.name == "__init__.py":
            continue            # package __init__ files are covered by the package README
        yield py


def _expected_doc(py: Path) -> Path:
    rel = py.relative_to(ROOT)
    if rel.parts[0] == "src":
        return MODULES_DOCS.joinpath(*rel.parts[1:]).with_suffix(".md")
    return MODULES_DOCS.joinpath(*rel.parts).with_suffix(".md")        # tests/... -> modules/tests/...


def test_every_source_and_test_file_has_a_doc():
    missing = [str(py.relative_to(ROOT)) for base in ("src", "tests") for py in _python_files(ROOT / base)
               if not _expected_doc(py).exists()]
    assert not missing, "files without a doc under md docs/modules/ (create one in the same change):\n  " \
        + "\n  ".join(missing)


def test_every_doc_is_listed_in_the_index():
    index = INDEX.read_text(encoding="utf-8")
    unlisted = [str(d.relative_to(MODULES_DOCS).as_posix()) for d in sorted(MODULES_DOCS.rglob("*.md"))
                if d != INDEX and d.name != "README.md" and d.relative_to(MODULES_DOCS).as_posix() not in index]
    assert not unlisted, "docs missing from md docs/modules/README.md:\n  " + "\n  ".join(unlisted)


def test_every_doc_has_a_change_log():
    missing = [str(d.relative_to(MODULES_DOCS).as_posix()) for d in sorted(MODULES_DOCS.rglob("*.md"))
               if "## Change log" not in d.read_text(encoding="utf-8")]
    assert not missing, "docs without a '## Change log' section:\n  " + "\n  ".join(missing)


def test_no_orphan_docs():
    """A doc whose source file no longer exists should be deleted (or the file was renamed and the doc forgotten)."""
    orphans = []
    for doc in sorted(MODULES_DOCS.rglob("*.md")):
        if doc.name == "README.md":
            continue
        rel = doc.relative_to(MODULES_DOCS).with_suffix(".py")
        candidate_src = ROOT / "src" / rel
        candidate_test = ROOT / rel                      # docs/modules/tests/... -> tests/...
        if not candidate_src.exists() and not candidate_test.exists():
            orphans.append(doc.relative_to(MODULES_DOCS).as_posix())
    assert not orphans, "docs with no matching source file:\n  " + "\n  ".join(orphans)
