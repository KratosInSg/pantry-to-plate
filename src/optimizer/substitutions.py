"""Ingredient substitution rules: "no buttermilk, but milk + lemon juice in the fridge -> use those, buy nothing".

Where it sits
-------------
The weekly optimiser chooses the dinners. The inventory replay (``optimizer.inventory``) then says what each dinner
takes from the pantry and what must be bought. This module is one more *rule* step on that replay: for each thing the
plan would buy, it checks whether a known substitution can be made entirely from pantry stock that nothing else in the
plan needs. If so, the item comes off the grocery list and the substitutes are cooked with instead. Every
substitution is recorded (:class:`Substitution`) so the explainer can say exactly which rule fired
(CLAUDE.md: explanations trace back to a cost term or a fired rule).

When a rule fires (all must hold)
---------------------------------
* the dinner on that day must **buy** the replaced ingredient (the pantry's own stock of it, if any, is used first by
  the replay as usual - this is the slide's "IF buttermilk unavailable");
* **every** substitute is spare pantry stock: left over at the end of the replayed plan, so taking it can never starve
  a later dinner (the replay serves days in order and stock only goes down, so stock still left at the end was never
  needed after this day);
* every substitute is still usable that day (``day <= last_use_day``);
* every substitute passes the user's hard rules (``hard_rules.ingredient_violations``: diet, allergens, excluded food
  groups, pork, alcohol, "never" foods) - a vegan's margarine is never swapped for butter - and is not a food the
  user dislikes (soft, but a swap should never surprise the user with something they said they dislike);
* the whole amount is covered. Half buttermilk, half milk + lemon still means buying buttermilk, so a partial swap
  saves no grocery item and is not made.

Rules are tried in table order; the first that fits wins. Staples assumed in every kitchen (salt, water) count as
available without being accounted, exactly as in the replay.

What it deliberately does not do
--------------------------------
* It does not change which dinners are planned. The optimiser does not know about substitutions, so it never
  *chooses* a recipe because a swap would make it cheap; substitutions can only shrink the grocery box and the waste of
  a plan that was chosen without them. (Folding them into the model is possible future work.)
* The benchmark (``evaluation.metrics``) scores plans *without* substitutions, so the numbers stay comparable with
  earlier runs and with the optimiser's own objective. Substitutions only ever lower groceries and waste, so the
  benchmark is the conservative figure.
* Nutrition is not recomputed for a swapped dinner: it stays the recipe's computed value (the substitutes are close
  in role, not identical in nutrients).

Where the numbers come from
---------------------------
Each rule is written as it appears in common household substitution tables (cookbook and university-extension
"ingredient substitution" charts): in kitchen units, e.g. "1 cup buttermilk = 1 cup milk less 1 tbsp + 1 tbsp lemon
juice". :func:`resolve_rules` converts both sides to grams with the dataset's own unit weights (USDA portions where
available), so the grams-per-gram ratios are derived, not typed in.
"""
from __future__ import annotations

import logging
from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass, field
from functools import lru_cache

from domain.models import Scenario, UserProfile
from knowledge.store import KnowledgeStore
from optimizer.hard_rules import ingredient_violations
from optimizer.inventory import InventoryReport, account_inventory
from optimizer.planning import PlanningContext

logger = logging.getLogger(__name__)

# A need smaller than this is a pinch, not shopping: no rule is fired for it (same threshold below which the explainer
# does not mention an amount, ``explain.facts.MIN_MENTION_G``).
MIN_SUBSTITUTION_G = 1.0
_EPS = 1e-9


@dataclass(frozen=True, slots=True)
class SubstitutionRule:
    """One substitution as a kitchen chart states it: ``amount unit`` of ``replaces`` = the ``uses`` together."""

    key: str                                   # stable id, cited by the explainer ("buttermilk_milk_lemon")
    replaces: str                              # canonical ingredient name
    amount: float
    unit: str                                  # a unit with a weight in the dataset (cup / tbsp / tsp ...)
    uses: tuple[tuple[str, float, str], ...]   # (canonical name, amount, unit) of each substitute
    note: str = ""                             # a practical caveat shown to the user


