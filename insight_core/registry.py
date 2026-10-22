"""The tool shelf: metadata in tool_registry.yaml, checks for each pathway step."""

from __future__ import annotations

import importlib
from functools import lru_cache

import yaml

from .paths import REGISTRY

USABLE_TYPES = ("numeric", "binary", "categorical")


@lru_cache(maxsize=1)
def load() -> dict:
    return yaml.safe_load(REGISTRY.read_text(encoding="utf-8"))["tools"]


def get(tool_id: str) -> dict:
    tools = load()
    if tool_id not in tools:
        raise KeyError(f"unknown tool '{tool_id}'; see list_tools.py")
    return tools[tool_id]


def function(tool_id: str):
    module, name = get(tool_id)["function"].split(":")
    return getattr(importlib.import_module(module), name)


def catalogue(phase: str | None = None) -> list[dict]:
    return [{"id": k, "phase": v["phase"], "question": v["question"], "target_types": v.get("target_types", []),
             "needs": v.get("needs", []), "params": {p: spec.get("description", "") for p, spec in v.get("params", {}).items()},
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


def step_columns(tool_id: str, params: dict, scope: dict, profile: dict) -> list[str]:
    spec = get(tool_id).get("params", {})
    used = []
    for name, value in params.items():
        kind = spec.get(name, {}).get("type")
        if kind == "column" and value:
            used.append(value)
        elif kind == "columns" and isinstance(value, list):
            used.extend(value)
    if "drivers" in spec and "drivers" not in params:
        used.extend(resolved_drivers(scope, profile))
    return list(dict.fromkeys(used))


def check_step(tool_id: str, params: dict, scope: dict, profile: dict, leakage: list[str]) -> dict:
    """Deterministic verdict for one step: ok | partial | blocked, with reasons."""
    reasons, warnings = [], []
    try:
        tool = get(tool_id)
    except KeyError as exc:
        return {"verdict": "blocked", "reasons": [str(exc)], "warnings": []}
    if tool_id == "multiple-testing":
        return {"verdict": "blocked", "reasons": ["multiple-testing runs automatically; do not add it as a step"], "warnings": []}
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

    excluded = {e["column"] for e in scope.get("exclude", [])}
    for c in step_columns(tool_id, params, scope, profile):
        if c not in cols:
            reasons.append(f"column '{c}' is not in the dataset")
            continue
        if c == target["column"]:
            reasons.append(f"'{c}' is the target; it cannot also be a driver")
        if c in excluded:
            reasons.append(f"'{c}' is excluded in the scope")
        if c in leakage:
            reasons.append(f"'{c}' looks like target leakage; add it to exclude or justify it")
        if cols[c]["type"] not in USABLE_TYPES:
            reasons.append(f"'{c}' is type '{cols[c]['type']}', not usable as a driver")
        elif cols[c]["missing_pct"] > 40:
            warnings.append(f"'{c}' is {cols[c]['missing_pct']}% missing")

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
    elif ent and tool_id != "correlation-matrix":
        warnings.append(f"panel data: this tool pools all {ent} rows and its CIs treat them as independent; "
                        "compare with panel-decomposition or panel-drivers")

    by = params.get("by")
    if by and by in cols:
        shown_levels = cols[by].get("levels", [])
        levels = [lv for lv in shown_levels if lv["count"] >= min_n]
        if "levels" not in cols[by]:
            if "max_levels" in tool.get("params", {}):
                cap = min(10, int(params.get("max_levels", tool["params"]["max_levels"].get("default", 10))))
                warnings.append(f"'{by}' has {cols[by]['n_unique']} levels; the {cap} most frequent will be kept and the rest combined as Other")
            else:
                reasons.append(f"'{by}' has too many levels to segment by")
        elif len(levels) < 2:
            reasons.append(f"'{by}' has fewer than 2 levels with n >= {min_n}")
        elif len(levels) < len(shown_levels):
            warnings.append(f"{len(shown_levels) - len(levels)} level(s) of '{by}' have n < {min_n} and will be skipped")
        max_spec = tool.get("params", {}).get("max_levels")
        if "levels" in cols[by] and max_spec and cols[by]["n_unique"] > min(10, int(params.get("max_levels", max_spec.get("default", 10)))):
            cap = min(10, int(params.get("max_levels", max_spec.get("default", 10))))
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
