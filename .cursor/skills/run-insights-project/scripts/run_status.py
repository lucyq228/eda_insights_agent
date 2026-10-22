"""Where is the run? Milestones, the next owner, open questions, and pending reruns."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[4]))

from insight_core.runner import base_parser, configure_stdout, emit_json, resolve  # noqa: E402
from insight_core.state import milestone_status, next_step, read_artifact  # noqa: E402

ROUTE = {
    "profile": "A4: profile_data.py",
    "scope_draft": "A2: draft the scope (read_context.py, save_scope.py)",
    "feasibility": "A3: check_feasibility.py, then save_feasibility.py",
    "approval": "Manager: show the scope + feasibility to the user, collect answers, approve only on explicit yes",
    "data_quality": "A4: data_quality.py",
    "prepared_data": "A5: prepare_data.py",
    "analyses": "A6: run_plan.py",
    "review": "A7: review_checks.py, then save_review.py",
    "insights": "A7: save_insights.py",
    "report": "A7: build_report.py",
}


def main() -> None:
    configure_stdout()
    args = base_parser(__doc__, "manager").parse_args()
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
        out["reruns_for_A6"] = review["rerun_requests"]
        out["next"] = {"milestone": "review", "route": "A6: run each rerun with run_tool.py --followup-reason, then A7 re-reviews"}
    if nxt is None:
        out["next"] = {"milestone": "done", "route": "Manager: finalize_run.py, then present report.html"}
    emit_json(out)


if __name__ == "__main__":
    main()
