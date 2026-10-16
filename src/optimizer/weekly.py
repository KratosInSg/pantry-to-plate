"""The weekly optimiser: choose 7 dinners that jointly minimise waste, groceries and penalties, subject to hard rules.

This is the only place in the system that decides the plan (CLAUDE.md non-negotiable). Everything upstream - the NLP
parse, hard-rule filter, preference scores, shortlist - only prepares inputs; everything downstream - the explainer - only
reads the cost terms returned here.

The mathematical model
----------------------
Indices: recipe ``k`` in the shortlist, day ``d`` in ``0..D-1``, ingredient ``i``.

Decision variables
    x[k,d]  in {0,1}   recipe k is cooked on day d
    u[i,d]  >= 0       grams of *pantry* stock of i used on day d (only on days the stock is still usable)
    g[i]    >= 0       grams of i that must be *bought*
    y[i]    in {0,1}   i is on the shopping list
    lo[d], hi[d], pr[d] >= 0   kcal below/above the dinner band on day d, protein shortfall on day d
    ex[c]   >= 0       how many meals beyond the cap share variety group c (cuisine / protein type)

Constraints
    sum_k x[k,d] = 1                         one dinner per day
    sum_d x[k,d] <= 1                        no repeated recipe
    u[i,d] <= sum_k grams[k,i] * x[k,d]     cannot use more stock than the meal needs
    sum_d u[i,d] <= stock[i]                 cannot use more than we have
    u[i,d] = 0 for d > last_use_day[i]       stock past its deadline is not planned with (known dates: HARD)
    g[i] >= sum_{k,d} grams[k,i] x[k,d] - sum_d u[i,d]      what the pantry cannot cover is bought
    g[i] <= M[i] * y[i]                      shopping list membership
    kcal[d] + lo[d] >= band_low ;  kcal[d] - hi[d] <= band_high ;  protein[d] + pr[d] >= protein_min
    ex[c] >= (meals in group c) - cap[c]

Objective (all terms in comparable "cost units", weights in :class:`OptimizerWeights`)
    waste:       w_waste * sum_i factor[i] * (stock[i] - sum_d u[i,d]) / 100      (only stock expiring inside the week)
    groceries:   w_item * sum_i y[i]  +  w_gram * sum_i g[i] / 100
    nutrition:   w_kcal * sum_d (lo[d] + hi[d]) / kcal_target  +  w_prot * sum_d pr[d] / protein_min
    preference:  w_pref * sum x[k,d] * (1 - preference[k])
    cook time:   w_time * sum x[k,d] * weekday[d] * max(0, minutes[k] - limit) / limit
    variety:     w_var * sum_c ex[c]

``factor[i]`` raises the cost of wasting stock that expires sooner and, for *estimated* deadlines, scales it by the
estimate's confidence (a guessed expiry is chased less hard than a stated one).

Decisions worth knowing
-----------------------
* **Stock is usable only up to its deadline for both known and estimated dates.** The difference between the two is
  the cost weight above, not feasibility - planning to eat past an estimated date is not something we should schedule.
* **Hard rules are not in the model.** They were applied before the shortlist; the solver never sees a violating recipe.
* **The shortlist bounds the model**, so solve time stays at seconds. It is pantry-aware, so urgent ingredients always
  have options.
* **Ablations are weights**, not code branches (``ABLATIONS``): switching a term off cannot accidentally change anything
  else, which is what makes ablation results attributable.
"""
from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass, replace

import numpy as np

