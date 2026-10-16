# `src/optimizer/replan.py`

## Purpose

Turn "days `0..t-1` have happened" into a fresh planning problem for the days that are left. It implements the
mid-week behaviour in `md docs/systemflow.md` — past days never touched, ingredients of a skipped or rejected meal stay
in stock and get used first, re-plan the remaining days from the *current* pantry — **without changing the
optimiser**.

## Public API

| Name | What |
| --- | --- |
| `roll_forward(scenario, cooked_recipe_ids, ctx) -> RolledForward` | `cooked_recipe_ids[d]` is the recipe actually cooked on day `d`, or `None` if skipped |
| `RolledForward` | `scenario` (the remaining-days problem), `elapsed_days`, `consumed_g`, `expired_g` |

## What it does

1. Replays the cooked dinners against the pantry (skipped days use nothing but still pass), with the same
   substitution rules the plan showed (`optimizer/substitutions.py`), so a dinner cooked with milk + lemon instead
   of buttermilk used up that milk.
2. What they consumed leaves the pantry. Stock whose deadline fell inside the elapsed days is **dropped and reported**
   in `expired_g` — never silently.
3. Remaining stock's deadlines shift by `t`; a deadline at or beyond the new horizon becomes "no deadline".
4. New scenario: `horizon_days - t` days, `start_weekday + t`, current pantry, same profile (with
   `expiry_known` / `expiry_confidence` / `urgency` / `quantity_assumed` carried).

## Why a roll-forward and not "locked days" in the model

A locked past day would need new variables and constraints and would still have to be excluded from the cost terms.
Removing it from the problem is simpler and *exactly* equivalent: nothing the future plan does can change the past.
A rejection is a hard rule on the profile (`excluded_recipe_ids`), applied by the caller.

## Limits

* The replay allocates pantry stock greedily by day (the same definition as everywhere else).
* Stock with several deadlines is carried with the earliest one (the planner's existing approximation).
* "Leftovers I cooked today" and groceries bought for the plan are not added to the pantry; the user adds what they
  actually have through the review step.

## Tests

[`tests/optimizer/test_replan.py`](../tests/optimizer/test_replan.md)

## Logging

Logger `optimizer.replan`. DEBUG: one line per roll-forward: days elapsed and skipped, days left, pantry items carried, grams used and grams expired.

## Change log

- 2026-10-13 — Created.
- 2026-10-14 — Logging: DEBUG summary of each roll-forward.
- 2026-10-16 — The roll-forward replay applies the substitution rules (`replay_with_substitutions`).
