"""Where is the run? Milestones, the next owner, open questions, and pending reruns."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[4]))

from insight_core.runner import base_parser, configure_stdout, emit_json, resolve  # noqa: E402
from insight_core.state import milestone_status, next_step, read_artifact  # noqa: E402

ROUTE = {
    "profile": "Coordinator: profile_data.py",
    "scope_draft": "Scope & Feasibility specialist: read_context.py, save_scope.py",
    "feasibility": "Scope & Feasibility specialist: check_feasibility.py, save_feasibility.py",
    "approval": "Coordinator: show scope + feasibility to the user and approve only on explicit yes",
    "data_quality": "Coordinator: advance_run.py (deterministic)",
    "prepared_data": "Coordinator: advance_run.py (deterministic)",
    "analyses": "Coordinator: advance_run.py (approved selected plan only)",
    "review": "Reviewer & Insights specialist: review_checks.py, save_review.py",
    "insights": "Reviewer & Insights specialist: save_insights.py",
    "report": "Reviewer & Insights specialist: build_report.py",
}


def main() -> None:
    configure_stdout()
    args = base_parser(__doc__, "coordinator").parse_args()
    run_dir = resolve(args)
    run = read_artifact(run_dir, "run.json")
    rows = milestone_status(run_dir)
    nxt = next_step(run_dir)
    out = {"run_id": run_dir.name, "data": Path(run["data_path"]).name, "request": run["request"],
           "milestones": {r["milestone"]: r["status"] + (f" ({r['reason']})" if r["reason"] else "") for r in rows},
           "next": None if nxt is None else {"milestone": nxt["milestone"], "route": ROUTE[nxt["milestone"]]}}
    proposal = read_artifact(run_dir, "scope_proposal.json")
    answers = (read_artifact(run_dir, "answers.json") or {}).get("answers", {})
    if proposal and not (run_dir / "approved_scope.json").exists():
        out["scope_version"] = proposal["version"]
        out["open_questions"] = [{"id": q["id"], "question": q["question"], "recommended": q.get("recommended")}
                                 for q in proposal["scope"].get("user_questions", []) if q["id"] not in answers]
        feas = read_artifact(run_dir, "feasibility.json")
        if feas:
            out["blocked_steps"] = [s["step_id"] for s in feas["steps"] if s["final_verdict"] == "blocked"]
    review = read_artifact(run_dir, "review.json")
    if review and review.get("rerun_requests") and out["milestones"]["review"].startswith("incomplete"):
        out["targeted_followups"] = review["rerun_requests"]
        out["next"] = {"milestone": "review", "route": "Coordinator runs each follow-up with run_tool.py, then reviewer rechecks"}
    if nxt is None:
        out["next"] = {"milestone": "done", "route": "Coordinator: finalize_run.py, then present report.html"}
    emit_json(out)


if __name__ == "__main__":
    main()
