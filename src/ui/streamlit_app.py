"""Pantry to Plate - the Streamlit prototype.

    streamlit run src/ui/streamlit_app.py

Flow: describe your pantry in words -> check what we understood -> plan the week -> read the reasons, shop, cook, and
re-plan when life happens. Every decision is the backend's (``app.service.PantryToPlateService``); this script is
state wiring and the page shell (``ui.theme`` for the look, ``ui.views`` for each area).
"""
from __future__ import annotations

import logging
import os
import sys
from datetime import date, datetime, timezone
from pathlib import Path

# Streamlit puts only this script's folder on sys.path; the project's packages live one level up (src/).
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import streamlit as st  # noqa: E402

from app.service import PantryToPlateService  # noqa: E402
from llm.client import LlmClient, LlmConfig  # noqa: E402
from logging_setup import configure_logging  # noqa: E402
from ui import logic, theme, views  # noqa: E402

logger = logging.getLogger(__name__)

TITLE = "Pantry to Plate"
# How long a "is a language model reachable?" answer is reused. Short enough that starting Ollama during local
# development is picked up within minutes; long enough that a cloud host is not probed on every click.
LLM_PROBE_TTL_S = 300
TAGLINE = "A week of dinners built around what you already have — less waste, fewer groceries, every choice explained."
PROMISES = ("🥫 Uses your pantry first", "🛒 Fewer trips to the shop", "💡 Every choice explained")


@st.cache_resource(show_spinner="Loading the recipe book…")
def get_service(use_llm: bool) -> PantryToPlateService:
    """One service per process and LLM setting: it holds the dataset and the parser's fuzzy index."""
    return PantryToPlateService(llm=LlmClient() if use_llm else None)


@st.cache_data(ttl=LLM_PROBE_TTL_S, show_spinner=False)
def llm_reachable(config: LlmConfig) -> bool:
    """Whether the configured language model answers (cached per config). False on a cloud host with no model, which
    hides the LLM switch instead of offering something that cannot work."""
    client = LlmClient(config)
    try:
        return client.is_available()
    finally:
        client.close()


def current_step() -> int:
    """Where the user is: 0 = describing the kitchen, 1 = checking it, 2 = looking at a week."""
    if st.session_state.get("week") is not None:
        return 2
    return 1 if st.session_state.get("entries") else 0


def main() -> None:
    st.set_page_config(page_title=TITLE, page_icon="🥘", layout="wide", initial_sidebar_state="expanded")
    st.markdown(theme.css(), unsafe_allow_html=True)
    st.markdown(theme.hero_html(TITLE, TAGLINE, PROMISES), unsafe_allow_html=True)

    # the profile form needs the service for the cuisine list, and the service depends on the LLM checkbox, so the
    # checkbox's previous value is read from state before the sidebar is drawn. With no model reachable the checkbox
    # is not shown at all and the service is the rules-only one.
    offer_llm = llm_reachable(LlmConfig.from_env())
    wants_llm = offer_llm and bool(st.session_state.get("use_llm", True))
    service = get_service(wants_llm)
    profile_values, use_llm = views.sidebar_profile(service, offer_llm=offer_llm)
    if use_llm != wants_llm:
        st.rerun()

    stepper = st.empty()                 # filled at the end, once this run has decided which step we are on
    # the visitor's date, not the server's (a cloud host runs on UTC); see logic.local_today
    today, today_source = logic.local_today(st.context.timezone, datetime.now(timezone.utc),
                                            os.environ.get(logic.ENV_TIMEZONE))
    logger.debug("today is %s (%s timezone %s)", today, today_source, st.context.timezone)
    pantry_entries = views.pantry_step(service, today)

    st.markdown(theme.section_html("Plan the week", "Seven dinners, one shopping list."), unsafe_allow_html=True)
    if st.button("🍳 Plan my week", type="primary", key="plan_week"):
        _plan(service, profile_values, pantry_entries, today)

    week = st.session_state.get("reworded") or st.session_state.get("week")
    if week is not None:
        new = views.week_view(service, week)
        if new is not None:
            st.session_state["week"] = new
            st.session_state.pop("reworded", None)
            st.session_state["week_id"] = st.session_state.get("week_id", 0) + 1
            st.session_state["toast"] = ("Re-planned from what's left in your kitchen", "🔄")
            st.rerun()
    else:
        views.empty_week()

    stepper.markdown(theme.stepper_html(current_step()), unsafe_allow_html=True)
    toast = st.session_state.pop("toast", None)
    if toast:
        st.toast(toast[0], icon=toast[1])


def _plan(service: PantryToPlateService, profile_values: dict, entries: list, today: date) -> None:
    try:
        built = service.build_profile(**profile_values)
    except ValueError as exc:                       # an out-of-range number, say: tell the user, do not crash
        st.error(f"Please check your details: {logic.md_escape(str(exc))}")
        return
    for note in built.notes:
        st.warning(logic.md_escape(note))           # notes quote the food names the user typed
    scenario = service.make_scenario(built.profile, service.pantry_items(entries), today=today)
    with st.spinner("Planning your week… weighing your pantry, targets and tastes."):
        week = service.plan_week(scenario)
    st.session_state["week"] = week
    st.session_state.pop("reworded", None)
    st.session_state["week_id"] = st.session_state.get("week_id", 0) + 1
    if week.days:
        st.session_state["toast"] = ("Your week is ready — bon appétit!", "🎉")


# Streamlit re-runs this script on every interaction; configure_logging is idempotent (no duplicated lines).
configure_logging()
main()
