"""Shared pytest fixtures.

The dataset-backed fixtures are session-scoped: loading Parquet and building the fuzzy index happens once per test
run, not once per test. Tests that need the dataset are integration tests by nature; they use the real
``data/canonical`` build so a regression in the build or in a reference CSV is caught here too.
"""
from __future__ import annotations

import subprocess
import sys
from datetime import date

import pytest

from knowledge.recipes import RecipeCatalog, get_default_catalog
from knowledge.store import KnowledgeStore, get_default_store
from nlp.pantry_parser import PantryParser
from nlp.resolver import IngredientResolver
from optimizer.planning import PlanningContext, make_context

# A fixed "today" (a Monday) so weekday cues like "use by friday" are reproducible.
FIXED_TODAY = date(2026, 10, 12)


@pytest.fixture(scope="session")
def store() -> KnowledgeStore:
    return get_default_store()


@pytest.fixture(scope="session")
def catalog() -> RecipeCatalog:
    return get_default_catalog()


@pytest.fixture(scope="session")
def ctx(catalog: RecipeCatalog, store: KnowledgeStore) -> PlanningContext:
    """Planning context (catalogue + store + staples) shared by the optimiser / evaluation tests."""
    return make_context(catalog, store)


@pytest.fixture(scope="session")
def resolver(store: KnowledgeStore) -> IngredientResolver:
    return IngredientResolver(store)


@pytest.fixture(scope="session")
def parser(store: KnowledgeStore, resolver: IngredientResolver) -> PantryParser:
    return PantryParser(store=store, resolver=resolver)


@pytest.fixture()
def today() -> date:
    return FIXED_TODAY


@pytest.fixture(scope="session")
def optimised_week(ctx: PlanningContext, catalog: RecipeCatalog, store: KnowledgeStore):
    """``(scenario, plan)``: one real optimiser plan, solved once per run, shared by the explainer tests."""
    from evaluation.scenarios import generate_scenario
    from optimizer.candidates import ShortlistConfig
    from optimizer.weekly import WeeklyPlanner

    scenario = generate_scenario("expiry_heavy", 20261012, catalog, store)
    planner = WeeklyPlanner(ctx, shortlist_config=ShortlistConfig(size=50), time_limit_s=20.0, mip_rel_gap=1e-3)
    return scenario, planner.plan(scenario)


@pytest.fixture(scope="session")
def cpsat_available() -> bool:
    """Whether OR-Tools CP-SAT can be loaded here. Probed in a child process, exactly as the backend runs it: in the
    test process pandas/pyarrow are already loaded and OR-Tools cannot share a process with them (see
    ``optimizer/cpsat_worker.py``), so an in-process import would always look "unavailable"."""
    probe = subprocess.run([sys.executable, "-I", "-c", "from ortools.sat.python import cp_model"],
                           capture_output=True)
    return probe.returncode == 0
