"""Drive the whole flow through the skill scripts, the way the agents do."""

from __future__ import annotations

import copy
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SKILLS = ROOT / ".cursor" / "skills"
EXAMPLE = json.loads((ROOT / "examples" / "example_scope.json").read_text(encoding="utf-8"))
# Keep this flow as the legacy artifact compatibility regression. V2 has dedicated tests.
EXAMPLE.pop("report_schema_version", None)


class Run:
    def __init__(self, tmp: Path):
        self.tmp = tmp
        self.env = {**os.environ, "INSIGHT_RUNS_DIR": str(tmp / "runs"), "PYTHONIOENCODING": "utf-8"}

    def __call__(self, skill: str, script: str, *args: str, ok: bool = True) -> dict:
        proc = subprocess.run([sys.executable, str(SKILLS / skill / "scripts" / f"{script}.py"), *args],
                              capture_output=True, text=True, env=self.env, cwd=ROOT, encoding="utf-8")
        try:
            out = json.loads(proc.stdout)
        except json.JSONDecodeError:
            raise AssertionError(f"{script} printed no JSON:\n{proc.stdout}\n{proc.stderr}")
        assert (proc.returncode == 0) == ok, f"{script} {args}: exit {proc.returncode}\n{json.dumps(out, indent=1)}\n{proc.stderr}"
        return out

    @property
    def dir(self) -> Path:
        runs = self.tmp / "runs"
        return runs / (runs / "CURRENT").read_text().strip()

    def draft(self, name: str, data: dict) -> str:
        path = self.dir / "drafts" / name
        path.write_text(json.dumps(data), encoding="utf-8")
        return str(path)

    def file(self, name: str, data: dict) -> str:
        path = self.tmp / name
        path.write_text(json.dumps(data), encoding="utf-8")
        return str(path)

    def artifact(self, name: str) -> dict:
        return json.loads((self.dir / name).read_text(encoding="utf-8"))


JUDGMENT = {"overall": "Feasible: one table, enough rows, clear target.",
            "can_answer": ["which drivers move with sales", "whether promo holds within region"],
            "cannot_answer": ["causal lift from promotions"],
            "recommendations": ["exclude sales_per_visitor"]}