from domain.models import PantryItem, Scenario, WeekPlan
from optimizer.backends import BACKENDS, SolveResult
from optimizer.candidates import ShortlistConfig, shortlist, urgency_weight
from optimizer.inventory import deadlines_from_pantry
from optimizer.linear_model import LinearModel
from optimizer.planning import PlanningContext, plan_from_indices, prepare

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class OptimizerWeights:
    """Cost weights. Hand-set defaults; tune on the *validation* scenarios only."""

    waste_per_100g: float = 1.0        # cost of 100 g of (urgency-weighted) expiring stock left unused
    grocery_item: float = 1.0          # cost of each distinct item that must be bought
    grocery_per_100g: float = 0.3      # cost of 100 g bought
    # per 1.0 of (daily kcal outside the band / dinner target), summed over days. Was 4.0; x2 adopted together with
    # preference x6 after confirmation on all 120 validation scenarios (md docs/evaluation.md "Weight sweep").
    kcal_deviation: float = 8.0
    protein_deviation: float = 4.0     # per 1.0 of (protein shortfall / minimum), summed over days. Was 2.0 (x2)
    # per meal, times (1 - preference score). Was 1.0, then 3.0; x6 adopted on 2026-10-13 after confirmation on all 120
    # VALIDATION scenarios against criteria fixed beforehand (``evaluation/weight_sweep.py``): liked-cuisine dinners
    # +15 pts, dinners in the calorie band +14 pts, for +2.8 extra grocery items a week.
    preference: float = 6.0
    weekday_time: float = 1.5          # per weekday meal, times fraction over the cooking-time limit
    variety: float = 0.7               # per meal beyond a variety cap
    cuisine_cap: int = 2               # at most this many meals of one cuisine before variety is penalised
    protein_type_cap: int = 4          # same for meat / poultry / fish / vegetarian
    urgency_weighting: bool = True     # ablation switch: False = every gram of expiring stock costs the same
    confidence_weighting: bool = True  # ablation switch: False = estimated expiry dates are trusted like known ones


DEFAULT_WEIGHTS = OptimizerWeights()

INF_KCAL = 1e6      # an effectively unbounded deviation variable (kcal / grams / meals)

# The objective's terms, in the order the explainer reports them. ``diagnostics["cost_<term>"]`` holds each one's
# contribution at the chosen plan; together they sum to ``diagnostics["objective"]`` (tested).
COST_TERMS = ("waste", "groceries", "nutrition", "preference", "cook_time", "variety")

# Ablations of our own system (docs/evaluation.md): switch one reasoning component off at a time.
ABLATIONS: dict[str, OptimizerWeights] = {
    "no_expiry": replace(DEFAULT_WEIGHTS, waste_per_100g=0.0),
    "no_nutrition": replace(DEFAULT_WEIGHTS, kcal_deviation=0.0, protein_deviation=0.0),
    "no_preference": replace(DEFAULT_WEIGHTS, preference=0.0),
}


@dataclass
class _Stock:
    """Aggregated pantry facts for one ingredient."""

    grams: float = 0.0
    last_use_day: int | None = None
    urgency_factor: float = 1.0       # >= 1
    confidence: float = 1.0           # 1 for known dates


def _aggregate_pantry(pantry: list[PantryItem], ignore: set[int], horizon: int, urgent_within: int) -> dict[int, _Stock]:
    """Merge duplicate stocks of an ingredient: grams add up, the earliest deadline applies, and the *lowest* confidence
    wins (a single guessed date makes the whole merged stock a guess)."""
    deadlines = deadlines_from_pantry(pantry)
    stock: dict[int, _Stock] = {}
    for item in pantry:
        if item.ingredient_id in ignore:
            continue
        first = item.ingredient_id not in stock
        s = stock.setdefault(item.ingredient_id, _Stock())
        s.grams += item.grams
        s.urgency_factor = max(s.urgency_factor, urgency_weight(item, urgent_within))
        confidence = 1.0 if item.expiry_known else item.expiry_confidence
        s.confidence = confidence if first else min(s.confidence, confidence)
    for iid, s in stock.items():
        d = deadlines.get(iid)
        s.last_use_day = d if (d is not None and d < horizon) else None     # deadlines beyond the week are no deadline
    return stock


