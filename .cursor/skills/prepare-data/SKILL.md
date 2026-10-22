---
name: prepare-data
description: Deterministically build the analysis table from the approved scope - drop duplicates, keep target and scoped drivers, code a binary target as 1/0, parse dates, keep missing categories as "Missing", and group rare levels as "Other". Use for the prepared_data milestone.
---

# Prepare data (deterministic pipeline)

```powershell
.venv\Scripts\python.exe .cursor\skills\prepare-data\scripts\prepare_data.py [--params-file p.json]
```

Optional params: `{"rare_level_share": 0.01}` (levels below this share become "Other").

Writes `datasets/prepared.parquet` and `prepared_data.json` (row count, column
types, and a log of every transformation). Requires a passing data-quality check.

Check the log against `data_quality.json`: duplicates dropped, rows without a
target dropped, excluded columns gone, binary target coded as stated. The
`id_column` and `entity_column` are kept as keys (the panel tools need the entity),
never as drivers.
Report anything surprising (for example, many rows lost).
