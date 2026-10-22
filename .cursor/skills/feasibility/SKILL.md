---
name: feasibility
description: Check whether the data supports each pathway step of the scope proposal (columns exist, types fit the tool, enough rows and segment levels, a usable date, no leakage), add analyst judgment, and save a feasibility review that says what the data can and cannot answer. Use for the feasibility milestone (A3 Feasibility), after every scope revision.
---

# Feasibility (A3)

```powershell
.venv\Scripts\python.exe .cursor\skills\feasibility\scripts\check_feasibility.py
.venv\Scripts\python.exe .cursor\skills\feasibility\scripts\save_feasibility.py --file runs\<run>\drafts\feasibility.json
```

## What the deterministic check covers

Per step: tool exists and is an analysis tool; params are known and required ones
present; target type is supported; columns exist, are usable types, are not the
target, not excluded, not leakage suspects; numeric `x` where needed; a parseable
date with at least 4 distinct dates for `time-trend`; at least 2 segment levels with
n >= `min_n`; enough rows with a target; for panel tools, an `entity_column` that
repeats (at least 2 rows per entity). Verdicts: `ok`, `partial` (runs, with
caveats: >40% missing, small levels skipped, few rows, few entities, or a pooled
tool on panel data whose CIs treat repeated rows as independent), `blocked`.

Scope-level: leakage suspects that would be drivers, no usable drivers, and panel
data without a decision (the profile found a panel but the scope has neither
`entity_column` nor `panel_reason`, or sets `entity_column` with no panel tool).

## Panel judgment

When the data is a panel, say in `can_answer` / `cannot_answer` which of within-
and between-entity the data supports: within needs drivers that change over time
for each entity (fixed traits such as region or format can only be read between);
between needs enough entities (roughly 30+). If the decision is about changing
something inside entities, recommend leading with the within estimates.

## Your judgment (`drafts/feasibility.json`)

```json
{
  "overall": "one or two sentences",
  "can_answer": ["..."],
  "cannot_answer": ["e.g. causal lift; margin (no cost data)"],
  "recommendations": ["exclude sales_per_visitor (ratio of the target)", "..."],
  "questions_for_user": ["only if the data cannot settle it"],
  "steps": [{"step_id": "H3.S1", "verdict": "partial", "judgment": "why stricter"}]
}
```

You may make a verdict stricter (with a reason), never looser. Think about:
power (n per segment), proxies (is the column really measuring the idea?), grain
(one row per unit?), time order (is a driver recorded after the target?), and
whether a step can distinguish its hypothesis from the obvious alternative.