# Ordered: for one replaced ingredient the first rule that fits wins, so the most common swap comes first.
SUBSTITUTION_RULES: tuple[SubstitutionRule, ...] = (
    SubstitutionRule("buttermilk_milk_lemon", "buttermilk", 1, "cup", (("milk", 15, "tbsp"), ("lemon juice", 1, "tbsp")),
                     "Stir the lemon juice into the milk and let it stand for 5-10 minutes."),
    SubstitutionRule("buttermilk_milk_vinegar", "buttermilk", 1, "cup", (("milk", 15, "tbsp"), ("vinegar", 1, "tbsp")),
                     "Stir the vinegar into the milk and let it stand for 5-10 minutes."),
    SubstitutionRule("buttermilk_yogurt_milk", "buttermilk", 1, "cup",
                     (("plain yogurt", 0.75, "cup"), ("milk", 0.25, "cup")), "Whisk the yogurt and milk together."),
    SubstitutionRule("sour_cream_yogurt", "sour cream", 1, "cup", (("plain yogurt", 1, "cup"),),
                     "Tangier and thinner; stir it in off the heat so it does not split."),
    SubstitutionRule("sour_cream_greek_yogurt", "sour cream", 1, "cup", (("greek yogurt", 1, "cup"),),
                     "Tangier; stir it in off the heat so it does not split."),
    SubstitutionRule("heavy_cream_milk_butter", "heavy cream", 1, "cup", (("milk", 0.75, "cup"), ("butter", 0.25, "cup")),
                     "Melt the butter into the milk. Works in sauces and baking, not for whipping."),
    SubstitutionRule("half_and_half_milk_cream", "half and half", 1, "cup",
                     (("milk", 0.5, "cup"), ("heavy cream", 0.5, "cup")), "Mix equal parts."),
    SubstitutionRule("self_rising_flour_flour_baking_powder", "self-rising flour", 1, "cup",
                     (("all-purpose flour", 1, "cup"), ("baking powder", 1.5, "tsp")), "Add a pinch of salt as well."),
    SubstitutionRule("lime_juice_lemon_juice", "lime juice", 1, "tbsp", (("lemon juice", 1, "tbsp"),),
                     "A slightly different citrus flavour."),
    SubstitutionRule("lemon_juice_lime_juice", "lemon juice", 1, "tbsp", (("lime juice", 1, "tbsp"),),
                     "A slightly different citrus flavour."),
    SubstitutionRule("shallot_onion", "shallot", 1, "tbsp", (("onion", 1, "tbsp"),),
                     "Onion is sharper; chop it finely."),
    SubstitutionRule("brown_sugar_sugar_molasses", "brown sugar", 1, "cup", (("sugar", 1, "cup"), ("molasses", 1, "tbsp")),
                     "Mix the molasses into the sugar."),
    SubstitutionRule("white_wine_vegetable_broth", "white wine", 1, "cup", (("vegetable broth", 1, "cup"),),
                     "Less acidic than wine."),
    SubstitutionRule("margarine_butter", "margarine", 1, "cup", (("butter", 1, "cup"),), ""),
    SubstitutionRule("ricotta_cottage_cheese", "ricotta cheese", 1, "tbsp", (("cottage cheese", 1, "tbsp"),),
                     "Drain it and mash it for a smoother texture."),
)


@dataclass(frozen=True, slots=True)
class ResolvedRule:
    """A rule in the units the replay works in: grams of each substitute per gram of the replaced ingredient."""

    key: str
    replaced_id: int
    ratios: tuple[tuple[int, float], ...]      # (substitute ingredient id, grams per gram replaced)
    note: str


@dataclass(frozen=True, slots=True)
class Substitution:
    """One fired rule: on ``day``, ``replaced_g`` of ``replaced_id`` is not bought; ``uses`` come from the pantry."""

    day: int
    rule_key: str
    replaced_id: int
    replaced_g: float
    uses: tuple[tuple[int, float], ...]        # (ingredient id, grams) taken from spare pantry stock (staples: 0 g)
    note: str


