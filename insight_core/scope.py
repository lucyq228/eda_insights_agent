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
        if not isinstance(drivers, list) or not drivers:
            errors.append("drivers must be 'all' or a non-empty list of columns")
        else:
            errors += [f"driver '{c}' is not in the dataset" for c in drivers if c not in cols]
    for e in scope.get("exclude", []):
        if not e.get("reason"):
            errors.append(f"exclude '{e.get('column')}' needs a reason")
    for c in scope.get("segments", []):
        if c not in cols:
            errors.append(f"segment '{c}' is not in the dataset")

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
    n_hypotheses = len(scope["hypotheses"])
    if n_hypotheses > 10:
        errors.append("use no more than 10 hypotheses; merge overlapping questions and keep only decision-relevant tests")
    elif n_hypotheses < 4:
        exception = str(scope.get("hypothesis_count_exception") or "").strip()
        if not exception:
            errors.append("use 4 to 10 hypotheses, or add hypothesis_count_exception explaining why fewer meaningful tests exist")
        else:
            warnings.append(f"only {n_hypotheses} hypotheses by explicit exception: {exception}")
    elif n_hypotheses > 8:
        warnings.append("9-10 hypotheses is allowed, but confirm each one changes the decision and is not shelf-coverage padding")
    qids = [q.get("id") for q in scope.get("user_questions", [])]
    if len(qids) != len(set(qids)):
        errors.append("user question ids must be unique")
    for q in scope.get("user_questions", []):
        if not q.get("question") or not q.get("why_it_matters"):
            errors.append(f"question {q.get('id')}: needs 'question' and 'why_it_matters'")
    return errors, warnings


def approve(run_dir: Path, confirmation: str) -> dict:
    if not confirmation or len(confirmation.strip()) < 2:
        raise ValueError("quote the user's explicit approval in --user-confirmation")
    if (run_dir / "approved_scope.json").exists():
        raise ValueError("this run already has an approved scope; a different scope needs a new run")
    proposal = read_artifact(run_dir, "scope_proposal.json")
    feas = read_artifact(run_dir, "feasibility.json")
    if not proposal:
        raise ValueError("no scope proposal")
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
                "approved_at": datetime.now().isoformat(timespec="seconds"), "user_confirmation": confirmation.strip()}
    write_artifact(run_dir, "approved_scope.json", approved)
    lock = {"sha256": sha(run_dir / "approved_scope.json"), "data_sha256": read_artifact(run_dir, "run.json")["data_sha256"]}
    write_artifact(run_dir, "scope.lock.json", lock)
    return approved


def load_approved(run_dir: Path) -> dict:
    lock = read_artifact(run_dir, "scope.lock.json")
    if not lock:
        refuse("no approved scope yet; the user must approve the scope first")
    if lock["sha256"] != sha(run_dir / "approved_scope.json"):
        refuse("approved_scope.json changed after approval; refusing to run (start a new run)")
    run = read_artifact(run_dir, "run.json")
    if sha(Path(run["data_path"])) != lock["data_sha256"]:
        refuse("the dataset file changed after approval; start a new run")
    return read_artifact(run_dir, "approved_scope.json")
