"""Pure decisions behind the UI, kept out of the Streamlit code so they can be tested without a browser.

What lives here
---------------
* **Re-plan requests.** The user marks each planned day *Cooked*, *Skipped*, *Reject this dinner* or leaves it
  *Planned*. ``build_replan_request`` turns those marks into what ``PantryToPlateService.replan`` needs - or says why
  they cannot be applied (days must be marked in order, something must be left to plan).
* **Use-by choices.** A pantry row's deadline is either our estimate or something the user states. The choices offered
  (Today / Tomorrow / a weekday / won't go off this week) and how they are applied to an entry.
* **Labels.** Short, honest wording for statuses, so the views contain layout only.

Nothing here imports Streamlit.
"""
from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass

from app.models import (ENTRY_ASSUMED, ENTRY_CHOOSE, ENTRY_NO_AMOUNT, ENTRY_OK, ENTRY_UNKNOWN, ENTRY_UNSAFE,
                        PantryEntry)
from explain.facts import WEEKDAY_NAMES

# ---------------------------------------------------------------------------------------------------- day marks
DAY_PLANNED = "Planned"
DAY_COOKED = "Cooked"
DAY_SKIPPED = "Skipped"
DAY_REJECTED = "Reject this dinner"
DAY_MARKS = (DAY_PLANNED, DAY_COOKED, DAY_SKIPPED, DAY_REJECTED)
_ELAPSED = (DAY_COOKED, DAY_SKIPPED)         # marks that mean "this day has passed"


@dataclass(frozen=True)
class ReplanRequest:
    """What the marks on the week mean for ``service.replan``."""

    cooked: tuple[int | None, ...] = ()      # per elapsed day: the recipe id cooked, or None if skipped
    rejected: tuple[int, ...] = ()           # recipe ids to exclude from the remaining days
    remaining_days: int = 0
    changed: bool = False                    # at least one day is marked
    problem: str = ""                        # why this cannot be applied ("" = it can)

    @property
    def ok(self) -> bool:
        return self.changed and not self.problem

    def describe(self, rejected_names: Sequence[str] = ()) -> str:
        """One sentence telling the user what pressing the button will do.

        ``rejected_names`` are the names of the dinners in ``rejected`` (the caller knows them; this module does not).
        """
        if self.problem:
            return self.problem
        if not self.changed:
            return "Mark a day as cooked, skipped or rejected to re-plan the rest of the week."
        parts: list[str] = []
        if self.cooked:
            done = sum(1 for c in self.cooked if c is not None)
            skipped = len(self.cooked) - done
            parts.append(f"{len(self.cooked)} day{'s' if len(self.cooked) != 1 else ''} will count as past "
                         f"({done} cooked, {skipped} skipped) and their food comes out of the pantry")
        if self.rejected:
            shown = ", ".join(rejected_names) if rejected_names else f"{len(self.rejected)} dinner(s)"
            parts.append(f"{shown} will not come back")
        parts.append(f"the remaining {self.remaining_days} day{'s' if self.remaining_days != 1 else ''} will be "
                     "planned again from what is left")
        text = "; ".join(parts)
        return text[0].upper() + text[1:] + "."


def build_replan_request(recipe_ids: Sequence[int], marks: Sequence[str]) -> ReplanRequest:
    """Interpret per-day marks.

    The leading run of *Cooked* / *Skipped* days is the past. After it, a day may only be *Planned* or *Rejected*:
    a *Cooked* day that follows an unresolved day is a contradiction, and is reported rather than guessed at.
    """
    if len(recipe_ids) != len(marks):
        raise ValueError("one mark per planned day is required")
    unknown = [m for m in marks if m not in DAY_MARKS]
    if unknown:
        raise ValueError(f"unknown day mark(s): {sorted(set(unknown))}")
    if all(m == DAY_PLANNED for m in marks):
        return ReplanRequest(remaining_days=len(marks))

    elapsed = 0
    while elapsed < len(marks) and marks[elapsed] in _ELAPSED:
        elapsed += 1
    for day in range(elapsed, len(marks)):
        if marks[day] in _ELAPSED:
            return ReplanRequest(changed=True, problem=(
                f"Day {day + 1} is marked {marks[day].lower()}, but day {elapsed + 1} has not been dealt with yet. "
                "Mark days in order, starting from the first."))
    remaining = len(marks) - elapsed
    if remaining <= 0:
        return ReplanRequest(changed=True, problem="Every day is marked as done: there is nothing left to plan.")
    cooked = tuple(None if marks[d] == DAY_SKIPPED else int(recipe_ids[d]) for d in range(elapsed))
    rejected = tuple(int(recipe_ids[d]) for d in range(elapsed, len(marks)) if marks[d] == DAY_REJECTED)
    return ReplanRequest(cooked=cooked, rejected=rejected, remaining_days=remaining, changed=True)


