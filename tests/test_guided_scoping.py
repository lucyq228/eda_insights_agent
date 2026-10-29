"""The proposal, confirmation gate and adaptive handoff share one scope."""
import copy
import json

import numpy as np
import pandas as pd
import pytest

from insight_core import data, registry
from insight_core.scope import validate, proposal_markdown
from insight_core.review import validate_review
from test_end_to_end import Run


def proposal():
    return {
        "project_name": "Understand the outcome", "purpose": "Find relevant outcome patterns",
        "decision_supported": "Prioritize further investigation", "mode": "exploratory",
        "target": {"column": "outcome", "type": "numeric", "definition": "Observed outcome"},
        "unit_of_analysis": "observation", "drivers": ["x"], "max_followups": 2,
        "hypotheses": [
            {"id": "H1", "statement": "What does the outcome look like?", "rationale": "Establish a baseline",
             "support_criteria": "Describe distribution and coverage", "pathway": [
                 {"tool": "feature-target-associations", "params": {}, "purpose": "Baseline"}]},
            {"id": "H2", "statement": "Where should we deepen?", "rationale": "Explain material patterns",
             "support_criteria": "Evaluate relevant relationships or explain limits", "pathway": [],
             "followup_when": "Baseline shows sufficient coverage", "candidate_tools": ["target-by-numeric-bins"]}
        ], "out_of_scope": ["Causal effects"], "user_questions": []}


@pytest.mark.parametrize("kind", ["numeric", "binary"])
def test_scope_table_and_initial_manifest(kind):
    df = pd.DataFrame({"outcome": [1., 2., 3., 4.], "x": [4., 3., 2., 1.]})
    s = proposal()
    if kind == "binary":
        df.outcome = ["No", "Yes", "No", "Yes"]
        s["target"].update(type="binary", positive_class="Yes")
    assert validate(s, data.profile(df))[0] == []
    assert [x["hypothesis"] for x in registry.plan_steps(s)] == ["H1"]
    text = proposal_markdown(s, 2)
    assert text.index(s["hypotheses"][0]["statement"]) < text.index(s["hypotheses"][1]["statement"])
    assert "conditional" in text and "target-by-numeric-bins" in text and "Causal effects" in text
    bad = copy.deepcopy(s)
    bad["hypotheses"][1].pop("followup_when")
    assert any("followup_when" in e for e in validate(bad, data.profile(df))[0])
    bad = copy.deepcopy(s)
    bad["hypotheses"][1]["candidate_tools"] = ["imaginary-tool"]
    assert any("unknown candidate" in e for e in validate(bad, data.profile(df))[0])


def test_confirmation_and_followup_handoff(tmp_path):
    rng = np.random.default_rng(20)
    source = tmp_path / "observations.csv"
    pd.DataFrame({"outcome": rng.normal(size=100), "x": rng.normal(size=100)}).to_csv(source, index=False)
    run = Run(tmp_path)
    run("run-insights-project", "start_run", "--data", str(source), "--request", "Explore outcome")
    run("profile-eda", "profile_data")
    run("scope", "save_scope", "--file", run.draft("scope.json", proposal()))
    assert (run.dir / "scope_proposal.md").exists()
    run("feasibility", "check_feasibility")
    run("feasibility", "save_feasibility", "--file", run.draft("feasibility.json", {
        "overall": "Feasible", "can_answer": ["Observed patterns"], "cannot_answer": ["Causal effects"]}))
    run("run-insights-project", "approve_scope", "--exploration", ok=False)
    run("insight-shelf", "run_plan", ok=False)
    run("run-insights-project", "approve_scope", "--user-confirmation", "Use this scope")
    run("run-insights-project", "advance_run")
    assert not list((run.dir / "results").glob("H2*.json"))
    params = run.draft("params.json", {"x": "x"})
    run("insight-shelf", "run_tool", "--tool", "target-by-numeric-bins", "--params-file", params,
        "--hypothesis", "UNKNOWN", "--followup-reason", "Check coverage", ok=False)
    run("insight-shelf", "run_tool", "--tool", "target-by-numeric-bins", "--params-file", params,
        "--hypothesis", "H2", "--followup-reason", "H1 establishes sufficient coverage")
    result = json.loads((run.dir / "results" / "F1.json").read_text())
    assert result["hypothesis"] == "H2"
    checks = run("review-insights", "review_checks")
    assert "F1" in checks["hypotheses"]["H2"]["results"]
    review = {"hypothesis_verdicts": [
        {"id": "H1", "verdict": "inconclusive", "reasoning": "Baseline only", "evidence": [{"result": "H1.S1"}]},
        {"id": "H2", "verdict": "inconclusive", "reasoning": "Exploratory relationship", "evidence": [{"result": "F1"}]}]}
    assert validate_review(review, run.dir) == []
    # A conditional stage may be unpursued only with a documented evidence basis.
    review["hypothesis_verdicts"][1].update(verdict="not_evaluated", reasoning="Earlier evidence does not justify further testing")
    assert validate_review(review, run.dir) == []
    review["hypothesis_verdicts"][1]["evidence"] = []
    assert any("evidence" in e for e in validate_review(review, run.dir))
