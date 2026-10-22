"""Run state: which milestones exist, which are stale, and what comes next."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

# name, artifact, owner, upstream artifact whose hash the artifact must carry
MILESTONES = [
    ("profile", "profile.json", "A4 Data Quality & EDA", None),
    ("scope_draft", "scope_proposal.json", "A2 Scope", None),
    ("feasibility", "feasibility.json", "A3 Feasibility", "scope_proposal.json"),
    ("approval", "approved_scope.json", "Manager + user", None),
    ("data_quality", "data_quality.json", "A4 Data Quality & EDA", "approved_scope.json"),
    ("prepared_data", "prepared_data.json", "A5 Data Prep", "approved_scope.json"),
    ("analyses", "analyses_index.json", "A6 Analysis", "prepared_data.json"),
    ("review", "review.json", "A7 Review & Insights", "analyses_index.json"),
    ("insights", "insights.json", "A7 Review & Insights", "review.json"),
    ("report", "report.json", "A7 Review & Insights", "insights.json"),
]


def sha(path: Path) -> str | None:
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def read_artifact(run_dir: Path, name: str) -> dict | None:
    path = run_dir / name
    return read_json(path) if path.exists() else None


def write_artifact(run_dir: Path, name: str, data: dict, upstream: str | None = None) -> Path:
    if upstream:
        data = {**data, "upstream": {"file": upstream, "sha256": sha(run_dir / upstream)}}
    path = run_dir / name
    path.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
    return path


def milestone_status(run_dir: Path) -> list[dict]:
    rows = []
    for name, artifact, owner, upstream in MILESTONES:
        data = read_artifact(run_dir, artifact)
        status, reason = "missing", ""
        if data is not None:
            status = "done"
            if upstream and (data.get("upstream") or {}).get("sha256") != sha(run_dir / upstream):
                status, reason = "stale", f"{upstream} changed since this was saved"
            elif data.get("errors"):
                status, reason = "incomplete", f"{len(data['errors'])} error(s)"
            elif name == "approval" and not _lock_ok(run_dir):
                status, reason = "tampered", "approved_scope.json does not match scope.lock.json"
        rows.append({"milestone": name, "artifact": artifact, "owner": owner, "status": status, "reason": reason})
    return rows


def _lock_ok(run_dir: Path) -> bool:
    lock = read_artifact(run_dir, "scope.lock.json")
    return bool(lock) and lock.get("sha256") == sha(run_dir / "approved_scope.json")


def milestone_done(run_dir: Path, name: str) -> bool:
    return any(r["milestone"] == name and r["status"] == "done" for r in milestone_status(run_dir))


def next_step(run_dir: Path) -> dict | None:
    for row in milestone_status(run_dir):
        if row["status"] != "done":
            return row
    return None
