"""The grocery box: what to buy for the plan, from the inventory replay.

One definition, again
---------------------
"What must be bought" is whatever the pantry could not cover when the plan's dinners are replayed in order
(``optimizer.inventory.account_inventory``), less what a fired substitution rule covers from spare pantry stock
(``optimizer.substitutions``; the service passes that replay) - the same numbers the explainer cites. This
module only *presents* them: names, food group, the first day each item is needed, and a ``minor`` flag for pinches.
Staples the user is assumed to have (salt, water) are not in the replay and so never appear here.
"""
from __future__ import annotations

from explain.facts import WEEKDAY_NAMES
from app.models import MINOR_GROCERY_G, GroceryBox, GroceryItem
from knowledge.store import KnowledgeStore
from optimizer.inventory import InventoryReport

UNKNOWN_GROUP = "other"


def build_grocery_box(report: InventoryReport, store: KnowledgeStore, start_weekday: int = 0) -> GroceryBox:
    """Present ``report.groceries_g`` as a shopping list.

    Args:
        report: the replay of the plan.
        store: for ingredient names and food groups.
        start_weekday: weekday of the plan's day 0 (0 = Monday), so "needed first on Wednesday" can be shown.

    Items are sorted by when they are first needed, then largest first, so the top of the list is what the user
    needs soonest. ``n_items`` equals ``report.n_grocery_items``.
    """
    first_day: dict[int, int] = {}
    for day, bought in enumerate(report.groceries_by_day):
        for iid, grams in bought.items():
            if grams > 1e-9:
                first_day.setdefault(iid, day)

    items: list[GroceryItem] = []
    for iid, grams in report.groceries_g.items():
        if grams <= 1e-9:
            continue
        info = store.ingredient(iid)
        day = first_day.get(iid, 0)
        items.append(GroceryItem(
            ingredient_id=iid, name=info.canonical_name if info else f"ingredient {iid}", grams=float(grams),
            food_group=(info.food_group if info and info.food_group else UNKNOWN_GROUP), first_needed_day=day,
            weekday=WEEKDAY_NAMES[(start_weekday + day) % 7], minor=grams < MINOR_GROCERY_G))
    items.sort(key=lambda i: (i.first_needed_day, -i.grams, i.name))
    return GroceryBox(items=tuple(items))
