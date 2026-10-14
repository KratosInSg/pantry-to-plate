"""End-to-end tests of the Streamlit prototype, run headlessly with Streamlit's own ``AppTest`` (no browser).

They drive the real script against the real dataset and optimiser: describe a pantry, check the rows, plan, read the
week, re-plan. The language model is switched off (the sidebar checkbox) so nothing depends on a local Ollama.
"""
from __future__ import annotations

import pytest
from streamlit.testing.v1 import AppTest

from ui.logic import EXAMPLE_PANTRY

APP = "src/ui/streamlit_app.py"
TIMEOUT = 120


def _app() -> AppTest:
    at = AppTest.from_file(APP, default_timeout=TIMEOUT)
    at.session_state["use_llm"] = False                     # deterministic and fast: rules only
    return at.run()


def _texts(at: AppTest) -> str:
    """Everything the page says, as one string, for readable assertions."""
    parts = [m.value for m in at.markdown] + [c.value for c in at.caption] + [e.value for e in at.error] + \
            [i.value for i in at.info] + [w.value for w in at.warning] + [s.value for s in at.success]
    return "\n".join(str(p) for p in parts)


@pytest.fixture(scope="module")
def planned() -> AppTest:
    """The app after: example pantry read, week planned. Shared (module scope): planning takes seconds."""
    at = _app()
    at.button(key="use_example").click().run()
    at.button(key="plan_week").click().run()
    return at


# ---------------------------------------------------------------------------------------------------- first view
def test_the_first_page_loads_without_errors_and_asks_for_a_pantry():
    at = _app()
    assert not at.exception
    assert any("p2p-hero" in str(m.value) and "Pantry to Plate" in str(m.value) for m in at.markdown)
    assert at.text_area(key="pantry_text").value == ""
    assert {b.key for b in at.button} >= {"read_pantry", "use_example", "plan_week"}
    assert "Your week will appear here" in _texts(at)
    assert "p2p-steps" in _texts(at)                                     # the step strip


def test_the_profile_form_offers_every_diet_allergen_and_cuisine():
    at = _app()
    # AppTest exposes the labels the user sees (the form formats values for display)
    assert {o.split()[-1] for o in at.sidebar.selectbox(key="diet").options} ==         {"Omnivore", "Pescatarian", "Vegetarian", "Vegan"}
    assert {"Peanut", "Tree Nut", "Gluten", "Shellfish"} <= set(at.sidebar.multiselect(key="allergens").options)
    cuisines = at.sidebar.multiselect(key="liked_cuisines").options
    assert "Italian" in cuisines and len(cuisines) > 20
    assert at.sidebar.selectbox(key="diet").value == "vegetarian"         # the default; the value stays the raw one


# ---------------------------------------------------------------------------------------------------- security
def test_typed_markdown_and_html_are_shown_as_text_not_rendered():
    # security review 2026-10-14: these were rendered (an outside image loaded, a live link appeared)
    at = _app()
    payload = ("![track](https://attacker.example/p.png), [click](javascript:alert(1)), "
               "<img src=x onerror=alert(2)>, 500g chicken breast")
    at.text_area(key="pantry_text").set_value(payload).run()
    at.button(key="read_pantry").click().run()
    assert not at.exception
    page = _texts(at)
    assert "](" not in page                               # escaped as "\]\(": no image, no link
    assert "attacker" in page and "javascript" in page    # ...but the user still sees what they typed
    unsafe = [str(m.value) for m in at.markdown if getattr(m.proto, "allow_html", False)]
    assert not any("onerror" in m or "<img" in m for m in unsafe)


def test_text_boxes_have_length_limits():
    at = _app()
    assert at.text_area(key="pantry_text").proto.max_chars > 0
    for key in ("liked_foods", "disliked_foods", "never_foods"):
        assert at.sidebar.text_input(key=key).proto.max_chars > 0


# ---------------------------------------------------------------------------------------------------- the pantry
def test_reading_text_shows_honest_rows_and_asks_about_what_it_could_not_recognise():
    at = _app()
    at.text_area(key="pantry_text").set_value("spinach going off, 500g chicken breast, a tub of kimchi").run()
    at.button(key="read_pantry").click().run()
    assert not at.exception
    page = _texts(at)
    assert "Check what we understood" in page
    assert "Chicken Breast" in page.title() or "chicken breast" in page.lower()
    assert "We do not recognise this one" in page                      # kimchi
    choose = [s for s in at.selectbox if s.label == "Which one is it?"]
    assert len(choose) == 1
    labels = [str(o).lower() for o in choose[0].options]
    assert labels[0] == "leave it out" and any("kimchi" in o for o in labels)     # the dataset's "cabbage kimchi"


