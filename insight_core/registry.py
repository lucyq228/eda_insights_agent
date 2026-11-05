"""The tool shelf: metadata in tool_registry.yaml, checks for each pathway step."""

from __future__ import annotations

import importlib
import math
from functools import lru_cache

import yaml

from .paths import REGISTRY

USABLE_TYPES = ("numeric", "binary", "categorical")


ALIASES = {
    "target-associations": "feature-target-associations",
    "pair-deep-dive": "target-by-numeric-bins",
    "segment-breakdown": "target-by-group",
    "segment-correlation": "correlation-by-group",
    "partial-correlation": "adjusted-correlation",
    "driver-importance": "predictive-feature-importance",
    "panel-decomposition": "within-between-correlation",
    "panel-drivers": "within-between-regression",
    "multiple-testing": "multiple-testing-adjustment",
}


def canonical(tool_id: str) -> str:
    return ALIASES.get(tool_id, tool_id)


def resolve_call(tool_id: str, params: dict, types: dict) -> tuple[str, dict]:
    """Translate legacy calls without changing approved scope snapshots."""
    if tool_id == "pair-deep-dive" and types.get(params.get("x")) in ("categorical", "binary"):
        return "target-by-group", {"by": params["x"], **{k: v for k, v in params.items() if k not in ("x", "bins")}}
    if tool_id == "pair-deep-dive":
        params = {k: v for k, v in params.items() if k != "max_levels"}
    return canonical(tool_id), dict(params)


@lru_cache(maxsize=1)
def load() -> dict:
    return yaml.safe_load(REGISTRY.read_text(encoding="utf-8"))["tools"]


def get(tool_id: str) -> dict:
    tools = load()
    tool_id = canonical(tool_id)
    if tool_id not in tools:
        raise KeyError(f"unknown tool '{tool_id}'; see list_tools.py")
    return tools[tool_id]


def function(tool_id: str):
    module, name = get(tool_id)["function"].split(":")
    return getattr(importlib.import_module(module), name)


def catalogue(phase: str | None = None) -> list[dict]:
    return [{"id": k, "phase": v["phase"], "question": v["question"], "target_types": v.get("target_types", []),
             "needs": v.get("needs", []), "params": {p: spec.get("description", "") for p, spec in v.get("params", {}).items()},
             "use_when": v.get("use_when", v["question"]), "reuse": v.get("reuse", ""),
             "cost_class": v.get("cost_class", "low"), "caveats": v.get("caveats", [])}
            for k, v in load().items() if phase in (None, v["phase"])]


def _profile_columns(profile: dict) -> dict[str, dict]:
    return {c["name"]: c for c in profile["columns"]}


def resolved_drivers(scope: dict, profile: dict) -> list[str]:
    cols = _profile_columns(profile)
    skip = {scope["target"]["column"], scope.get("id_column"), scope.get("date_column"), scope.get("entity_column")}
    skip |= {e["column"] for e in scope.get("exclude", [])}
    if scope.get("drivers", "all") == "all":
        return [c for c, info in cols.items() if info["type"] in USABLE_TYPES and c not in skip]
    return [c for c in scope["drivers"] if c not in skip]


def grouping_columns(by) -> list[str]:
    """Normalize a count grouping without joining labels or accepting duplicate fields."""
    columns = [by] if isinstance(by, str) else by
    if (not isinstance(columns, list) or not columns
            or any(not isinstance(c, str) or not c.strip() for c in columns)
            or len(set(columns)) != len(columns)):
        raise ValueError("by must be a column name or a nonempty list of distinct column names")
    return columns


def broad_change(scope: dict) -> bool:
    """Change investigations default to broad; focused exceptions must be explicit."""
    return bool(change_steps(scope)) and scope.get("change_investigation", "broad") != "focused"


