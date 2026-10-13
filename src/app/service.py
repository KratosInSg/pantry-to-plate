"""``PantryToPlateService`` - the one object a UI talks to.

Why a facade
------------
A prototype UI needs about eight things: free text -> reviewable pantry rows, a profile, a plan, the reasons, a grocery
list, cooking steps, and "I did not cook that / reject this" re-planning. Doing that straight against the packages means
importing ``nlp``, ``domain``, ``optimizer``, ``explain`` and ``knowledge`` and knowing the order to call them in. This
class is that order, written once and tested, so the UI is only layout.

It decides nothing. Planning is ``optimizer``, reasons are ``explain``; this class parses input, calls them in order,
and shapes the results for display. Everything it returns is derived from the same inventory replay the evaluation uses.

Typical use::

    service = PantryToPlateService(llm=LlmClient())          # llm is optional; everything works without it
    review = service.review_pantry("spinach going off, 500g chicken, 6 eggs, a tub of kimchi")
    # ... the UI shows review.entries; the user fixes rows ...
    pantry = service.pantry_items(review.entries)
    profile = service.build_profile(diet="vegetarian", allergens=["peanut"], liked_cuisines=["italian"]).profile
    week = service.plan_week(service.make_scenario(profile, pantry))
    # ... later, day 0 was cooked, day 1 skipped, and the user rejected Wednesday's dinner:
    week = service.replan(week, cooked=[week.days[0].recipe_id, None], rejected=[week.days[2].recipe_id])
"""
from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field, replace
from datetime import date

from rapidfuzz import fuzz, process

from app.grocery import build_grocery_box
from app.models import (ENTRY_ASSUMED, ENTRY_CHOOSE, ENTRY_NO_AMOUNT, ENTRY_OK, ENTRY_UNKNOWN, ENTRY_UNSAFE, DayPlan,
                        IngredientChoice, IngredientLine, PantryEntry, PantryReview, PlannedWeek)
from domain.models import ALLERGENS, HORIZON_DAYS, Diet, PantryItem, Scenario, UserProfile, WeekPlan
from domain.pantry import (SKIP_AMBIGUOUS, SKIP_NO_AMOUNT, SKIP_UNKNOWN, SKIP_UNSAFE, make_pantry_item,
                           merge_pantry_items, pantry_from_parse)
from explain.facts import build_facts
from explain.paraphrase import Paraphraser, build_paraphraser, paraphrase_explanation
from explain.render import Explanation, render
from llm.client import LlmClient
from nlp.pantry_parser import PantryParser
from nlp.llm_fallback import parser_with_llm
from nlp.resolver import IngredientResolver, normalise_name
from nlp.schemas import MatchStatus, ParsedItem, ParseResult, Urgency
from optimizer.candidates import ShortlistConfig
from optimizer.inventory import account_inventory, visible_deadlines
from optimizer.planning import PlanningContext, make_context
from optimizer.replan import roll_forward
from optimizer.weekly import DEFAULT_WEIGHTS, OptimizerWeights, WeeklyPlanner

DEFAULT_SHORTLIST = 120          # candidate recipes handed to the solver (~6 s per plan; see optimizer/weekly.py)
DEFAULT_TIME_LIMIT_S = 8.0
DEFAULT_GAP = 0.02

_PROBLEMS = {
    ENTRY_UNKNOWN: "We do not recognise this one. Pick the closest ingredient or leave it out.",
    ENTRY_CHOOSE: "Several ingredients could match. Which did you mean?",
    ENTRY_NO_AMOUNT: "How much do you have?",
    ENTRY_UNSAFE: "This may not be safe to eat, so it was left out of the plan.",
}
_STATUS_OF_SKIP = {SKIP_UNKNOWN: ENTRY_UNKNOWN, SKIP_AMBIGUOUS: ENTRY_CHOOSE, SKIP_NO_AMOUNT: ENTRY_NO_AMOUNT,
                   SKIP_UNSAFE: ENTRY_UNSAFE}


