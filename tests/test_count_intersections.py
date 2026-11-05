"""Generic regressions for broad screens followed by joint count attribution."""
import copy
import json

import pandas as pd
import pytest

from insight_core import data, registry, report, review, scope
from insight_core.context import Ctx
from insight_core.runner import save_result


@pytest.fixture
def counts(tmp_path):
    cells = [("A", "new", 100, 60), ("A", "established", 100, 80),
             ("B", "new", 90, 80), ("B", "established", 200, 200),
             ("C", "new", 10, 2)]
    rows = [(period, channel, tenure, value)
            for channel, tenure, before, after in cells
            for period, value in [("before", before), ("after", after)]]
    df = pd.DataFrame(rows, columns=["period", "channel", "tenure", "count"])
    params = {"cohort": "period", "baseline": "before", "comparison": "after"}
    steps = [{"tool": "count-change-contribution", "purpose": f"Screen {dim}",
              "params": {**params, "by": dim}} for dim in ("channel", "tenure")]
    spec = {"project_name": "Count shifts", "purpose": "Locate losses",
            "decision_supported": "Choose follow-ups", "unit_of_analysis": "disjoint cell per period",
            "min_n": 1, "target": {"column": "count", "type": "numeric", "definition": "Completed units"},
            "segments": ["period", "channel", "tenure"], "dimension_omissions": {},
            "hypotheses": [{"id": "H1", "statement": "Locate changes", "rationale": "Compare groups",
                           "support_criteria": "Reconciled contributions", "pathway": steps}]}
    return Ctx(tmp_path, df, data.column_types(df), spec, "demo"), params


def run(ctx, params, by):
    return registry.function("count-change-contribution")(ctx, {**params, "by": by})


def test_joint_reconciliation_size_and_percentages(counts):
    ctx, params = counts
    result = run(ctx, params, ["channel", "tenure"])
    groups = result["tables"]["groups"]
    assert result["grouping_columns"] == {"group_1": "channel", "group_2": "tenure"}
    assert groups.expected.sum() == 500
    assert groups.observed.sum() == 422
    assert groups.contribution.sum() == -78
    assert groups.contribution_pp.sum() == pytest.approx(-15.6)
    assert groups.net_change_share.sum() == pytest.approx(1)
    assert groups.expected_share.sum() == pytest.approx(1)
    assert groups.observed_share.sum() == pytest.approx(1)
    assert groups.share_change_pp.sum() == pytest.approx(0)
    small = groups.loc[groups.group_1.eq("C")].iloc[0]
    assert small.group_change_pct == -80
    assert small.expected_share == .02
    assert small.contribution_pp == pytest.approx(-1.6)
    # Findings are citable and survive the real result writer.
    ctx.run_dir.joinpath("results").mkdir()
    saved = save_result(ctx.run_dir, "joint", "count-change-contribution",
                        {**params, "by": ["channel", "tenure"]}, result, {})
    assert saved["tables"]["groups"]["rows"] == 5
    assert any(f["metric"] == "contribution_pp" and f.get("group", {}).get("channel") == "C"
               for f in saved["findings"])
    for dim in ("channel", "tenure"):
        marginal = run(ctx, params, dim)["tables"]["groups"]
        assert marginal.contribution.sum() == groups.contribution.sum()
    pd.testing.assert_frame_equal(run(ctx, params, "channel")["tables"]["groups"],
                                  run(ctx, params, ["channel"])["tables"]["groups"])


def test_joint_zero_baselines_missing_cells_and_offsets(counts):
    ctx, params = counts
    # Explicit zero is different from missing coverage.
    ctx.df = pd.DataFrame([("before", "A", "x", 0), ("after", "A", "x", 5),
                           ("before", "B", "x", 10), ("after", "B", "x", 0)],
                          columns=["period", "channel", "tenure", "count"])
    groups = run(ctx, params, ["channel", "tenure"])["tables"]["groups"]
    assert pd.isna(groups.loc[groups.group_1.eq("A"), "group_change_pct"].iloc[0])
    assert groups.contribution_pp.sum() == -50
    assert sorted(groups.net_change_share) == [-1, 2]
    ctx.df.loc[ctx.df.period.eq("after") & ctx.df.channel.eq("A"), "count"] = 10
    groups = run(ctx, params, ["channel", "tenure"])["tables"]["groups"]
    assert groups.net_change_share.isna().all()
    assert groups.contribution_pp.sum() == 0
    ctx.df = ctx.df.iloc[1:]
    with pytest.raises(ValueError, match="Missing group-period"):
        run(ctx, params, ["channel", "tenure"])
    assert run(ctx, {**params, "absent_is_zero": True}, ["channel", "tenure"])["tables"]["groups"].expected.sum() == 10
    ctx.df["count"] = 0
    groups = run(ctx, {**params, "absent_is_zero": True}, ["channel", "tenure"])["tables"]["groups"]
    assert groups.contribution_pp.isna().all()
    assert groups.expected_share.isna().all()
    assert groups.observed_share.isna().all()


