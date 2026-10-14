"""Streamlit layout for the prototype: one function per screen area. No decisions are made here.

Every number and sentence shown comes from ``PantryToPlateService`` results (``PlannedWeek`` and friends); the helpers
in ``ui.logic`` decide what marks and choices mean; ``ui.theme`` owns the look. A view reads, lays out, and reports
what the user did.

Layout principles (the redesign of 2026-10-13)
----------------------------------------------
* **One question per screen area.** Kitchen → check it → your week, with a step strip showing where you are.
* **Progressive disclosure.** A dinner card shows the name, a few chips and the day mark; reasons, ingredients and
  steps open on demand. The profile lives in collapsible sidebar groups.
* **Signal, not decoration.** Chip colours carry meaning: green = on target / from your pantry, terracotta = worth a
  look (outside your calorie range, over your weeknight time). Never colour alone: the chip text says it too.

State (``st.session_state``)
----------------------------
``review_id``  bumps with every new reading of the pantry text, so widget keys never leak between readings
``entries`` / ``originals``  the editable rows, and the rows as first parsed (to restore "we estimate")
``week``  the current ``PlannedWeek`` (replaced on every re-plan);  ``week_id`` bumps with it
``reworded``  an LLM-reworded copy of the week;  ``read_requested``  set by the example button's callback
"""
from __future__ import annotations

from datetime import date

import pandas as pd
import streamlit as st

from app.models import ENTRY_ASSUMED, ENTRY_NO_AMOUNT, ENTRY_UNSAFE, DayPlan, PantryEntry, PlannedWeek
from app.service import PantryToPlateService
from domain.models import ALLERGENS, HORIZON_DAYS, Diet
from explain.facts import KCAL_IN_RANGE
from explain.render import TERM_LABELS, fmt_g
from ui import logic, theme

KIND_ICON = {"ok": "✅", "assumed": "🟡", "choose": "❓", "unknown": "❌", "amount": "❓", "unsafe": "⚠️"}
DIET_ICON = {"vegetarian": "🥕", "omnivore": "🍽️", "pescatarian": "🐟", "vegan": "🌱"}


def _html(markup: str, where=None) -> None:
    (where or st).markdown(markup, unsafe_allow_html=True)


# ==================================================================================================================
# sidebar: who is cooking
# ==================================================================================================================
def sidebar_profile(service: PantryToPlateService) -> tuple[dict, bool]:
    """Render the profile form; return the raw values for ``service.build_profile`` and the LLM switch."""
    sb = st.sidebar
    sb.markdown("## 👋 About you")
    sb.caption("Tell us once; every plan respects it.")

    with sb.expander("🥗  Diet & allergies", expanded=True):
        diet = st.selectbox("Diet", [d.value for d in Diet], key="diet",
                            format_func=lambda d: f"{DIET_ICON.get(d, '')} {d.title()}".strip())
        allergens = st.multiselect("Allergies — never planned", list(ALLERGENS), key="allergens",
                                   format_func=lambda a: a.replace("_", " ").title())
        col1, col2 = st.columns(2)
        avoid_pork = col1.checkbox("No pork", key="avoid_pork")
        avoid_alcohol = col2.checkbox("No alcohol", key="avoid_alcohol")

    with sb.expander("😋  Tastes"):
        cuisines = service.cuisines()
        liked = st.multiselect("Cuisines I love", cuisines, key="liked_cuisines", format_func=_pretty)
        disliked = st.multiselect("Cuisines I'd skip", cuisines, key="disliked_cuisines", format_func=_pretty)
        liked_foods = st.text_input("Foods I like", key="liked_foods", placeholder="basil, mushrooms")
        disliked_foods = st.text_input("Foods I dislike", key="disliked_foods", placeholder="cilantro")
        never_foods = st.text_input("Never serve me", key="never_foods", placeholder="liver")

    with sb.expander("🎯  Targets"):
        kcal = st.number_input("Calories per day", 1200, 4500, 2000, step=50, key="daily_kcal")
        protein = st.number_input("Protein per dinner (g)", 0, 100, 20, step=5, key="min_protein")
        minutes = st.slider("Weeknight cooking time (min)", 10, 120, 45, step=5, key="weekday_minutes")

    with sb.expander("⚙️  Advanced"):
        use_llm = st.checkbox("Use the local language model when it is running", value=True, key="use_llm",
                              help="Re-reads pantry text the rules cannot understand and can reword the "
                                   "explanations. Everything works without it.")
    return dict(diet=diet, allergens=allergens, avoid_pork=avoid_pork, avoid_alcohol=avoid_alcohol,
                liked_cuisines=liked, disliked_cuisines=disliked, liked_foods=_split(liked_foods),
                disliked_foods=_split(disliked_foods), excluded_foods=_split(never_foods),
                daily_kcal_target=float(kcal), min_protein_g_per_dinner=float(protein),
                max_weekday_minutes=int(minutes)), use_llm