@dataclass(frozen=True)
class NameResolution:
    """Outcome of resolving food names typed into a preference field."""

    ids: dict[str, int] = field(default_factory=dict)                   # typed name -> ingredient id (confident)
    unresolved: list[str] = field(default_factory=list)                 # names with no plausible match
    ambiguous: dict[str, list[IngredientChoice]] = field(default_factory=dict)   # name -> candidates to pick from


@dataclass(frozen=True)
class ProfileBuild:
    """A profile plus whatever in the form could not be understood (the UI shows these next to the field)."""

    profile: UserProfile
    resolution: NameResolution
    notes: list[str] = field(default_factory=list)


class PantryToPlateService:
    """Parse, plan, explain, re-plan. Construct once and reuse: it caches the dataset and the parser index."""

    def __init__(self, ctx: PlanningContext | None = None, llm: LlmClient | None = None,
                 weights: OptimizerWeights = DEFAULT_WEIGHTS, shortlist_size: int = DEFAULT_SHORTLIST,
                 time_limit_s: float = DEFAULT_TIME_LIMIT_S, mip_rel_gap: float = DEFAULT_GAP,
                 backend: str = "highs") -> None:
        """
        Args:
            ctx: planning context; the default dataset is loaded if omitted.
            llm: an LLM client, or ``None``. It is only ever used to re-read pantry text the rules could not
                understand and to reword explanations (validated); every feature works without it.
            weights, shortlist_size, time_limit_s, mip_rel_gap, backend: passed to the weekly optimiser.
        """
        self.ctx = ctx or make_context()
        self._llm = llm
        self._resolver = IngredientResolver(self.ctx.store)
        self._parser: PantryParser = parser_with_llm(llm, store=self.ctx.store, resolver=self._resolver)
        self._planner = WeeklyPlanner(self.ctx, weights, shortlist_config=ShortlistConfig(size=shortlist_size),
                                      time_limit_s=time_limit_s, mip_rel_gap=mip_rel_gap, backend=backend)
        self._paraphraser: Paraphraser | None = None
        self._paraphraser_tried = False

    # ------------------------------------------------------------------------------------------------ vocabulary
    def cuisines(self) -> list[str]:
        """Every cuisine in the recipe pool, sorted - for a dropdown (so a typo cannot reach the scorer)."""
        return sorted({c for c in self.ctx.catalog.cuisine if c})

    def search_ingredients(self, query: str, limit: int = 8) -> list[IngredientChoice]:
        """Autocomplete: canonical ingredients matching ``query`` (prefix matches first, then fuzzy)."""
        q = normalise_name(query)
        if len(q) < 2:
            return []
        aliases, id_tuples = self.ctx.store.fuzzy_candidates
        hits = process.extract(q, aliases, scorer=fuzz.WRatio, limit=60, score_cutoff=62)
        ranked = sorted(hits, key=lambda h: (not aliases[h[2]].startswith(q), -h[1]))
        out: list[IngredientChoice] = []
        seen: set[int] = set()
        for alias, score, idx in ranked:
            ids = id_tuples[idx]
            if len(ids) != 1 or ids[0] in seen:
                continue                                     # "salt and pepper" style splits are not one ingredient
            info = self.ctx.store.ingredient(ids[0])
            if info is None:
                continue
            seen.add(ids[0])
            out.append(IngredientChoice(ingredient_id=ids[0], name=info.canonical_name, score=round(score / 100, 3)))
            if len(out) >= limit:
                break
        return out

    def resolve_names(self, names: Iterable[str]) -> NameResolution:
        """Map typed food names ("basil", "peenut butter") to ingredient ids, flagging what could not be resolved."""
        ids: dict[str, int] = {}
        unresolved: list[str] = []
        ambiguous: dict[str, list[IngredientChoice]] = {}
        for raw in names:
            name = raw.strip()
            if not name:
                continue
            res = self._resolver.resolve(name)
            if res.status is MatchStatus.MATCHED and len(res.ingredient_ids) == 1:
                ids[name] = res.ingredient_ids[0]
            elif res.suggestions:
                ambiguous[name] = [IngredientChoice(ingredient_id=s.ingredient_id, name=s.canonical_name,
                                                    score=s.score) for s in res.suggestions]
            else:
                found = self.search_ingredients(name, limit=3)
                if found:
                    ambiguous[name] = found
                else:
                    unresolved.append(name)
        return NameResolution(ids=ids, unresolved=unresolved, ambiguous=ambiguous)

    # ------------------------------------------------------------------------------------------------ the profile
    def build_profile(self, *, diet: str = "omnivore", allergens: Iterable[str] = (), avoid_pork: bool = False,
                      avoid_alcohol: bool = False, liked_cuisines: Iterable[str] = (),
                      disliked_cuisines: Iterable[str] = (), liked_foods: Iterable[str] = (),
                      disliked_foods: Iterable[str] = (), excluded_foods: Iterable[str] = (),
                      excluded_recipe_ids: Iterable[int] = (), daily_kcal_target: float = 2000.0,
                      dinner_kcal_share: float = 0.30, kcal_tolerance: float = 0.20,
                      min_protein_g_per_dinner: float = 20.0, max_weekday_minutes: int = 45,
                      max_total_minutes: int | None = None, dinner_only: bool = True) -> ProfileBuild:
        """Build a validated :class:`UserProfile` from plain form values.

        Food fields take *names*; names that cannot be matched are reported in ``resolution`` and left out (never
        silently turned into a different food). ``dinner_only`` (on by default for the app) leaves out breakfast
        dishes, doughs and batters that the dataset's "main-dish" tag lets through; the explanation says how many.

        Raises:
            ValueError: an unknown diet / allergen / cuisine, or a number outside its allowed range. The message
                says what is allowed.
        """
        try:
            diet_value = Diet(diet.strip().lower())
        except ValueError:
            raise ValueError(f"unknown diet {diet!r}; choose from {[d.value for d in Diet]}") from None
        allergen_set = frozenset(a.strip().lower().replace(" ", "_") for a in allergens)
        unknown_allergens = allergen_set - set(ALLERGENS)
        if unknown_allergens:
            raise ValueError(f"unknown allergen(s) {sorted(unknown_allergens)}; choose from {list(ALLERGENS)}")
        known_cuisines = set(self.cuisines())
        liked_c = frozenset(c.strip().lower() for c in liked_cuisines)
        disliked_c = frozenset(c.strip().lower() for c in disliked_cuisines)
        bad = (liked_c | disliked_c) - known_cuisines
        if bad:
            raise ValueError(f"unknown cuisine(s) {sorted(bad)}; choose from the list returned by cuisines()")

        liked, disliked, excluded = list(liked_foods), list(disliked_foods), list(excluded_foods)
        res = self.resolve_names(liked + disliked + excluded)
        notes = [f"could not find '{n}' - it was left out" for n in res.unresolved]
        notes += [f"'{n}' is ambiguous - pick one of the suggestions" for n in res.ambiguous]

        def ids_of(names: list[str]) -> frozenset[int]:
            return frozenset(res.ids[n.strip()] for n in names if n.strip() in res.ids)

        profile = UserProfile(
            diet=diet_value, allergens=allergen_set, avoid_pork=avoid_pork, avoid_alcohol=avoid_alcohol,
            excluded_ingredient_ids=ids_of(excluded), excluded_recipe_ids=frozenset(int(r) for r in excluded_recipe_ids),
            max_total_minutes=max_total_minutes, dinner_only=dinner_only, liked_ingredient_ids=ids_of(liked),
            disliked_ingredient_ids=ids_of(disliked), liked_cuisines=liked_c, disliked_cuisines=disliked_c,
            max_weekday_minutes=max_weekday_minutes, daily_kcal_target=daily_kcal_target,
            dinner_kcal_share=dinner_kcal_share, kcal_tolerance=kcal_tolerance,
            min_protein_g_per_dinner=min_protein_g_per_dinner)
        return ProfileBuild(profile=profile, resolution=res, notes=notes)

    # ------------------------------------------------------------------------------------------------ the pantry
    def review_pantry(self, text: str, today: date | None = None, horizon_days: int = HORIZON_DAYS) -> PantryReview:
        """Parse free text into rows the user can confirm or fix. Never raises for odd input."""
        parse = self._parser.parse(text, today)
        entries = [self._entry_for(item, horizon_days) for item in parse.items]
        return PantryReview(source_text=text, entries=entries, unparsed=list(parse.unparsed))

    def add_pantry_entry(self, ingredient_id: int, grams: float, days_left: int | None = None, urgent: bool = False,
                         horizon_days: int = HORIZON_DAYS) -> PantryEntry:
        """A row added by hand. ``days_left`` is a use-by the user gave (0 = today); without it the deadline is the
        FoodKeeper estimate and is marked as an estimate."""
        if grams <= 0:
            raise ValueError("amount must be positive")
        info = self.ctx.store.ingredient(ingredient_id)
        if info is None:
            raise ValueError(f"unknown ingredient id {ingredient_id}")
        item = make_pantry_item(ingredient_id, grams, self.ctx.store, days_left=days_left,
                                urgency=Urgency.URGENT if urgent else Urgency.NONE, horizon_days=horizon_days)
        return self._entry_from_item(item, name=info.canonical_name, days_left=days_left, explicit=days_left is not None)

    def choose_ingredient(self, entry: PantryEntry, ingredient_id: int, horizon_days: int = HORIZON_DAYS) -> PantryEntry:
        """The user picked which ingredient a "did you mean?" row is. Needs an amount (assumed or given)."""
        info = self.ctx.store.ingredient(ingredient_id)
        if info is None:
            raise ValueError(f"unknown ingredient id {ingredient_id}")
        if entry.grams is None or entry.grams <= 0:
            return entry.model_copy(update={"ingredient_id": ingredient_id, "name": info.canonical_name,
                                            "status": ENTRY_NO_AMOUNT, "problem": _PROBLEMS[ENTRY_NO_AMOUNT],
                                            "suggestions": []})
        item = make_pantry_item(ingredient_id, entry.grams, self.ctx.store, days_left=entry.days_left_hint,
                                urgency=entry.urgency, horizon_days=horizon_days,
                                days_left_explicit=entry.days_left_explicit)
        chosen = self._entry_from_item(item, name=info.canonical_name, days_left=entry.days_left_hint,
                                       explicit=entry.days_left_explicit)
        return chosen.model_copy(update={"raw_text": entry.raw_text, "quantity_assumed": entry.quantity_assumed,
                                         "status": ENTRY_ASSUMED if entry.quantity_assumed else ENTRY_OK,
                                         "warnings": list(entry.warnings)})

    @staticmethod
    def pantry_items(entries: Iterable[PantryEntry]) -> list[PantryItem]:
        """The planner's pantry from the (possibly edited) review rows: usable rows only, duplicates merged."""
        return merge_pantry_items([e.to_pantry_item() for e in entries if e.usable])

    def _entry_for(self, item: ParsedItem, horizon_days: int) -> PantryEntry:
        """One parsed item -> one review row, using the same deadline ladder the planner uses."""
        build = pantry_from_parse(ParseResult(source_text=item.raw_text, items=[item]), self.ctx.store, horizon_days)
        suggestions = [IngredientChoice(ingredient_id=s.ingredient_id, name=s.canonical_name, score=s.score)
                       for s in item.suggestions]
        common = dict(raw_text=item.raw_text, grams=item.grams, quantity_assumed=item.quantity_is_assumed,
                      days_left_hint=item.days_left_hint, days_left_explicit=item.days_left_explicit,
                      urgency=item.urgency, suggestions=suggestions, warnings=list(item.warnings))
        if build.items:
            p = build.items[0]
            return PantryEntry(**{**common, "ingredient_id": p.ingredient_id, "name": item.canonical_name,
                                  "grams": p.grams, "last_use_day": p.last_use_day, "expiry_known": p.expiry_known,
                                  "expiry_confidence": p.expiry_confidence,
                                  "status": ENTRY_ASSUMED if p.quantity_assumed else ENTRY_OK})
        _, reason = build.skipped[0]
        status = _STATUS_OF_SKIP.get(reason, ENTRY_UNKNOWN)
        if status in (ENTRY_UNKNOWN, ENTRY_CHOOSE) and not common["suggestions"]:
            common["suggestions"] = self.search_ingredients(item.name_text, limit=3)    # "kimchi" -> "cabbage kimchi"
        # an ambiguous / unrecognised row has no ingredient yet; the user picks one of the suggestions
        return PantryEntry(**{**common, "ingredient_id": None, "name": None, "status": status,
                              "problem": _PROBLEMS.get(status, reason)})

    @staticmethod
    def _entry_from_item(item: PantryItem, name: str, days_left: int | None, explicit: bool) -> PantryEntry:
        return PantryEntry(ingredient_id=item.ingredient_id, name=name, grams=item.grams,
                           last_use_day=item.last_use_day, expiry_known=item.expiry_known,
                           expiry_confidence=item.expiry_confidence, days_left_hint=days_left,
                           days_left_explicit=explicit, urgency=item.urgency, status=ENTRY_OK)

    # ------------------------------------------------------------------------------------------------ planning
    @staticmethod
    def make_scenario(profile: UserProfile, pantry: Sequence[PantryItem], today: date | None = None,
                      horizon_days: int = HORIZON_DAYS, scenario_id: str = "app") -> Scenario:
        """The planning problem: this user, this pantry, starting today (so weekday names are right)."""
        weekday = (today or date.today()).weekday()
        return Scenario(scenario_id=scenario_id, family="app", profile=profile, pantry=list(pantry),
                        horizon_days=horizon_days, start_weekday=weekday)

    def plan_week(self, scenario: Scenario, paraphrase: bool = False) -> PlannedWeek:
        """Plan, explain and present. ``paraphrase=True`` also asks the LLM to reword the reasons (~20 s; validated,
        and the template text is kept wherever a rewrite is rejected or the model is unavailable)."""
        plan = self._planner.plan(scenario)
        return self._present(scenario, plan, paraphrase=paraphrase)

    def reword(self, planned: PlannedWeek) -> PlannedWeek:
        """Reword an already-planned week's reasons with the LLM. A no-op if the model is not reachable."""
        paraphraser = self._get_paraphraser()
        if paraphraser is None:
            return planned
        explanation = paraphrase_explanation(planned.explanation, paraphraser)
        days = tuple(replace(d, explanation=explanation.section(f"day:{d.day}") or d.explanation) for d in planned.days)
        return replace(planned, explanation=explanation, days=days)

    def replan(self, planned: PlannedWeek, cooked: Sequence[int | None] = (), rejected: Iterable[int] = (),
               paraphrase: bool = False) -> PlannedWeek:
        """Re-plan the days that are left, from the current pantry.

        Args:
            planned: the week being lived.
            cooked: for each day that has passed, the recipe id actually cooked, or ``None`` if it was skipped.
                ``cooked=[]`` re-plans the whole week (e.g. after rejecting a dinner before cooking anything).
            rejected: recipe ids the user does not want. They are excluded from every remaining day (and stay
                excluded through later re-plans, because the exclusion lives in the carried scenario's profile).
            paraphrase: as for :meth:`plan_week`.

        Past days are never touched: they are outside the new problem. Food a skipped or rejected dinner would
        have used is still in the pantry, one day closer to its deadline, which is what the waste term chases.
        """
        rolled = roll_forward(planned.scenario, cooked, self.ctx)
        scenario = rolled.scenario
        rejected_ids = frozenset(int(r) for r in rejected)
        if rejected_ids:
            profile = scenario.profile.model_copy(update={
                "excluded_recipe_ids": scenario.profile.excluded_recipe_ids | rejected_ids})
            scenario = scenario.model_copy(update={"profile": profile})
        plan = self._planner.plan(scenario)
        expired = {self._name(i): g for i, g in rolled.expired_g.items()}
        return self._present(scenario, plan, paraphrase=paraphrase, day_offset=planned.day_offset + rolled.elapsed_days,
                             expired=expired)

    # ------------------------------------------------------------------------------------------------ LLM
    def llm_available(self) -> bool:
        """Whether a language model is configured and reachable right now."""
        available = getattr(self._llm, "is_available", None)
        return self._llm is not None and (not callable(available) or bool(available()))

    def _get_paraphraser(self) -> Paraphraser | None:
        if not self._paraphraser_tried:
            self._paraphraser = build_paraphraser(self._llm, self.ctx.store)
            self._paraphraser_tried = True
        return self._paraphraser

    # ------------------------------------------------------------------------------------------------ presentation
    def _name(self, ingredient_id: int) -> str:
        info = self.ctx.store.ingredient(ingredient_id)
        return info.canonical_name if info is not None else f"ingredient {ingredient_id}"

    def _present(self, scenario: Scenario, plan: WeekPlan, paraphrase: bool, day_offset: int = 0,
                 expired: dict[str, float] | None = None) -> PlannedWeek:
        ctx = self.ctx
        facts = build_facts(scenario, plan, ctx)
        explanation: Explanation = render(facts)
        if paraphrase:
            paraphraser = self._get_paraphraser()
            if paraphraser is not None:
                explanation = paraphrase_explanation(explanation, paraphraser)

        indices = [ctx.catalog.index_of(r) for r in plan.recipe_ids]
        deadlines = visible_deadlines(scenario.pantry, scenario.horizon_days)
        report = account_inventory(indices, scenario.pantry, ctx.catalog, deadlines, ctx.ignore_ids,
                                   scenario.horizon_days)

        days: list[DayPlan] = []
        for day, idx in enumerate(indices):
            info = ctx.catalog.info(idx)
            df = facts.days[day]
            uses = {u.name: u for u in df.pantry_uses}
            ids, grams = ctx.catalog.ingredients(idx)
            lines: list[IngredientLine] = []
            for iid, g in zip(ids.tolist(), grams.tolist()):
                name = self._name(iid)
                taken = report.uses_by_day[day].get(iid, 0.0)
                use = uses.get(name)
                lines.append(IngredientLine(
                    name=name, grams=float(g), from_pantry_g=float(taken),
                    to_buy_g=float(report.groceries_by_day[day].get(iid, 0.0)), staple=iid in ctx.ignore_ids,
                    use_by_day=use.last_use_day if use is not None else None,
                    deadline_known=use.deadline_known if use is not None else False))
            lines.sort(key=lambda l: (l.staple, -l.grams))
            days.append(DayPlan(
                day=day, weekday=df.weekday, recipe_id=info.recipe_id, name=info.name, minutes=info.minutes,
                cuisine=info.cuisine, kcal=info.kcal, protein_g=info.protein_g, fat_g=info.fat_g,
                carbohydrate_g=info.carbohydrate_g, ingredients=tuple(lines),
                steps=tuple(s[:1].upper() + s[1:] for s in ctx.catalog.steps(idx)),
                explanation=explanation.section(f"day:{day}")))

        return PlannedWeek(
            scenario=scenario, plan=plan, days=tuple(days),
            grocery_box=build_grocery_box(report, ctx.store, scenario.start_weekday), explanation=explanation,
            status=plan.status, complete=facts.complete, solve_seconds=float(plan.diagnostics.get("solve_seconds", 0.0)),
            day_offset=day_offset, expired=expired or {})