# ---------------------------------------------------------------------------------------------------- use-by
@dataclass(frozen=True)
class UseByChoice:
    """One option of the "use by" selector."""

    label: str
    kind: str                    # "estimate" | "day" | "never"
    days: int | None = None      # for kind == "day": days from today (0 = today)


def use_by_choices(start_weekday: int, horizon_days: int, original: PantryEntry) -> list[UseByChoice]:
    """The options for one row: our estimate first, then each day of the plan, then "won't go off"."""
    if original.last_use_day is None:
        estimate = "Not sure (we assume it keeps this week)"
    else:
        day = WEEKDAY_NAMES[(start_weekday + original.last_use_day) % 7]
        estimate = f"Not sure (we estimate: use by {day})"
    choices = [UseByChoice(estimate, "estimate")]
    for d in range(horizon_days):
        name = WEEKDAY_NAMES[(start_weekday + d) % 7]
        label = "Today" if d == 0 else ("Tomorrow" if d == 1 else f"{name} (in {d} days)")
        choices.append(UseByChoice(label, "day", d))
    choices.append(UseByChoice("Won't go off this week", "never"))
    return choices


def current_use_by_index(entry: PantryEntry, choices: Sequence[UseByChoice]) -> int:
    """Which option describes the entry as it is now."""
    if not entry.expiry_known:
        return 0
    if entry.last_use_day is None:
        return len(choices) - 1
    for i, c in enumerate(choices):
        if c.kind == "day" and c.days == entry.last_use_day:
            return i
    return 0


def apply_use_by(entry: PantryEntry, original: PantryEntry, choice: UseByChoice, horizon_days: int) -> PantryEntry:
    """``entry`` with the chosen deadline. "Not sure" restores what the parser estimated; a day is a stated, hard
    deadline; "won't go off" is a stated *absence* of a deadline."""
    if choice.kind == "estimate":
        return entry.model_copy(update={
            "last_use_day": original.last_use_day, "expiry_known": original.expiry_known,
            "expiry_confidence": original.expiry_confidence, "days_left_hint": original.days_left_hint,
            "days_left_explicit": original.days_left_explicit})
    if choice.kind == "never":
        return entry.with_days_left(None, horizon_days)
    return entry.with_days_left(choice.days, horizon_days)


# ---------------------------------------------------------------------------------------------------- labels
_STATUS = {
    ENTRY_OK: ("ok", "Understood"),
    ENTRY_ASSUMED: ("assumed", "Amount assumed - please check"),
    ENTRY_CHOOSE: ("choose", "Which one did you mean?"),
    ENTRY_UNKNOWN: ("unknown", "Not recognised"),
    ENTRY_NO_AMOUNT: ("amount", "How much do you have?"),
    ENTRY_UNSAFE: ("unsafe", "Left out: may not be safe to eat"),
}


def status_label(entry: PantryEntry) -> tuple[str, str]:
    """``(kind, text)`` for a row's status; ``kind`` lets a view pick colour/icon, ``text`` is user-facing."""
    return _STATUS.get(entry.status, ("unknown", entry.status))


def needs_choice(entry: PantryEntry) -> bool:
    """The row has no ingredient yet and the user must pick one (or leave it out)."""
    return entry.ingredient_id is None and entry.status in (ENTRY_CHOOSE, ENTRY_UNKNOWN)


def weekday_label(start_weekday: int, day: int, day_offset: int = 0) -> str:
    """``"Wednesday"`` for plan day ``day`` (``day_offset`` = days of an earlier plan that already passed)."""
    return WEEKDAY_NAMES[(start_weekday + day + day_offset) % 7]


def display_name(name: str) -> str:
    """A recipe or ingredient name for display. Food.com names lost their apostrophes ("julie s salsa chicken"), so a
    lone trailing "s" after a word is restored as a possessive: "Julie's Salsa Chicken"."""
    return re.sub(r"\b([A-Za-z]{2,}) S\b", r"\1's", name.strip().title())


EXAMPLE_PANTRY = ("half a bag of spinach that is going off, 500g chicken breast, 6 eggs, leftover rice, "
                  "a tub of kimchi, 2 lbs potatoes, milk that expires tomorrow, flour, a can of chickpeas, "
                  "some old tomatoes")
