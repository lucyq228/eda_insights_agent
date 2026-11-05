import itertools
import json

import pandas as pd
import pytest

from insight_core import data, registry, report, review, scope
from insight_core.context import Ctx


@pytest.fixture
def screen(tmp_path):
    rows = []
    for week, a, b, c in itertools.product(range(1, 5), "AB", "XY", "LR"):
        shift = (3 if c == "L" else -3) if week == 4 else 0
        rows.append((week, a, b, c, 10 + week + shift))
    df = pd.DataFrame(rows, columns=["week", "area", "channel", "plan", "count"])
    steps = [{"tool": "count-change-contribution", "purpose": f"Screen {dim}",
              "params": {"cohort": "week", "baseline": "3", "comparison": "4", "by": dim,
                         "history": ["1", "2", "3"]}} for dim in ["area", "channel", "plan"]]
    spec = {"project_name": "Count change", "purpose": "Locate changes", "decision_supported": "Where to investigate",
            "unit_of_analysis": "disjoint cell per week", "target": {"column": "count", "type": "numeric",
            "definition": "Count of completed units"}, "segments": ["area", "channel", "plan", "week"],
            "dimension_omissions": {}, "hypotheses": [{"id": "H1", "statement": "Locate changes",
            "rationale": "Compare groups with trend", "support_criteria": "Offsetting shifts", "pathway": steps}]}
    return Ctx(tmp_path, df, data.column_types(df), spec, "demo"), steps


def test_full_screen_finds_late_dimension_and_missing_evidence(screen):
    ctx, steps = screen
    profile = data.profile(ctx.df)
    assert scope.validate(ctx.scope, profile)[0] == []
    results = {}
    for step in registry.plan_steps(ctx.scope):
        check = registry.check_step(step["tool"], step["params"], ctx.scope, profile, [])
        assert check["verdict"] != "blocked", check
        result = registry.function(step["tool"])(ctx, step["params"])
        evidence = {f["metric"]: f["estimate"] for f in result["findings"]}
        assert evidence["net_change"] == pytest.approx(0)
        assert evidence["gains"] == pytest.approx(12 if step["params"]["by"] == "plan" else 0)
        results[step["step_id"]] = {"label": step["step_id"], "findings": result["findings"]}
    (ctx.run_dir / "results").mkdir()
    for label, record in results.items():
        (ctx.run_dir / "results" / f"{label}.json").write_text(json.dumps(record))
    (ctx.run_dir / "approved_scope.json").write_text(json.dumps(ctx.scope))
    draft = {"hypothesis_verdicts": [{"id": "H1", "verdict": "supported", "reasoning": "Offsets in plan",
                                     "evidence": [{"result": "H1.S3"}]}],
             "dimension_coverage": {label: {"status": "little movement", "reason": "Zero group gaps"}
                                    for label in results}}
    draft["dimension_coverage"]["H1.S3"] = {"status": "movement", "reason": "Loss of 12 offsets gain of 12"}
    draft["intersection_review"] = {
        "status": "unresolved", "reason": "Combined-dimension follow-up remains to be examined.",
        "evidence": [{"result": "H1.S3"}]}
    assert review.validate_review(draft, ctx.run_dir) == []
    assert report.dimension_rows(ctx.scope, draft)[-2][1] == "movement"
    assert report.dimension_rows(ctx.scope, draft)[-1][1] == "unresolved"
    del draft["dimension_coverage"]["H1.S3"]
    assert review.validate_review(draft, ctx.run_dir)
    steps.pop()
    assert any("plan" in e for e in scope.validate(ctx.scope, profile)[0])


def test_prior_period_missing_cells_and_leakage(screen):
    ctx, steps = screen
    params = dict(steps[-1]["params"])
    del params["history"]
    tool = steps[-1]["tool"]
    result = registry.function(tool)(ctx, params)
    assert result["tables"]["groups"].contribution.sum() == 8
    for col in ("week", "plan"):
        assert registry.check_step(tool, params, ctx.scope, data.profile(ctx.df), [col])["verdict"] == "blocked"
    ctx.df = ctx.df.loc[~(ctx.df.week.eq(3) & ctx.df.plan.eq("R"))]
    with pytest.raises(ValueError, match="Missing group-period"):
        registry.function(tool)(ctx, params)
    out = registry.function(tool)(ctx, dict(params, absent_is_zero=True))
    assert out["tables"]["groups"].expected.sum() == 52