class WeeklyPlanner:
    """Plans a week by solving the model above. ``name`` identifies the method in results."""

    def __init__(self, ctx: PlanningContext, weights: OptimizerWeights = DEFAULT_WEIGHTS, name: str = "optimiser",
                 shortlist_config: ShortlistConfig = ShortlistConfig(size=120), time_limit_s: float = 8.0,
                 mip_rel_gap: float = 0.02, backend: str = "highs") -> None:
        if backend not in BACKENDS:
            raise ValueError(f"unknown solver backend {backend!r}; expected one of {sorted(BACKENDS)}")
        self._ctx = ctx
        self.weights = weights
        self.name = name
        self.backend = backend
        self._solve = BACKENDS[backend]
        self._shortlist_cfg = shortlist_config
        self._time_limit = time_limit_s
        self._gap = mip_rel_gap

    # ---------------------------------------------------------------------------------------------- public API
    def plan(self, scenario: Scenario) -> WeekPlan:
        ctx = self._ctx
        prepared = prepare(scenario, ctx)
        horizon = scenario.horizon_days
        feasible = prepared.feasible_indices
        if len(feasible) == 0:
            logger.warning("%s: no recipe passes the hard rules for scenario %s", self.name, scenario.scenario_id)
            return plan_from_indices(self.name, ctx, [], horizon, status="no_candidates", n_feasible=0)
        if len(feasible) <= horizon:           # nothing to optimise: cook everything that is allowed
            logger.info("%s: only %d feasible recipe(s) for %d day(s) - nothing to optimise", self.name,
                        len(feasible), horizon)
            return plan_from_indices(self.name, ctx, feasible.tolist(), horizon, n_feasible=len(feasible))

        cand = shortlist(ctx.catalog, scenario.profile, scenario.pantry, prepared.feasible, prepared.preference,
                         ctx.ignore_ids, self._shortlist_cfg)
        model, handles = self._build(scenario, cand, prepared.preference)
        logger.debug("%s: shortlist %d of %d feasible; model %d vars (%d integer), %d constraints; backend %s",
                     self.name, len(cand), len(feasible), model.n_vars, model.n_integer, model.n_constraints,
                     self.backend)
        result = self._solve(model, self._time_limit, self._gap)
        if result.x is None:
            logger.warning("%s: solver returned no plan (status %s, %.1f s): %s", self.name, result.status,
                           result.seconds, result.message)
            return plan_from_indices(self.name, ctx, [], horizon, status=result.status, n_feasible=len(feasible),
                                     n_candidates=len(cand), solve_seconds=round(result.seconds, 2))

        chosen = [int(cand[k]) for k in self._extract(result, handles, horizon)]   # shortlist position -> catalogue row
        diag = self._diagnostics(result, handles, cand, len(feasible))
        logger.debug("%s: %s in %.2f s, objective %.3f (gap %s); %s", self.name, result.status, result.seconds,
                     diag["objective"], diag["mip_gap"], ", ".join(f"{t} {diag['cost_' + t]:.2f}" for t in COST_TERMS))
        return plan_from_indices(self.name, ctx, chosen, horizon, status=result.status, **diag)

    # ---------------------------------------------------------------------------------------------- model build
    def _build(self, scenario: Scenario, cand: np.ndarray, preference: np.ndarray):
        ctx, w = self._ctx, self.weights
        cat, profile = ctx.catalog, scenario.profile
        horizon = scenario.horizon_days
        ignore = set(ctx.ignore_ids)
        K = len(cand)
        stock = _aggregate_pantry(scenario.pantry, ignore, horizon, self._shortlist_cfg.urgent_within_days)

        # per-candidate ingredient demand (non-staples only)
        demand: dict[int, list[tuple[int, float]]] = defaultdict(list)       # ingredient -> [(k, grams)]
        for k, idx in enumerate(cand):
            ids, grams = cat.ingredients(int(idx))
            for iid, g in zip(ids.tolist(), grams.tolist()):
                if iid not in ignore and g > 0.5:
                    demand[iid].append((k, float(g)))

        lo, hi = profile.dinner_kcal_range
        target = profile.dinner_kcal_target
        kcal, protein = cat.kcal[cand], cat.protein_g[cand]
        minutes = cat.minutes[cand]
        limit = max(1, profile.max_weekday_minutes)
        over = np.maximum(0.0, (minutes - limit) / limit)
        m = LinearModel()
        # Which variables carry which cost term, as (variable, coefficient) pairs. The model only needs the summed
        # coefficient per variable, but the explainer needs "how much of the objective is groceries / nutrition / ...",
        # so each term is recorded as it is added and evaluated at the solution in ``_diagnostics``.
        terms: dict[str, list[tuple[int, float]]] = defaultdict(list)

        # --- recipe-per-day binaries, with their linear costs (preference + weekday cook time) -----------------
        x = np.empty((K, horizon), dtype=int)
        for k in range(K):
            for d in range(horizon):
                pref_cost = w.preference * (1.0 - float(preference[cand[k]]))
                time_cost = w.weekday_time * float(over[k]) if scenario.is_weekday(d) else 0.0
                x[k, d] = m.add_binary(pref_cost + time_cost, f"x[{k},{d}]")
                terms["preference"].append((int(x[k, d]), pref_cost))
                if time_cost:
                    terms["cook_time"].append((int(x[k, d]), time_cost))
        for d in range(horizon):
            m.add_constraint({int(x[k, d]): 1.0 for k in range(K)}, 1.0, 1.0)            # one dinner per day
        for k in range(K):
            m.add_constraint({int(x[k, d]): 1.0 for d in range(horizon)}, ub=1.0)         # no repeats

        # --- inventory flows ----------------------------------------------------------------------------------------
        constant_waste_cost = 0.0
        grocery_vars: dict[int, int] = {}
        buy_item_vars: dict[int, int] = {}
        use_vars: dict[int, list[int]] = {}
        for iid, uses in demand.items():
            total_row = {int(x[k, d]): g for k, g in uses for d in range(horizon)}        # all demand of iid
            big_m = float(sum(sorted((g for _, g in uses), reverse=True)[:horizon]))      # at most D meals per week
            g_var = m.add_var(0.0, big_m, False, w.grocery_per_100g / 100.0, f"buy[{iid}]")
            y_var = m.add_binary(w.grocery_item, f"item[{iid}]")
            terms["groceries"] += [(g_var, w.grocery_per_100g / 100.0), (y_var, w.grocery_item)]
            m.add_constraint({g_var: 1.0, y_var: -big_m}, ub=0.0)
            grocery_vars[iid], buy_item_vars[iid] = g_var, y_var

            s = stock.get(iid)
            if s is None or s.grams <= 0:
                m.add_constraint({g_var: 1.0, **{v: -c for v, c in total_row.items()}}, lb=0.0)   # g >= demand
                continue
            last = horizon - 1 if s.last_use_day is None else s.last_use_day
            unit_waste = 0.0
            if s.last_use_day is not None:            # only stock that can expire inside the week creates waste
                factor = s.urgency_factor if w.urgency_weighting else 1.0
                conf = s.confidence if w.confidence_weighting else 1.0
                unit_waste = w.waste_per_100g * factor * conf / 100.0
                constant_waste_cost += unit_waste * s.grams
            u_list = []
            for d in range(last + 1):
                u = m.add_var(0.0, s.grams, False, -unit_waste, f"use[{iid},{d}]")        # cost = -waste avoided
                u_list.append(u)
                terms["waste"].append((u, -unit_waste))
                # u[i,d] <= demand of i on day d
                row = {u: 1.0}
                for k, g in uses:
                    row[int(x[k, d])] = row.get(int(x[k, d]), 0.0) - g
                m.add_constraint(row, ub=0.0)
            use_vars[iid] = u_list
            m.add_constraint({u: 1.0 for u in u_list}, ub=s.grams)                        # cannot exceed the stock
            row = {g_var: 1.0}                                                             # g >= demand - sum(u)
            for v, c in total_row.items():
                row[v] = -c
            for u in u_list:
                row[u] = row.get(u, 0.0) + 1.0
            m.add_constraint(row, lb=0.0)

        # Expiring pantry ingredients absent from the candidate recipe pool still spoil.
        # They are constant across plans, so omitting them did not change recipe selection,
        # but it understated the reported MILP waste objective relative to GA replay.
        for iid, item in stock.items():
            if iid not in demand and item.last_use_day is not None:
                factor = item.urgency_factor if w.urgency_weighting else 1.0
                confidence = item.confidence if w.confidence_weighting else 1.0
                constant_waste_cost += w.waste_per_100g * factor * confidence * item.grams / 100.0

        # --- nutrition: dinner kcal band and protein minimum --------------------------------------------------------
        dev_vars: list[tuple[int, int, int]] = []
        for d in range(horizon):
            protein_cost = (w.protein_deviation / profile.min_protein_g_per_dinner
                            if profile.min_protein_g_per_dinner > 0 else 0.0)
            lo_v = m.add_var(0.0, INF_KCAL, False, w.kcal_deviation / target, f"kcal_lo[{d}]")
            hi_v = m.add_var(0.0, INF_KCAL, False, w.kcal_deviation / target, f"kcal_hi[{d}]")
            pr_v = m.add_var(0.0, INF_KCAL, False, protein_cost, f"prot[{d}]")
            terms["nutrition"] += [(lo_v, w.kcal_deviation / target), (hi_v, w.kcal_deviation / target),
                                   (pr_v, protein_cost)]
            kcal_row = {int(x[k, d]): float(kcal[k]) for k in range(K)}
            m.add_constraint({**kcal_row, lo_v: 1.0}, lb=lo)                               # kcal + lo >= band low
            m.add_constraint({**kcal_row, hi_v: -1.0}, ub=hi)                              # kcal - hi <= band high
            if profile.min_protein_g_per_dinner > 0:
                m.add_constraint({**{int(x[k, d]): float(protein[k]) for k in range(K)}, pr_v: 1.0},
                                 lb=profile.min_protein_g_per_dinner)
            dev_vars.append((lo_v, hi_v, pr_v))

        # --- variety: cap how often one cuisine / protein type repeats ----------------------------------------------
        groups: dict[str, list[int]] = defaultdict(list)
        for k, idx in enumerate(cand):
            c = cat.cuisine[int(idx)]
            if c is not None:
                groups[f"cuisine:{c}"].append(k)
            groups[f"type:{protein_type(cat, int(idx))}"].append(k)
        excess_vars: list[int] = []
        for key, members in groups.items():
            cap = w.cuisine_cap if key.startswith("cuisine:") else w.protein_type_cap
            if len(members) <= cap:
                continue
            ex = m.add_var(0.0, INF_KCAL, False, w.variety, f"excess[{key}]")
            terms["variety"].append((ex, w.variety))
            row = {int(x[k, d]): 1.0 for k in members for d in range(horizon)}
            row[ex] = -1.0
            m.add_constraint(row, ub=float(cap))                                           # meals - excess <= cap
            excess_vars.append(ex)

        handles = {"x": x, "grocery": grocery_vars, "items": buy_item_vars, "use": use_vars, "dev": dev_vars,
                   "excess": excess_vars, "stock": stock, "constant_waste_cost": constant_waste_cost, "K": K,
                   "terms": dict(terms)}
        return m, handles

    # ---------------------------------------------------------------------------------------------- results
    @staticmethod
    def _extract(result: SolveResult, h: dict, horizon: int) -> list[int]:
        """Position *in the shortlist* of the recipe chosen on each day (map through ``cand`` for catalogue rows)."""
        x = h["x"]
        return [int(np.argmax(result.x[x[:, d]])) for d in range(horizon)]

    def _diagnostics(self, result: SolveResult, h: dict, cand: np.ndarray, n_feasible: int) -> dict:
        """Cost terms as the *model* sees them (the explainer's source); the evaluation re-measures them by replay."""
        x = result.x
        stock: dict[int, _Stock] = h["stock"]
        waste_g = sum(s.grams - sum(x[u] for u in h["use"].get(iid, [])) for iid, s in stock.items()
                      if s.last_use_day is not None)
        grocery_g = sum(float(x[v]) for v in h["grocery"].values())
        items = sum(1 for v in h["items"].values() if x[v] > 0.5)
        kcal_dev = sum(float(x[lo] + x[hi]) for lo, hi, _ in h["dev"])
        prot_dev = sum(float(x[pr]) for _, _, pr in h["dev"])
        # Each cost term's share of the objective at this solution. They are non-negative and sum to ``objective``;
        # the waste term carries the constant (stock that can expire is charged in full, then credited when used).
        costs = {name: sum(c * float(x[v]) for v, c in pairs) for name, pairs in h["terms"].items()}
        costs["waste"] = costs.get("waste", 0.0) + h["constant_waste_cost"]
        term_costs = {f"cost_{name}": round(costs.get(name, 0.0), 4) for name in COST_TERMS}
        return {
            "n_feasible": n_feasible, "n_candidates": len(cand), "backend": self.backend,
            "solve_seconds": round(result.seconds, 2), **term_costs,
            "objective": round(result.objective + h["constant_waste_cost"], 3),
            "mip_gap": -1.0 if result.mip_gap is None else round(float(result.mip_gap), 5),
            "model_waste_g": round(float(waste_g), 1), "model_grocery_items": int(items),
            "model_grocery_g": round(float(grocery_g), 1), "model_kcal_dev": round(kcal_dev, 1),
            "model_protein_dev_g": round(prot_dev, 1), "weights": str(self.weights),
        }


