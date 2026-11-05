"""Regression coverage for preparation -> scope -> change calculations -> review."""
import json

import pandas as pd
import pytest

from insight_core import data, registry, review, scope
from insight_core.context import Ctx
from insight_core.tools_eda import prepare_dataset
from insight_core.tools_business import count_change_contribution, rate_change_decomposition


def make_ctx(tmp_path, df, params, target_type="numeric"):
    tool = "rate-change-decomposition" if "denominator" in params or target_type == "binary" else "count-change-contribution"
    spec = {"project_name": "Change", "purpose": "Locate change", "decision_supported": "Investigate segments",
            "unit_of_analysis": "disjoint observations", "min_n": 1,
            "target": {"column": "value", "type": target_type, "definition": "Observed events", "positive_class": "1"},
            "drivers": "all", "dimension_omissions": {},
            "hypotheses": [{"id": "H1", "statement": "Where did change occur?", "rationale": "Prioritize investigation",
                            "support_criteria": "Reconcile contributions", "pathway": [
                                {"tool": tool, "params": params, "purpose": "Locate change"}]}]}
    (tmp_path / "datasets").mkdir(exist_ok=True)
    return Ctx(tmp_path, df, data.column_types(df), spec, "check")


P = {"cohort": "period", "baseline": "A", "comparison": "B", "by": "segment"}


def test_repeated_events_survive_preparation_and_reconcile(tmp_path):
    df = pd.DataFrame({"period": ["A"] * 100 + ["B"] * 80,
                       "segment": ["all"] * 180, "value": [1] * 180})
    ctx = make_ctx(tmp_path, df, P)
    prepared = prepare_dataset(ctx, {})
    ctx.df = pd.read_parquet(prepared["path"])
    out = count_change_contribution(ctx, P)
    assert {f["metric"]: f["estimate"] for f in out["findings"]}["net_change"] == -20
    assert prepared["reconciliation"]["input_rows"] == prepared["reconciliation"]["output_rows"] == 180
    assert [r["components"]["value"]["sum"] for r in prepared["reconciliation"]["period_totals"]] == [100, 80]


def test_missing_targets_preserved_and_change_fails_explicitly(tmp_path):
    df = pd.DataFrame({"period": ["A", "B"], "segment": ["x", "x"], "value": [1, None]})
    ctx = make_ctx(tmp_path, df, P)
    prepared = prepare_dataset(ctx, {})
    ctx.df = pd.read_parquet(prepared["path"])
    assert len(ctx.df) == 2 and ctx.df.value.isna().sum() == 1
    with pytest.raises(ValueError, match="finite"):
        count_change_contribution(ctx, P)


def test_aggregate_rate_equals_binary_rate_including_joint_bands(tmp_path):
    rows = []
    for period, segment, age, n, events in [("A", "x", 20, 30, 3), ("A", "y", 50, 10, 4),
                                           ("B", "x", 20, 20, 4), ("B", "y", 50, 20, 10)]:
        rows += [(period, segment, age, int(i < events)) for i in range(n)]
    raw = pd.DataFrame(rows, columns=["period", "segment", "age", "value"])
    params = dict(P, by=["segment", "age"])
    unit = make_ctx(tmp_path, raw, params, "binary")
    unit.scope["dimension_bins"] = {"age": [30]}
    agg = raw.groupby(["period", "segment", "age"], as_index=False).agg(value=("value", "sum"), eligible=("value", "size"))
    aggregate = make_ctx(tmp_path, agg, dict(params, denominator="eligible"))
    aggregate.scope["dimension_bins"] = {"age": [30]}
    aggregate.scope["exclude"] = [{"column": "eligible", "reason": "metric component, not predictor"}]
    check = registry.check_step("rate-change-decomposition", dict(params, denominator="eligible"), aggregate.scope, data.profile(agg), ["eligible"])
    assert check["verdict"] != "blocked", check
    prepared = prepare_dataset(aggregate, {})
    aggregate.df = pd.read_parquet(prepared["path"])
    assert sum(row["components"]["eligible"]["sum"] for row in prepared["reconciliation"]["period_totals"]) == 80
    a = rate_change_decomposition(unit, params)
    b = rate_change_decomposition(aggregate, dict(params, denominator="eligible"))
    assert {f["metric"]: f["estimate"] for f in a["findings"]} == pytest.approx({f["metric"]: f["estimate"] for f in b["findings"]})
    assert b["tables"]["groups"].baseline_n.sum() == 40
    assert b["tables"]["groups"].comparison_n.sum() == 40
    assert b["grouping_columns"] == {"group_1": "segment", "group_2": "age"}
    assert b["tables"]["groups"].group_2.nunique() == 2
    aggregate.df.loc[0, "eligible"] = 0
    with pytest.raises(ValueError, match="events <= eligible"):
        rate_change_decomposition(aggregate, dict(params, denominator="eligible"))