@dataclass(frozen=True)
class SubstitutedInventory:
    """The replay after the substitutions, and the substitutions themselves (empty when no rule fired)."""

    report: InventoryReport
    substitutions: tuple[Substitution, ...] = field(default_factory=tuple)

    def on_day(self, day: int) -> tuple[Substitution, ...]:
        return tuple(s for s in self.substitutions if s.day == day)


# ==================================================================================================================
# rules -> grams
# ==================================================================================================================
def _grams(store: KnowledgeStore, name: str, amount: float, unit: str) -> tuple[int, float]:
    info = store.ingredient_by_name(name)
    if info is None:
        raise ValueError(f"substitution rule names {name!r}, which is not a canonical ingredient")
    weight = store.unit_weight(info.ingredient_id, unit)
    if weight is None:
        raise ValueError(f"no weight for one {unit} of {name!r}: the substitution rule cannot be converted to grams")
    return info.ingredient_id, amount * weight.grams


def resolve_rules(store: KnowledgeStore, rules: Sequence[SubstitutionRule] = SUBSTITUTION_RULES
                  ) -> tuple[ResolvedRule, ...]:
    """Convert kitchen-unit rules to grams-per-gram ratios with the dataset's unit weights.

    Raises:
        ValueError: a rule names an ingredient that is not in the dataset, or a unit with no weight for it. The rule
            table is code, so this is a bug to fix (a test resolves every rule against the real dataset), not a case
            to skip silently.
    """
    out: list[ResolvedRule] = []
    for rule in rules:
        replaced_id, replaced_g = _grams(store, rule.replaces, rule.amount, rule.unit)
        ratios = []
        for name, amount, unit in rule.uses:
            sid, grams = _grams(store, name, amount, unit)
            ratios.append((sid, grams / replaced_g))
        out.append(ResolvedRule(rule.key, replaced_id, tuple(ratios), rule.note))
    return tuple(out)


@lru_cache(maxsize=4)
def default_rules(store: KnowledgeStore) -> tuple[ResolvedRule, ...]:
    """``SUBSTITUTION_RULES`` resolved against ``store`` (cached per store)."""
    return resolve_rules(store)


def allowed_substitutes(store: KnowledgeStore, profile: UserProfile, rules: Sequence[ResolvedRule]) -> frozenset[int]:
    """The substitute ingredients of ``rules`` this user may be given: passes every hard rule, and is not disliked."""
    table = store.all_ingredients()
    ids = {sid for rule in rules for sid, _ in rule.ratios}
    allowed = set()
    for sid in ids:
        if sid not in table.index or sid in profile.disliked_ingredient_ids:
            continue
        if not ingredient_violations(table.loc[sid], sid, profile):
            allowed.add(sid)
    return frozenset(allowed)


# ==================================================================================================================
# applying the rules to a replay
# ==================================================================================================================
def _copy(report: InventoryReport) -> InventoryReport:
    return InventoryReport(
        consumed_g=dict(report.consumed_g), groceries_g=dict(report.groceries_g), waste_g=dict(report.waste_g),
        unused_g=dict(report.unused_g), expired_demand_g=dict(report.expired_demand_g), pantry_g=dict(report.pantry_g),
        uses_by_day=[dict(d) for d in report.uses_by_day], groceries_by_day=[dict(d) for d in report.groceries_by_day],
        expiring_ids=set(report.expiring_ids))


def _reduce(d: dict[int, float], key: int, grams: float) -> None:
    left = d.get(key, 0.0) - grams
    if left > _EPS:
        d[key] = left
    else:
        d.pop(key, None)


