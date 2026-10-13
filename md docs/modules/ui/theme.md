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

## Limits

* Relies on Streamlit's `data-testid` attributes and `st-key-` classes. A Streamlit upgrade may rename them; the
  page would still work, only plainer.
* Loads the *Plus Jakarta Sans* font from Google Fonts; offline it falls back to the system font.
* Light theme only (`.streamlit/config.toml` sets `base = "light"`).

## Tests

[`tests/ui/test_theme.py`](../tests/ui/test_theme.md)

## Change log

- 2026-10-13 — Created (UI redesign).
