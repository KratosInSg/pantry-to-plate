# Eight evidence-based XAI cards

`src/explain/cards.py` implements structured per-meal cards, rendered in the Streamlit "Why this dinner" expander. The proposal PPT **slide 8** contains eight *evaluation metrics*, while **slide 9** describes the XAI design: six types (Expiry, Nutrition, Pantry, Preference, Constraint, Substitution) and a five-factor Palak Paneer example. We preserve the six XAI terms and add Groceries and Cooking time for eight visible cards.

Cards always appear in this order: ⏳ Expiry, 🥫 Pantry, ❤️ Preference, 🥗 Nutrition, 🛒 Groceries, 🛡️ Constraint, 🔄 Substitution, ⏱️ Cooking time.

Each card carries a source label and uses only existing typed `DayFacts` / `PlanFacts` values. Missing or unsupported information must be explicitly identified; the Substitution card states only a substitution rule that actually fired (`optimizer/substitutions.py`): what was not bought, what replaced it and the rule key as its source. When no rule fired it says so and is marked unavailable, so it **never claims a substitution that did not happen**. No counterfactuals are claimed unless the optimiser actually recomputes a changed plan. Estimated use-by dates are distinguished from known dates. Nutrition is described relative to the user's targets, not as medical advice.

The optional LLM paraphraser continues to reword existing detailed explanations, not the eight structured cards. The cards are deterministic, so they work offline and remain testable.

## Optional future LLM wording template

**System instruction:** You are the Pantry-to-Plate explanation narrator. You never choose meals or alter optimiser outputs. For a given meal, reword only the eight supplied evidence records. Preserve the order, icon and label of each category: ⏳ Expiry, 🥫 Pantry, ❤️ Preference, 🥗 Nutrition, 🛒 Groceries, 🛡️ Constraint, 🔄 Substitution, ⏱️ Cooking time. Use one short factual sentence per category. Retain all quantities, dates, known-versus-estimated distinctions, user targets and safety caveats. If a category is unsupported, state "Not verified" or "No recorded evidence"; never invent a substitution, counterfactual, nutrition benefit, allergen guarantee, or claimed reason a rejected recipe lost. Do not imply that an optimiser cost term proves causal necessity for a particular recipe. Output exactly eight labelled lines. No additional recommendations or marketing language.

**User input:** Structured category records (label, source, detail) generated from `meal_cards`. The system must validate any LLM response against these records before displaying it; until that validator exists, display the deterministic cards rather than generated lines.

## Change log
- 2026-10-16 — Substitution card shows fired substitution rules (source `substitution rule: <key>`), otherwise says none fired.
- 2026-10-16 — Preference card names the closest rated dinners when the rating history raised the dinner's score; its source then adds "+ your rated dinners".
