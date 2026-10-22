"""Merge the saved deterministic check with specialist judgment; do not rescan the data."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[4]))

from insight_core import events  # noqa: E402
from insight_core.feasibility import load_auto_check, merge  # noqa: E402
from insight_core.runner import base_parser, configure_stdout, emit_json, read_json_file, resolve  # noqa: E402
from insight_core.state import write_artifact  # noqa: E402


def main() -> None:
    configure_stdout()
    p = base_parser(__doc__, "scope-feasibility")
    p.add_argument("--file", help="default: drafts/feasibility.json")
    args = p.parse_args()
    run_dir = resolve(args)
    if (run_dir / "approved_scope.json").exists():
        emit_json({"error": "scope already approved"}, ok=False)
    judgment = read_json_file(args.file or run_dir / "drafts" / "feasibility.json")
    auto = load_auto_check(run_dir)
    merged, errors = merge(auto, judgment)
    if errors:
        emit_json({"error": "feasibility draft has problems", "issues": errors}, ok=False)
    steps = merged["steps"]
    counts = {v: sum(s["final_verdict"] == v for s in steps) for v in ("ok", "partial", "blocked")}
    art = {"scope_version": auto["scope_version"], "steps": steps, "counts": counts,
           "leakage_suspects": auto["leakage_suspects"], "resolved_drivers": auto["resolved_drivers"],
           "scope_issues": auto["scope_issues"], "overall": judgment["overall"], "can_answer": judgment["can_answer"],
           "cannot_answer": judgment["cannot_answer"], "recommendations": judgment.get("recommendations", []),
           "questions_for_user": judgment.get("questions_for_user", [])}
    write_artifact(run_dir, "feasibility.json", art, upstream="scope_proposal.json")
    events.emit(run_dir, "feasibility", args.actor, f"scope v{auto['scope_version']}: {counts}")
    blocked = [s["step_id"] for s in steps if s["final_verdict"] == "blocked"]
    emit_json({"scope_version": auto["scope_version"], "counts": counts, "blocked": blocked,
               "scope_issues": auto["scope_issues"],
               "next": "scope-feasibility specialist revises the scope" if blocked or auto["scope_issues"]
               else "coordinator presents scope + feasibility to the user"})


if __name__ == "__main__":
    main()