def test_store_sales_full_flow(tmp_path):
    run = Run(tmp_path)
    run("run-insights-project", "start_run", "--data", "data/store_weekly_sales.csv",
        "--request", "Can you find insights in this store data?")

    # Before scoping: nothing downstream can run.
    run("insight-shelf", "run_plan", ok=False)
    prof = run("profile-eda", "profile_data")
    assert prof["duplicate_rows"] == 8
    assert "store_id" in prof["id_columns"] and "week_start" in prof["date_columns"]
    assert any(c["column"] == "weekly_sales_k" for c in prof["target_candidates"])
    assert any("customer_rating" in f for f in prof["flags"])
    panel = next(p for p in prof["panel_candidates"] if p["column"] == "store_id")
    assert panel["n_entities"] == 80 and panel["date_column"] == "week_start"
    assert [p["column"] for p in prof["panel_candidates"]] == ["store_id"]
    ctx = run("scope", "read_context")
    assert "tool_shelf" in ctx and "multiple-testing" not in [t["id"] for t in ctx["tool_shelf"]]
    assert ctx["panel_candidates"] and "panel-decomposition" in [t["id"] for t in ctx["tool_shelf"]]

    # v1 forgets the leakage column and ignores the panel: feasibility must catch both.
    v1 = copy.deepcopy(EXAMPLE)
    v1["exclude"] = []
    del v1["entity_column"]
    bad = copy.deepcopy(v1)
    bad["target"]["column"] = "no_such_column"
    run("scope", "save_scope", "--file", run.draft("scope.json", bad), ok=False)
    run("scope", "save_scope", "--file", run.draft("scope.json", v1))
    auto = run("feasibility", "check_feasibility")
    assert any("sales_per_visitor" in s for s in auto["scope_issues"])
    assert "sales_per_visitor" in [x["column"] for x in auto["leakage_suspects"]]
    assert any("looks like a panel" in s for s in auto["scope_issues"])
    assert any(s["tool"] == "panel-decomposition" and s["verdict"] == "blocked" for s in auto["steps"])
    run("feasibility", "save_feasibility", "--file", run.draft("feasibility.json", JUDGMENT))
    run("run-insights-project", "approve_scope", "--user-confirmation", "yes", ok=False)

    # v2 fixes it; the old feasibility is now stale.
    run("scope", "save_scope", "--file", run.draft("scope.json", EXAMPLE), "--change-note", "exclude leakage")
    status = run("run-insights-project", "run_status")
    assert status["milestones"]["feasibility"].startswith("stale")
    run("run-insights-project", "approve_scope", "--user-confirmation", "yes", ok=False)
    run("feasibility", "check_feasibility")
    unexplained = {**JUDGMENT, "steps": [{"step_id": "H1.S1", "verdict": "blocked"}]}
    run("feasibility", "save_feasibility", "--file", run.draft("feasibility.json", unexplained), ok=False)
    feas = run("feasibility", "save_feasibility", "--file", run.draft("feasibility.json", JUDGMENT))
    assert feas["blocked"] == [] and feas["scope_issues"] == []

    # Questions must be answered by the user before approval.
    refused = run("run-insights-project", "approve_scope", "--user-confirmation", "yes", ok=False)
    assert "Q1" in refused["error"]
    run("run-insights-project", "record_answers", "--answers-file",
        run.file("bad.json", {"answers": {"Q9": "x"}}), ok=False)
    run("run-insights-project", "record_answers", "--answers-file",
        run.file("ans.json", {"answers": {"Q1": "weekly_sales_k", "Q2": "within regions"}}))
    run("run-insights-project", "approve_scope", "--user-confirmation", "Looks good, go ahead")
    run("scope", "save_scope", "--file", run.draft("scope.json", EXAMPLE), ok=False)

    advanced = run("run-insights-project", "advance_run")
    assert [s["stage"] for s in advanced["stages"]] == ["data_quality", "prepared_data", "analyses"]
    prep = run.artifact("prepared_data.json")
    assert any("8 exact duplicate" in x for x in prep["log"])
    assert not advanced["stages"][-1]["result"]["errors"]

    res = {p.stem: json.loads(p.read_text(encoding="utf-8")) for p in (run.dir / "results").glob("*.json")}
    ranked = res["H1.S1"]["findings"]
    assert ranked[0]["x"] == "foot_traffic" and ranked[0]["estimate"] > .3
    temp = next(f for f in ranked if f["x"] == "avg_temp_c")
    assert abs(temp["estimate"]) < .1
    assert "sales_per_visitor" not in [f["x"] for f in ranked]
    assert res["H2.S1"]["simpson_flag"], res["H2.S1"]["summary"]
    within = next(f for f in res["H2.S1"]["findings"] if f["segment"] == "within")
    assert within["estimate"] > .1 and within["ci_low"] > 0
    assert res["H3.S1"]["nonlinear"] and "inverted-U" in res["H3.S1"]["findings"][1]["direction"]
    assert res["H4.S1"]["findings"][1]["estimate"] < -.1
    assert res["multiple-testing"]["q_values"]
    decomp = res["H2.S2"]
    assert [f["metric"] for f in decomp["findings"]] == [
        "spearman_r_pooled", "spearman_r_within_entity", "spearman_r_between_entity"]
    assert all(f["n_entities"] == 80 for f in decomp["findings"]) and decomp["time_effects"]
    assert decomp["findings"][2]["n"] == 80 and decomp["charts"]
    pdrv = res["H5.S3"]
    assert {f["metric"] for f in pdrv["findings"]} == {"within_std_coef", "between_std_coef"}
    assert pdrv["holdout_score"]["metric"].startswith("within R^2")
    assert any("whole store_id" in n for n in res["H5.S2"]["notes"])
    mt_results = {r["result"] for r in res["multiple-testing"]["q_values"]}
    assert {"H2.S2", "H5.S3"} <= mt_results

    # Follow-ups need a reason and still pass feasibility.
    run("insight-shelf", "run_tool", "--tool", "pair-deep-dive", "--params-file",
        run.file("p0.json", {"x": "sales_per_visitor"}), "--followup-reason", "curious", ok=False)

    checks = run("review-insights", "review_checks")
    assert set(checks["hypotheses"]) == {"H1", "H2", "H3", "H4", "H5"}
    assert checks["prompts"][0].startswith("Panel data")
    flags = {r["result"]: r["flags"] for r in checks["results"]}
    assert any(f.startswith("PANEL POOLED") for f in flags["H1.S1"])
    assert not any(f.startswith("PANEL POOLED") for f in flags["H2.S2"])
    verdicts = [{"id": h, "verdict": "supported", "reasoning": "Meets its support criteria.",
                 "evidence": [{"result": f"{h}.S1"}]} for h in ("H1", "H2", "H3", "H4")]
    verdicts.append({"id": "H5", "verdict": "partially_supported", "reasoning": "Joint model agrees in part.",
                     "evidence": [{"result": "H5.S2"}]})
    review = {"hypothesis_verdicts": verdicts,
              "challenges": [{"issue": "Pooled promo result misleads", "resolution": "Lead with within-region"}],
              "rerun_requests": [{"tool": "segment-correlation", "params": {"x": "staff_hours", "by": "store_format"},
                                  "reason": "Is staffing stronger in some formats?"}]}
    run("review-insights", "save_review", "--file", run.draft("review.json", review))
    status = run("run-insights-project", "run_status")
    assert status["targeted_followups"]
    run("review-insights", "save_insights", "--file", run.draft("insights.json", {}), ok=False)

    fu = run("insight-shelf", "run_tool", "--tool", "segment-correlation", "--params-file",
             run.file("p1.json", {"x": "staff_hours", "by": "store_format"}),
             "--followup-reason", "The reviewer asked whether staffing differs by format")
    assert fu["result"]["label"] == "F1"
    assert any(f.startswith("HETEROGENEITY") for f in fu["result"]["flags"]), fu["result"]
    assert run("run-insights-project", "run_status")["milestones"]["review"].startswith("stale")

    review["rerun_requests"] = []
    run("review-insights", "save_review", "--file", run.draft("review.json", review))

    insights = {
        "headline_summary": "Traffic, availability, and a mid-range price are the clearest associations with sales.",
        "insights": [
            {"id": "I1", "title": "Promo spend drives sales", "statement": "x", "strength": "moderate", "confidence": "medium",
             "evidence": [{"result": "H2.S1", "finding": "promo_spend_k ~ weekly_sales_k | within region"},
                          {"result": "H2.S2", "finding": "promo_spend_k ~ weekly_sales_k | within store_id and period"}]},
            {"id": "I2", "title": "Traffic", "statement": "y", "strength": "strong", "confidence": "high",
             "evidence": [{"result": "H1.S1", "finding": "foot_traffic ~ weekly_sales_k"}]},
            {"id": "I3", "title": "Price has a curved relationship", "statement": "Sales are highest in a mid-price range.",
             "strength": "moderate", "confidence": "high",
             "evidence": [{"result": "H3.S1", "finding": "avg_price ~ weekly_sales_k | curvature"}]},
            {"id": "I4", "title": "Stock availability matters", "statement": "Higher stockout rates go with lower sales after controls.",
             "strength": "moderate", "confidence": "high",
             "evidence": [{"result": "H4.S1", "finding": "stockout_rate ~ weekly_sales_k | controlling foot_traffic, region"}]}],
        "limitations": ["observational"], "next_steps": ["test a promo pilot"]}
    out = run("review-insights", "save_insights", "--file", run.draft("insights.json", insights), ok=False)
    assert any("causal" in i for i in out["issues"])
    insights["insights"][0]["title"] = "Within each region, higher promo spend goes with higher sales"
    insights["insights"][0]["statement"] = "Pooled, promo looks unrelated or negative; within regions it is positive."
    run("review-insights", "save_insights", "--file", run.draft("insights.json", insights))
    rep = run("review-insights", "build_report")
    assert rep["n_insights"] == 4 and (run.dir / "report.html").is_file()
    html = (run.dir / "report.html").read_text(encoding="utf-8")
    assert "within region" in html and "q = " in html
    assert "Panel data: each store_id" in html and "entities = 80" in html
    final = run("run-insights-project", "finalize_run")
    assert final["report_html"].endswith("report.html")

    # Tampering with the locked scope stops everything.
    approved = run.dir / "approved_scope.json"
    approved.write_text(approved.read_text(encoding="utf-8").replace("store-week", "store"), encoding="utf-8")
    run("insight-shelf", "run_plan", "--force", ok=False)