# ==================================================================================================================
# step 1: the pantry
# ==================================================================================================================
def pantry_step(service: PantryToPlateService, today: date) -> list[PantryEntry]:
    """Text box -> editable review rows. Returns the rows that will be planned with."""
    _html(theme.section_html("What's in your kitchen?", "Write it the way you'd say it."))
    st.text_area("Your pantry", key="pantry_text", height=120, label_visibility="collapsed",
                 placeholder="e.g. half a bag of spinach going off, 500g chicken breast, 6 eggs, leftover rice…")
    left, middle, _ = st.columns([1.1, 1.1, 3])
    read_clicked = left.button("✨ Read my pantry", type="primary", key="read_pantry")
    # a callback, not an `if`: it runs before the text area is created, which is the only time Streamlit allows its
    # value to be set (assigning to a widget's key after it exists raises StreamlitAPIException). It only queues the
    # read, so the work happens below, inside a spinner.
    middle.button("🎲 Try an example", key="use_example", on_click=_queue_example)
    if read_clicked or st.session_state.pop("read_requested", False):
        with st.spinner("Reading your pantry… if the language model has to wake up, the first read can take up to "
                        "half a minute."):
            _load_review(service, st.session_state.get("pantry_text", ""), today)

    entries: list[PantryEntry] = st.session_state.get("entries") or []
    if not entries:
        if st.session_state.get("review_id", 0):
            st.info("Nothing was recognised. Try naming foods, e.g. “spinach, 2 eggs, rice”, or add items below.")
            if st.session_state.get("unparsed"):
                st.caption("We could not make sense of: "
                           + "; ".join(f"“{u}”" for u in st.session_state["unparsed"]))
        _add_item_form(service, today)
        return []

    usable = sum(1 for e in entries if e.usable)
    attention = sum(1 for e in entries if not e.usable)
    _html(theme.section_html("Check what we understood",
                             f"{usable} ready" + (f" · {attention} need a look" if attention else "")))
    if st.session_state.get("unparsed"):
        st.caption("We could not make sense of: " + "; ".join(f"“{u}”" for u in st.session_state["unparsed"]))
    originals: list[PantryEntry] = st.session_state["originals"]
    review_id = st.session_state["review_id"]
    updated: list[PantryEntry] = []
    changed_status = False
    for i, entry in enumerate(entries):
        new, flipped = _entry_row(service, i, entry, originals[i], review_id, today)
        changed_status = changed_status or flipped
        updated.append(new)
    st.session_state["entries"] = updated

    _add_item_form(service, today)
    if changed_status:
        st.rerun()
    return [e for i, e in enumerate(updated) if e.usable and st.session_state.get(f"use_{review_id}_{i}", True)]


def _queue_example() -> None:
    """Button callback: put the example in the text box and ask for it to be read on this run."""
    st.session_state["pantry_text"] = logic.EXAMPLE_PANTRY
    st.session_state["read_requested"] = True


def _load_review(service: PantryToPlateService, text: str, today: date) -> None:
    review = service.review_pantry(text, today=today)
    st.session_state["review_id"] = st.session_state.get("review_id", 0) + 1
    st.session_state["entries"] = list(review.entries)
    st.session_state["originals"] = [e.model_copy(deep=True) for e in review.entries]
    st.session_state["unparsed"] = list(review.unparsed)
    st.session_state.pop("week", None)
    st.session_state.pop("reworded", None)