@pytest.mark.parametrize("bad", [None, -1, 1.5, float("inf")])
def test_invalid_aggregate_denominators_rejected(tmp_path, bad):
    df = pd.DataFrame({"period": ["A", "B"], "segment": ["x", "x"], "value": [1, 2], "eligible": [bad, 10]})
    ctx = make_ctx(tmp_path, df, dict(P, denominator="eligible"))
    with pytest.raises(ValueError, match="finite nonnegative"):
        rate_change_decomposition(ctx, dict(P, denominator="eligible"))


def test_numeric_inventory_broad_default_and_focused_exception(tmp_path):
    df = pd.DataFrame({"period": ["A"] * 4 + ["B"] * 4, "segment": ["x", "x", "y", "y"] * 2,
                       "age": [20, 25, 40, 50] * 2, "value": list(range(1, 9))})
    ctx = make_ctx(tmp_path, df, P)
    profile = data.profile(df)
    assert any("age" in e for e in scope.validate(ctx.scope, profile)[0])
    ctx.scope["dimension_omissions"] = {"age": "No business justification for age bands"}
    assert not scope.validate(ctx.scope, profile)[0]
    del ctx.scope["dimension_omissions"]
    assert any("require dimension_omissions" in e for e in scope.validate(ctx.scope, profile)[0])
    ctx.scope["change_investigation"] = "focused"
    assert any("focus_reason" in e for e in scope.validate(ctx.scope, profile)[0])
    ctx.scope["focus_reason"] = "User asked only about segment"
    assert not scope.validate(ctx.scope, profile)[0]
    ctx.scope.pop("change_investigation")
    ctx.scope["dimension_omissions"] = {}
    ctx.scope["dimension_bins"] = {"age": [30]}
    ctx.scope["hypotheses"][0]["pathway"].append({"tool": "count-change-contribution", "params": dict(P, by="age"), "purpose": "Screen age bands"})
    assert not scope.validate(ctx.scope, profile)[0]
    for params in [dict(P, by="age"), dict(P, by=["segment", "age"])]:
        check = registry.check_step("count-change-contribution", params, ctx.scope, profile, [])
        assert check["verdict"] != "blocked", check
        result = count_change_contribution(ctx, params)
        assert result["tables"]["groups"].contribution.sum() == 16
    ctx.scope["dimension_bins"] = {"age": [30, 20]}
    assert scope.validate(ctx.scope, profile)[0]


def test_review_cannot_skip_broad_checks_when_metadata_missing(tmp_path):
    df = pd.DataFrame({"period": ["A", "B"], "segment": ["x", "y"], "value": [10, 8]})
    ctx = make_ctx(tmp_path, df, P)
    del ctx.scope["dimension_omissions"]
    (tmp_path / "results").mkdir()
    (tmp_path / "approved_scope.json").write_text(json.dumps(ctx.scope))
    errors = review.validate_review({}, tmp_path)
    assert any("dimension_coverage" in e for e in errors)
    assert any("intersection_review" in e for e in errors)
