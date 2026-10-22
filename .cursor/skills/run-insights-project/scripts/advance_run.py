"""Advance an approved run through deterministic quality, preparation, and selected analysis steps."""

import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[4]))

from insight_core import events  # noqa: E402
from insight_core.paths import ROOT  # noqa: E402
from insight_core.runner import base_parser, configure_stdout, emit_json, resolve  # noqa: E402


STAGES = [
    ("data_quality", ROOT / ".cursor" / "skills" / "profile-eda" / "scripts" / "data_quality.py"),
    ("prepared_data", ROOT / ".cursor" / "skills" / "prepare-data" / "scripts" / "prepare_data.py"),
    ("analyses", ROOT / ".cursor" / "skills" / "insight-shelf" / "scripts" / "run_plan.py"),
]


def _last_json(stdout: str) -> dict:
    try:
        return json.loads(stdout)
    except json.JSONDecodeError:
        return {"output": stdout[-2000:]}


def main() -> None:
    configure_stdout()
    p = base_parser(__doc__, "coordinator")
    p.add_argument("--through", choices=[s[0] for s in STAGES], default="analyses")
    args = p.parse_args()
    run_dir = resolve(args)
    completed = []
    for stage, script in STAGES:
        events.emit(run_dir, "stage start", args.actor, stage)
        proc = subprocess.run([sys.executable, str(script), "--run", run_dir.name, "--actor", args.actor],
                              cwd=ROOT, text=True, capture_output=True, encoding="utf-8")
        payload = _last_json(proc.stdout)
        completed.append({"stage": stage, "returncode": proc.returncode, "result": payload})
        events.emit(run_dir, "stage complete" if proc.returncode == 0 else "stage failed", args.actor, stage,
                    {"returncode": proc.returncode})
        if proc.returncode != 0:
            emit_json({"error": f"{stage} failed", "stages": completed,
                       "stderr": proc.stderr[-2000:]}, ok=False)
        if stage == args.through:
            break
    emit_json({"summary": f"advanced through {args.through}", "stages": completed,
               "next": "review-insights specialist" if args.through == "analyses" else "continue deterministic execution"})


if __name__ == "__main__":
    main()