def _entry_row(service: PantryToPlateService, i: int, entry: PantryEntry, original: PantryEntry, review_id: int,
               today: date) -> tuple[PantryEntry, bool]:
    """One review row. Returns ``(possibly edited entry, whether its status changed)``."""
    kind, text = logic.status_label(entry)
    key = f"{review_id}_{i}"
    card = f"pantryrow_attn_{i}_{review_id}" if not entry.usable else f"pantryrow_{i}_{review_id}"
    with st.container(border=True, key=card):
        if logic.needs_choice(entry):
            return _choice_row(service, entry, key, kind, text, today)

        if entry.status == ENTRY_UNSAFE:                       # shown, never planned with, nothing to edit
            st.markdown(f"{KIND_ICON.get(kind, '•')} **{entry.name or entry.raw_text}**  \n:gray[{text}]")
            return entry, False

        c_name, c_amt, c_use, c_keep = st.columns([3, 2, 3, 1.4], vertical_alignment="center")
        c_name.markdown(f"{KIND_ICON.get(kind, '•')} **{logic.display_name(entry.name or entry.raw_text)}**  \n"
                        f":gray[{text}]")
        shown = min(max(float(entry.grams), 0.1), 20000.0) if entry.grams else 100.0
        grams = c_amt.number_input("Amount (g)", min_value=0.1, max_value=20000.0, value=shown, step=10.0,
                                   format="%g", key=f"g_{key}")
        start = today.weekday()
        choices = logic.use_by_choices(start, HORIZON_DAYS, original)
        picked = c_use.selectbox("Use by", range(len(choices)), index=logic.current_use_by_index(entry, choices),
                                 format_func=lambda n: choices[n].label, key=f"u_{key}")
        c_keep.checkbox("Use it", value=True, key=f"use_{key}", help="Untick to leave this out of the plan")

        new = entry
        flipped = False
        if entry.grams is None:
            # a default was shown only so there is something to edit; it is OUR assumption and is labelled as one
            new = entry.model_copy(update={"grams": grams, "quantity_assumed": True, "status": ENTRY_ASSUMED,
                                           "problem": ""})
            flipped = True
        elif abs(grams - entry.grams) > 1e-6:
            new = new.with_grams(grams)
            flipped = True                       # the "amount assumed" label should disappear
        target = choices[picked]
        if logic.current_use_by_index(new, choices) != picked:
            new = logic.apply_use_by(new, original, target, HORIZON_DAYS)
        return new, flipped


def _choice_row(service: PantryToPlateService, entry: PantryEntry, key: str, kind: str, text: str,
                today: date) -> tuple[PantryEntry, bool]:
    """A row with no ingredient yet: pick one of the suggestions, or leave it out."""
    st.markdown(f"{KIND_ICON.get(kind, '•')} **“{entry.raw_text}”**  \n:gray[{entry.problem or text}]")
    options = [None] + [s.ingredient_id for s in entry.suggestions]
    names = {s.ingredient_id: s.name for s in entry.suggestions}
    picked = st.selectbox("Which one is it?", options, key=f"c_{key}", index=0,
                          format_func=lambda v: "Leave it out" if v is None else names[v].title())
    if picked is None:
        return entry, False
    chosen = service.choose_ingredient(entry, int(picked))
    if chosen.status == ENTRY_NO_AMOUNT:
        st.warning("Tell us how much you have.")
    return chosen, True


def _add_item_form(service: PantryToPlateService, today: date) -> None:
    with st.expander("➕  Add something we missed"):
        query = st.text_input("Search for an ingredient", key="add_query", placeholder="e.g. chickpeas")
        hits = service.search_ingredients(query, limit=6) if query else []
        names = {h.ingredient_id: h.name for h in hits}
        chosen = st.selectbox("Ingredient", [h.ingredient_id for h in hits], key="add_choice",
                              format_func=lambda v: names[v].title(), disabled=not hits)
        c1, c2 = st.columns(2)
        grams = c1.number_input("Amount (g)", 1.0, 20000.0, 200.0, step=10.0, key="add_grams")
        days = c2.selectbox("Use by", [None, 0, 1, 2, 3, 4, 5, 6], key="add_days",
                            format_func=lambda d: "Not sure" if d is None else logic.weekday_label(today.weekday(), d))
        if st.button("Add to my pantry", key="add_item", disabled=not hits):
            entry = service.add_pantry_entry(int(chosen), float(grams), days_left=days)
            entries = list(st.session_state.get("entries") or [])
            originals = list(st.session_state.get("originals") or [])
            entries.append(entry)
            originals.append(entry.model_copy(deep=True))
            st.session_state["entries"], st.session_state["originals"] = entries, originals
            st.session_state.setdefault("review_id", 1)       # keys are (review_id, row): the new row is last
            st.rerun()


# ==================================================================================================================
# step 2: the week
# ==================================================================================================================
def empty_week() -> None:
    """The placeholder shown before the first plan."""
    _html(theme.empty_state_html("🍽️", "Your week will appear here",
                                 "Tell us what's in your kitchen, then press Plan my week."))


