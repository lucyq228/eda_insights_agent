"""Cursor hook: copy subagent and shell activity into the active run's log.

Registered in .cursor/hooks.json. Standard library only, never blocks the agent:
subagentStart always answers {"permission": "allow"} and every failure is swallowed.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))


def _short(value, limit: int = 300) -> str:
    text = " ".join(str(value or "").split())
    return text if len(text) <= limit else text[: limit - 1] + "\u2026"


def _record(payload: dict) -> None:
    from insight_core import events
    from insight_core.paths import current_run_dir

    run_dir = current_run_dir()
    if run_dir is None:
        return
    name = payload.get("hook_event_name", "")
    agent = payload.get("subagent_type") or "subagent"
    if name == "subagentStart":
        events.emit(run_dir, "subagent start", agent,
                    f"model={payload.get('subagent_model') or 'inherit'}; task={_short(payload.get('task'), 240)}")
    elif name == "subagentStop":
        seconds = (payload.get("duration_ms") or 0) / 1000
        events.emit(run_dir, "subagent stop", agent,
                    f"status={payload.get('status')}; {seconds:.0f}s; summary={_short(payload.get('summary'))}")
    elif name == "postToolUse" and payload.get("tool_name") == "Shell":
        command = (payload.get("tool_input") or {}).get("command", "")
        if ".cursor" in command:
            events.emit(run_dir, "shell", "agent", _short(command))


def main() -> None:
    name = ""
    try:
        payload = json.loads(sys.stdin.read() or "{}")
        name = payload.get("hook_event_name", "")
        _record(payload)
    except Exception:
        pass
    print(json.dumps({"permission": "allow"} if name == "subagentStart" else {}))


if __name__ == "__main__":
    main()