def test_joint_nulls_and_labels_are_not_concatenated(counts):
    ctx, params = counts
    ctx.df = pd.DataFrame([(p, a, b, n) for p in ("before", "after")
                          for a, b, n in [("A|B", "C", 2), ("A", "B|C", 3), (None, "C", 4)]],
                         columns=["period", "channel", "tenure", "count"])
    groups = run(ctx, params, ["channel", "tenure"])["tables"]["groups"]
    assert len(groups) == 3
    assert groups.expected.sum() == groups.observed.sum() == 9
    assert groups.group_1.isna().sum() == 1


def test_validation_checks_every_grouping_field(counts):
    ctx, params = counts
    profile = data.profile(ctx.df)
    tool = "count-change-contribution"
    joint = {**params, "by": ["channel", "tenure"]}
    assert registry.check_step(tool, joint, ctx.scope, profile, [])["verdict"] != "blocked"
    assert registry.step_columns(tool, joint, ctx.scope, profile) == ["period", "channel", "tenure"]
    assert registry.check_step(tool, joint, ctx.scope, profile, ["tenure"])["verdict"] == "blocked"
    excluded = {**ctx.scope, "exclude": [{"column": "tenure", "reason": "Timing unknown"}]}
    assert registry.check_step(tool, joint, excluded, profile, [])["verdict"] == "blocked"
    for by in ([], ["channel", "channel"], ["channel", None], ["channel", "period"],
               ["channel", "count"], ["channel", "unknown"], 42):
        assert registry.check_step(tool, {**params, "by": by}, ctx.scope, profile, [])["verdict"] == "blocked"
    spec = copy.deepcopy(ctx.scope)
    spec["hypotheses"][0]["pathway"] = [{"tool": tool, "params": joint, "purpose": "Joint only"}]
    assert any("screen or explain" in e for e in scope.validate(spec, profile)[0])
    assert scope.validate(ctx.scope, profile)[0] == []


def test_review_requires_joint_result_or_reason_and_reports_it(counts):
    ctx, params = counts
    ctx.run_dir.joinpath("results").mkdir()
    ctx.run_dir.joinpath("approved_scope.json").write_text(json.dumps(ctx.scope))
    for step in registry.plan_steps(ctx.scope):
        save_result(ctx.run_dir, step["step_id"], step["tool"], step["params"],
                    registry.function(step["tool"])(ctx, step["params"]), {})
    save_result(ctx.run_dir, "joint", "count-change-contribution",
                {**params, "by": ["channel", "tenure"]}, run(ctx, params, ["channel", "tenure"]), {})
    draft = {"hypothesis_verdicts": [{"id": "H1", "verdict": "supported", "reasoning": "Losses concentrated",
                                    "evidence": [{"result": "H1.S1"}]}],
             "dimension_coverage": {s["step_id"]: {"status": "movement", "reason": "Observed losses"}
                                    for s in registry.plan_steps(ctx.scope)}}
    assert any("intersection_review" in e for e in review.validate_review(draft, ctx.run_dir))
    item = {"status": "completed", "reason": "Joint groups locate overlapping losses.",
            "evidence": [{"result": "H1.S1"}]}
    draft["intersection_review"] = item
    assert any("combined-dimension" in e for e in review.validate_review(draft, ctx.run_dir))
    item["evidence"] = [{"result": "joint"}]
    assert review.validate_review(draft, ctx.run_dir) == []
    assert report.dimension_rows(ctx.scope, draft)[-1] == (
        "Combined dimensions", "completed", item["reason"], "joint")
    path = ctx.run_dir / "results" / "joint.json"
    result = json.loads(path.read_text())
    result["params"]["baseline"] = "different"
    path.write_text(json.dumps(result))
    assert review.validate_review(draft, ctx.run_dir)
    result["params"]["baseline"] = params["baseline"]
    next(f for f in result["findings"] if f["metric"] == "observed_count")["estimate"] += 1
    path.write_text(json.dumps(result))
    assert review.validate_review(draft, ctx.run_dir)
    for status in ("not_needed", "unresolved"):
        item.update(status=status, reason="No useful second dimension or insufficient coverage.",
                    evidence=[{"result": "H1.S1"}])
        assert review.validate_review(draft, ctx.run_dir) == []
    item["reason"] = ""
    assert review.validate_review(draft, ctx.run_dir)


def test_joint_history_uses_the_same_projected_reference(counts):
    ctx, _ = counts
    ctx.df = pd.DataFrame([(str(i), channel, "x", 10 + i + (shift if i == 4 else 0))
                          for i in range(1, 5) for channel, shift in [("A", 5), ("B", -3)]],
                         columns=["period", "channel", "tenure", "count"])
    params = {"cohort": "period", "baseline": "3", "comparison": "4", "history": ["1", "2", "3"]}
    groups = run(ctx, params, ["channel", "tenure"])["tables"]["groups"]
    assert groups.expected.sum() == pytest.approx(28)
    assert groups.observed.sum() == 30
    assert groups.contribution_pp.sum() == pytest.approx(100 * 2 / 28)
    assert groups.expected_share.sum() == pytest.approx(1)
    assert groups.contribution.sum() == run(ctx, params, "channel")["tables"]["groups"].contribution.sum()