def week_view(service: PantryToPlateService, week: PlannedWeek) -> PlannedWeek | None:
    """Render a plan. Returns a new ``PlannedWeek`` if the user re-planned, else ``None``."""
    facts = week.explanation.facts
    if not week.days:
        _html(theme.empty_state_html("🤔", "No plan fits these rules", week.overview.text))
        if week.rules is not None:
            st.markdown(week.rules.text)
        return None

    if week.day_offset:
        done = logic.weekday_label(week.scenario.start_weekday, 0, -week.day_offset)
        st.success(f"Re-planned. {week.day_offset} day{'s' if week.day_offset != 1 else ''} "
                   f"({done} onwards) are behind you; here are the {len(week.days)} that are left.", icon="🔄")
    if week.expired:
        gone = ", ".join(f"{fmt_g(g)} {n}" for n, g in sorted(week.expired.items(), key=lambda kv: -kv[1]))
        st.warning(f"Went off while days passed: {gone}.", icon="⏳")

    m = st.columns(4)
    m[0].metric("Dinners planned", f"{len(week.days)}")
    m[1].metric("Pantry food used", fmt_g(facts.pantry_consumed_g))
    m[2].metric("Extra items to buy", f"{week.grocery_box.n_items}")
    m[3].metric("In your calorie range", f"{facts.n_kcal_in_range} / {facts.n_dinners}")

    tab_week, tab_shop, tab_why, tab_rules = st.tabs(["🍽️ Your week", "🛒 Shopping list", "💡 Why this plan",
                                                      "📋 Rules & notes"])
    result: PlannedWeek | None = None
    with tab_week:
        result = _week_tab(service, week)
    with tab_shop:
        _shopping_tab(week)
    with tab_why:
        _why_tab(service, week)
    with tab_rules:
        _rules_tab(week)
    return result


def _week_tab(service: PantryToPlateService, week: PlannedWeek) -> PlannedWeek | None:
    wid = st.session_state.get("week_id", 0)
    marks = [_day_card(day, week, wid) for day in week.days]

    request = logic.build_replan_request([d.recipe_id for d in week.days], marks)
    rejected_names = [logic.display_name(d.name) for d in week.days if d.recipe_id in request.rejected]
    with st.container(border=True, key=f"card_replan_{wid}"):
        st.markdown("#### 🔄 Life happens")
        st.caption("Mark what you did on each dinner above, then re-plan the rest of the week from what's left.")
        (st.error if request.problem else st.info)(request.describe(rejected_names))
        if st.button("Re-plan the remaining days", type="primary", key="replan", disabled=not request.ok):
            with st.spinner("Re-planning from what is left in your kitchen…"):
                return service.replan(week, cooked=list(request.cooked), rejected=list(request.rejected))
    return None


def _day_chips(day: DayPlan, week: PlannedWeek) -> list[tuple[str, str]]:
    """What a glance at a dinner should tell you, coloured by whether it is on target."""
    f = week.explanation.facts.days[day.day]
    chips = [(f"⏱ {day.minutes} min", "warn" if f.minutes_over > 0 else ""),
             (f"🔥 {day.kcal:.0f} kcal", "good" if f.kcal_status == KCAL_IN_RANGE else "warn"),
             (f"💪 {day.protein_g:.0f} g protein", "warn" if f.protein_gap_g > 0 else "good")]
    if f.pantry_uses:
        n = len(f.pantry_uses)
        chips.append((f"🥫 uses {n} pantry item{'s' if n != 1 else ''}", "good"))
    if day.cuisine:
        chips.append((day.cuisine.replace("-", " ").title(), ""))
    return chips


def _day_card(day: DayPlan, week: PlannedWeek, wid: int) -> str:
    """One dinner. Returns the mark the user has chosen for it."""
    with st.container(border=True, key=f"daycard_{day.day}_{wid}"):
        head, mark_col = st.columns([3, 2], vertical_alignment="top")
        _html(theme.day_label_html(day.weekday), head)
        head.markdown(f"### {logic.display_name(day.name)}")
        _html(theme.chips_html(_day_chips(day, week)), head)
        mark = mark_col.radio("How did it go?", logic.DAY_MARKS, horizontal=True, key=f"mark_{wid}_{day.day}",
                              label_visibility="collapsed")

        with st.expander("💡 Why this dinner"):
            section = day.explanation
            if section.source == "llm":
                st.write(section.text)
                st.caption("Reworded by the language model; every number and food was checked against the facts.")
            else:
                for statement in section.statements[1:]:        # the first sentence repeats the header
                    st.markdown(f"- {statement.text}")
        left, right = st.columns(2)
        with left.expander("🧺 Ingredients"):
            rows = [{"Ingredient": logic.display_name(l.name), "Amount": fmt_g(l.grams),
                     "From": ("staple" if l.staple else _source(l)),
                     "Use by": (logic.weekday_label(week.scenario.start_weekday, l.use_by_day, 0)
                                + ("" if l.deadline_known else " (est.)")) if l.use_by_day is not None else ""}
                    for l in day.ingredients]
            st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
        with right.expander("👩‍🍳 How to cook it"):
            if day.steps:
                for n, step in enumerate(day.steps, 1):
                    st.markdown(f"{n}. {step}")
            else:
                st.caption("No instructions are available for this recipe.")
    return mark


