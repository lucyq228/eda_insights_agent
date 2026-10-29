"""Association measures that pick themselves from the column types.

Every measure returns the same finding shape:
{metric, estimate, ci_low, ci_high, p, n, direction}
"""

from __future__ import annotations

import hashlib
import json

import numpy as np
import pandas as pd
from scipy import stats

BOOT = 300
SEED = 7


def fisher_ci(r: float, n: int, alpha: float = .05) -> tuple[float, float]:
    if n <= 3 or not np.isfinite(r):
        return (np.nan, np.nan)
    z, se = np.arctanh(np.clip(r, -.999999, .999999)), 1 / np.sqrt(n - 3)
    crit = stats.norm.ppf(1 - alpha / 2)
    return float(np.tanh(z - crit * se)), float(np.tanh(z + crit * se))


def _boot_ci(fn, *arrays, alpha: float = .05) -> tuple[float, float]:
    rng = np.random.default_rng(SEED)
    n = len(arrays[0])
    vals = []
    for _ in range(BOOT):
        idx = rng.integers(0, n, n)
        try:
            vals.append(fn(*[a[idx] for a in arrays]))
        except Exception:
            continue
    vals = [v for v in vals if np.isfinite(v)]
    if len(vals) < 20:
        return (np.nan, np.nan)
    return float(np.quantile(vals, alpha / 2)), float(np.quantile(vals, 1 - alpha / 2))


def _eta(groups: np.ndarray, y: np.ndarray) -> float:
    """Correlation ratio using one factorization and vectorized group sums."""
    codes, _ = pd.factorize(groups, sort=False)
    return _eta_codes(codes, y)


def _eta_codes(codes: np.ndarray, y: np.ndarray) -> float:
    """Correlation ratio for non-negative integer group codes."""
    codes = np.asarray(codes, dtype=np.intp)
    y = np.asarray(y, dtype=float)
    valid = (codes >= 0) & np.isfinite(y)
    codes, y = codes[valid], y[valid]
    if not len(y):
        return np.nan
    grand = y.mean()
    ss_total = ((y - grand) ** 2).sum()
    if ss_total == 0:
        return np.nan
    counts = np.bincount(codes)
    sums = np.bincount(codes, weights=y, minlength=len(counts))
    used = counts > 0
    means = sums[used] / counts[used]
    ss_between = (counts[used] * (means - grand) ** 2).sum()
    return float(np.sqrt(ss_between / ss_total))


def _cramers_v(a: np.ndarray, b: np.ndarray) -> float:
    table = pd.crosstab(a, b).to_numpy()
    if min(table.shape) < 2:
        return np.nan
    chi2 = stats.chi2_contingency(table, correction=False)[0]
    return float(np.sqrt(chi2 / (table.sum() * (min(table.shape) - 1))))


def _round(d: dict) -> dict:
    return {k: (float(v) if isinstance(v, (float, np.floating)) and np.isfinite(v) else
                (None if isinstance(v, (float, np.floating)) else v)) for k, v in d.items()}


def associate_point(x: pd.Series, y: pd.Series, x_type: str, y_type: str, alpha: float = .05) -> dict:
    """Return an association point estimate without resampling a confidence interval."""
    return _associate(x, y, x_type, y_type, alpha=alpha, with_interval=False)


def associate_with_interval(x: pd.Series, y: pd.Series, x_type: str, y_type: str,
                            alpha: float = .05) -> dict:
    """Return a report-grade association with its confidence interval."""
    return _associate(x, y, x_type, y_type, alpha=alpha, with_interval=True)


def associate(x: pd.Series, y: pd.Series, x_type: str, y_type: str, alpha: float = .05) -> dict:
    """Backward-compatible report-grade association."""
    return associate_with_interval(x, y, x_type, y_type, alpha)


