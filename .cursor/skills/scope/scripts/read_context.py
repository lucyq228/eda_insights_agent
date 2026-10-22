"""Everything the scope-feasibility specialist needs: request, answers, profile, feedback, and shelf."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[4]))

from insight_core import registry  # noqa: E402
from insight_core.runner import base_parser, configure_stdout, emit_json, resolve  # noqa: E402
from insight_core.state import read_artifact  # noqa: E402


def main() -> None:
    configure_stdout()
    args = base_parser(__doc__, "scope-feasibility").parse_args()
    run_dir = resolve(args)
    run = read_artifact(run_dir, "run.json")
    prof = read_artifact(run_dir, "profile.json")
    if not prof:
        emit_json({"error": "no profile yet; the coordinator must run profile_data.py first"}, ok=False)
    cols = {}
    for c in prof["columns"]:
        desc = f"{c['type']}; {c['missing_pct']}% missing; {c['n_unique']} unique"
        if "summary" in c:
            s = c["summary"]
            desc += f"; median {s['median']}, range {s['min']} to {s['max']}"
        if "levels" in c:
            desc += "; levels " + ", ".join(f"{lv['level']}({lv['count']})" for lv in c["levels"][:8])
        if "range" in c:
            desc += f"; {c['range'][0]} to {c['range'][1]}"
        cols[c["name"]] = desc
    out = {"request": run["request"], "data_file": Path(run["data_path"]).name, "rows": prof["n_rows"],
           "duplicate_rows": prof["duplicate_rows"], "columns": cols, "target_candidates": prof["target_candidates"],
           "id_columns": prof["id_columns"], "date_columns": prof["date_columns"],
           "segment_candidates": prof["segment_candidates"],
           "panel_candidates": prof.get("panel_candidates", []), "profile_flags": prof["flags"]}
    answers = read_artifact(run_dir, "answers.json")
    if answers:
        out["user_answers"] = answers["answers"]
        out["user_context"] = answers["user_context"]
    proposal = read_artifact(run_dir, "scope_proposal.json")
    if proposal:
        out["current_scope_version"] = proposal["version"]
        out["current_scope_file"] = "scope_proposal.json (field 'scope'); copy it to drafts/scope.json to revise"
    feas = read_artifact(run_dir, "feasibility.json")
    if feas:
        out["feasibility_feedback"] = {
            "for_scope_version": feas.get("scope_version"),
            "steps": [{"step_id": s["step_id"], "verdict": s["final_verdict"], "reasons": s["reasons"] + s["warnings"],
                       "judgment": s.get("judgment")} for s in feas["steps"] if s["final_verdict"] != "ok"],
            "leakage_suspects": feas.get("leakage_suspects", []), "recommendations": feas.get("recommendations", [])}
    out["tool_shelf"] = [{"id": t["id"], "question": t["question"], "target_types": t["target_types"],
                          "needs": t["needs"], "params": t["params"], "cost_class": t["cost_class"],
                          "caveats": t["caveats"]} for t in registry.catalogue("analysis")
                         if t["id"] != "multiple-testing"]
    emit_json(out)


if __name__ == "__main__":
    main()
