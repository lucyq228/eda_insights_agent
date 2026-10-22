"""Regression cases for business mechanisms that line-level correlations miss."""
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from insight_core import data, stats, registry
from insight_core.context import Ctx
from insight_core.tools_business import business_summary, temporal_diagnostics, period_comparison
from insight_core.tools_eda import prepare_dataset
from insight_core.tools_analysis import pair_deep_dive, driver_importance
from insight_core.views import build_view, validate_views
from insight_core.runner import save_result
from insight_core.scope import approve
from insight_core.state import write_artifact, sha


@pytest.fixture
def ctx(tmp_path):
    rows = []
    for segment, visits in [("families", 4), ("singles", 2)]:
        for customer in range(10):
            for visit in range(visits):
                rows.append({"customer_nbr": f"{segment}-{customer}", "txn": len(rows), "store_nbr": 1,
                             "date": pd.Timestamp("2024-01-01") + pd.Timedelta(days=visit),
                             "segment": segment, "qty": 2, "sales": 8., "product": "chips"})
    df = pd.DataFrame(rows)
    scope = {"target": {"column": "sales", "type": "numeric"}, "date_column": "date",
             "unit_of_analysis": "line", "roles": {"customer": "customer_nbr", "transaction": ["store_nbr", "txn"],
                                                   "quantity": "qty"}, "mode": "exploratory"}
    for directory in ("datasets", "results", "charts"):
        (tmp_path/directory).mkdir()
    return Ctx(tmp_path, df, data.column_types(df), scope, "test", ["segment"])


def test_frequency_can_differ_when_line_amount_is_identical(ctx):
    table = business_summary(ctx, {"dimensions": ["segment"]})["tables"]["business_metrics"].set_index("segment")
    assert table.loc["families", "sales_per_customer"] == 32
    assert table.loc["singles", "sales_per_customer"] == 16
    assert table.loc["families", "transactions_per_customer"] == 4
    assert table.loc["families", "sales_per_transaction"] == table.loc["singles", "sales_per_transaction"]


def test_preparation_preserves_keys_components_and_categories(ctx):
    ctx.scope["exclude"] = [{"column": "qty", "reason": "accounting component, not model driver"}]
    result = prepare_dataset(ctx, {})
    saved = pd.read_parquet(result["path"])
    assert set(saved) == set(ctx.df)
    assert saved["customer_nbr"].equals(ctx.df["customer_nbr"])
    assert saved["product"].equals(ctx.df["product"])


def test_temporal_spike_is_visible_with_constant_line_amount(ctx):
    result = temporal_diagnostics(ctx, {"freq": "D"})
    table = result["tables"]["period_metrics"]
    assert table.sales.max() == 2 * table.sales.min()
    assert table.sales_per_transaction.nunique() == 1
    assert all(f["p"] is None for f in result["findings"])


def test_accounting_contributions_reconcile(ctx):
    result = period_comparison(ctx, {"baseline_start": "2024-01-01", "baseline_end": "2024-01-02",
                                     "comparison_start": "2024-01-03", "comparison_end": "2024-01-04"})
    contributions = result["tables"]["contributions"]
    assert contributions.contribution.sum() == pytest.approx(-160)
    assert result["findings"][-1]["estimate"] == -160


def test_views_retain_grain_and_safe_ratios(ctx):
    ctx.scope["min_n"] = 5
    ctx.scope["views"] = {"customer": {"group_by": ["customer_nbr", "segment"],
        "metrics": {"spend": {"column": "sales", "agg": "sum"}, "visits": {"column": "txn", "agg": "nunique"}},
        "ratios": {"ticket": {"numerator": "spend", "denominator": "visits"}},
        "target": "spend", "drivers": ["segment"]}}
    assert validate_views(ctx.scope, data.profile(ctx.df)) == []
    view = build_view(ctx.df, ctx.scope, "customer")
    assert len(view) == 20 and view.ticket.eq(8).all()
    check = registry.check_step("segment-breakdown", {"view": "customer", "by": "segment"}, ctx.scope, data.profile(ctx.df), [])
    assert check["verdict"] != "blocked"


def test_repeated_number_keys_detected_without_needing_panel(ctx):
    values = pd.Series([1, 2, 3] * 50)
    assert data.infer_type(values, "STORE_NBR") == "id"


def test_result_json_contains_readable_aggregate_evidence(ctx):
    result = save_result(ctx.run_dir, "H1.S1", "business-summary", {}, business_summary(ctx, {"dimensions": ["segment"]}), {})
    table = result["tables"]["business_metrics"]
    assert len(table["preview"]) == 2 and not table["preview_truncated"]


def test_small_pvalues_survive_adjustment():
    assert stats._round({"p": 0.00001234})["p"] == 0.00001234
    assert stats.bh_qvalues([1e-9, .01])[0] == pytest.approx(2e-9)


def test_display_cap_does_not_change_association(ctx, monkeypatch):
    ctx.df = pd.DataFrame({"product": np.repeat([f"p{i}" for i in range(15)], 5),
                           "sales": np.repeat(np.arange(15), 5).astype(float)})
    ctx.types = {"product": "categorical", "sales": "numeric"}
    monkeypatch.setattr(stats, "BOOT", 20)
    result = pair_deep_dive(ctx, {"x": "product", "max_levels": 3})
    assert result["findings"][0]["estimate"] == pytest.approx(1.)
    assert len(result["tables"]["profile"]) == 4


def test_rank_deficient_coefficients_are_suppressed(ctx):
    rng = np.random.default_rng(2)
    x = rng.normal(size=100)
    ctx.df = pd.DataFrame({"x": x, "duplicate": x, "sales": x + rng.normal(size=100)})
    ctx.types = {c: "numeric" for c in ctx.df}
    ctx.drivers = ["x", "duplicate"]
    result = driver_importance(ctx, {})
    assert result["findings"] == []
    assert any("RANK DEFICIENT" in f for f in result["flags"])


def test_exploration_activation_does_not_fabricate_consent(ctx):
    scope = {**ctx.scope, "hypotheses": [], "user_questions": []}
    write_artifact(ctx.run_dir, "scope_proposal.json", {"scope": scope, "version": 1})
    write_artifact(ctx.run_dir, "feasibility.json", {"steps": [], "scope_issues": []}, upstream="scope_proposal.json")
    write_artifact(ctx.run_dir, "run.json", {"request": "Explore sales", "data_sha256": "test"})
    result = approve(ctx.run_dir, exploration=True)
    assert result["user_confirmation"] == ""
    assert result["authorization"] == "user_requested_exploration"
