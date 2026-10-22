from __future__ import annotations

import json

import numpy as np
import pandas as pd

from insight_core import scope as scope_module
from insight_core import stats
from insight_core.association_cache import associate_cached
from insight_core.context import Ctx
from insight_core.review import validate_review
from insight_core.runner import write_analyses_index
from insight_core.state import write_artifact
from insight_core.tools_analysis import group_top_levels


def _reference_eta(groups: np.ndarray, y: np.ndarray) -> float:
    grand = y.mean()
    total = ((y - grand) ** 2).sum()
    between = sum(len(y[groups == level]) * (y[groups == level].mean() - grand) ** 2
                  for level in np.unique(groups))
    return float(np.sqrt(between / total))


def test_vectorized_eta_matches_reference_and_point_screen_skips_bootstrap(monkeypatch):
    rng = np.random.default_rng(12)
    groups = rng.choice([f"level-{i}" for i in range(25)], 2500)
    y = rng.normal(size=2500) + pd.factorize(groups)[0] / 20
    assert stats._eta(groups, y) == pytest_approx(_reference_eta(groups, y))

    def no_bootstrap(*args, **kwargs):
        raise AssertionError("screening must not bootstrap")

    monkeypatch.setattr(stats, "_boot_ci", no_bootstrap)
    result = stats.associate_point(pd.Series(groups), pd.Series(y), "categorical", "numeric")
    assert result["metric"] == "eta" and result["estimate"] > 0
    assert result["ci_low"] is None and result["ci_high"] is None


def pytest_approx(value: float):
    import pytest

    return pytest.approx(value, rel=1e-12, abs=1e-12)


def test_top_levels_are_selected_by_frequency_and_combined_as_other():
    values = pd.Series(list("aaaaabbbbccdef"), dtype="string")
    grouped, meta = group_top_levels(values, max_levels=2)
    assert meta["kept_levels"] == ["a", "b"]
    assert meta["original_levels"] == 6 and meta["other_n"] == 5
    assert grouped.value_counts().to_dict() == {"a": 5, "Other": 5, "b": 4}


def test_association_cache_reuses_identical_calculation(tmp_path, monkeypatch):
    df = pd.DataFrame({"group": ["a", "a", "b", "b", "c", "c"], "target": [1, 2, 3, 4, 5, 6]})
    ctx = Ctx(tmp_path, df, {"group": "categorical", "target": "numeric"},
              {"target": {"column": "target", "type": "numeric"}}, "test")
    calls = 0
    original = stats.associate_point

    def counted(*args, **kwargs):
        nonlocal calls
        calls += 1
        return original(*args, **kwargs)

    monkeypatch.setattr(stats, "associate_point", counted)
    first = associate_cached(ctx, "group", "categorical", with_interval=False)
    second = associate_cached(ctx, "group", "categorical", with_interval=False)
    assert calls == 1 and not first["cache_hit"] and second["cache_hit"]


def _scope(n: int) -> dict:
    hypotheses = [{"id": f"H{i}", "statement": "A testable association", "rationale": "decision relevance",
                   "support_criteria": "eta > 0.1",
                   "pathway": [{"tool": "pair-deep-dive", "params": {"x": "driver"}, "purpose": "test it"}]}
                  for i in range(1, n + 1)]
    return {"project_name": "p", "purpose": "p", "decision_supported": "d",
            "target": {"column": "target", "type": "numeric", "definition": "higher is better"},
            "unit_of_analysis": "row", "drivers": ["driver"], "hypotheses": hypotheses}


PROFILE = {"n_rows": 100, "columns": [
    {"name": "target", "type": "numeric", "missing_pct": 0, "n_unique": 100},
    {"name": "driver", "type": "categorical", "missing_pct": 0, "n_unique": 2,
     "levels": [{"level": "a", "count": 50}, {"level": "b", "count": 50}]},
]}


def test_hypothesis_policy_is_flexible_within_four_to_ten():
    errors, warnings = scope_module.validate(_scope(4), PROFILE)
    assert errors == [] and warnings == []

    errors, _ = scope_module.validate(_scope(11), PROFILE)
    assert any("no more than 10" in issue for issue in errors)

    three = _scope(3)
    errors, _ = scope_module.validate(three, PROFILE)
    assert any("4 to 10" in issue for issue in errors)
    three["hypothesis_count_exception"] = "Only three distinct decision-relevant tests exist."
    errors, warnings = scope_module.validate(three, PROFILE)
    assert errors == [] and any("explicit exception" in warning for warning in warnings)


def test_user_waived_step_is_skipped_not_failed(tmp_path):
    (tmp_path / "results").mkdir()
    scope = _scope(1)
    write_artifact(tmp_path, "approved_scope.json", scope)
    write_artifact(tmp_path, "prepared_data.json", {"n_rows": 100})
    write_artifact(tmp_path, "step_waivers.json",
                   {"waivers": [{"step_id": "H1.S1", "reason": "User chose to omit this deep dive."}]},
                   upstream="approved_scope.json")
    (tmp_path / "results" / "multiple-testing.json").write_text(json.dumps({
        "label": "multiple-testing", "tool": "multiple-testing", "params": {}, "summary": "0 tests",
        "findings": [], "q_values": [], "followup_reason": None,
    }), encoding="utf-8")
    index = write_analyses_index(tmp_path)
    assert index["errors"] == [] and index["steps"][0]["status"] == "skipped"

    review = {"hypothesis_verdicts": [{"id": "H1", "verdict": "not_evaluated",
                                        "reasoning": "The user approved omitting its only step.", "evidence": []}],
              "challenges": [], "rerun_requests": []}
    assert validate_review(review, tmp_path) == []