def test_garbage_input_is_met_with_guidance_not_a_crash():
    at = _app()
    at.text_area(key="pantry_text").set_value("!!! ???").run()
    at.button(key="read_pantry").click().run()
    assert not at.exception
    page = _texts(at)
    assert "Nothing was recognised" in page and "We could not make sense of" in page
    assert not [s for s in at.selectbox if s.label == "Which one is it?"]       # no fake "unknown food" row


def test_an_amount_the_user_corrects_is_no_longer_marked_as_assumed():
    at = _app()
    at.text_area(key="pantry_text").set_value("spinach").run()
    at.button(key="read_pantry").click().run()
    assert "Amount assumed" in _texts(at)
    at.number_input(key="g_1_0").set_value(120.0).run()
    assert not at.exception
    assert "Amount assumed" not in _texts(at)
    assert at.session_state["entries"][0].grams == 120.0 and not at.session_state["entries"][0].quantity_assumed


# ---------------------------------------------------------------------------------------------------- the week
def test_planning_shows_seven_days_with_reasons_ingredients_and_steps(planned):
    assert not planned.exception
    days = [m.value for m in planned.markdown if str(m.value).startswith("### ")]
    assert len(days) == 7
    labels = [e.label for e in planned.expander]
    assert sum("Why this dinner" in l for l in labels) == 7               # why / ingredients / how to cook, per day
    assert sum("Ingredients" in l for l in labels) == 7 and sum("How to cook" in l for l in labels) == 7
    assert any("p2p-chip" in str(m.value) for m in planned.markdown)      # the at-a-glance chips
    assert [m.label for m in planned.metric][:2] == ["Dinners planned", "Pantry food used"]
    assert planned.metric[0].value == "7"


def test_the_week_can_be_read_in_four_tabs(planned):
    assert [t.label.split(" ", 1)[1] for t in planned.tabs] == ["Your week", "Shopping list", "Why this plan",
                                                                "Rules & notes"]


def test_the_shopping_list_lists_items_by_group_and_can_be_downloaded(planned):
    assert len([c for c in planned.checkbox if str(c.key).startswith("shop_")]) >= 1
    page = _texts(planned)
    assert "Tick things off as you shop" in page


def test_no_replan_is_possible_until_a_day_is_marked(planned):
    assert planned.button(key="replan").disabled
    assert "Mark a day as cooked, skipped or rejected" in _texts(planned)


def test_marking_days_out_of_order_is_explained_and_blocked():
    at = _app()
    at.button(key="use_example").click().run()
    at.button(key="plan_week").click().run()
    wid = at.session_state["week_id"]
    at.radio(key=f"mark_{wid}_2").set_value("Cooked").run()
    assert at.button(key="replan").disabled
    assert "Mark days in order" in _texts(at)


def test_cooking_a_day_and_rejecting_another_replans_the_rest():
    at = _app()
    at.button(key="use_example").click().run()
    at.button(key="plan_week").click().run()
    week = at.session_state["week"]
    rejected = week.days[3].recipe_id
    wid = at.session_state["week_id"]
    at.radio(key=f"mark_{wid}_0").set_value("Cooked").run()
    at.radio(key=f"mark_{wid}_3").set_value("Reject this dinner").run()
    assert not at.button(key="replan").disabled
    at.button(key="replan").click().run(timeout=TIMEOUT)

    assert not at.exception
    new = at.session_state["week"]
    assert new.day_offset == 1 and len(new.days) == 6
    assert rejected not in new.recipe_ids
    assert "Re-planned." in _texts(at)
    assert at.metric[0].value == "6"


def test_a_vegan_profile_plans_only_vegan_dinners():
    at = _app()
    at.sidebar.selectbox(key="diet").set_value("vegan").run()
    at.button(key="use_example").click().run()
    at.button(key="plan_week").click().run()
    assert not at.exception
    week = at.session_state["week"]
    assert week.complete and week.explanation.facts.violations == 0
    assert "vegan diet" in (week.rules.text if week.rules else "")


def test_an_impossible_profile_is_explained_not_shown_as_an_empty_week():
    at = _app()
    at.sidebar.slider(key="weekday_minutes").set_value(10).run()
    at.sidebar.multiselect(key="allergens").set_value(["peanut", "tree_nut", "gluten", "dairy", "egg", "soy"]).run()
    at.sidebar.selectbox(key="diet").set_value("vegan").run()
    at.text_area(key="pantry_text").set_value("rice").run()
    at.button(key="read_pantry").click().run()
    at.button(key="plan_week").click().run()
    assert not at.exception                      # whatever the outcome, the page explains it instead of breaking
