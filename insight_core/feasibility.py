"""Deterministic feasibility of the current scope proposal, plus specialist judgment."""

from __future__ import annotations

from pathlib import Path

from . import registry
from .data import load_table
from .paths import refuse
from .state import read_artifact, sha, write_artifact
from .tools_eda import leakage_suspects

ORDER = {"ok": 0, "partial": 1, "blocked": 2}
AUTO_CHECK_VERSION = 1


def auto_check(run_dir: Path) -> dict:
    proposal = read_artifact(run_dir, "scope_proposal.json")
    if not proposal:
        refuse("no scope proposal yet")
    prof = read_artifact(run_dir, "profile.json")
    scope = proposal["scope"]
    df = load_table(read_artifact(run_dir, "run.json")["data_path"])
    types = {c["name"]: c["type"] for c in prof["columns"]}
    leaks = leakage_suspects(df, scope, types)
    leak_cols = [x["column"] for x in leaks if x.get("blocking", True) and not scope.get("leakage_justifications", {}).get(x["column"]) and x["column"] not in {e["column"] for e in scope.get("exclude", [])}]
    steps = registry.check_scope(scope, prof, leak_cols)
    drivers = registry.resolved_drivers(scope, prof)
    scope_issues = []
    for c in leak_cols:
        if c in drivers:
            scope_issues.append(f"'{c}' would be a driver but looks like leakage: {next(x['reason'] for x in leaks if x['column'] == c)}")
    scope_issues += panel_issues(scope, prof)
    return {"scope_version": proposal["version"], "steps": steps, "leakage_suspects": leaks,
            "resolved_drivers": drivers, "scope_issues": scope_issues,
            "counts": {v: sum(s["verdict"] == v for s in steps) for v in ORDER}}


def save_auto_check(run_dir: Path) -> dict:
    """Run the expensive deterministic screen once and persist its inputs."""
    auto = auto_check(run_dir)
    run = read_artifact(run_dir, "run.json") or {}
    artifact = {**auto, "algorithm_version": AUTO_CHECK_VERSION,
                "profile_sha256": sha(run_dir / "profile.json"),
                "data_sha256": run.get("data_sha256")}
    write_artifact(run_dir, "feasibility_auto.json", artifact, upstream="scope_proposal.json")
    return artifact


def load_auto_check(run_dir: Path) -> dict:
    """Load a current auto check; never silently repeat the raw-data scan."""
    auto = read_artifact(run_dir, "feasibility_auto.json")
    run = read_artifact(run_dir, "run.json") or {}
    stale = []
    if not auto:
        stale.append("it has not been run")
    else:
        if auto.get("algorithm_version") != AUTO_CHECK_VERSION:
            stale.append("the feasibility algorithm changed")
        if (auto.get("upstream") or {}).get("sha256") != sha(run_dir / "scope_proposal.json"):
            stale.append("the scope proposal changed")
        if auto.get("profile_sha256") != sha(run_dir / "profile.json"):
            stale.append("the data profile changed")
        if auto.get("data_sha256") != run.get("data_sha256"):
            stale.append("the run data changed")
    if stale:
        refuse("feasibility auto-check is missing or stale (" + "; ".join(stale) + "); run check_feasibility.py")
    return auto


def panel_issues(scope: dict, profile: dict) -> list[str]:
    """Panel data needs an explicit decision: an entity_column with a panel tool, or a panel_reason."""
    ent = scope.get("entity_column")
    if ent:
        return []  # Entity identity is useful without requiring a panel regression.
    found = profile.get("panel_candidates", [])
    if found and not scope.get("panel_reason"):
        p = found[0]
        return [f"the data looks like a panel: '{p['column']}' repeats across '{p['date_column']}' "
                f"({p['n_entities']} entities, median {p['median_periods']} periods each). Set entity_column and add "
                "a panel tool so within- and between-entity patterns are separated, or give panel_reason for "
                "treating rows as independent"]
    return []


def merge(auto: dict, judgment: dict) -> tuple[dict, list[str]]:
    """The specialist may make a verdict stricter, never looser."""
    errors = []
    by_id = {s["step_id"]: s for s in judgment.get("steps", [])}
    steps = []
    for s in auto["steps"]:
        j = by_id.get(s["step_id"], {})
        verdict = j.get("verdict", s["verdict"])
        if verdict not in ORDER:
            errors.append(f"{s['step_id']}: verdict must be ok, partial, or blocked")
            verdict = s["verdict"]
        if ORDER[verdict] < ORDER[s["verdict"]]:
            errors.append(f"{s['step_id']}: cannot loosen '{s['verdict']}' to '{verdict}'")
            verdict = s["verdict"]
        if verdict != s["verdict"] and not j.get("judgment"):
            errors.append(f"{s['step_id']}: explain why you made the verdict stricter")
        steps.append({**s, "auto_verdict": s["verdict"], "final_verdict": verdict, "judgment": j.get("judgment", "")})
    unknown = sorted(set(by_id) - {s["step_id"] for s in auto["steps"]})
    if unknown:
        errors.append(f"unknown step ids in judgment: {unknown}")
    for key in ("can_answer", "cannot_answer", "overall"):
        if not judgment.get(key):
            errors.append(f"judgment needs '{key}'")
    if auto["scope_issues"] and not judgment.get("recommendations"):
        errors.append("scope issues found; add recommendations for scope revision")
    return {"steps": steps}, errors
