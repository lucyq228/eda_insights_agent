"""Scope proposal validation, approval, and the SHA-256 lock."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from . import registry
from .paths import refuse
from .state import read_artifact, sha, write_artifact

REQUIRED = ["project_name", "purpose", "decision_supported", "target", "unit_of_analysis", "hypotheses"]
TARGET_TYPES = ("numeric", "binary", "categorical")


def validate(scope: dict, profile: dict) -> tuple[list[str], list[str]]:
    errors, warnings = [], []
    for key in REQUIRED:
        if not scope.get(key):
            errors.append(f"missing '{key}'")
    if errors:
        return errors, warnings
    version = scope.get("report_schema_version", 1)
    if version not in (1, 2):
        errors.append("report_schema_version must be 1 or 2")
    if version == 2:
        context = scope.get("business_context")
        if not isinstance(context, dict):
            errors.append("v2 scope needs business_context")
        else:
            for key in ("audience", "decision"):
                if not isinstance(context.get(key), str) or not context[key].strip():
                    errors.append(f"business_context needs {key}; explicit unknown is allowed")
            for key in ("available_levers", "constraints", "success_measures", "unknowns"):
                if not isinstance(context.get(key), list) or any(not isinstance(x, str) for x in context[key]):
                    errors.append(f"business_context.{key} must be a list of strings")
    cols = {c["name"]: c for c in profile["columns"]}
    target = scope["target"]
    tc = target.get("column")
    if tc not in cols:
        errors.append(f"target column '{tc}' is not in the dataset")
    if target.get("type") not in TARGET_TYPES:
        errors.append(f"target.type must be one of {TARGET_TYPES}")
    if target.get("type") == "binary":
        levels = [lv["level"] for lv in cols.get(tc, {}).get("levels", [])]
        if str(target.get("positive_class")) not in levels:
            errors.append(f"binary target needs positive_class, one of {levels}")
    if not target.get("definition"):
        errors.append("target.definition: say what the target measures and which direction is good")
    for key in ("id_column", "date_column", "entity_column"):
        if scope.get(key) and scope[key] not in cols:
            errors.append(f"{key} '{scope[key]}' is not in the dataset")
    if scope.get("entity_column") and scope["entity_column"] == tc:
        errors.append("entity_column cannot be the target")
    drivers = scope.get("drivers", "all")
    if drivers != "all":
        if not isinstance(drivers, list):
            errors.append("drivers must be 'all' or a list of columns (empty is valid for descriptive plans)")
        else:
            errors += [f"driver '{c}' is not in the dataset" for c in drivers if c not in cols]
    for e in scope.get("exclude", []):
        if not e.get("reason"):
            errors.append(f"exclude '{e.get('column')}' needs a reason")
    for c in scope.get("segments", []):
        if c not in cols:
            errors.append(f"segment '{c}' is not in the dataset")

    if not isinstance(scope["hypotheses"], list):
        return ["hypotheses must be a list of meaningful questions"], warnings
    ids = [h.get("id") for h in scope["hypotheses"]]
    if len(ids) != len(set(ids)):
        errors.append("hypothesis ids must be unique")
    tools = registry.load()
    for h in scope["hypotheses"]:
        for key in ("id", "statement", "rationale", "support_criteria", "pathway"):
            if not h.get(key):
                errors.append(f"{h.get('id', '?')}: missing '{key}'")
        for step in h.get("pathway", []):
            if step.get("tool") not in tools:
                errors.append(f"{h.get('id')}: unknown tool '{step.get('tool')}'")
            elif not step.get("purpose"):
                errors.append(f"{h.get('id')}: step '{step['tool']}' needs a purpose")
    if scope.get("mode", "confirmatory") not in ("exploratory", "confirmatory"):
        errors.append("mode must be exploratory or confirmatory")
    roles = scope.get("roles", {})
    for role, value in roles.items():
        values = value if isinstance(value, list) else [value]
        errors += [f"role {role}: unknown column {c}" for c in values if c not in cols]
    if not isinstance(scope.get("max_followups", 12), int) or scope.get("max_followups", 12) < 0:
        errors.append("max_followups must be a nonnegative integer")
    for c, reason in scope.get("leakage_justifications", {}).items():
        if c not in cols or not isinstance(reason, str) or not reason.strip():
            errors.append(f"leakage justification for {c} needs a known column and provenance/timing rationale")
    from .views import validate_views
    errors += validate_views(scope, profile)
    qids = [q.get("id") for q in scope.get("user_questions", [])]
    if len(qids) != len(set(qids)):
        errors.append("user question ids must be unique")
    for q in scope.get("user_questions", []):
        if not q.get("question") or not q.get("why_it_matters"):
            errors.append(f"question {q.get('id')}: needs 'question' and 'why_it_matters'")
    return errors, warnings


def approve(run_dir: Path, confirmation: str = "", *, exploration: bool = False) -> dict:
    if not exploration and (not confirmation or len(confirmation.strip()) < 2):
        raise ValueError("quote the user's explicit approval in --user-confirmation")
    if (run_dir / "approved_scope.json").exists():
        raise ValueError("this run already has an approved scope; a different scope needs a new run")
    proposal = read_artifact(run_dir, "scope_proposal.json")
    feas = read_artifact(run_dir, "feasibility.json")
    if not proposal:
        raise ValueError("no scope proposal")
    if exploration:
        if proposal["scope"].get("mode") != "exploratory":
            raise ValueError("automatic activation is only for exploratory scopes")
        if not (read_artifact(run_dir, "run.json") or {}).get("request"):
            raise ValueError("exploration needs the original user request")
        confirmation = ""  # Never manufacture a user approval quote.

    if not feas or (feas.get("upstream") or {}).get("sha256") != sha(run_dir / "scope_proposal.json"):
        raise ValueError("feasibility is missing or stale; rerun feasibility on the current scope")
    blocked = [s["step_id"] for s in feas["steps"] if s["final_verdict"] == "blocked"]
    if blocked:
        raise ValueError(f"blocked steps must be removed or fixed first: {blocked}")
    if feas.get("scope_issues"):
        raise ValueError(f"scope issues must be fixed first: {feas['scope_issues']}")
    answers = (read_artifact(run_dir, "answers.json") or {}).get("answers", {})
    open_q = [q["id"] for q in proposal["scope"].get("user_questions", []) if q["id"] not in answers]
    if open_q:
        raise ValueError(f"unanswered user questions: {open_q}")
    approved = {**proposal["scope"], "version": proposal["version"], "answers": answers,
                "authorization": "user_requested_exploration" if exploration else "explicit_confirmation",
                "approved_at": datetime.now().isoformat(timespec="seconds"), "user_confirmation": confirmation.strip()}
    write_artifact(run_dir, "approved_scope.json", approved)
    lock = {"sha256": sha(run_dir / "approved_scope.json"), "data_sha256": read_artifact(run_dir, "run.json")["data_sha256"]}
    write_artifact(run_dir, "scope.lock.json", lock)
    return approved


def load_approved(run_dir: Path) -> dict:
    lock = read_artifact(run_dir, "scope.lock.json")
    if not lock:
        refuse("no active scope; activate exploration or obtain confirmatory approval first")
    if lock["sha256"] != sha(run_dir / "approved_scope.json"):
        refuse("approved_scope.json changed after approval; refusing to run (start a new run)")
    run = read_artifact(run_dir, "run.json")
    if sha(Path(run["data_path"])) != lock["data_sha256"]:
        refuse("the dataset file changed after approval; start a new run")
    return read_artifact(run_dir, "approved_scope.json")