def protein_type(cat, idx: int) -> str:
    """Coarse protein category of recipe row ``idx`` (poultry / meat / seafood / vegetarian): what the variety
    cap counts, and what the evaluation uses to measure "the same protein every night"."""
    if cat.flag("contains_poultry")[idx]:
        return "poultry"
    if cat.flag("contains_meat")[idx]:
        return "meat"
    if cat.flag("contains_fish")[idx] or cat.flag("contains_shellfish")[idx]:
        return "seafood"
    return "vegetarian"


CPSAT_SUFFIX = "_cpsat"


def make_planner(name: str, ctx: PlanningContext, **kwargs) -> WeeklyPlanner:
    """Factory used by the benchmark runner: ``optimiser`` or ``opt_<ablation>`` (see ``ABLATIONS``).

    A ``_cpsat`` suffix (``optimiser_cpsat``, ``opt_no_expiry_cpsat``) selects the CP-SAT backend; the unsuffixed name
    uses HiGHS. The suffix stays in ``plan.method`` so a results table can never mix the two up.
    """
    if name.endswith(CPSAT_SUFFIX):
        kwargs.setdefault("backend", "cpsat")
    base = name[:-len(CPSAT_SUFFIX)] if name.endswith(CPSAT_SUFFIX) else name
    if base == "optimiser":
        return WeeklyPlanner(ctx, DEFAULT_WEIGHTS, name, **kwargs)
    if base.startswith("opt_") and base[4:] in ABLATIONS:
        return WeeklyPlanner(ctx, ABLATIONS[base[4:]], name, **kwargs)
    raise ValueError(f"unknown optimiser variant {name!r}; expected 'optimiser' or one of "
                     f"{['opt_' + a for a in ABLATIONS]}, optionally with the '{CPSAT_SUFFIX}' suffix")
