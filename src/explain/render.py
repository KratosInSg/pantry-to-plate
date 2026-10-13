"""Facts -> plain-English sections. Deterministic templates; this is what the user sees when no LLM is available.

Design rules
------------
* **One statement = one fact, tagged with where it came from** (``Statement.term`` / ``Statement.source``). A UI or a
  test can therefore ask "which solver cost term or rule does this sentence trace to?" for every sentence.
* **Honest by construction.** A shortfall is stated as a shortfall (below the calorie range, protein short, over the
  time limit, stock that will still go unused). The text never turns a miss into a win, and never says a dinner is
  "healthy" or "tasty": it states distance to the user's *own* targets.
* **Sections are the unit of paraphrasing.** ``overview`` and each ``day`` may later be reworded by the LLM
  (``paraphrase.py``); ``rules`` and ``caveats`` are safety statements and are *never* reworded.
* **No facts beyond ``PlanFacts``.** Everything below reads a field; nothing is looked up or computed from outside it.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace

from explain.facts import KCAL_ABOVE, KCAL_BELOW, DayFacts, Leftover, PantryUse, PlanFacts, RuleFact

# ``Statement.source`` values.
SRC_REPLAY = "replay"                  # the inventory replay (same definitions as the grocery box and the evaluation)
SRC_COST_TERM = "solver_cost_term"     # a term of the objective the weekly optimiser minimised
SRC_RULE = "hard_rule"                 # a named hard rule
SRC_PROFILE = "profile"                # the user's own stated targets / preferences
SRC_INPUT = "input"                    # how the pantry data itself was obtained (e.g. estimated use-by dates)

# Human wording for each cost term of the objective (``optimizer.weekly.COST_TERMS``).
TERM_LABELS = {
    "waste": "food left unused",
    "groceries": "extra shopping",
    "nutrition": "calorie and protein fit",
    "preference": "taste match",
    "cook_time": "weekday cooking time",
    "variety": "repeated cuisines or proteins",
}
# A term must carry at least this share of the objective to be named (below it the sentence would be noise).
MIN_TERM_SHARE = 0.10
# Items listed individually in one sentence before "and N more".
MAX_LISTED = 4

# Second-person phrasing of each hard rule (the rule-level reasons in ``optimizer.hard_rules`` speak about "the user").
_RULE_PHRASES = {
    "diet": "are not compatible with your {detail} diet",
    "allergen": "contain {detail}, which is on your allergy list",
    "pork": "contain pork, which you avoid",
    "alcohol": "contain alcohol, which you avoid",
    "excluded": "contain an ingredient you never eat",
    "excluded_recipe": "are dinners you rejected",
    "time": "take longer than your maximum cooking time",
    "not_dinner": "look like breakfast dishes, doughs or batters rather than dinners",
}


@dataclass(frozen=True, slots=True)
class Statement:
    """One sentence and where it comes from."""

    text: str
    term: str        # waste | groceries | nutrition | preference | cook_time | variety | overview | rule | solver | data
    source: str      # SRC_*


@dataclass(frozen=True, slots=True)
class Section:
    """A titled group of statements, shown as one paragraph."""

    key: str                           # "overview" | "day:<n>" | "rules" | "caveats"
    title: str
    statements: tuple[Statement, ...]
    text: str = ""                     # what is shown: the statements joined, or an accepted paraphrase of them
    source: str = "template"           # "template" | "llm"
    note: str = ""                     # why a paraphrase was rejected (for the UI / evaluation), else ""

    @property
    def template_text(self) -> str:
        """The statements joined: the ground truth any paraphrase is validated against."""
        return " ".join(s.text for s in self.statements)


@dataclass(frozen=True, slots=True)
class Explanation:
    """The full, sectioned explanation of one plan."""

    sections: tuple[Section, ...]
    facts: PlanFacts = field(repr=False)

    def section(self, key: str) -> Section | None:
        return next((s for s in self.sections if s.key == key), None)

    def to_text(self) -> str:
        """Plain text, one heading per section."""
        return "\n\n".join(f"{s.title}\n{s.text}" for s in self.sections if s.text)


# ==================================================================================================================
# formatting helpers
# ==================================================================================================================
def fmt_g(grams: float) -> str:
    """``300 g``, ``1.5 g``, ``1.2 kg``: whole grams above 10 g, one decimal below."""
    if grams >= 1000:
        return f"{grams / 1000:.1f} kg".replace(".0 kg", " kg")
    if grams >= 10 or abs(grams - round(grams)) < 0.05:
        return f"{grams:.0f} g"
    return f"{grams:.1f} g"


def _gap(x: float) -> str:
    """A shortfall to print: whole numbers from 1 up, one decimal below 1 - so a miss of 0.4 g never reads "0 g"."""
    return f"{x:.0f}" if x >= 1 else f"{x:.1f}"


def _join(items: list[str]) -> str:
    if len(items) <= 1:
        return "".join(items)
    return ", ".join(items[:-1]) + " and " + items[-1]


def _listed(items: list[str], total: int) -> str:
    """``a, b and c`` or, when ``total`` exceeds what is listed, ``a, b, c and 2 more`` (never two "and"s)."""
    extra = total - len(items)
    if extra > 0:
        return ", ".join(items) + f" and {extra} more"
    return _join(items)


def _by(facts: PlanFacts, last_use_day: int | None, known: bool) -> str:
    """``by Tuesday`` / ``by Tuesday, estimated`` or ``""`` when there is no deadline in the plan."""
    if last_use_day is None:
        return ""
    return f"by {facts.weekday(last_use_day)}" + ("" if known else ", estimated")


def _use_phrase(facts: PlanFacts, use: PantryUse) -> str:
    by = _by(facts, use.last_use_day, use.deadline_known)
    return f"{fmt_g(use.grams)} {use.name}" + (f" (use {by})" if by else "")


def _leftover_phrase(facts: PlanFacts, left: Leftover) -> str:
    return f"{fmt_g(left.grams)} {left.name} (use {_by(facts, left.last_use_day, left.deadline_known)})"


# ==================================================================================================================
# sections
# ==================================================================================================================
def render(facts: PlanFacts) -> Explanation:
    """Build the full explanation (all sections, template text) from ``facts``."""
    sections: list[Section] = [_overview(facts)]
    sections += [_day(facts, d) for d in facts.days]
    rules = _rules(facts)
    if rules.statements:
        sections.append(rules)
    caveats = _caveats(facts)
    if caveats.statements:
        sections.append(caveats)
    sections = [_with_text(s) for s in sections]
    return Explanation(sections=tuple(sections), facts=facts)


def _with_text(section: Section) -> Section:
    return replace(section, text=section.template_text)


def _overview(f: PlanFacts) -> Section:
    s: list[Statement] = []
    if not f.days:
        if f.n_allowed == 0:
            s.append(Statement(f"None of the {f.n_catalogue:,} dinners we know passes all of your rules, so no plan "
                               "is possible with them as they are.", "overview", SRC_RULE))
        elif f.n_allowed < f.horizon:
            s.append(Statement(f"Only {f.n_allowed:,} dinners pass all of your rules, fewer than the {f.horizon} "
                               "needed for a week.", "overview", SRC_RULE))
        else:
            s.append(Statement(f"No plan was produced (status: {f.status}).", "overview", SRC_REPLAY))
        return Section("overview", "Your week", tuple(s))

    if not f.complete:
        s.append(Statement(f"Only {f.n_dinners} of {f.horizon} dinners could be planned.", "overview", SRC_REPLAY))

    bought = (f"need {f.n_grocery_items} extra item{'s' if f.n_grocery_items != 1 else ''} from the shop "
              f"({fmt_g(sum(g.grams for g in f.groceries))})") if f.n_grocery_items else "need nothing extra from the shop"
    if f.has_pantry:
        s.append(Statement(f"These {f.n_dinners} dinners use {fmt_g(f.pantry_consumed_g)} of your pantry and {bought}.",
                           "groceries", SRC_REPLAY))
    else:
        s.append(Statement(f"These {f.n_dinners} dinners {bought}.", "groceries", SRC_REPLAY))

    in_range, protein_ok = f.n_kcal_in_range, f.n_protein_ok
    s.append(Statement(
        f"{in_range} of {f.n_dinners} dinners {'is' if in_range == 1 else 'are'} inside your calorie range "
        f"({f.kcal_low:.0f}-{f.kcal_high:.0f} kcal) and {protein_ok} of {f.n_dinners} "
        f"{'reaches' if protein_ok == 1 else 'reach'} your {f.protein_min_g:.0f} g protein minimum.",
        "nutrition", SRC_PROFILE))

    if f.expiring_stock_g > 0:
        if f.waste_g <= 0:
            s.append(Statement(f"All {fmt_g(f.expiring_stock_g)} of pantry stock that expires this week is used up.",
                               "waste", SRC_REPLAY))
        else:
            shown = [l for l in f.leftovers if l.grams >= 1.0][:MAX_LISTED]
            listing = f": {_listed([_leftover_phrase(f, l) for l in shown], len(f.leftovers))}" if shown else ""
            s.append(Statement(
                f"{fmt_g(f.waste_g)} of the {fmt_g(f.expiring_stock_g)} of pantry stock that expires this week will "
                f"still go unused{listing}.", "waste", SRC_REPLAY))
    stranded = [x for x in f.stranded if x.grams >= 1.0]
    if stranded:
        listing = _listed([f"{fmt_g(x.grams)} {x.name} (use {_by(f, x.last_use_day, x.deadline_known)})"
                           for x in stranded[:MAX_LISTED]], len(stranded))
        one = len(stranded) == 1
        s.append(Statement(f"You already have {listing}, but {'it expires' if one else 'they expire'} before the "
                           f"dinner that needs {'it' if one else 'them'}, so the plan buys "
                           f"{'it' if one else 'them'} again.", "waste", SRC_REPLAY))

    sv = f.solver
    if sv is not None:
        total = sum(sv.terms.values())
        if total <= 1e-9:
            s.append(Statement("By the planner's own scoring this plan has no penalty in any category.",
                               "solver", SRC_COST_TERM))
        else:
            ranked = sorted(((t, v / total) for t, v in sv.terms.items() if v / total >= MIN_TERM_SHARE),
                            key=lambda kv: -kv[1])
            parts = [f"{TERM_LABELS[t]} ({share * 100:.0f}%)" for t, share in ranked]
            s.append(Statement(f"What still costs this plan the most, by the planner's own scoring: "
                               f"{_join(parts)}.", "solver", SRC_COST_TERM))
        if sv.mip_gap is not None:
            if sv.status == "optimal":
                s.append(Statement(f"The solver proved this plan is within {sv.mip_gap * 100:.0f}% of the best "
                                   "possible one under that scoring.", "solver", SRC_COST_TERM))
            else:
                s.append(Statement(f"The solver ran out of time; it can only prove this plan is within "
                                   f"{sv.mip_gap * 100:.0f}% of the best possible one under that scoring.",
                                   "solver", SRC_COST_TERM))
    return Section("overview", "Your week", tuple(s))


def _day(f: PlanFacts, d: DayFacts) -> Section:
    s: list[Statement] = [Statement(
        f"{d.name} takes {d.minutes} min and has about {d.kcal:.0f} kcal and {d.protein_g:.0f} g protein per serving.",
        "overview", SRC_REPLAY)]

    if d.pantry_uses:
        shown = list(d.pantry_uses[:MAX_LISTED])
        s.append(Statement(f"Uses {_listed([_use_phrase(f, u) for u in shown], len(d.pantry_uses))} from your pantry.",
                           "waste", SRC_REPLAY))
    elif f.has_pantry:
        s.append(Statement("Nothing from your pantry goes into this one.", "waste", SRC_REPLAY))

    if d.groceries:
        shown = [g for g in d.groceries if g.grams >= 1.0][:MAX_LISTED]
        if shown:
            s.append(Statement(
                f"You need to buy {_listed([f'{g.name} ({fmt_g(g.grams)})' for g in shown], len(d.groceries))}.",
                "groceries", SRC_REPLAY))
    else:
        s.append(Statement("Everything it needs is in your pantry or among the staples we assume you have.",
                           "groceries", SRC_REPLAY))

    if d.kcal_status == KCAL_BELOW:
        s.append(Statement(f"At {d.kcal:.0f} kcal it is {_gap(d.kcal_gap)} kcal below your dinner range "
                           f"({f.kcal_low:.0f}-{f.kcal_high:.0f} kcal).", "nutrition", SRC_PROFILE))
    elif d.kcal_status == KCAL_ABOVE:
        s.append(Statement(f"At {d.kcal:.0f} kcal it is {_gap(d.kcal_gap)} kcal above your dinner range "
                           f"({f.kcal_low:.0f}-{f.kcal_high:.0f} kcal).", "nutrition", SRC_PROFILE))
    else:
        s.append(Statement(f"At {d.kcal:.0f} kcal it sits inside your dinner range "
                           f"({f.kcal_low:.0f}-{f.kcal_high:.0f} kcal).", "nutrition", SRC_PROFILE))
    if f.protein_min_g > 0:
        if d.protein_gap_g > 0:
            s.append(Statement(f"Its {d.protein_g:.0f} g protein is {_gap(d.protein_gap_g)} g short of your "
                               f"{f.protein_min_g:.0f} g minimum.", "nutrition", SRC_PROFILE))
        else:
            s.append(Statement(f"Its {d.protein_g:.0f} g protein meets your {f.protein_min_g:.0f} g minimum.",
                               "nutrition", SRC_PROFILE))

    cuisine = d.cuisine.title() if d.cuisine else ""
    if d.liked_cuisine:
        s.append(Statement(f"It is {cuisine} food, which you like.", "preference", SRC_PROFILE))
    if d.disliked_cuisine:
        s.append(Statement(f"It is {cuisine} food, which you said you dislike.", "preference", SRC_PROFILE))
    if d.liked_ingredients:
        s.append(Statement(f"It contains {_join(list(d.liked_ingredients))}, which you like.",
                           "preference", SRC_PROFILE))
    if d.disliked_ingredients:
        s.append(Statement(f"It contains {_join(list(d.disliked_ingredients))}, which you said you dislike.",
                           "preference", SRC_PROFILE))

    if d.is_weekday:
        if d.minutes_over > 0:
            s.append(Statement(f"It takes {d.minutes_over} min longer than your {f.weekday_limit_min}-minute "
                               "weekday limit.", "cook_time", SRC_PROFILE))
        else:
            s.append(Statement(f"It fits your {f.weekday_limit_min}-minute weekday limit.", "cook_time", SRC_PROFILE))
    return Section(f"day:{d.day}", f"{d.weekday}: {d.name}", tuple(s))


def _rules(f: PlanFacts) -> Section:
    s: list[Statement] = []
    active = [r for r in f.rules if r.n_excluded > 0]
    for r in active:
        s.append(Statement(f"{r.n_excluded:,} dinners were removed because they {_rule_phrase(r)}.", "rule", SRC_RULE))
    if f.rules:
        s.append(Statement(f"{f.n_allowed:,} of {f.n_catalogue:,} dinners were left to choose from"
                           + (" (some dinners break more than one rule)." if len(active) > 1 else "."),
                           "rule", SRC_RULE))
        if f.days and f.violations == 0:
            s.append(Statement(f"All {f.n_dinners} planned dinners pass every one of these rules.", "rule", SRC_RULE))
        elif f.violations:
            s.append(Statement(f"WARNING: {f.violations} rule violation{'s' if f.violations != 1 else ''} found among "
                               "the planned dinners. Please do not cook from this plan.", "rule", SRC_RULE))
    if any(r.name.startswith("allergen:") for r in f.rules):
        s.append(Statement("Allergy checks use our ingredient list, so hidden ingredients inside packaged foods are "
                           "not caught. Please check labels.", "rule", SRC_RULE))
    return Section("rules", "Your rules", tuple(s))


def _rule_phrase(rule: RuleFact) -> str:
    kind, _, detail = rule.name.partition(":")
    return _RULE_PHRASES.get(kind, "violate a rule you set").format(detail=detail.replace("_", " "))


def _caveats(f: PlanFacts) -> Section:
    s: list[Statement] = []
    if f.assumed_quantities:
        shown = [f"{fmt_g(a.grams)} {a.name}" for a in f.assumed_quantities[:MAX_LISTED]]
        s.append(Statement(
            f"You did not say how much of some items you have, so we assumed {_listed(shown, len(f.assumed_quantities))}. "
            "Please correct these if they are wrong.", "data", SRC_INPUT))
    if f.estimated_deadline_items:
        names = list(f.estimated_deadline_items)
        s.append(Statement(
            f"For {_listed(names[:MAX_LISTED], len(names))} you did not give a use-by date, so the date used is an "
            "estimate from typical shelf life. Check the food itself before relying on it.", "data", SRC_INPUT))
    return Section("caveats", "Worth knowing", tuple(s))
