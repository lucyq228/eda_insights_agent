"""Append-only run log: live_run.log for people, events.jsonl for machines."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path


def emit(run_dir: Path, event: str, actor: str, message: str, details: dict | None = None) -> None:
    now = datetime.now().isoformat(timespec="seconds")
    with open(run_dir / "live_run.log", "a", encoding="utf-8") as fh:
        fh.write(f"{now}  {actor:<14} {event:<18} {message}\n")
    with open(run_dir / "events.jsonl", "a", encoding="utf-8") as fh:
        fh.write(json.dumps({"time": now, "event": event, "actor": actor, "message": message,
                             "details": details or {}}, default=str) + "\n")
