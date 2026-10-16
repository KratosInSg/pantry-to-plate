"""Eight evidence-labelled XAI cards for each meal (PPT slide 9 terminology).

Pure presentation: consumes deterministic DayFacts / PlanFacts; never alters planning.
No fabricated substitutions, counterfactuals, or NLP performance claims: the substitution card states only a
substitution rule that actually fired (``optimizer.substitutions``), and says so when none did.
"""
from __future__ import annotations

from dataclasses import dataclass
from explain.facts import DayFacts, PlanFacts, KCAL_IN_RANGE
from explain.render import fmt_g, substitution_phrase


@dataclass(frozen=True)
class XAICard:
    key: str
    icon: str
    label: str
    detail: str
    source: str
    available: bool = True


def meal_cards(day: DayFacts, facts: PlanFacts) -> tuple[XAICard, ...]:
    """Always return eight ordered, evidence-based explanations for one dinner."""
    urgent = [x for x in day.pantry_uses if x.last_use_day is not None]
    if urgent:
        first = min(urgent, key=lambda x: x.last_use_day)
        deadline = ("known" if first.deadline_known else "estimated")
        expiry = f"Uses {fmt_g(first.grams)} {first.name} before its {deadline} use-by day {first.last_use_day + 1}."
    else:
        expiry = "No ingredient used by this dinner has a recorded deadline within the planning week."
    pantry_g = sum(x.grams for x in day.pantry_uses)
    pantry = (f"Uses {fmt_g(pantry_g)} from {len(day.pantry_uses)} existing pantry ingredient(s)."
              if day.pantry_uses else "No starting pantry stock is used for this dinner.")
    preference = []
    if day.liked_cuisine and day.cuisine:
        preference.append(f"Matches your liked cuisine: {day.cuisine}.")
    if day.liked_ingredients:
        preference.append("Uses liked ingredients: " + ", ".join(day.liked_ingredients) + ".")
    if day.disliked_cuisine or day.disliked_ingredients:
        preference.append("Some soft dislikes remain; they are not hard exclusions.")
    if not preference:
        preference.append("No explicit liked cuisine or ingredient match is recorded.")
    nutrition = (f"{day.kcal:.0f} kcal is within your selected range."
                 if day.kcal_status == KCAL_IN_RANGE else
                 f"{day.kcal:.0f} kcal is outside your selected range by {day.kcal_gap:.0f} kcal.")
    if day.protein_gap_g > 0:
        nutrition += f" Protein is {day.protein_gap_g:.1f} g below your target."
    else:
        nutrition += f" Protein: {day.protein_g:.1f} g; meets your minimum."
    grocery_g = sum(x.grams for x in day.groceries)
    groceries = (f"Needs {len(day.groceries)} additional ingredient(s), totalling {fmt_g(grocery_g)}."
                 if day.groceries else "No additional grocery ingredients needed for this dinner.")
    constraint = ("Passes all currently configured recipe-level hard rules."
                  if facts.violations == 0 else
                  "The plan has detected rule violations; inspect Rules & notes.")
    time = (f"{day.minutes} minutes; {day.minutes_over} minutes above your weekday preference."
            if day.minutes_over else f"{day.minutes} minutes; no weekday overtime penalty.")
    if day.substitutions:
        substitution = XAICard("substitution", "🔄", "Substitution",
                               " ".join(substitution_phrase(x) for x in day.substitutions),
                               "substitution rule: " + ", ".join(x.rule_key for x in day.substitutions))
    else:
        substitution = XAICard("substitution", "🔄", "Substitution",
                               "No substitution rule fired for this dinner: nothing it needs to buy can be replaced "
                               "by spare pantry stock.", "substitution rules (none fired)", False)
    return (
        XAICard("expiry", "⏳", "Expiry", expiry, "pantry replay + expiry metadata"),
        XAICard("pantry", "🥫", "Pantry", pantry, "pantry replay"),
        XAICard("preference", "❤️", "Preference", " ".join(preference), "user profile + recipe attributes"),
        XAICard("nutrition", "🥗", "Nutrition", nutrition, "recipe nutrition + profile targets"),
        XAICard("groceries", "🛒", "Groceries", groceries, "pantry replay"),
        XAICard("constraint", "🛡️", "Constraint", constraint, "hard-rule checker"),
        substitution,
        XAICard("cooking_time", "⏱️", "Cooking time", time, "recipe duration + profile limit"),
    )