def test_attrition_binary_target(tmp_path):
    run = Run(tmp_path)
    run("run-insights-project", "start_run", "--data", "data/employee_attrition.csv",
        "--request", "Why do people leave? Find correlations.")
    prof = run("profile-eda", "profile_data")
    assert "employee_id" in prof["id_columns"] and prof["panel_candidates"] == []
    scope = {
        "project_name": "Attrition correlates", "purpose": "See which work conditions go with leaving.",
        "decision_supported": "Which retention programme to pilot first.",
        "target": {"column": "left_company", "type": "binary", "positive_class": "Yes",
                   "definition": "1 if the employee left; lower is better."},
        "unit_of_analysis": "employee", "id_column": "employee_id", "drivers": "all",
        "exclude": [{"column": "exit_interview_done", "reason": "Only happens after leaving."}],
        "segments": ["department"],
        "hypothesis_count_exception": "This focused regression fixture intentionally tests two pre-specified questions.",
        "hypotheses": [
            {"id": "H1", "statement": "Lower engagement goes with more leaving.", "rationale": "r",
             "support_criteria": "r < -0.1", "pathway": [
                {"tool": "target-associations", "params": {}, "purpose": "screen"},
                {"tool": "segment-breakdown", "params": {"by": "department"}, "purpose": "by department"}]},
            {"id": "H2", "statement": "Attrition risk is concentrated early in tenure.", "rationale": "r",
             "support_criteria": "curvature", "pathway": [
                {"tool": "nonlinearity-check", "params": {"x": "tenure_years"}, "purpose": "shape"},
                {"tool": "driver-importance", "params": {}, "purpose": "joint"}]}],
        "user_questions": []}
    leaky = copy.deepcopy(scope)
    leaky["exclude"] = []
    run("scope", "save_scope", "--file", run.draft("scope.json", leaky))
    auto = run("feasibility", "check_feasibility")
    assert "exit_interview_done" in [x["column"] for x in auto["leakage_suspects"]]
    run("scope", "save_scope", "--file", run.draft("scope.json", scope))
    run("feasibility", "check_feasibility")
    run("feasibility", "save_feasibility", "--file", run.draft("feasibility.json", JUDGMENT))
    run("run-insights-project", "approve_scope", "--user-confirmation", "approved")
    run("run-insights-project", "advance_run")
    res = {p.stem: json.loads(p.read_text(encoding="utf-8")) for p in (run.dir / "results").glob("*.json")}
    ranked = {f["x"]: f for f in res["H1.S1"]["findings"]}
    assert ranked["engagement_score"]["estimate"] < -.1
    assert ranked["overtime_hours_month"]["estimate"] > .1
    assert abs(ranked["remote"]["estimate"]) < .1
    assert res["H2.S2"]["holdout_score"]["metric"] == "AUC"


@pytest.mark.parametrize("bad_type", ["categorical_target_partial"])
def test_tool_target_type_gate(tmp_path, bad_type):
    run = Run(tmp_path)
    run("run-insights-project", "start_run", "--data", "data/employee_attrition.csv", "--request", "x")
    run("profile-eda", "profile_data")
    scope = {"project_name": "p", "purpose": "p", "decision_supported": "d",
             "target": {"column": "department", "type": "categorical", "definition": "department"},
             "unit_of_analysis": "employee", "drivers": ["tenure_years"],
             "hypothesis_count_exception": "This fixture isolates one type-gate check.",
             "hypotheses": [{"id": "H1", "statement": "s", "rationale": "r", "support_criteria": "c",
                             "pathway": [{"tool": "partial-correlation",
                                          "params": {"x": "tenure_years", "controls": ["commute_km"]},
                                          "purpose": "p"}]}]}
    run("scope", "save_scope", "--file", run.draft("scope.json", scope))
    auto = run("feasibility", "check_feasibility")
    assert auto["steps"][0]["verdict"] == "blocked"
    assert any("target type" in r for r in auto["steps"][0]["reasons"])
