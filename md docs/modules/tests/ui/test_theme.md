# `tests/ui/test_theme.py`

Tests [`ui/theme.py`](../../ui/theme.md). Pure string checks, no Streamlit.

| Test | Pins |
| --- | --- |
| `test_every_building_block_escapes_its_text` (×7) | an `<img onerror>` payload never survives into the HTML |
| `test_stepper_marks_past_current_and_future_steps` | done / now / future states; out-of-range step is an error |
| `test_chip_tones_are_a_closed_set` | only `""`, `good`, `warn` |
| `test_unknown_food_groups_get_the_basket` | icon fallback |
| `test_every_dataset_food_group_has_its_own_icon` | every `food_group` in the dataset is a key of `GROUP_ICONS` (a rebuild adding a group fails here) |
| `test_item_icons_name_real_ingredients` | every `ITEM_ICONS` key is a canonical name (a typo would never match) |
| `test_food_icon_prefers_the_item_then_the_group_then_the_basket` | item beats group; case/space tolerant; exact names only ("egg noodles" is not an egg) |
| `test_the_stylesheet_honours_reduced_motion_and_staggers_cards` | reduced motion disables animation; a full week of cards has entrance delays; palette in use |
| `test_the_stylesheet_has_balanced_braces` | an unbalanced brace in the f-string would silently drop every later rule |

## Change log

- 2026-10-13 — Created.
- 2026-10-17 — Added the three food-icon tests; `food_icon_html` joins the escaping test.
