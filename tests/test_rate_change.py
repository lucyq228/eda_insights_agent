import pandas as pd
import pytest

from insight_core import data, registry
from insight_core.context import Ctx


TOOL = "rate-change-decomposition"
PARAMS = {"cohort": "wave", "baseline": "A", "comparison": "B", "by": "channel"}


@pytest.fixture
def ctx(tmp_path):
    df = pd.DataFrame({"wave": ["A"] * 4 + ["B"] * 8,
                       "channel": ["direct"] * 3 + ["partner"] + ["direct"] * 4 + ["partner"] * 4,
                       "completed": [0, 0, 0, 1, 0, 0, 0, 1, 1, 1, 1, 1]})
    scope = {"target": {"column": "completed", "type": "binary"}, "min_n": 2,
             "segments": ["wave", "channel"], "drivers": []}
    return Ctx(tmp_path, df, data.column_types(df), scope, "demo")


def test_attribution_and_counts_with_unequal_cohorts(ctx):
    out = registry.function(TOOL)(ctx, PARAMS)
    estimates = {f["metric"]: f["estimate"] for f in out["findings"]}
    assert estimates == pytest.approx({"rate_change_pp": 37.5, "benchmark_rate": .5,
                                      "mix_pp": 25, "within_pp": 12.5})
    assert list(out["tables"]["cohorts"]["n"]) == [4, 8]
    assert out["tables"]["groups"]["expected_events"].sum() == 4


def test_new_group_prevents_full_attribution(ctx):
    ctx.df.loc[4, "channel"] = "new"
    out = registry.function(TOOL)(ctx, PARAMS)
    assert [f["metric"] for f in out["findings"]] == ["rate_change_pp"]
    assert any("undefined" in msg for msg in out["flags"])


def test_missing_and_disappearing_groups_stay_in_denominators(ctx):
    ctx.df.loc[ctx.df.channel.eq("direct"), "channel"] = None
    ctx.df.loc[3, "channel"] = "legacy"
    ctx.df.loc[2, "channel"] = "partner"
    out = registry.function(TOOL)(ctx, PARAMS)
    table = out["tables"]["groups"]
    assert table.group.isna().sum() == 1
    assert table.baseline_n.sum() == 4 and table.comparison_n.sum() == 8
    assert table.loc[table.group.eq("legacy"), "within_pp"].item() == 0
    assert table.mix_pp.sum() + table.within_pp.sum() == pytest.approx(37.5)


def test_feasibility_checks_both_inputs_and_rejects_views(ctx):
    profile = data.profile(ctx.df)
    def verdict(params, leakage):
        return registry.check_step(TOOL, params, ctx.scope, profile, leakage)["verdict"]
    assert verdict(PARAMS, []) != "blocked"
    for column in ("wave", "channel"):
        assert verdict(PARAMS, [column]) == "blocked"
    assert verdict(dict(PARAMS, view="aggregate"), []) == "blocked"
    assert verdict(dict(PARAMS, by="completed"), []) == "blocked"
    assert verdict(dict(PARAMS, comparison="A"), []) == "blocked"
    ctx.scope["exclude"] = [{"column": "channel", "reason": "post-outcome"}]
    assert verdict(PARAMS, []) == "blocked"


def test_numeric_zero_as_scoped_event():
    assert data.encode_binary(pd.Series([1, 0]), "0").tolist() == [0., 1.]


def test_repeated_units_rejected(ctx):
    ctx.df["record_id"] = list(range(11)) + [0]
    ctx.scope["id_column"] = "record_id"
    with pytest.raises(ValueError, match="unique"):
        registry.function(TOOL)(ctx, PARAMS)
