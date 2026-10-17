"""The prototype's visual language: one stylesheet and a few HTML building blocks.

Why a module of its own
-----------------------
Streamlit's widgets are functional but plain. Rather than scatter inline styles through the views, the look lives
here: a single stylesheet (colours, type, cards, motion) plus small functions that return HTML for the pieces
Streamlit has no widget for (the hero, the step indicator, chips, empty states). Views call these; they never write
CSS themselves.

Design decisions
----------------
* **Palette**: warm off-white canvas, herb green (primary: actions, progress), terracotta (accent: warnings worth
  noticing, never errors), soft neutrals. Food apps read best warm, not clinical.
* **Cards everywhere** a thing can be acted on (a pantry row, a dinner): rounded 16 px, a soft shadow, a lift on hover.
* **Motion with purpose**: content fades up once as it appears (staggered across cards so a week "arrives"), buttons
  respond to press. Everything is disabled under ``prefers-reduced-motion``.
* **Safety**: every function that puts text into HTML escapes it (``html.escape``). Recipe and ingredient names come
  from a public dataset and must never be able to inject markup.

Nothing here imports Streamlit; the views render what these functions return.
"""
from __future__ import annotations

import html
from collections.abc import Iterable, Sequence

# ------------------------------------------------------------------------------------------------- palette
GREEN = "#2F6B4F"          # primary: actions, progress
GREEN_SOFT = "#E6F0EA"
TERRACOTTA = "#D9734E"     # accent: "worth a look"
TERRACOTTA_SOFT = "#FBEDE6"
INK = "#1F2A24"
MUTED = "#6B7A72"
CANVAS = "#FAF8F4"
CARD = "#FFFFFF"
LINE = "#ECE7DF"

STEPS = ("Your kitchen", "Check it", "Your week")

# Food-group icons for the pantry rows and the shopping list. Keys are exactly the 22 ``food_group`` values in
# data/canonical/ingredients/ingredient.parquet (a test checks none is missing); anything else gets the basket.
GROUP_ICONS = {
    "vegetable": "🥦", "fruit": "🍎", "meat": "🥩", "poultry": "🍗", "seafood": "🐟", "dairy": "🧀", "egg": "🥚",
    "grain_pasta": "🍝", "bakery": "🍞", "legume": "🫘", "nut_seed": "🥜", "herb_spice": "🌿", "oil_fat": "🫒",
    "sauce_condiment": "🥫", "soup_broth": "🍲", "sweetener": "🍯", "snack_sweet": "🍪", "beverage": "🧃",
    "alcohol": "🍷", "water": "💧", "mixed_dish": "🥘", "other": "🧺",
}
# A more specific icon for the everyday ingredients a group icon would describe badly (rice is not pasta, milk is not
# cheese). Exact canonical names only: a word match would put an egg on "egg noodles". Chosen by hand from the most
# common pantry items; every name must exist in the dataset (a test checks).
ITEM_ICONS = {
    "spinach": "🥬", "lettuce": "🥬", "cabbage": "🥬", "tomato": "🍅", "potato": "🥔", "sweet potato": "🍠",
    "carrot": "🥕", "onion": "🧅", "garlic": "🧄", "ginger": "🫚", "broccoli": "🥦", "corn": "🌽", "cucumber": "🥒",
    "eggplant": "🍆", "mushroom": "🍄", "bell pepper": "🫑", "green bell pepper": "🫑", "red bell pepper": "🫑",
    "chili": "🌶️", "jalapeno": "🌶️", "hot pepper": "🌶️", "avocado": "🥑", "olive": "🫒",
    "banana": "🍌", "lemon": "🍋", "lime": "🍋", "orange": "🍊", "strawberry": "🍓", "cherry": "🍒", "peach": "🍑",
    "pear": "🍐", "pineapple": "🍍", "watermelon": "🍉", "mango": "🥭", "kiwi": "🥝", "coconut": "🥥",
    "rice": "🍚", "oats": "🌾", "all-purpose flour": "🌾", "bread": "🍞", "bagel": "🥯", "croissant": "🥐",
    "pancake": "🥞", "pretzel": "🥨", "chocolate": "🍫",
    "milk": "🥛", "butter": "🧈", "plain yogurt": "🥛", "heavy cream": "🥛",
    "salt": "🧂", "honey": "🍯", "peanut": "🥜",
    "shrimp": "🦐", "bacon": "🥓", "coffee": "☕", "tea": "🍵", "beer": "🍺",
}

# How many cards get their own entrance delay (a week has 7 dinners; a pantry rarely more than ~20 rows).
_STAGGERED = 24


