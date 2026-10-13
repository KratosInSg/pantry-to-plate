"""Inventory accounting: replay a week of dinners against a pantry and report what was used, bought and wasted.

One definition, three users
---------------------------
* the application shows the **grocery box** (what the plan needs that the pantry cannot supply),
* the evaluation replays every method's plan through the *same* function so metrics are comparable,
* the weekly optimiser's own objective mirrors these definitions (a test cross-checks them).

Keeping a single, deliberately simple definition is what makes "waste" and "extra groceries" mean the same thing
everywhere.

Rules of the replay
-------------------
* Days are processed in order. Each dinner needs ``grams_per_serving`` of each of its ingredients.
* Demand is first served from pantry stock **if the stock is still usable that day** (``day <= last_use_day``, or the
  item has no deadline). Anything not served from the pantry is a **grocery**.
* Staples the user is assumed to have (salt, pepper, water: ``ignore_ids``) are ignored entirely - they neither count
  as pantry nor as groceries.
* After the last dinner, stock left over is **waste** if its deadline fell inside the horizon (it spoiled), otherwise it
  is simply **unused** (it keeps).
* If a plan wants stock that is already past its deadline, that demand is bought instead - the user is never told to
  cook with expired stock, whatever the plan - and the grams are reported in ``expired_demand_g``. That is a
  *diagnostic* (the old stock was stranded and the ingredient is bought a second time), not a constraint breach. The
  guarantee "no planned use after a known use-by date" lives in the optimiser's model, which has no pantry-use
  variable after the deadline (tested in ``tests/optimizer/test_weekly.py``).

Which deadline? The caller chooses: pass the planner-visible ``last_use_day`` values to answer "what do we tell the
user", or the scenario's hidden ``true_last_use_day`` to measure what *really* happens.
"""
from __future__ import annotations

from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass, field

from domain.models import PantryItem
from knowledge.recipes import RecipeCatalog


@dataclass
class InventoryReport:
    """Everything that happened to the pantry and the shopping list over the plan. All quantities in grams."""

    consumed_g: dict[int, float] = field(default_factory=dict)         # pantry stock actually cooked with
    groceries_g: dict[int, float] = field(default_factory=dict)        # to buy
    waste_g: dict[int, float] = field(default_factory=dict)            # stock that expired unused inside the horizon
    unused_g: dict[int, float] = field(default_factory=dict)           # stock left, still good at the end
    expired_demand_g: dict[int, float] = field(default_factory=dict)   # demand that wanted already-expired stock
    pantry_g: dict[int, float] = field(default_factory=dict)           # starting stock (ignored staples removed)
    uses_by_day: list[dict[int, float]] = field(default_factory=list)  # day -> {ingredient_id: grams from pantry}
    groceries_by_day: list[dict[int, float]] = field(default_factory=list)  # day -> {ingredient_id: grams to buy}
    expiring_ids: set[int] = field(default_factory=set)               # stock with a deadline inside the horizon

    # ---- convenience totals ------------------------------------------------------------------------------
    @property
    def total_pantry_g(self) -> float:
        return sum(self.pantry_g.values())

    @property
    def total_consumed_g(self) -> float:
        return sum(self.consumed_g.values())

    @property
    def total_waste_g(self) -> float:
        return sum(self.waste_g.values())

    @property
    def total_groceries_g(self) -> float:
        return sum(self.groceries_g.values())

    @property
    def n_grocery_items(self) -> int:
        return sum(1 for g in self.groceries_g.values() if g > 0)

    @property
    def expiring_pantry_g(self) -> float:
        """Starting stock that had a deadline inside the horizon - the only part that *can* be wasted."""
        return sum(self.pantry_g[i] for i in self.expiring_ids)


