---
name: profile-eda
description: Profile any tabular dataset before scoping (column types, missingness, distributions, candidate targets, ids, dates, segments) and run data-quality checks and a target overview after the scope is approved (duplicates, key uniqueness, target balance, outliers, leakage). Use for the profile and data_quality milestones (A4 Data Quality & EDA).
---

# Profile and data quality (A4)

```powershell
.venv\Scripts\python.exe .cursor\skills\profile-eda\scripts\profile_data.py    # before scoping
.venv\Scripts\python.exe .cursor\skills\profile-eda\scripts\data_quality.py    # after approval
```

## profile_data.py -> profile.json

Aggregates only: per column the inferred type (numeric, binary, categorical,
datetime, id, text, constant), % missing, unique count, quantiles and skew, levels
for columns with at most 30 levels, and date ranges. Also: duplicate rows,
candidate targets (outcome-like names, binary columns, last column), id columns,
date columns, segment candidates (2-15 levels), panel candidates (a column whose
values repeat across dates with about one row per value and date, e.g. store_id by
week: entities, median periods, balance), and flags. Charts:
`charts/profile__histograms.png`, `charts/profile__missingness.png`.

## data_quality.py -> data_quality.json (needs the approved scope)

Checks: duplicates, one row per unit (entity or id + date), panel shape (rows per
entity) when the scope has `entity_column`, target missingness, sample size
vs `min_n`, target balance or skew, driver missingness and outliers, cardinality,
leakage suspects (very high association, name overlap, or the target being a
product/ratio of a column), and date parsing. Any `fail` makes the milestone
incomplete. Also writes the target overview and target-by-segment charts.

## How to read it

- Say what each issue means for the analysis, e.g. "12% missing ratings: rating
  results rest on about 1,800 rows", "8 duplicates: prep drops them".
- A leakage suspect that is still a driver is a hard stop: report it.
- Do not open the data file or print rows. Work only from the script output.
