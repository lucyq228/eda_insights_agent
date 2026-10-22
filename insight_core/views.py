"""Declarative aggregate views. No eval, arbitrary code, or mutation of the base table."""
from __future__ import annotations

import pandas as pd

OPS = {"sum", "mean", "median", "min", "max", "nunique", "count", "size"}


def validate_views(scope, profile):
    columns = {c["name"] for c in profile["columns"]}
    errors = []
    for name, spec in scope.get("views", {}).items():
        groups = spec.get("group_by", [])
        if not groups:
            errors.append(f"view {name}: needs group_by")
        for c in groups:
            if c not in columns:
                errors.append(f"view {name}: unknown group {c}")
        outputs = set(groups)
        for output, metric in spec.get("metrics", {}).items():
            if output in outputs or metric.get("column") not in columns or metric.get("agg") not in OPS:
                errors.append(f"view {name}: invalid metric {output}")
            outputs.add(output)
        for output, ratio in spec.get("ratios", {}).items():
            if output in outputs or any(ratio.get(k) not in outputs for k in ("numerator", "denominator")):
                errors.append(f"view {name}: invalid ratio {output}")
            outputs.add(output)
        if spec.get("target") not in outputs or spec.get("target") in groups:
            errors.append(f"view {name}: target must be a calculated metric")
        if any(c not in outputs for c in spec.get("drivers", [])):
            errors.append(f"view {name}: drivers must exist in the view")
        for key in ("entity_column", "date_column"):
            if spec.get(key) and spec[key] not in groups:
                errors.append(f"view {name}: {key} must be in group_by")
        if spec.get("freq") and spec.get("date_column") not in groups:
            errors.append(f"view {name}: frequency needs a grouped date column")
    return errors


def view_scope_profile(scope, profile, name):
    """Schema for feasibility. Actual sample size is checked again after aggregation."""
    if name not in scope.get("views", {}):
        raise ValueError(f"unknown view {name}")
    spec = scope["views"][name]
    source = {c["name"]: c for c in profile["columns"]}
    columns = [dict(source[c]) for c in spec["group_by"]]
    columns += [{"name": c, "type": "numeric", "missing_pct": 0, "n_unique": profile["n_rows"]}
                for c in list(spec["metrics"]) + list(spec.get("ratios", {}))]
    effective = {**scope, "active_view": name, "target": {"column": spec["target"], "type": "numeric",
                 "definition": spec.get("definition", spec["target"])},
                 "unit_of_analysis": spec.get("unit", ", ".join(spec["group_by"])),
                 "drivers": spec.get("drivers", []), "exclude": [], "segments": [],
                 "entity_column": spec.get("entity_column"), "id_column": None,
                 "date_column": spec.get("date_column")}
    return effective, {**profile, "columns": columns}


def build_view(df, scope, name):
    spec = scope["views"][name]
    d = df.copy()
    date = spec.get("date_column")
    if spec.get("freq"):
        d[date] = pd.to_datetime(d[date], errors="coerce").dt.to_period(spec["freq"]).dt.to_timestamp()
    grouped = d.groupby(spec["group_by"], dropna=False, observed=True)
    parts = {}
    for output, m in spec["metrics"].items():
        col = grouped[m["column"]]
        parts[output] = col.sum(min_count=1) if m["agg"] == "sum" else col.agg(m["agg"])
    result = pd.DataFrame(parts).reset_index()
    for output, ratio in spec.get("ratios", {}).items():
        den = result[ratio["denominator"]]
        result[output] = result[ratio["numerator"]] / den.where(den != 0)
    return result