def _associate(x: pd.Series, y: pd.Series, x_type: str, y_type: str, alpha: float,
               with_interval: bool) -> dict:
    """x is a driver, y the target. Types: numeric | binary | categorical.

    A binary target arrives already coded 0/1 and counts as numeric here.
    """
    d = pd.DataFrame({"x": x, "y": y}).dropna()
    n = len(d)
    if n < 5 or d["x"].nunique() < 2 or d["y"].nunique() < 2:
        return {"metric": "none", "estimate": None, "ci_low": None, "ci_high": None, "p": None, "n": n,
                "direction": "not estimable"}
    y_num = y_type in ("numeric", "binary")
    if x_type == "numeric" and y_num:
        r, p = stats.spearmanr(d["x"], d["y"])
        lo, hi = fisher_ci(r, n, alpha) if with_interval else (np.nan, np.nan)
        pearson = stats.pearsonr(d["x"], d["y"])[0]
        out = {"metric": "spearman_r", "estimate": r, "ci_low": lo, "ci_high": hi, "p": p, "n": n,
               "pearson_r": pearson, "direction": "positive" if r > 0 else "negative"}
    elif x_type in ("categorical", "binary") and y_num:
        g, v = d["x"].astype(str).to_numpy(), d["y"].to_numpy(float)
        codes, levels = pd.factorize(g, sort=False)
        eta = _eta_codes(codes, v)
        p = stats.f_oneway(*[v[codes == k] for k in range(len(levels))]).pvalue
        lo, hi = _boot_ci(_eta_codes, codes, v, alpha=alpha) if with_interval else (np.nan, np.nan)
        means = d.groupby(d["x"].astype(str))["y"].mean().sort_values()
        out = {"metric": "eta", "estimate": eta, "ci_low": lo, "ci_high": hi, "p": p, "n": n,
               "direction": f"highest in {means.index[-1]}, lowest in {means.index[0]}",
               "level_means": {k: round(float(m), 4) for k, m in means.items()}}
    elif x_type == "numeric" and y_type == "categorical":
        g, v = d["y"].astype(str).to_numpy(), d["x"].to_numpy(float)
        codes, levels = pd.factorize(g, sort=False)
        eta = _eta_codes(codes, v)
        p = stats.f_oneway(*[v[codes == k] for k in range(len(levels))]).pvalue
        lo, hi = _boot_ci(_eta_codes, codes, v, alpha=alpha) if with_interval else (np.nan, np.nan)
        means = d.groupby(d["y"].astype(str))["x"].mean().sort_values()
        out = {"metric": "eta", "estimate": eta, "ci_low": lo, "ci_high": hi, "p": p, "n": n,
               "direction": f"driver highest when target={means.index[-1]}"}
    else:
        a, b = d["x"].astype(str).to_numpy(), d["y"].astype(str).to_numpy()
        v = _cramers_v(a, b)
        p = stats.chi2_contingency(pd.crosstab(a, b).to_numpy())[1]
        lo, hi = _boot_ci(_cramers_v, a, b, alpha=alpha) if with_interval else (np.nan, np.nan)
        out = {"metric": "cramers_v", "estimate": v, "ci_low": lo, "ci_high": hi, "p": p, "n": n,
               "direction": "see breakdown"}
    out["test_id"] = test_identity("association:" + x_type + ":" + y_type, d, [x.name, y.name])
    return _round(out)


def strength(estimate: float | None) -> str:
    if estimate is None:
        return "n/a"
    a = abs(estimate)
    return "strong" if a >= .5 else "moderate" if a >= .3 else "weak" if a >= .1 else "negligible"


def bh_qvalues(pvalues: list[float]) -> list[float]:
    p = np.asarray(pvalues, float)
    n = len(p)
    if n == 0:
        return []
    order = np.argsort(p)
    ranked = p[order] * n / np.arange(1, n + 1)
    q = np.minimum.accumulate(ranked[::-1])[::-1]
    out = np.empty(n)
    out[order] = np.clip(q, 0, 1)
    return [float(v) for v in out]


def residualize(y: np.ndarray, X: np.ndarray) -> np.ndarray:
    X = np.column_stack([np.ones(len(y)), X])
    beta, *_ = np.linalg.lstsq(X, y, rcond=None)
    return y - X @ beta


def design(df: pd.DataFrame, cols: list[str], types: dict[str, str]) -> pd.DataFrame:
    """Numeric matrix: numeric columns median-imputed, categoricals one-hot."""
    parts = []
    for c in cols:
        if types.get(c) == "numeric":
            s = pd.to_numeric(df[c], errors="coerce")
            parts.append(s.fillna(s.median()).rename(c))
        else:
            parts.append(pd.get_dummies(df[c].astype(str), prefix=c, drop_first=True, dtype=float))
    return pd.concat(parts, axis=1) if parts else pd.DataFrame(index=df.index)


def test_identity(method: str, data: pd.DataFrame, specification: list) -> str:
    """Identify the exact sample and test, independently of display/tool names."""
    digest = hashlib.sha256(pd.util.hash_pandas_object(data, index=True).values.tobytes()).hexdigest()
    return hashlib.sha256(json.dumps([method, specification, digest], default=str).encode()).hexdigest()


def adjusted_test_id(x, y, data, controls, types):
    controls = sorted(set(controls))
    frame = data[[x.name, y.name] + controls]
    return test_identity("partial-spearman", frame,
                         [x.name, y.name, [(c, types.get(c)) for c in controls]])