def group_icon(food_group: str | None) -> str:
    """Icon for a food group; the basket for anything unknown."""
    return GROUP_ICONS.get((food_group or "").lower(), GROUP_ICONS["other"])


def food_icon(name: str | None, food_group: str | None) -> str:
    """Icon for one ingredient: its own (``ITEM_ICONS``, exact canonical name) if it has one, else its group's.

    Decorative: the name is always shown next to it. A row with no ingredient yet (``name`` and ``food_group``
    ``None``) gets the basket.
    """
    return ITEM_ICONS.get((name or "").strip().lower()) or group_icon(food_group)


def food_icon_html(icon: str) -> str:
    """The pantry row's icon, large, on a round tile. Its own block (rendered in a narrow column) because Markdown
    cannot size one character, and the name line next to it holds user text that must never be rendered as HTML.
    The tile's neutral background keeps pale emoji (🥛, 🧂) visible on the white card."""
    return f'<div class="p2p-food-icon" aria-hidden="true">{html.escape(icon)}</div>'


def css() -> str:
    """The whole stylesheet, as a ``<style>`` block to render once per page run."""
    stagger = "\n".join(
        f'[class*="st-key-daycard_{i}"], [class*="st-key-pantryrow_{i}"] {{ animation-delay: {0.04 * i:.2f}s; }}'
        for i in range(_STAGGERED))
    return f"""<style>
@import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&display=swap');

:root {{
  --green: {GREEN}; --green-soft: {GREEN_SOFT}; --accent: {TERRACOTTA}; --accent-soft: {TERRACOTTA_SOFT};
  --ink: {INK}; --muted: {MUTED}; --canvas: {CANVAS}; --card: {CARD}; --line: {LINE};
  --radius: 16px; --shadow: 0 1px 2px rgba(31,42,36,.04), 0 4px 16px rgba(31,42,36,.06);
  --shadow-hover: 0 2px 4px rgba(31,42,36,.06), 0 12px 28px rgba(31,42,36,.10);
}}
html, body, .stApp, .stMarkdown, p, li, label, h1, h2, h3, h4, button, input, textarea, select {{
  font-family: 'Plus Jakarta Sans', system-ui, -apple-system, 'Segoe UI', sans-serif;
}}
/* Streamlit draws its arrows and icons with an icon font: never override it, or "arrow_right" shows as text */
[data-testid="stIconMaterial"], .material-symbols-rounded, [class*="material-symbols"] {{
  font-family: 'Material Symbols Rounded' !important;
}}
[data-testid="stAppViewContainer"] {{ background: var(--canvas); }}
[data-testid="stHeader"] {{ background: transparent; }}
.block-container {{ padding-top: 1.6rem; max-width: 1080px; }}
h1, h2, h3 {{ color: var(--ink); letter-spacing: -0.01em; }}

/* ---------- entrance motion ---------- */
@keyframes p2p-fade-up {{ from {{ opacity: 0; transform: translateY(10px); }} to {{ opacity: 1; transform: none; }} }}
@keyframes p2p-float {{ 0%, 100% {{ transform: translateY(0) rotate(-4deg); }} 50% {{ transform: translateY(-6px) rotate(4deg); }} }}
@keyframes p2p-sheen {{ from {{ background-position: 0% 50%; }} to {{ background-position: 100% 50%; }} }}
@keyframes p2p-pop {{ 0% {{ transform: scale(.96); opacity: 0; }} 100% {{ transform: scale(1); opacity: 1; }} }}

/* ---------- hero ---------- */
.p2p-hero {{
  position: relative; overflow: hidden; border-radius: 24px; padding: 28px 32px; margin-bottom: 18px;
  background: linear-gradient(120deg, #2F6B4F 0%, #3E8463 45%, #D9734E 120%); background-size: 200% 200%;
  animation: p2p-sheen 14s ease-in-out infinite alternate, p2p-fade-up .5s ease-out both; color: #fff;
  box-shadow: 0 12px 32px rgba(47,107,79,.25);
}}
.p2p-hero h1 {{ color: #fff !important; font-size: 2.2rem !important; font-weight: 800 !important; margin: 0 0 6px 0 !important; padding: 0 !important; }}
.p2p-hero a, .p2p-section a {{ display: none !important; }}   /* Streamlit's heading anchor icons */
.p2p-hero p {{ color: rgba(255,255,255,.88); font-size: 1.02rem; margin: 0 0 14px 0; max-width: 620px; }}
.p2p-hero .p2p-float {{ position: absolute; right: 30px; top: 18px; font-size: 3.4rem; animation: p2p-float 5s ease-in-out infinite; }}
.p2p-hero .p2p-float.two {{ right: 104px; top: 62px; font-size: 2.3rem; animation-delay: 1.2s; opacity: .9; }}
.p2p-pill {{ display: inline-block; padding: 5px 12px; margin: 0 6px 6px 0; border-radius: 999px; font-size: .82rem;
  font-weight: 600; background: rgba(255,255,255,.16); color: #fff; backdrop-filter: blur(4px); }}

/* ---------- stepper ---------- */
.p2p-steps {{ display: flex; gap: 10px; margin: 4px 0 18px 0; animation: p2p-fade-up .45s ease-out both; }}
.p2p-step {{ flex: 1; display: flex; align-items: center; gap: 10px; padding: 10px 14px; border-radius: 14px;
  background: var(--card); border: 1px solid var(--line); color: var(--muted); font-weight: 600; font-size: .9rem;
  transition: all .3s ease; }}
.p2p-step .num {{ width: 26px; height: 26px; border-radius: 50%; display: grid; place-items: center; font-size: .8rem;
  background: var(--line); color: var(--muted); transition: all .3s ease; }}
.p2p-step.done {{ color: var(--green); }}
.p2p-step.done .num {{ background: var(--green-soft); color: var(--green); }}
.p2p-step.now {{ border-color: var(--green); color: var(--ink); box-shadow: 0 0 0 4px var(--green-soft); }}
.p2p-step.now .num {{ background: var(--green); color: #fff; }}

/* ---------- section titles ---------- */
.p2p-section {{ display: flex; align-items: baseline; gap: 10px; margin: 18px 0 6px 0; animation: p2p-fade-up .4s ease-out both; }}
.p2p-section .title {{ font-size: 1.45rem; font-weight: 800; color: var(--ink); line-height: 1.3; letter-spacing: -0.01em; }}
.p2p-section span {{ color: var(--muted); font-size: .92rem; }}

/* ---------- cards (bordered containers) ---------- */
[class*="st-key-daycard_"], [class*="st-key-pantryrow_"], [class*="st-key-card_"] {{
  background: var(--card); border: 1px solid var(--line) !important; border-radius: var(--radius) !important;
  box-shadow: var(--shadow); padding: 14px 18px !important; transition: transform .2s ease, box-shadow .2s ease;
  animation: p2p-fade-up .45s ease-out both;
}}
[class*="st-key-daycard_"]:hover, [class*="st-key-pantryrow_"]:hover {{ transform: translateY(-2px); box-shadow: var(--shadow-hover); }}
[class*="st-key-daycard_"] {{ border-left: 5px solid var(--green) !important; }}
[class*="st-key-pantryrow_attn"] {{ border-left: 5px solid var(--accent) !important; background: #FFFCFA; }}
/* the food icon on a pantry row: ~1.5x the name's size (the text-sized emoji read as bullets, not pictures) */
.p2p-food-icon {{ width: 46px; height: 46px; border-radius: 50%; background: #F3F1EC; display: flex;
  align-items: center; justify-content: center; font-size: 1.6rem; line-height: 1; }}

/* ---------- chips ---------- */
.p2p-chips {{ display: flex; flex-wrap: wrap; gap: 6px; margin: 2px 0 8px 0; }}
.p2p-chip {{ padding: 4px 10px; border-radius: 999px; font-size: .8rem; font-weight: 600; background: #F3F1EC; color: var(--ink); }}
.p2p-chip.good {{ background: var(--green-soft); color: var(--green); }}
.p2p-chip.warn {{ background: var(--accent-soft); color: #A4482A; }}
.p2p-day {{ display: inline-block; font-size: .74rem; font-weight: 800; letter-spacing: .08em; text-transform: uppercase;
  color: var(--green); background: var(--green-soft); padding: 3px 10px; border-radius: 999px; margin-bottom: 4px; }}

/* ---------- metrics as stat cards ---------- */
[data-testid="stMetric"] {{ background: var(--card); border: 1px solid var(--line); border-radius: var(--radius);
  padding: 14px 16px; box-shadow: var(--shadow); animation: p2p-pop .4s ease-out both; }}
[data-testid="stMetricValue"] {{ color: var(--green); font-weight: 800; }}
[data-testid="stMetricLabel"] p {{ color: var(--muted); font-weight: 600; font-size: .85rem; }}

/* ---------- buttons ---------- */
.stButton > button, .stDownloadButton > button {{ border-radius: 12px; font-weight: 700; padding: .55rem 1.1rem; white-space: nowrap;
  transition: transform .12s ease, box-shadow .2s ease, background .2s ease; }}
.stButton > button:hover {{ transform: translateY(-1px); box-shadow: 0 6px 16px rgba(47,107,79,.18); }}
.stButton > button:active {{ transform: scale(.97); }}
.stButton > button[kind="primary"] {{ background: var(--green); border-color: var(--green); }}
.stButton > button[kind="primary"]:hover {{ background: #285C44; border-color: #285C44; }}
.stButton > button:disabled {{ transform: none; box-shadow: none; }}

/* ---------- inputs, tabs, expanders, sidebar ---------- */
.stTextArea textarea {{ border-radius: 14px; font-size: 1rem; line-height: 1.5; }}
.stTabs [data-baseweb="tab-list"] {{ gap: 6px; }}
.stTabs [data-baseweb="tab"] {{ border-radius: 999px; padding: 6px 16px; font-weight: 700; background: #F1EEE8; }}
.stTabs [aria-selected="true"] {{ background: var(--green) !important; color: #fff !important; }}
.stTabs [data-baseweb="tab-highlight"], .stTabs [data-baseweb="tab-border"] {{ display: none; }}
[data-testid="stExpander"] details {{ border-radius: 12px; border-color: var(--line); background: #FCFBF8; }}
[data-testid="stSidebar"] {{ background: #F3F0EA; border-right: 1px solid var(--line); }}
[data-testid="stSidebar"] [data-testid="stExpander"] details {{ background: var(--card); }}

/* ---------- empty state ---------- */
.p2p-empty {{ text-align: center; padding: 34px 20px; border: 2px dashed var(--line); border-radius: 20px;
  color: var(--muted); animation: p2p-fade-up .5s ease-out both; background: rgba(255,255,255,.5); }}
.p2p-empty .icon {{ font-size: 2.6rem; display: block; margin-bottom: 6px; animation: p2p-float 5s ease-in-out infinite; }}
.p2p-empty b {{ color: var(--ink); display: block; font-size: 1.05rem; margin-bottom: 2px; }}

/* ---------- respect the user's motion setting ---------- */
@media (prefers-reduced-motion: reduce) {{
  *, *::before, *::after {{ animation: none !important; transition: none !important; }}
}}
{stagger}
</style>"""


