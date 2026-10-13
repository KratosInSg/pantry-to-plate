"""Shared planning plumbing: the ``Planner`` interface and the per-scenario preparation every planner reuses.

Why this exists
---------------
The evaluation compares *methods* (random, greedy, the weekly optimiser, its ablations). For that comparison to be fair, they must all see
exactly the same inputs: the same hard-rule filter, the same preference scores, the same staples assumption. Doing
that preparation once, here, means a method can only differ from another in its **decision logic**, which is the thing
being measured.

Interface
---------
A planner is anything with a ``name`` and ``plan(scenario) -> WeekPlan``. It is constructed with a
:class:`PlanningContext` (catalogue + knowledge store + derived constants), so planners hold no global state.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import numpy as np

from domain.models import Scenario, UserProfile, WeekPlan
from knowledge.recipes import RecipeCatalog, get_default_catalog
from knowledge.store import KnowledgeStore, get_default_store
from optimizer.hard_rules import feasible_mask
from preference.scorer import PreferenceWeights, DEFAULT_WEIGHTS, score_recipes


@dataclass(frozen=True)
class PlanningContext:
    """Everything a planner needs that does not depend on the scenario."""

    catalog: RecipeCatalog
    store: KnowledgeStore
    ignore_ids: frozenset[int]          # assumed-available staples: never count as pantry or groceries
    preference_weights: PreferenceWeights = DEFAULT_WEIGHTS


def make_context(catalog: RecipeCatalog | None = None, store: KnowledgeStore | None = None,
                 preference_weights: PreferenceWeights = DEFAULT_WEIGHTS) -> PlanningContext:
    """Build a context from the default dataset (or the given catalogue/store)."""
    store = store or get_default_store()
    catalog = catalog or get_default_catalog()
    tbl = store.all_ingredients()
    ignore = frozenset(int(i) for i in tbl.loc[tbl.is_assumed_available, "ingredient_id"])
    return PlanningContext(catalog=catalog, store=store, ignore_ids=ignore, preference_weights=preference_weights)


@dataclass(frozen=True)
class Prepared:
    """A scenario after the steps that are identical for every method."""

    scenario: Scenario
    feasible: np.ndarray                # bool over the catalogue: passes every hard rule
    preference: np.ndarray              # float in [0, 1] over the catalogue

    @property
    def feasible_indices(self) -> np.ndarray:
        return np.flatnonzero(self.feasible)


def prepare(scenario: Scenario, ctx: PlanningContext) -> Prepared:
    """Apply the hard rules and score preferences for this scenario's user."""
    profile: UserProfile = scenario.profile
    return Prepared(
        scenario=scenario,
        feasible=feasible_mask(ctx.catalog, profile),
        preference=score_recipes(ctx.catalog, profile, ignore_for_likes=ctx.ignore_ids,
                                 weights=ctx.preference_weights))


class Planner(Protocol):
    """Anything that can turn a scenario into a week plan."""

    name: str

    def plan(self, scenario: Scenario) -> WeekPlan: ...


def plan_from_indices(planner: str, ctx: PlanningContext, indices: list[int], horizon: int, status: str | None = None,
                      **diagnostics) -> WeekPlan:
    """Wrap chosen catalogue row indices into a ``WeekPlan`` (converting to Food.com recipe ids)."""
    ids = [ctx.catalog.recipe_id_of(i) for i in indices]
    st = status or ("ok" if len(ids) >= horizon else ("partial" if ids else "no_candidates"))
    return WeekPlan(planner=planner, recipe_ids=ids, status=st, diagnostics=dict(diagnostics))
