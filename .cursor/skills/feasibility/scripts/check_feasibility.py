"""Deterministic feasibility of every pathway step in the current scope proposal."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[4]))

from insight_core.feasibility import save_auto_check  # noqa: E402
from insight_core.locking import milestone_lock  # noqa: E402
from insight_core.runner import base_parser, configure_stdout, emit_json, resolve  # noqa: E402


def main() -> None:
    configure_stdout()
    args = base_parser(__doc__, "scope-feasibility").parse_args()
    run_dir = resolve(args)
    with milestone_lock(run_dir, "feasibility-auto"):
        auto = save_auto_check(run_dir)
        emit_json({"scope_version": auto["scope_version"], "counts": auto["counts"], "scope_issues": auto["scope_issues"],
                   "leakage_suspects": auto["leakage_suspects"], "resolved_drivers": auto["resolved_drivers"],
                   "steps": [{"step_id": s["step_id"], "tool": s["tool"], "params": s["params"], "verdict": s["verdict"],
                              "reasons": s["reasons"], "warnings": s["warnings"]} for s in auto["steps"]],
                   "next": "write drafts/feasibility.json with your judgment, then save_feasibility.py"})


if __name__ == "__main__":
    main()
