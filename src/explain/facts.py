"""Facts about a plan: everything the explainer is allowed to say, as typed, immutable data.

Where it sits
-------------
``optimizer`` decides the week; this module *reads* the result and extracts the facts that can honestly be stated about
it. ``render.py`` turns facts into sentences and ``paraphrase.py`` may reword those sentences with an LLM. Nothing in
``explain`` decides, ranks or changes a plan (CLAUDE.md: "Explanations must trace back to an actual solver cost term
or fired rule - never a rationalisation").

Where every fact comes from
---------------------------
=====================  =====================================================================================
fact                   source
=====================  =====================================================================================
pantry used / bought   ``optimizer.substitutions.replay_with_substitutions``: the inventory replay the evaluation
                       uses (``optimizer.inventory.account_inventory``) plus the substitution rules that fired - the
                       same call the app's grocery box uses, so a number here can never disagree with it
substitutions          the fired rule itself (``optimizer.substitutions.Substitution``): rule key, grams, substitutes
unused expiring stock  the same replay
kcal / protein / time  the recipe's computed nutrition and the user's own targets (``UserProfile``)
preference reasons     the scorer's own components: liked / disliked cuisine and ingredients, and - when the
                       rating-history term raised this dinner's score - the liked dinners it is closest to
                       (``preference.history.nearest_rated``, the same similarity the term ranks by)
rules                  ``optimizer.hard_rules.violation_masks``: how many dinners each active rule removed
cost terms             ``WeekPlan.diagnostics["cost_<term>"]`` written by the weekly optimiser, whose sum is the
                       objective it minimised. Absent for baselines, which have no cost terms to cite
=====================  =====================================================================================

What it deliberately does *not* do
----------------------------------
* It never explains why a *rejected* recipe lost: the solver does not record that, and inventing it would be exactly
  the rationalisation the project forbids.
* It does not claim a plan is "healthy": it states distance to the user's own kcal band and protein minimum.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from domain.models import Scenario, WeekPlan
from optimizer.hard_rules import count_violations, violation_masks
from optimizer.inventory import visible_deadlines
from optimizer.planning import PlanningContext
from optimizer.substitutions import replay_with_substitutions
from optimizer.weekly import COST_TERMS
from preference.history import nearest_rated
from preference.scorer import history_term

WEEKDAY_NAMES = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")

# A leftover or purchase smaller than this is not worth a sentence of its own. It is still counted in the totals.
MIN_MENTION_G = 1.0

KCAL_IN_RANGE = "in_range"
KCAL_BELOW = "below"
KCAL_ABOVE = "above"

# A gap this small (kcal or grams) is float noise, not a miss: catalogue nutrition is float32 and the user's band is
# computed from percentages. Anything larger is reported, even if it is only 0.3 kcal, because the text prints it.
GAP_TOLERANCE = 0.05


@dataclass(frozen=True, slots=True)
class PantryUse:
    """Pantry stock one dinner consumes."""

    name: str
    grams: float
    last_use_day: int | None     # deadline inside the plan (inclusive); None = none inside the horizon
    deadline_known: bool         # True: the user stated it. False: we estimated it from typical shelf life
    said_urgent: bool            # the user's own words flagged it ("going bad")


@dataclass(frozen=True, slots=True)
class GroceryNeed:
    """Something that has to be bought: what the pantry could not supply."""

    name: str
    grams: float


@dataclass(frozen=True, slots=True)
class SubstitutionFact:
    """A substitution rule that fired for one dinner: the replaced food is not bought, the substitutes are used."""

    rule_key: str                # ``optimizer.substitutions.SUBSTITUTION_RULES`` key, e.g. "buttermilk_milk_lemon"
    replaced: str                # canonical name of the food not bought
    replaced_g: float
    uses: tuple[tuple[str, float], ...]   # (substitute name, grams from the pantry; 0 for an assumed staple)
    note: str                    # the rule's practical caveat ("" if none)


@dataclass(frozen=True, slots=True)
class Leftover:
    """Pantry stock whose deadline falls inside the plan but that no dinner uses: it will be wasted."""

    name: str
    grams: float
    last_use_day: int
    deadline_known: bool


@dataclass(frozen=True, slots=True)
class Stranded:
    """Pantry stock that a dinner wanted *after* its deadline, so that dinner buys the ingredient again.

    The replay never schedules cooking with expired stock; this is the visible cost of that: you own the food, it will
    not be usable by the day a dinner needs it, and the plan buys it anyway.
    """

    name: str
    grams: float                 # the stock the user has
    last_use_day: int            # its deadline
    deadline_known: bool


@dataclass(frozen=True, slots=True)
class AssumedQuantity:
    """Pantry stock whose amount is our estimate, not something the user told us."""

    name: str
    grams: float


@dataclass(frozen=True, slots=True)
class RuleFact:
    """One active hard rule and how many dinners in the catalogue it removed (rules overlap)."""

    name: str                    # e.g. "diet:vegan", "allergen:peanut", "pork", "excluded", "time"
    n_excluded: int


@dataclass(frozen=True, slots=True)
class DayFacts:
    """Everything stated about one planned dinner."""

    day: int
    weekday: str
    recipe_id: int
    name: str
    minutes: int
    cuisine: str | None
    kcal: float
    protein_g: float
    kcal_status: str             # KCAL_IN_RANGE | KCAL_BELOW | KCAL_ABOVE
    kcal_gap: float              # kcal outside the user's band (0 when in range)
    protein_gap_g: float         # shortfall against the user's minimum (0 when met)
    is_weekday: bool
    minutes_over: int            # minutes beyond the soft weekday limit (0 when within it or at the weekend)
    pantry_uses: tuple[PantryUse, ...]
    groceries: tuple[GroceryNeed, ...]
    liked_cuisine: bool
    disliked_cuisine: bool
    liked_ingredients: tuple[str, ...]
    disliked_ingredients: tuple[str, ...]
    substitutions: tuple[SubstitutionFact, ...] = ()
    similar_rated: tuple[str, ...] = ()   # liked rated dinners this one is close to (only when that raised its score)


@dataclass(frozen=True, slots=True)
class SolverFacts:
    """What the weekly optimiser reported about how it reached the plan."""

    status: str                  # optimal | feasible
    backend: str | None
    objective: float
    mip_gap: float | None        # proven relative gap to the best possible plan; None when unknown
    terms: dict[str, float]      # COST_TERMS name -> its contribution to ``objective`` (non-negative)


@dataclass(frozen=True, slots=True)
class PlanFacts:
    """Facts about a whole plan. Built once by :func:`build_facts`; read by ``render`` / ``paraphrase``."""

    planner: str
    status: str
    horizon: int
    start_weekday: int
    complete: bool               # every day of the horizon has a dinner
    # the user's own targets (for "inside your range" wording)
    kcal_low: float
    kcal_high: float
    protein_min_g: float
    weekday_limit_min: int
    # per day
    days: tuple[DayFacts, ...]
    # week totals (replay)
    has_pantry: bool
    pantry_consumed_g: float
    expiring_stock_g: float      # starting stock with a deadline inside the plan: the only stock that can be wasted
    waste_g: float
    leftovers: tuple[Leftover, ...]
    stranded: tuple[Stranded, ...]
    groceries: tuple[GroceryNeed, ...]
    n_grocery_items: int
    # rules
    n_catalogue: int
    n_allowed: int
    rules: tuple[RuleFact, ...]
    violations: int              # (meal, rule) violations among the planned dinners: must be 0
    # caveats about the input
    estimated_deadline_items: tuple[str, ...]
    assumed_quantities: tuple[AssumedQuantity, ...]
    # solver
    solver: SolverFacts | None

    # ---- convenience --------------------------------------------------------------------------------------
    def weekday(self, day: int) -> str:
        return WEEKDAY_NAMES[(self.start_weekday + day) % 7]

    @property
    def n_dinners(self) -> int:
        return len(self.days)

    @property
    def n_kcal_in_range(self) -> int:
        return sum(1 for d in self.days if d.kcal_status == KCAL_IN_RANGE)

    @property
    def n_protein_ok(self) -> int:
        return sum(1 for d in self.days if d.protein_gap_g <= 0)


def build_facts(scenario: Scenario, plan: WeekPlan, ctx: PlanningContext) -> PlanFacts:
    """Extract every statable fact about ``plan`` for ``scenario``.

    Pure and deterministic: the same inputs give the same facts. Works for any planner's plan (random, greedy,
    optimiser); ``solver`` is ``None`` unless the plan carries the optimiser's cost terms.

    Raises:
        KeyError: ``plan`` contains a recipe id that is not in the catalogue.
    """
    cat, store, profile = ctx.catalog, ctx.store, scenario.profile
    horizon = scenario.horizon_days
    indices = [cat.index_of(r) for r in plan.recipe_ids]
    deadlines = visible_deadlines(scenario.pantry, horizon)
    replay = replay_with_substitutions(indices, scenario, ctx, deadlines, horizon)
    report = replay.report

    def name_of(iid: int) -> str:
        info = store.ingredient(iid)
        return info.canonical_name if info is not None else f"ingredient {iid}"

    # --- what the user told us about each stock: was the deadline stated or guessed, were they worried? -----------
    known: dict[int, bool] = {}
    urgent: dict[int, bool] = {}
    for iid, deadline in deadlines.items():
        items = [p for p in scenario.pantry if p.ingredient_id == iid]
        binding = [p for p in items if p.last_use_day == min(
            (q.last_use_day for q in items if q.last_use_day is not None), default=None)]
        known[iid] = bool(binding) and all(p.expiry_known for p in binding)
        urgent[iid] = any(p.urgency.value != "none" for p in items)

    low, high = profile.dinner_kcal_range
    # the rating-history term as the scorer computed it; a dinner is said to be "close to dinners you rated highly"
    # only where the term pushed its score up, never as an after-the-fact justification
    rated = profile.rated_dinners
    term = (history_term(cat, profile, ctx.ignore_ids, ctx.preference_weights)
            if rated and ctx.preference_weights.history > 0 else None)
    days: list[DayFacts] = []
    for day, idx in enumerate(indices):
        info = cat.info(idx)
        ids, _ = cat.ingredients(idx)
        used_today = report.uses_by_day[day] if day < len(report.uses_by_day) else {}

        uses = tuple(PantryUse(name_of(i), float(g), deadlines.get(i), known.get(i, False), urgent.get(i, False))
                     for i, g in sorted(used_today.items(), key=lambda kv: -kv[1]))
        needs = report.groceries_by_day[day] if day < len(report.groceries_by_day) else {}
        groceries = tuple(GroceryNeed(name_of(i), float(g)) for i, g in sorted(needs.items(), key=lambda kv: -kv[1]))

        in_recipe = {int(i) for i in ids.tolist()}
        liked = tuple(sorted(name_of(i) for i in in_recipe & set(profile.liked_ingredient_ids)
                             if i not in ctx.ignore_ids))
        disliked = tuple(sorted(name_of(i) for i in in_recipe & set(profile.disliked_ingredient_ids)))
        is_weekday = scenario.is_weekday(day)
        kcal = info.kcal
        below, above = low - kcal, kcal - high
        status = (KCAL_BELOW if below > GAP_TOLERANCE else KCAL_ABOVE if above > GAP_TOLERANCE else KCAL_IN_RANGE)
        protein_gap = profile.min_protein_g_per_dinner - info.protein_g
        similar: tuple[str, ...] = ()
        if term is not None and term[idx] > 0:
            similar = tuple(rated[pos].name or "a dinner you rated"
                            for pos, _ in nearest_rated(cat, rated, idx, ctx.ignore_ids))
        swaps = tuple(SubstitutionFact(sw.rule_key, name_of(sw.replaced_id), sw.replaced_g,
                                       tuple((name_of(i), g) for i, g in sw.uses), sw.note)
                      for sw in replay.on_day(day))
        days.append(DayFacts(
            day=day, weekday=WEEKDAY_NAMES[(scenario.start_weekday + day) % 7], recipe_id=info.recipe_id,
            name=info.name, minutes=info.minutes, cuisine=info.cuisine, kcal=kcal, protein_g=info.protein_g,
            kcal_status=status, kcal_gap=below if status == KCAL_BELOW else above if status == KCAL_ABOVE else 0.0,
            protein_gap_g=protein_gap if protein_gap > GAP_TOLERANCE else 0.0,
            is_weekday=is_weekday,
            minutes_over=max(0, info.minutes - profile.max_weekday_minutes) if is_weekday else 0,
            pantry_uses=uses, groceries=groceries,
            liked_cuisine=info.cuisine is not None and info.cuisine in profile.liked_cuisines,
            disliked_cuisine=info.cuisine is not None and info.cuisine in profile.disliked_cuisines,
            liked_ingredients=liked, disliked_ingredients=disliked, substitutions=swaps, similar_rated=similar))

    masks = violation_masks(cat, profile)
    allowed = np.ones(cat.n, dtype=bool)
    for m in masks.values():
        allowed &= ~m

    estimated = tuple(sorted({name_of(i) for i, d in deadlines.items() if d is not None and not known.get(i, False)}))
    leftovers = tuple(Leftover(name_of(i), float(g), int(deadlines[i]), known.get(i, False))
                      for i, g in sorted(report.waste_g.items(), key=lambda kv: -kv[1]))
    groceries_total = tuple(GroceryNeed(name_of(i), float(g))
                            for i, g in sorted(report.groceries_g.items(), key=lambda kv: -kv[1]))
    assumed_g: dict[int, float] = {}
    for p in scenario.pantry:
        if p.quantity_assumed and p.ingredient_id not in ctx.ignore_ids:
            assumed_g[p.ingredient_id] = assumed_g.get(p.ingredient_id, 0.0) + p.grams
    assumed = tuple(AssumedQuantity(name_of(i), float(g)) for i, g in sorted(assumed_g.items(), key=lambda kv: -kv[1]))
    stranded = tuple(
        Stranded(name_of(i), float(report.pantry_g.get(i, 0.0)), int(deadlines[i]), known.get(i, False))
        for i in sorted(report.expired_demand_g, key=lambda i: -report.pantry_g.get(i, 0.0))
        if report.expired_demand_g[i] > 1e-9 and deadlines.get(i) is not None)

    return PlanFacts(
        planner=plan.planner, status=plan.status, horizon=horizon, start_weekday=scenario.start_weekday,
        complete=len(indices) >= horizon, kcal_low=low, kcal_high=high,
        protein_min_g=profile.min_protein_g_per_dinner, weekday_limit_min=profile.max_weekday_minutes,
        days=tuple(days), has_pantry=bool(report.pantry_g), pantry_consumed_g=report.total_consumed_g,
        expiring_stock_g=report.expiring_pantry_g, waste_g=report.total_waste_g, leftovers=leftovers,
        stranded=stranded, groceries=groceries_total, n_grocery_items=report.n_grocery_items,
        n_catalogue=int(cat.n), n_allowed=int(allowed.sum()),
        rules=tuple(RuleFact(name, int(m.sum())) for name, m in masks.items()),
        violations=count_violations(cat, profile, indices), estimated_deadline_items=estimated,
        assumed_quantities=assumed, solver=_solver_facts(plan))


def _solver_facts(plan: WeekPlan) -> SolverFacts | None:
    """The optimiser's own account of the plan, or ``None`` if this plan did not come with one (baselines)."""
    d = plan.diagnostics
    if "objective" not in d or any(f"cost_{t}" not in d for t in COST_TERMS):
        return None
    gap = d.get("mip_gap")
    return SolverFacts(
        status=plan.status, backend=str(d["backend"]) if "backend" in d else None, objective=float(d["objective"]),
        mip_gap=float(gap) if isinstance(gap, (int, float)) and gap >= 0 else None,   # the planner stores -1 = unknown
        terms={t: float(d[f"cost_{t}"]) for t in COST_TERMS})