def validate_dimension_bins(scope: dict, types: dict) -> list[str]:
    bins = scope.get("dimension_bins", {})
    if not isinstance(bins, dict):
        return ["dimension_bins must map numeric fields to fixed cut points"]
    errors = []
    for column, edges in bins.items():
        if (types.get(column) not in ("numeric", "binary") or not isinstance(edges, list) or not edges
                or any(isinstance(x, bool) or not isinstance(x, (int, float)) or not math.isfinite(x) for x in edges)
                or edges != sorted(set(edges))):
            errors.append(f"dimension_bins {column}: use a numeric field and increasing finite cut points")
    return errors


def step_columns(tool_id: str, params: dict, scope: dict, profile: dict) -> list[str]:
    spec = get(tool_id).get("params", {})
    used = []
    for name, value in params.items():
        kind = spec.get(name, {}).get("type")
        if kind == "column_or_columns":
            used.extend(grouping_columns(value))
        elif kind == "column" and value:
            used.append(value)
        elif kind == "columns" and isinstance(value, list):
            used.extend(value)
    if "drivers" in spec and "drivers" not in params:
        used.extend(resolved_drivers(scope, profile))
    return list(dict.fromkeys(used))


def check_step(tool_id: str, params: dict, scope: dict, profile: dict, leakage: list[str]) -> dict:
    """Deterministic verdict for one step: ok | partial | blocked, with reasons."""
    count_change = tool_id == "count-change-contribution"
    change = count_change or tool_id == "rate-change-decomposition"
    if change and params.get("view"):
        return {"verdict": "blocked", "reasons": ["change tools require the approved base grain"], "warnings": []}
    if params.get("view"):
        from .views import view_scope_profile
        try:
            scope, profile = view_scope_profile(scope, profile, params["view"])
            params = {k: v for k, v in params.items() if k != "view"}
            leakage = []  # Raw column leakage does not describe derived metrics.
        except (KeyError, ValueError) as exc:
            return {"verdict": "blocked", "reasons": [str(exc)], "warnings": []}
    tool_id, params = resolve_call(tool_id, params, {c["name"]: c["type"] for c in profile["columns"]})
    reasons, warnings = [], []
    try:
        tool = get(tool_id)
    except KeyError as exc:
        return {"verdict": "blocked", "reasons": [str(exc)], "warnings": []}
    if tool_id == "multiple-testing-adjustment":
        return {"verdict": "blocked", "reasons": ["multiple-testing-adjustment runs automatically; do not add it as a step"], "warnings": []}
    if tool["phase"] != "analysis":
        return {"verdict": "blocked", "reasons": [f"{tool_id} is a {tool['phase']} tool, not an analysis step"], "warnings": []}
    cols = _profile_columns(profile)
    target = scope["target"]
    min_n = int(scope.get("min_n", 30))

    unknown = sorted(set(params) - set(tool.get("params", {})))
    if unknown:
        reasons.append(f"unknown params {unknown}; allowed: {sorted(tool.get('params', {}))}")
    if target["type"] not in tool.get("target_types", USABLE_TYPES):
        reasons.append(f"target type '{target['type']}' not supported (needs {tool['target_types']})")
    for name, pspec in tool.get("params", {}).items():
        if pspec.get("required") and not params.get(name):
            reasons.append(f"param '{name}' is required")

    if change:
        cohort, by = params.get("cohort"), params.get("by")
        try:
            groups = grouping_columns(by)
        except ValueError as exc:
            return {"verdict": "blocked", "reasons": [str(exc)], "warnings": []}
        if not isinstance(cohort, str):
            return {"verdict": "blocked", "reasons": ["cohort must be one column"], "warnings": []}
        if cohort in groups:
            reasons.append("cohort and grouping must be distinct")
        reasons += validate_dimension_bins(scope, {c: info["type"] for c, info in cols.items()})
        if not count_change:
            denominator = params.get("denominator")
            if target["type"] != "binary" and not denominator:
                reasons.append("numeric rate target requires a denominator column; target must be event counts")
            if denominator and target["type"] != "numeric":
                reasons.append("aggregated rates require a numeric event-count target")
            if denominator and (denominator in groups or denominator == cohort or denominator == target["column"]):
                reasons.append("denominator must be distinct from target, cohort and grouping")
            if denominator in cols and cols[denominator]["type"] not in ("numeric", "binary", "constant"):
                reasons.append("denominator must contain numeric eligible counts")
        allowed = set(resolved_drivers(scope, profile)) | set(scope.get("segments", []))
        for field in [cohort, *groups]:
            scoped_date = count_change and field == cohort == scope.get("date_column")
            if (field not in allowed and not scoped_date) or field in (scope.get("id_column"), scope.get("entity_column")):
                reasons.append(f"'{field}' must be a scoped driver or segment, distinct from unit identifiers")
            supported = ("binary", "categorical", "numeric", "datetime") if count_change and field == cohort else ("binary", "categorical")
            if field in cols and cols[field]["type"] not in supported and not (field in groups and field in scope.get("dimension_bins", {})):
                reasons.append(f"'{field}' has an unsupported period or grouping type")
        labels = [params.get(key) for key in ("baseline", "comparison")]
        if not all(isinstance(label, str) and label.strip() for label in labels) or labels[0] == labels[1]:
            reasons.append("provide two distinct cohort labels as text")
        elif cohort in cols and "levels" in cols[cohort]:
            known = {item["level"] for item in cols[cohort]["levels"]}
            if not set(labels) <= known:
                reasons.append("requested cohort label missing from profile")

    if count_change:
        history = params.get("history")
        if "history" in params and not (isinstance(history, list) and len(history) >= 3
                and all(isinstance(item, str) and item for item in history)
                and len(set(history)) == len(history) and history[-1] == params.get("baseline")
                and params.get("comparison") not in history):
            reasons.append("trend requires at least three distinct ordered pre-period labels ending at baseline")
        if "absent_is_zero" in params and not isinstance(params["absent_is_zero"], bool):
            reasons.append("absent_is_zero must be a boolean")

    excluded = {e["column"] for e in scope.get("exclude", [])}
    for c in step_columns(tool_id, params, scope, profile):
        if c not in cols:
            reasons.append(f"column '{c}' is not in the dataset")
            continue
        if c == target["column"]:
            reasons.append(f"'{c}' is the target; it cannot also be a driver")
        component = tool_id == "rate-change-decomposition" and c == params.get("denominator")
        if c in excluded and not component and (change or not tool.get("descriptive")):
            reasons.append(f"'{c}' is excluded in the scope")
        if c in leakage and not component and (change or not tool.get("descriptive")):
            reasons.append(f"'{c}' looks like target leakage; add it to exclude or justify it")
        if cols[c]["type"] not in USABLE_TYPES and not tool.get("descriptive"):
            reasons.append(f"'{c}' is type '{cols[c]['type']}', not usable as a driver")
        elif cols[c]["missing_pct"] > 40:
            warnings.append(f"'{c}' is {cols[c]['missing_pct']}% missing")

    if "drivers" in tool.get("params", {}) and not (params.get("drivers") or resolved_drivers(scope, profile)):
        reasons.append("this tool needs at least one model driver")
    x = params.get("x")
    if "numeric_x" in tool.get("needs", []) and x in cols and cols[x]["type"] != "numeric":
        reasons.append(f"'{x}' must be numeric for {tool_id}")
    if "date" in tool.get("needs", []):
        date = scope.get("date_column")
        if not date or date not in cols or cols[date]["type"] != "datetime":
            reasons.append("needs a date column in the scope (date_column) that parses as dates")
        elif cols[date].get("distinct_dates", 0) < 4:
            reasons.append("fewer than 4 distinct dates; no trend can be read")
    ent = scope.get("entity_column")
    if "entity" in tool.get("needs", []):
        if not ent or ent not in cols:
            reasons.append("needs an entity_column in the scope (the unit observed repeatedly, e.g. store_id)")
        else:
            n_ent = cols[ent]["n_unique"]
            per = profile["n_rows"] / max(1, n_ent)
            if n_ent < 2 or per < 2:
                reasons.append(f"'{ent}' does not repeat (about {per:.1f} rows each); there is no within-entity variation")
            else:
                if n_ent < min_n:
                    warnings.append(f"only {n_ent} {ent} values; the between-entity estimate will be wide")
                if per < 4:
                    warnings.append(f"about {per:.1f} rows per {ent}; within-entity estimates will be fragile")
            if str(params.get("time_effects", True)).lower() not in ("false", "0", "no", "off") \
                    and not scope.get("date_column"):
                warnings.append("no date_column, so period-wide swings are not removed from the within estimate")
    elif ent and tool_id != "correlation-matrix" and not change:
        warnings.append(f"panel data: this tool pools all {ent} rows and its CIs treat them as independent; "
                        "compare with within-between-correlation or within-between-regression")

    by = params.get("by")
    if "categorical_by" in tool.get("needs", []) and by in cols and cols[by]["type"] not in ("categorical", "binary"):
        reasons.append("target-by-group requires categorical groups; use target-by-numeric-bins for numeric features")
    if not change and by and by in cols:
        shown_levels = cols[by].get("levels", [])
        levels = [lv for lv in shown_levels if lv["count"] >= min_n]
        if "levels" not in cols[by]:
            if "max_levels" in tool.get("params", {}):
                cap = max(2, int(params.get("max_levels", tool["params"]["max_levels"].get("default", 10))))
                warnings.append(f"'{by}' has {cols[by]['n_unique']} levels; the {cap} most frequent will be kept and the rest combined as Other")
            else:
                reasons.append(f"'{by}' has too many levels to segment by")
        elif len(levels) < 2:
            reasons.append(f"'{by}' has fewer than 2 levels with n >= {min_n}")
        elif len(levels) < len(shown_levels):
            warnings.append(f"{len(shown_levels) - len(levels)} level(s) of '{by}' have n < {min_n} and will be skipped")
        max_spec = tool.get("params", {}).get("max_levels")
        if "levels" in cols[by] and max_spec and cols[by]["n_unique"] > max(2, int(params.get("max_levels", max_spec.get("default", 10)))):
            cap = max(2, int(params.get("max_levels", max_spec.get("default", 10))))
            warnings.append(f"only the {cap} most frequent '{by}' levels will be shown separately; all others become Other")

    n_target = round(profile["n_rows"] * (1 - cols.get(target["column"], {}).get("missing_pct", 100) / 100))
    if n_target < min_n:
        reasons.append(f"only {n_target} rows with a target value (min_n {min_n})")
    elif n_target < 2 * min_n:
        warnings.append(f"only {n_target} rows with a target value; estimates will be wide")

    verdict = "blocked" if reasons else "partial" if warnings else "ok"
    return {"verdict": verdict, "reasons": reasons, "warnings": warnings}


def check_scope(scope: dict, profile: dict, leakage: list[str]) -> list[dict]:
    rows = []
    for h in scope.get("hypotheses", []):
        for i, step in enumerate(h.get("pathway", []), 1):
            res = check_step(step["tool"], step.get("params", {}), scope, profile, leakage)
            rows.append({"step_id": f"{h['id']}.S{i}", "hypothesis": h["id"], "tool": step["tool"],
                         "params": step.get("params", {}), **res})
    return rows


def panel_tools() -> list[str]:
    return [k for k, v in load().items() if "entity" in v.get("needs", [])]


def plan_steps(scope: dict) -> list[dict]:
    steps = []
    for h in scope.get("hypotheses", []):
        for i, step in enumerate(h.get("pathway", []), 1):
            steps.append({"step_id": f"{h['id']}.S{i}", "hypothesis": h["id"], "tool": step["tool"],
                          "params": step.get("params", {}), "purpose": step.get("purpose", "")})
    return steps


def change_steps(scope: dict) -> list[dict]:
    return [step for step in plan_steps(scope)
            if step["tool"] in ("rate-change-decomposition", "count-change-contribution")]
