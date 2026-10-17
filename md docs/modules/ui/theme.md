# `src/ui/theme.py`

## Purpose

The prototype's visual language in one place: a stylesheet (palette, type, cards, motion) and small functions that
return HTML for the pieces Streamlit has no widget for. Views call these; they never write CSS themselves.

## Public API

| Name | What |
| --- | --- |
| `css()` | The whole stylesheet as a `<style>` block (render once per run) |
| `hero_html(title, tagline, pills)` | Gradient header with the promise and value pills, two floating food icons |
| `stepper_html(current, steps=STEPS)` | The 3-step strip (Your kitchen / Check it / Your week); past steps get a tick |
| `section_html(title, subtitle)` | A section title (a styled div, not `<h2>`, so Streamlit does not restyle it) |
| `chips_html([(text, tone)])` | At-a-glance chips; tone `""` / `"good"` / `"warn"` |
| `day_label_html(weekday)`, `empty_state_html(icon, title, text)`, `group_icon(food_group)` | Small pieces |
| `food_icon_html(icon)` | The pantry row's icon at ~1.5× text size on a round neutral tile (`.p2p-food-icon`); the tile keeps pale emoji such as 🥛 visible on a white card |
| `food_icon(name, food_group)`, `GROUP_ICONS`, `ITEM_ICONS` | An ingredient's emoji: its own (`ITEM_ICONS`, ~60 everyday items, exact canonical name) else its group's, else the basket 🧺. Used by the pantry rows; `group_icon` also heads the shopping-list groups |
| `GREEN`, `TERRACOTTA`, … | The palette |

## Design decisions

* **Palette**: warm off-white canvas, herb green for actions and "on target", terracotta for "worth a look" (never
  for errors). Colour never carries meaning alone: chip text says it too.
* **Cards** for anything you can act on (a pantry row, a dinner, a shopping group), styled through Streamlit
  container keys (`st.container(key="daycard_…")` adds a `st-key-…` class the CSS targets).
* **Motion with purpose**: cards fade up once, staggered so a week "arrives"; cards lift on hover; buttons respond
  to press; a toast celebrates a finished plan. **All motion is disabled under `prefers-reduced-motion`.**
* **Safety**: every builder escapes its text with `html.escape`. Recipe names come from a public dataset.
* **Never override the icon font**: Streamlit draws arrows with *Material Symbols*. An early broad font rule turned
  every expander arrow into the literal text `arrow_right` (seen in the browser, fixed, and now excluded explicitly).

* **Food icons are emoji, keyed on the dataset.** No image files to license, host or load. `GROUP_ICONS` has one
  key per `food_group` value in `ingredient.parquet` (22); `ITEM_ICONS` refines everyday items a group icon describes
  badly (rice is not pasta, milk is not cheese). Item icons match the *exact* canonical name, never a word inside it,
  so "egg noodles" keeps the pasta icon rather than an egg.

## Limits

* Emoji look different per OS (Segoe UI Emoji on Windows, Apple / Noto elsewhere); a very old system may show a box
  for newer ones (🫘 🫚 🫑 🫒 are Emoji 13–15).

* Relies on Streamlit's `data-testid` attributes and `st-key-` classes. A Streamlit upgrade may rename them; the
  page would still work, only plainer.
* Loads the *Plus Jakarta Sans* font from Google Fonts; offline it falls back to the system font.
* Light theme only (`.streamlit/config.toml` sets `base = "light"`).

## Tests

[`tests/ui/test_theme.py`](../tests/ui/test_theme.md)

## Change log

- 2026-10-13 — Created (UI redesign).
- 2026-10-17 — `GROUP_ICONS` keys aligned with the dataset's 22 food groups (`bakery`, `sauce_condiment`, `snack_sweet`, `soup_broth`, `mixed_dish`, `alcohol`, `water` were missing or misspelt and fell back to the basket); added `ITEM_ICONS`, `food_icon` and `food_icon_html` (large icon on a round tile) for the pantry rows.