def _source(line) -> str:
    if line.from_pantry_g > 0 and line.to_buy_g > 0:
        return f"{fmt_g(line.from_pantry_g)} pantry + {fmt_g(line.to_buy_g)} buy"
    return "pantry" if line.from_pantry_g > 0 else "buy"


def _shopping_tab(week: PlannedWeek) -> None:
    box = week.grocery_box
    if not box.items:
        _html(theme.empty_state_html("🎉", "Nothing to buy",
                                     "Everything is already in your kitchen or among the staples we assume you have."))
        return
    st.caption(f"{box.n_items} items, {fmt_g(box.total_g)} in total. Tick things off as you shop.")
    main = [i for i in box.items if not i.minor]
    pinches = [i for i in box.items if i.minor]
    by_group: dict[str, list] = {}
    for item in sorted(main, key=lambda i: i.name):
        by_group.setdefault(item.food_group, []).append(item)
    cols = st.columns(2)
    for n, group in enumerate(sorted(by_group)):
        with cols[n % 2].container(border=True, key=f"card_shop_{group}_{week.scenario.scenario_id}"):
            st.markdown(f"**{theme.group_icon(group)} {group.replace('_', ' ').title()}**")
            for item in by_group[group]:
                st.checkbox(f"{logic.display_name(item.name)} — {fmt_g(item.grams)} · {item.weekday}",
                            key=f"shop_{item.ingredient_id}_{week.scenario.scenario_id}")
    if pinches:
        with st.expander(f"🧂 Pinches and dashes ({len(pinches)})"):
            st.write(", ".join(f"{i.name} ({fmt_g(i.grams)})" for i in pinches))
    st.download_button("⬇️ Download the list", _shopping_text(week), file_name="shopping-list.txt", key="dl_list")


def _shopping_text(week: PlannedWeek) -> str:
    lines = ["Pantry to Plate - shopping list", ""]
    for group, items in week.grocery_box.by_group().items():
        lines.append(group.replace("_", " ").title())
        lines += [f"  [ ] {i.name.title()} - {fmt_g(i.grams)} (needed {i.weekday})" for i in items]
        lines.append("")
    return "\n".join(lines)


def _why_tab(service: PantryToPlateService, week: PlannedWeek) -> None:
    st.markdown("#### The week in one paragraph")
    overview = week.overview
    st.write(overview.text)
    if overview.source == "llm":
        st.caption("Reworded by the language model; checked against the facts.")
    solver = week.explanation.facts.solver
    if solver is not None and sum(solver.terms.values()) > 0:
        total = sum(solver.terms.values())
        frame = pd.DataFrame({"Share of the plan's remaining cost (%)": {
            TERM_LABELS[t]: round(100 * v / total, 1) for t, v in solver.terms.items()}})
        st.markdown("#### What still costs this plan the most")
        st.bar_chart(frame, horizontal=True, color=theme.GREEN)
        st.caption("By the planner's own scoring. A larger bar is a trade-off the plan could not avoid, "
                   "not a mistake: it is what your pantry, rules and targets left open.")
    if service.llm_available():
        if st.button("✍️ Reword the explanations with the language model (about 20 s)", key="reword"):
            with st.spinner("Rewording and checking every fact…"):
                st.session_state["reworded"] = service.reword(week)
            st.rerun()
    else:
        st.caption("The language model is not running; explanations use the built-in wording.")


def _rules_tab(week: PlannedWeek) -> None:
    if week.rules is not None:
        st.markdown("#### Your rules")
        st.write(week.rules.text)
    if week.caveats is not None:
        st.markdown("#### Worth knowing")
        st.write(week.caveats.text)
    if week.rules is None and week.caveats is None:
        st.write("No rules were set and nothing about your pantry needs a caveat.")


# ==================================================================================================================
# helpers
# ==================================================================================================================
def _pretty(value: str) -> str:
    return value.replace("-", " ").title()


def _split(text: str) -> list[str]:
    return [p.strip() for p in text.split(",") if p.strip()]