def hero_html(title: str, tagline: str, pills: Iterable[str]) -> str:
    """The page header: title, one-line promise, value pills, two floating food icons."""
    chips = "".join(f'<span class="p2p-pill">{html.escape(p)}</span>' for p in pills)
    return (f'<div class="p2p-hero"><span class="p2p-float">🥘</span><span class="p2p-float two">🥕</span>'
            f'<h1>{html.escape(title)}</h1><p>{html.escape(tagline)}</p><div>{chips}</div></div>')


def stepper_html(current: int, steps: Sequence[str] = STEPS) -> str:
    """The three-step progress strip. ``current`` is 0-based; earlier steps show a tick."""
    if not 0 <= current < len(steps):
        raise ValueError(f"current step {current} is outside 0..{len(steps) - 1}")
    items = []
    for i, label in enumerate(steps):
        state = "done" if i < current else ("now" if i == current else "")
        mark = "✓" if i < current else str(i + 1)
        items.append(f'<div class="p2p-step {state}"><span class="num">{mark}</span>{html.escape(label)}</div>')
    return f'<div class="p2p-steps">{"".join(items)}</div>'


def section_html(title: str, subtitle: str = "") -> str:
    """A section title with an optional quiet subtitle on the same line."""
    sub = f"<span>{html.escape(subtitle)}</span>" if subtitle else ""
    # a styled div, not <h2>: Streamlit restyles headings inside markdown and adds anchor icons to them
    return f'<div class="p2p-section"><div class="title">{html.escape(title)}</div>{sub}</div>'


def chips_html(chips: Iterable[tuple[str, str]]) -> str:
    """A row of chips; each is ``(text, tone)`` with tone ``""`` / ``"good"`` / ``"warn"``."""
    out = []
    for text, tone in chips:
        if tone not in ("", "good", "warn"):
            raise ValueError(f"unknown chip tone {tone!r}")
        out.append(f'<span class="p2p-chip {tone}">{html.escape(text)}</span>')
    return f'<div class="p2p-chips">{"".join(out)}</div>'


def day_label_html(weekday: str) -> str:
    """The small weekday pill above a dinner's name."""
    return f'<span class="p2p-day">{html.escape(weekday)}</span>'


def empty_state_html(icon: str, title: str, text: str) -> str:
    """A friendly placeholder for an area with nothing in it yet."""
    return (f'<div class="p2p-empty"><span class="icon">{html.escape(icon)}</span><b>{html.escape(title)}</b>'
            f'{html.escape(text)}</div>')
