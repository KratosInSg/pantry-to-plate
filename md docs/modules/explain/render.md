# `src/explain/render.py`

## Purpose

Deterministic templates: `PlanFacts` → a sectioned plain-English `Explanation`. This is what the user sees with no
language model attached, and it is the ground truth any paraphrase is validated against.

## Public API

| Name | What |
| --- | --- |
| `render(facts) -> Explanation` | All sections, template text |
| `Statement(text, term, source)` | One sentence = one fact. `term`: `waste` / `groceries` / `nutrition` / `preference` / `cook_time` / `variety` / `overview` / `rule` / `solver` / `data`. `source`: `replay` / `solver_cost_term` / `hard_rule` / `profile` / `input` / `substitution_rule` |
| `Section(key, title, statements, text, source, note)` | `key` is `overview`, `day:<n>`, `rules` or `caveats`. `text` is what is shown; `template_text` is the statements joined |
| `Explanation.sections`, `.section(key)`, `.to_text()` | |
| `fmt_g`, `TERM_LABELS` | `300 g` / `1.2 kg`; human names of the objective's terms |
| `substitution_phrase(swap)` | "No buttermilk (27 g) to buy: milk (25 g) and lemon juice (1.7 g) from your pantry stand in for it." + the rule's note. Shared with the substitution card |

## What it says

* **overview** — pantry used and groceries, dinners inside the calorie range / reaching the protein minimum, expiring
  stock that will still go unused (named, with deadlines), stock bought again because it expires first, what still
  costs the plan most *by the planner's own scoring* (cost-term shares ≥ 10 %), and the solver's proven gap.
  With no plan, says why from the rule counts instead.
* **day:n** — the dinner, pantry stock it uses (with deadline and whether it was stated or estimated), what to buy,
  the calorie band, protein, liked / disliked cuisine and ingredients, the weekday time limit.
* **rules** — how many dinners each active rule removed, how many were left, that every planned dinner passes (or a
  `WARNING` if one does not), and the honest limit of allergen checks.
* **caveats** — amounts we assumed ("we assumed 250 g spinach — please correct") and deadlines that are estimates.

## Decisions

* **Misses read as misses.** "At 410 kcal it is 70 kcal below your dinner range", "x g short of your minimum",
  "a g will still go unused". The text never says healthy or tasty; it states distance to the user's own targets.
* **Cost terms are shown as shares, in words** ("extra shopping (46%)"), not as raw cost units: the units are an
  internal scale; the ranking is the information.
* **Lists never contain two "and"s** (`a, b, c and 2 more`).
* **Second-person rule phrases are defined here**, not reused from `hard_rules._REASONS`, which speak about "the user".

## Limits

* English only; no pluralisation beyond "item(s)".
* A recipe's name is shown as the dataset spells it (lower-case, sometimes odd); it is not cleaned.
* Tiny quantities (e.g. 1.8 g of a sauce) are listed when they are real grocery items; the list is capped at four per
  sentence with "and N more".

## Tests

[`tests/explain/test_render.py`](../tests/explain/test_render.md)

## Change log

- 2026-10-13 — Created.
- 2026-10-13 — Singular/plural agreement ("1 of 7 dinners is"), sub-1 shortfalls printed with a decimal, assumed-amount caveat, second-person phrases for `excluded_recipe` and `not_dinner`.
- 2026-10-16 — Day sections state each fired substitution rule (`SRC_SUBSTITUTION`, term `groceries`); added `substitution_phrase`.