def apply_substitutions(report: InventoryReport, last_use_day: Mapping[int, int | None],
                        rules: Sequence[ResolvedRule], allowed_ids: Collection[int],
                        ignore_ids: Collection[int] = ()) -> SubstitutedInventory:
    """Fire every rule that fits (module docstring) on ``report``, a replay from ``account_inventory``.

    Args:
        report: the plan's replay. Not modified; the result holds an updated copy.
        last_use_day: the same deadlines the replay used (ingredient id -> last usable day, ``None`` = none).
        rules: resolved rules, in priority order.
        allowed_ids: substitute ingredients this user may be given (:func:`allowed_substitutes`).
        ignore_ids: assumed-available staples: always available, never accounted.

    Returns:
        The updated replay (groceries down; pantry use up; waste/unused down by exactly the grams taken) and the
        substitutions made, in day order.
    """
    by_replaced: dict[int, list[ResolvedRule]] = {}
    for rule in rules:
        by_replaced.setdefault(rule.replaced_id, []).append(rule)
    ignore, allowed = set(ignore_ids), set(allowed_ids)
    # stock still there after the whole plan: nothing later in the week needs it (see the module docstring)
    spare: dict[int, float] = {**report.unused_g, **report.waste_g}

    out = _copy(report)
    made: list[Substitution] = []
    for day, bought in enumerate(report.groceries_by_day):
        for iid in sorted(bought):
            need = bought[iid]
            if need < MIN_SUBSTITUTION_G:
                continue
            for rule in by_replaced.get(iid, ()):
                takes = _takes(rule, need, day, spare, last_use_day, allowed, ignore)
                if takes is None:
                    continue
                out.groceries_by_day[day].pop(iid)
                _reduce(out.groceries_g, iid, need)
                for sid, grams in takes:
                    if sid in ignore:
                        continue
                    spare[sid] -= grams
                    out.uses_by_day[day][sid] = out.uses_by_day[day].get(sid, 0.0) + grams
                    out.consumed_g[sid] = out.consumed_g.get(sid, 0.0) + grams
                    _reduce(out.waste_g if sid in out.expiring_ids else out.unused_g, sid, grams)
                made.append(Substitution(day, rule.key, iid, float(need),
                                         tuple((sid, 0.0 if sid in ignore else float(g)) for sid, g in takes), rule.note))
                logger.debug("day %d: rule %s replaces %.0f g of ingredient %d", day, rule.key, need, iid)
                break
    return SubstitutedInventory(out, tuple(made))


def _takes(rule: ResolvedRule, need: float, day: int, spare: Mapping[int, float],
           last_use_day: Mapping[int, int | None], allowed: set[int], ignore: set[int]
           ) -> list[tuple[int, float]] | None:
    """Grams of each substitute if ``rule`` can cover ``need`` on ``day`` entirely, else ``None``."""
    takes: list[tuple[int, float]] = []
    for sid, ratio in rule.ratios:
        if sid not in allowed:
            return None
        grams = need * ratio
        if sid not in ignore:
            deadline = last_use_day.get(sid)
            if spare.get(sid, 0.0) + _EPS < grams or (deadline is not None and day > deadline):
                return None
        takes.append((sid, grams))
    return takes


def replay_with_substitutions(recipe_indices: Sequence[int | None], scenario: Scenario, ctx: PlanningContext,
                              last_use_day: Mapping[int, int | None], horizon_days: int | None = None,
                              rules: Sequence[ResolvedRule] | None = None) -> SubstitutedInventory:
    """``account_inventory`` followed by :func:`apply_substitutions` for this scenario's user.

    The one call the app, the explainer and re-planning use, so the grocery box, the reasons and the rolled-forward
    pantry always agree on which swaps were made. ``horizon_days`` defaults to the scenario's; ``rules`` to
    :func:`default_rules`.
    """
    horizon = scenario.horizon_days if horizon_days is None else horizon_days
    report = account_inventory(recipe_indices, scenario.pantry, ctx.catalog, last_use_day, ctx.ignore_ids, horizon)
    rules = default_rules(ctx.store) if rules is None else rules
    if not report.groceries_g or not rules:
        return SubstitutedInventory(report)
    allowed = allowed_substitutes(ctx.store, scenario.profile, rules)
    return apply_substitutions(report, last_use_day, rules, allowed, ctx.ignore_ids)
