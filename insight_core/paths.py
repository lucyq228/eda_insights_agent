from __future__ import annotations

import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "tool_registry.yaml"
RUN_SUBDIRS = ("drafts", "results", "charts", "datasets")


def refuse(message: str):
    """Stop a script with the same JSON shape every script prints."""
    print(json.dumps({"ok": False, "error": message}))
    sys.exit(1)


def runs_dir() -> Path:
    return Path(os.environ.get("INSIGHT_RUNS_DIR") or ROOT / "runs")


def current_run_dir() -> Path | None:
    marker = runs_dir() / "CURRENT"
    if not marker.exists():
        return None
    run_dir = runs_dir() / marker.read_text(encoding="utf-8").strip()
    return run_dir if run_dir.is_dir() else None


def run_dir_for(run_id: str | None) -> Path:
    if run_id:
        path = runs_dir() / run_id
        if not path.is_dir():
            refuse(f"run not found: {run_id}")
        return path
    path = current_run_dir()
    if path is None:
        refuse("no current run; start one with start_run.py")
    return path


def new_run_dir(name: str) -> Path:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:40] or "insights"
    run_id = f"{datetime.now():%Y%m%d-%H%M%S}-{slug}"
    path = runs_dir() / run_id
    for sub in RUN_SUBDIRS:
        (path / sub).mkdir(parents=True, exist_ok=True)
    (runs_dir() / "CURRENT").write_text(run_id, encoding="utf-8")
    return path
