---
name: insight-shelf
description: The shared analysis tools for any tabular dataset - target screen, correlation matrix, pair deep dive, segment breakdown, segment correlation with Simpson's paradox check, partial correlation, nonlinearity, time trend with lags, driver importance, panel within/between-entity decomposition and drivers, and automatic multiple-testing correction - with metadata in tool_registry.yaml. Use to browse tools when scoping, to run the approved plan (A6), or to run a recorded follow-up.
---

# Insight shelf

```powershell
.venv\Scripts\python.exe .cursor\skills\insight-shelf\scripts\list_tools.py [--phase analysis] [--tool <id>]
.venv\Scripts\python.exe .cursor\skills\insight-shelf\scripts\run_plan.py [--force]
.venv\Scripts\python.exe .cursor\skills\insight-shelf\scripts\run_tool.py --tool <id> --params-file p.json --followup-reason "..."
```

| Tool | Question it answers |
|---|---|
| `target-associations` | Which drivers move with the target, ranked (Spearman / eta / Cramer's V, with CI) |
| `correlation-matrix` | Which numeric drivers overlap each other |
| `pair-deep-dive` | What one driver-target relationship looks like (binned or group means) |
| `segment-breakdown` | Does the target differ across segments |
| `segment-correlation` | Does an association hold within segments (Simpson's paradox, heterogeneity) |
| `partial-correlation` | Does it survive holding other columns fixed |
| `nonlinearity-check` | Is it curved or threshold-like |
| `time-trend` | How the target moves over time; lagged driver correlation |
| `driver-importance` | Joint predictive importance and adjusted coefficients (holdout by entity on panels) |
| `panel-decomposition` | Panel data: pooled vs within-entity vs between-entity association for one driver |
| `panel-drivers` | Panel data: which drivers move with the target within entities over time, and between them |
| `multiple-testing` | Benjamini-Hochberg q-values across every test (automatic) |

Every finding has the same shape: `label, x, y, metric, estimate, ci_low, ci_high,
p, n, direction` (panel findings add `n_entities`). Results go to `results/<label>.json` (plan steps are labelled
`H1.S1`, follow-ups `F1`, `F2`, ...), tables to CSV, charts to `charts/`.

Guardrails: tools run only on the approved scope and prepared data; every call is
re-checked for feasibility; follow-ups need a reason, are shown in the report, and
join the multiple-testing family.
