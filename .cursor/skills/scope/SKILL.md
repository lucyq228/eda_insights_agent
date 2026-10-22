---
name: scope
description: Turn a vague "find me insights" request into a testable scope for any tabular dataset - the target and its definition, the purpose and decision, drivers and exclusions, segments, 3-6 hypotheses with tool pathways, and questions only the user can answer. Use for the scope_draft milestone (A2 Scope) and to revise the scope after user answers or feasibility feedback.
---

# Scope (A2)

```powershell
.venv\Scripts\python.exe .cursor\skills\scope\scripts\read_context.py
.venv\Scripts\python.exe .cursor\skills\scope\scripts\save_scope.py --file runs\<run>\drafts\scope.json [--change-note "..."]
```

`read_context.py` prints the request, the user's answers and context, a compact
profile of every column, feasibility feedback (if any), and the analysis shelf.

## The scope draft (`drafts/scope.json`)

```json
{
  "project_name": "What moves with weekly store sales?",
  "purpose": "why the user wants this, in one or two sentences",
  "decision_supported": "the decision the findings will inform",
  "target": {"column": "weekly_sales_k", "type": "numeric | binary | categorical",
             "positive_class": "Yes (binary only)", "definition": "what it measures; which direction is good"},
  "unit_of_analysis": "store-week",
  "id_column": "store_id", "date_column": "week_start",
  "entity_column": "store_id  (panel data only; or omit and give panel_reason)",
  "drivers": "all  (or a list of columns)",
  "exclude": [{"column": "sales_per_visitor", "reason": "computed from the target"}],
  "segments": ["region"], "controls": ["region"],
  "min_n": 30, "alpha": 0.05,
  "hypotheses": [{
    "id": "H1", "statement": "an association, testable", "rationale": "why, citing profile facts",
    "support_criteria": "what result counts as support, e.g. r > 0.2 with CI excluding 0",
    "pathway": [{"tool": "segment-correlation", "params": {"x": "promo_spend_k", "by": "region"}, "purpose": "..."}]
  }],
  "user_questions": [{"id": "Q1", "question": "...", "options": ["..."], "recommended": "...", "why_it_matters": "..."}],
  "out_of_scope": ["causal claims", "..."]
}
```

See `examples/example_scope.json` for a complete one.

## How to scope well

1. **Target.** Use the user's answer. If none, pick the best candidate and add a
   question to confirm it. Binary targets need `positive_class`.
2. **Purpose and decision.** One sentence each. Every hypothesis should matter for
   the decision; drop the ones that would not change it.
3. **Exclusions.** Exclude ids, free text, columns computed from the target or
   recorded after it (leakage), and anything the user ruled out. Give a reason.
4. **Hypotheses (3-6).** Start broad, then sharpen:
   - a screen of all drivers (`target-associations`) - usually H1;
   - the 1-3 most decision-relevant driver relationships (`pair-deep-dive`);
   - a confounding check where segments differ in both driver and target
     (`segment-correlation`, `partial-correlation`);
   - a shape check for drivers where "more" may not be "better" (`nonlinearity-check`);
   - a joint view (`correlation-matrix`, `driver-importance`); time (`time-trend`) if dated;
   - for panel data, a panel check (see below).
5. **Panel data.** If `read_context.py` lists `panel_candidates` (the same store,
   restaurant, market, or customer appears in many periods), decide explicitly:
   - **Use it (usual):** set `entity_column`, and add `panel-decomposition` for the
     1-2 key drivers and/or `panel-drivers` for the joint view. These separate
     *within-entity* (the same store in its higher vs lower weeks) from
     *between-entity* (stores that are higher on average). Keep the pooled tools too;
     the review compares them.
   - **Ignore it:** omit `entity_column` and give `panel_reason` (e.g. "the rows are
     independent customers; the repeat is incidental").
   If the user's decision is about changing something *inside* an entity (promo
   next month), within matters most; if it is about *which* entities to pick or
   open, between matters most. Ask the user when that is unclear.
6. **Questions.** Only choices the user owns (target, purpose, exclusions, which
   comparison matters). Each has a recommended option; set the scope to it meanwhile.
7. **Revisions.** Read the answers and feasibility feedback; fix blocked steps,
   exclude leakage suspects, reflect answers, and save a new version with a change note.

Do not add `multiple-testing` as a step; it runs automatically.