def account_inventory(recipe_indices: Sequence[int | None], pantry: Sequence[PantryItem], catalog: RecipeCatalog,
                      last_use_day: Mapping[int, int | None], ignore_ids: Collection[int] = (),
                      horizon_days: int | None = None) -> InventoryReport:
    """Replay ``recipe_indices`` (one catalogue row index per day) against ``pantry``.

    Args:
        recipe_indices: catalogue row index of the dinner on each day, in day order. ``None`` is a day with no home
            dinner (skipped / eating out): nothing is used or bought, but the day still passes, so deadlines keep
            counting down.
        pantry: starting stock. Several entries for one ingredient are summed.
        catalog: recipe pool (supplies each dinner's ingredients and grams).
        last_use_day: ingredient id -> last usable day (inclusive) or ``None`` (no deadline). Ingredients missing
            from the mapping are treated as having no deadline.
        ignore_ids: assumed-available staples to leave out of every total.
        horizon_days: plan length; defaults to ``len(recipe_indices)``. Deadlines at or after it do not create waste.
    """
    horizon = horizon_days if horizon_days is not None else len(recipe_indices)
    ignore = set(ignore_ids)

    stock: dict[int, float] = {}
    for item in pantry:
        if item.ingredient_id not in ignore:
            stock[item.ingredient_id] = stock.get(item.ingredient_id, 0.0) + item.grams

    report = InventoryReport(pantry_g=dict(stock))
    remaining = dict(stock)

    for day, idx in enumerate(recipe_indices):
        used_today: dict[int, float] = {}
        bought_today: dict[int, float] = {}
        if idx is None:                       # a skipped day: the clock runs, the pantry is untouched
            report.uses_by_day.append(used_today)
            report.groceries_by_day.append(bought_today)
            continue
        ing_ids, grams = catalog.ingredients(idx)
        for iid, g in zip(ing_ids.tolist(), grams.tolist()):
            if iid in ignore or g <= 0:
                continue
            have = remaining.get(iid, 0.0)
            deadline = last_use_day.get(iid)
            usable = have > 0 and (deadline is None or day <= deadline)
            take = min(have, g) if usable else 0.0
            if take > 0:
                remaining[iid] = have - take
                used_today[iid] = used_today.get(iid, 0.0) + take
                report.consumed_g[iid] = report.consumed_g.get(iid, 0.0) + take
            if have > 0 and not usable:
                report.expired_demand_g[iid] = report.expired_demand_g.get(iid, 0.0) + min(have, g)
            short = g - take
            if short > 1e-9:
                report.groceries_g[iid] = report.groceries_g.get(iid, 0.0) + short
                bought_today[iid] = bought_today.get(iid, 0.0) + short
        report.uses_by_day.append(used_today)
        report.groceries_by_day.append(bought_today)

    for iid in stock:
        deadline = last_use_day.get(iid)
        if deadline is not None and deadline < horizon:
            report.expiring_ids.add(iid)
    for iid, left in remaining.items():
        if left <= 1e-9:
            continue
        (report.waste_g if iid in report.expiring_ids else report.unused_g)[iid] = left
    return report


def visible_deadlines(pantry: Sequence[PantryItem], horizon_days: int) -> dict[int, int | None]:
    """Planner-visible deadline per ingredient, with deadlines at or beyond the horizon read as "no deadline" (which is
    how the weekly model treats them). The one definition shared by the explainer and the app's recipe view."""
    return {iid: (d if d is not None and d < horizon_days else None)
            for iid, d in deadlines_from_pantry(pantry).items()}


def deadlines_from_pantry(pantry: Sequence[PantryItem]) -> dict[int, int | None]:
    """Planner-visible deadlines (``last_use_day``) per ingredient. For duplicate stocks the earliest deadline wins
    (a missing deadline counts as "never")."""
    out: dict[int, int | None] = {}
    for item in pantry:
        current = out.get(item.ingredient_id)            # None means both "unseen" and "no deadline yet"
        if item.last_use_day is None:
            out.setdefault(item.ingredient_id, None)
        else:
            out[item.ingredient_id] = item.last_use_day if current is None else min(current, item.last_use_day)
    return out
