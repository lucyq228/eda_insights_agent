"""Analysis tools (phase: analysis). Each returns findings in one shape:
{label, x, y, metric, estimate, ci_low, ci_high, p, n, ...}.
"""

from __future__ import annotations

import json

import numpy as np
import pandas as pd
import statsmodels.api as sm
from scipy import stats as st

from . import charts, stats
from .association_cache import associate_cached
from .context import Ctx


def _xtype(ctx: Ctx, c: str) -> str:
    return "numeric" if ctx.types.get(c) == "numeric" else "categorical"


def _finding(label: str, x: str, y: str, res: dict, **extra) -> dict:
    keys = ("metric", "estimate", "ci_low", "ci_high", "p", "n", "direction", "test_id")
    return {"label": label, "x": x, "y": y, **{k: res.get(k) for k in keys}, **extra}


def _numeric_target(ctx: Ctx) -> None:
    if ctx.target_type == "categorical":
        raise ValueError("this tool needs a numeric or binary target")


def _binned(x: pd.Series, y: pd.Series, bins: int = 10) -> pd.DataFrame:
    d = pd.DataFrame({"x": x, "y": y}).dropna()
    d["bin"] = pd.qcut(d["x"], q=min(bins, d["x"].nunique()), duplicates="drop")
    g = d.groupby("bin", observed=True)
    t = pd.DataFrame({"bin_mid": g["x"].median(), "mean": g["y"].mean(), "sd": g["y"].std(), "n": g["y"].size()})
    half = 1.96 * t["sd"].fillna(0) / np.sqrt(t["n"])
    t["ci_low"], t["ci_high"] = t["mean"] - half, t["mean"] + half
    return t.reset_index(drop=True).drop(columns="sd")


def _group_table(seg: pd.Series, y: pd.Series) -> pd.DataFrame:
    d = pd.DataFrame({"level": seg.astype(str), "y": y}).dropna()
    t = d.groupby("level")["y"].agg(["mean", "std", "count"]).reset_index().rename(columns={"count": "n"})
    half = 1.96 * t["std"].fillna(0) / np.sqrt(t["n"])
    t["ci_low"], t["ci_high"] = t["mean"] - half, t["mean"] + half
    return t.drop(columns="std").sort_values("mean", ascending=False)


def group_top_levels(series: pd.Series, max_levels: int = 10, other_label: str = "Other") -> tuple[pd.Series, dict]:
    """Keep the most frequent levels and combine the rest without looking at the target."""
    max_levels = max(2, int(max_levels))
    text = series.astype("string")
    counts = text.value_counts(dropna=True).rename_axis("level").reset_index(name="n")
    counts["sort_key"] = counts["level"].astype(str)
    counts = counts.sort_values(["n", "sort_key"], ascending=[False, True], kind="stable")
    original_levels = len(counts)
    kept = counts.head(max_levels)["level"].astype(str).tolist()
    grouped = text.map(lambda value: value if pd.isna(value) or str(value) in kept else other_label)
    other_n = int((grouped == other_label).sum()) if original_levels > max_levels else 0
    metadata = {
        "applied": original_levels > max_levels,
        "selection": "top levels by frequency; remaining levels combined as Other",
        "original_levels": original_levels,
        "max_levels": max_levels,
        "kept_levels": kept,
        "other_n": other_n,
        "other_share": round(other_n / max(1, int(text.notna().sum())), 4),
    }
    return grouped, metadata


def feature_target_associations(ctx: Ctx, params: dict) -> dict:
    drivers = params.get("drivers") or ctx.drivers
    findings = []
    for c in drivers:
        # A broad screen needs ranking, not hundreds of resamples per column.
        res = associate_cached(ctx, c, _xtype(ctx, c), with_interval=False)
        findings.append(_finding(f"{c} ~ {ctx.target}", c, ctx.target, res, strength=stats.strength(res["estimate"])))
    metric_order = {"spearman_r": 0, "eta": 1, "cramers_v": 2}
    findings.sort(key=lambda f: (metric_order.get(f["metric"], 3), -abs(f["estimate"] or 0)))
    ci_top = max(0, min(int(params.get("ci_top", 3)), len(findings)))
    intervals_computed = 0
    for i in range(ci_top):
        c = findings[i]["x"]
        if _xtype(ctx, c) == "categorical" and ctx.df[c].nunique(dropna=True) > 10:
            findings[i]["interval_status"] = "screening_point_estimate_high_cardinality"
            findings[i]["report_grade_next_step"] = "target-by-group (all levels tested; display may be capped)"
            continue
        res = associate_cached(ctx, c, _xtype(ctx, c), with_interval=True)
        findings[i] = _finding(f"{c} ~ {ctx.target}", c, ctx.target, res,
                               strength=stats.strength(res["estimate"]), interval_status="report_grade")
        intervals_computed += 1
    for f in findings[ci_top:]:
        f["interval_status"] = "screening_point_estimate"
    ok = [f for f in findings if f["p"] is not None]
    for f, q in zip(ok, stats.bh_qvalues([f["p"] for f in ok])):
        f["q_within_tool"] = q
    top = [f for f in findings if f["estimate"] is not None][:15]
    chart = charts.ci_bars([f"{f['x']} ({f['metric']})" for f in top], [f["estimate"] for f in top],
                           [f["ci_low"] if f["ci_low"] is not None else f["estimate"] for f in top],
                           [f["ci_high"] if f["ci_high"] is not None else f["estimate"] for f in top],
                           f"Association with {ctx.target} (95% CI where report-grade)", "estimate", ctx.chart("ranked"))
    lead = ", ".join(f"{f['x']} {f['metric']}={f['estimate']}" for f in top[:3])
    return {"summary": f"{len(findings)} drivers screened by metric family (not a common importance scale): {lead}", "findings": findings,
            "tables": {"ranked": pd.DataFrame(findings)}, "charts": [chart],
            "notes": [f"report-grade intervals were computed for {intervals_computed} of the top {ci_top} ranked drivers; the rest are screening point estimates",
                      "high-cardinality drivers need a selected deep dive for intervals; both screen and deep dive test all levels",
                      "eta, Cramer's V and Spearman measure different relationships; compare ranks only within a metric family",
                      "these are one-at-a-time associations; overlapping drivers can share the same signal"]}


def correlation_matrix(ctx: Ctx, params: dict) -> dict:
    drivers = [c for c in (params.get("drivers") or ctx.drivers) if ctx.types.get(c) == "numeric"]
    cols = drivers + ([ctx.target] if ctx.target_type != "categorical" else [])
    m = ctx.df[cols].corr(method="spearman").round(3)
    threshold = float(params.get("threshold", .8))
    pairs = [{"a": a, "b": b, "spearman_r": float(m.loc[a, b])} for i, a in enumerate(drivers) for b in drivers[i + 1:]
             if abs(m.loc[a, b]) >= threshold]
    chart = charts.heatmap(m, "Spearman correlation matrix", ctx.chart("heatmap"))
    flags = [f"{p['a']} and {p['b']} overlap strongly (r={p['spearman_r']}); read them as one signal" for p in pairs]
    return {"summary": f"{len(cols)} numeric columns; {len(pairs)} driver pairs with |r| >= {threshold}",
            "findings": [], "tables": {"matrix": m.reset_index()}, "charts": [chart], "flags": flags,
            "collinear_pairs": pairs}


def target_by_numeric_bins(ctx: Ctx, params: dict) -> dict:
    x = params["x"]
    if _xtype(ctx, x) != "numeric":
        raise ValueError("target-by-numeric-bins requires numeric x; use target-by-group for categories")
    res = associate_cached(ctx, x, "numeric", with_interval=True)
    f = _finding(f"{x} ~ {ctx.target}", x, ctx.target, res, strength=stats.strength(res["estimate"]))
    if ctx.target_type == "categorical":
        bins = pd.qcut(ctx.df[x], int(params.get("bins", 10)), duplicates="drop")
        table = pd.crosstab(bins, ctx.df[ctx.target], normalize="index").round(3).reset_index().astype(str)
        chart_list = []
    else:
        table = _binned(ctx.df[x], ctx.df[ctx.target], int(params.get("bins", 10)))
        chart_list = [charts.binned_line(table, x, ctx.target,
                     f"{ctx.target} across {x} quantile bins (95% CI)", ctx.chart("binned"))]
    return {"summary": f"{x}: {res['metric']}={res['estimate']} (n={res['n']})", "findings": [f],
            "tables": {"profile": table}, "charts": chart_list,
            "notes": ["Bins summarize the display; association uses the original unbinned observations."]}


def target_by_group(ctx: Ctx, params: dict) -> dict:
    by = params["by"]
    if _xtype(ctx, by) == "numeric":
        raise ValueError("target-by-group requires categorical groups; use target-by-numeric-bins")
    segments, grouping = group_top_levels(ctx.df[by], params.get("max_levels", 10))
    variant = f"top-{grouping['max_levels']}-by-frequency" if grouping["applied"] else "raw"
    res = associate_cached(ctx, by, "categorical", with_interval=True, values=ctx.df[by], variant="raw")
    f = _finding(f"{by} (segments) ~ {ctx.target}", by, ctx.target, res)
    extra = ({"level_grouping": grouping,
              "notes": ["display only: levels selected by frequency; association uses all original levels"]}
             if grouping["applied"] else {})
    if ctx.target_type == "categorical":
        table = pd.crosstab(segments, ctx.df[ctx.target], normalize="index").round(3).reset_index()
        return {"summary": f"{by}: Cramer's V={res['estimate']}", "findings": [f],
                "tables": {"breakdown": table}, "charts": [], **extra}
    table = _group_table(segments, ctx.df[ctx.target])
    small = table[table["n"] < ctx.min_n]["level"].tolist()
    chart = charts.group_bars(table, "level", f"{ctx.target} by {by} (95% CI)", f"mean {ctx.target}", ctx.chart("bars"))
    gap = float(table["mean"].max() - table["mean"].min())
    return {"summary": f"{by}: {res['metric']}={res['estimate']}, gap between highest and lowest level {gap:.3g}",
            "findings": [f], "tables": {"breakdown": table}, "charts": [chart],
            "flags": [f"levels with n < {ctx.min_n}: {small}"] if small else [], **extra}


def _partial_r(x: np.ndarray, y: np.ndarray, Z: np.ndarray) -> float:
    return float(np.corrcoef(stats.residualize(x, Z), stats.residualize(y, Z))[0, 1])


def correlation_by_group(ctx: Ctx, params: dict) -> dict:
    _numeric_target(ctx)
    x, by = params["x"], params["by"]
    d = ctx.df[[x, by, ctx.target]].dropna()
    pooled = stats.associate(d[x], d[ctx.target], "numeric", ctx.target_type, ctx.alpha)
    findings = [_finding(f"{x} ~ {ctx.target} | pooled", x, ctx.target, pooled, segment="pooled")]
    rows, undefined = [], []
    for level, g in d.groupby(by):
        if len(g) < ctx.min_n:
            continue
        r = stats.associate(g[x], g[ctx.target], "numeric", ctx.target_type, ctx.alpha)
        findings.append(_finding(f"{x} ~ {ctx.target} | {by}={level}", x, ctx.target, r, segment=str(level)))
        estimate = r["estimate"]
        if estimate is None or not np.isfinite(estimate):
            undefined.append(str(level))
            continue
        rows.append((str(level), float(estimate), len(g)))
    rx, ry = d[x].rank().to_numpy(float), d[ctx.target].rank().to_numpy(float)
    Z = pd.get_dummies(d[by].astype(str), drop_first=True, dtype=float).to_numpy()
    within_r = _partial_r(rx, ry, Z)
    n, k = len(d), Z.shape[1]
    lo, hi = stats.fisher_ci(within_r, n - k, ctx.alpha)
    t = within_r * np.sqrt((n - 2 - k) / max(1e-12, 1 - within_r ** 2))
    within = {"test_id": stats.adjusted_test_id(d[x], d[ctx.target], d, [by], ctx.types),
              "metric": "spearman_r_within_segments", "estimate": round(within_r, 4), "ci_low": round(lo, 4),
              "ci_high": round(hi, 4), "p": float(2 * st.t.sf(abs(t), n - 2 - k)), "n": n,
              "direction": "positive" if within_r > 0 else "negative"}
    findings.append(_finding(f"{x} ~ {ctx.target} | within {by}", x, ctx.target, within, segment="within"))

    z = np.array([np.arctanh(np.clip(r, -.999, .999)) for _, r, _ in rows])
    w = np.array([m - 3 for _, _, m in rows], float)
    q_stat = float((w * (z - (w * z).sum() / w.sum()) ** 2).sum()) if len(rows) > 1 else np.nan
    het_p = float(st.chi2.sf(q_stat, len(rows) - 1)) if len(rows) > 1 else None
    flags = []
    if undefined:
        flags.append(f"NOT ESTIMABLE: {x} does not vary within {by} for {', '.join(undefined)}, "
                     "so those levels have no within-level correlation")
    pr, wr = pooled["estimate"] or 0, within_r
    if np.sign(pr) != np.sign(wr) and max(abs(pr), abs(wr)) >= .1 or abs(pr - wr) >= .15:
        flags.append(f"SIMPSON/CONFOUNDING: pooled r={pr:.2f} but within-{by} r={wr:.2f}; "
                     f"the {by} mix distorts the pooled number, lead with the within-{by} result")
    if het_p is not None and het_p < ctx.alpha:
        ests = ", ".join(f"{lv}={r:.2f}" for lv, r, _ in rows)
        flags.append(f"HETEROGENEITY: the association differs across {by} (Cochran Q p={het_p:.3g}): {ests}")
    seg = [f for f in findings if f["estimate"] is not None]
    chart = charts.ci_bars([f["segment"] for f in seg], [f["estimate"] for f in seg], [f["ci_low"] for f in seg],
                           [f["ci_high"] for f in seg], f"{x} vs {ctx.target}: pooled, by {by}, within {by}",
                           "Spearman r (95% CI)", ctx.chart("forest"))
    return {"summary": f"pooled r={pr:.3f}, within-{by} r={wr:.3f}, heterogeneity p={het_p if het_p is None else round(het_p, 4)}",
            "findings": findings, "tables": {"by_segment": pd.DataFrame(findings)}, "charts": [chart], "flags": flags,
            "heterogeneity_p": het_p, "simpson_flag": any(f.startswith("SIMPSON") for f in flags)}


def adjusted_correlation(ctx: Ctx, params: dict) -> dict:
    _numeric_target(ctx)
    x, controls = params["x"], params["controls"]
    d = ctx.df[[x, ctx.target] + controls].dropna(subset=[x, ctx.target])
    raw = stats.associate(d[x], d[ctx.target], "numeric", ctx.target_type, ctx.alpha)
    ranked = d.copy()
    for c in controls:
        if ctx.types.get(c) == "numeric":
            ranked[c] = ranked[c].rank()
    Z = stats.design(ranked, controls, ctx.types).to_numpy(float)
    r = _partial_r(d[x].rank().to_numpy(float), d[ctx.target].rank().to_numpy(float), Z)
    n, k = len(d), Z.shape[1]
    lo, hi = stats.fisher_ci(r, n - k, ctx.alpha)
    t = r * np.sqrt((n - 2 - k) / max(1e-12, 1 - r ** 2))
    part = {"test_id": stats.adjusted_test_id(d[x], d[ctx.target], d, controls, ctx.types),
            "metric": "partial_spearman_r", "estimate": round(r, 4), "ci_low": round(lo, 4), "ci_high": round(hi, 4),
            "p": float(2 * st.t.sf(abs(t), n - 2 - k)), "n": n, "direction": "positive" if r > 0 else "negative"}
    label_c = ", ".join(controls)
    findings = [_finding(f"{x} ~ {ctx.target} | raw", x, ctx.target, raw),
                _finding(f"{x} ~ {ctx.target} | controlling {label_c}", x, ctx.target, part, controls=controls)]
    flags = []
    rr = raw["estimate"] or 0
    if abs(rr) >= .1 and abs(r) < .5 * abs(rr):
        flags.append(f"ATTENUATED: r falls from {rr:.2f} to {r:.2f} after controlling for {label_c}; "
                     "much of the raw association is shared with the controls")
    if np.sign(rr) != np.sign(r) and abs(r) >= .1:
        flags.append(f"SIGN FLIP: raw r={rr:.2f}, partial r={r:.2f}")
    return {"summary": f"raw r={rr:.3f} -> partial r={r:.3f} controlling {label_c}", "findings": findings,
            "tables": {"comparison": pd.DataFrame(findings)}, "charts": [], "flags": flags}


def nonlinearity_check(ctx: Ctx, params: dict) -> dict:
    _numeric_target(ctx)
    from sklearn.feature_selection import mutual_info_regression

    x = params["x"]
    d = ctx.df[[x, ctx.target]].dropna()
    xs = (d[x] - d[x].mean()) / d[x].std()
    y = d[ctx.target].to_numpy(float)
    lin = sm.OLS(y, sm.add_constant(xs.to_numpy())).fit()
    quad = sm.OLS(y, sm.add_constant(np.column_stack([xs, xs ** 2]))).fit()
    coef, (lo, hi), p = quad.params[2], quad.conf_int(ctx.alpha)[2], quad.pvalues[2]
    delta_r2 = float(quad.rsquared - lin.rsquared)
    mi = float(mutual_info_regression(d[[x]], y, random_state=0)[0])
    spearman = stats.associate(d[x], d[ctx.target], "numeric", ctx.target_type, ctx.alpha)
    q_res = {"metric": "quadratic_coef_per_sd2", "estimate": round(float(coef), 4), "ci_low": round(float(lo), 4),
             "ci_high": round(float(hi), 4), "p": float(p), "n": len(d),
             "direction": "inverted-U (rises then falls)" if coef < 0 else "U-shape or accelerating"}
    findings = [_finding(f"{x} ~ {ctx.target} | monotonic", x, ctx.target, spearman),
                _finding(f"{x} ~ {ctx.target} | curvature", x, ctx.target, q_res, delta_r2=round(delta_r2, 4))]
    table = _binned(d[x], d[ctx.target], int(params.get("bins", 10)))
    chart = charts.binned_line(table, x, ctx.target, f"{ctx.target} across {x} deciles", ctx.chart("shape"))
    flags = []
    nonlinear = p < ctx.alpha and delta_r2 >= .01
    if nonlinear:
        peak = float(d[x].mean() - quad.params[1] / (2 * coef) * d[x].std())
        inside = d[x].min() < peak < d[x].max()
        flags.append(f"NONLINEAR: curvature adds {delta_r2:.1%} R^2 (p={p:.2g})"
                     + (f"; turning point near {x}={peak:.3g}" if inside else ""))
        if abs(spearman["estimate"] or 0) < .1:
            flags.append("a near-zero correlation here hides a real curved relationship")
    return {"summary": f"Spearman r={spearman['estimate']}, mutual info={mi:.3f}, quadratic dR2={delta_r2:.3f} (p={p:.3g})",
            "findings": findings, "tables": {"binned": table}, "charts": [chart], "flags": flags,
            "mutual_information": round(mi, 4), "pearson_r": spearman.get("pearson_r"), "nonlinear": nonlinear}


def time_trend(ctx: Ctx, params: dict) -> dict:
    _numeric_target(ctx)
    date = ctx.scope["date_column"]
    freq = params.get("freq", "M")
    d = ctx.df.dropna(subset=[date]).copy()
    d["period"] = d[date].dt.to_period(freq).dt.to_timestamp()
    agg = d.groupby("period")[ctx.target].agg(["mean", "size"]).reset_index().rename(columns={"size": "n"})
    r, p = st.spearmanr(np.arange(len(agg)), agg["mean"])
    lo, hi = stats.fisher_ci(r, len(agg), ctx.alpha)
    trend = {"metric": "spearman_r_vs_time", "estimate": round(float(r), 4), "ci_low": round(lo, 4), "ci_high": round(hi, 4),
             "p": float(p), "n": len(agg), "direction": "rising" if r > 0 else "falling"}
    findings = [_finding(f"{ctx.target} over time ({freq})", date, ctx.target, trend, unit="periods")]
    charts_out = [charts.line(agg, "period", "mean", f"Mean {ctx.target} per period ({freq})", ctx.chart("trend"))]
    x = params.get("x")
    lag_rows = []
    if x:
        px = d.groupby("period")[x].mean() if ctx.types.get(x) == "numeric" else None
        if px is not None:
            py = agg.set_index("period")["mean"]
            for lag in range(int(params.get("max_lag", 3)) + 1):
                pair = pd.DataFrame({"x": px.shift(lag), "y": py}).dropna()
                if len(pair) >= 4:
                    rl, pl = st.spearmanr(pair["x"], pair["y"])
                    l_lo, l_hi = stats.fisher_ci(rl, len(pair), ctx.alpha)
                    res = {"metric": "spearman_r_period_level", "estimate": round(float(rl), 4), "ci_low": round(l_lo, 4),
                           "ci_high": round(l_hi, 4), "p": float(pl), "n": len(pair), "direction": f"{x} leads by {lag}"}
                    findings.append(_finding(f"{x} (lag {lag}) ~ {ctx.target} per period", x, ctx.target, res, lag=lag))
                    lag_rows.append({"lag": lag, **res})
    flags = []
    if len(agg) < 8:
        flags.append(f"only {len(agg)} periods; a trend over so few points is fragile")
    return {"summary": f"{len(agg)} periods; trend r={trend['estimate']} [{trend['ci_low']}, {trend['ci_high']}]",
            "findings": findings, "tables": {"by_period": agg, "lags": pd.DataFrame(lag_rows)}, "charts": charts_out,
            "flags": flags}


def predictive_feature_importance(ctx: Ctx, params: dict) -> dict:
    from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor
    from sklearn.metrics import accuracy_score, r2_score, roc_auc_score
    from sklearn.model_selection import GroupShuffleSplit, train_test_split

    drivers = params.get("drivers") or ctx.drivers
    ent = ctx.entity if ctx.entity in ctx.df.columns else None
    d = ctx.df[drivers + [ctx.target] + ([ent] if ent else [])].dropna(subset=[ctx.target]).reset_index(drop=True)
    X = stats.design(d, drivers, ctx.types)
    y = d[ctx.target]
    is_class = ctx.target_type != "numeric"
    if ent and d[ent].nunique() >= 4:
        tr, te = next(GroupShuffleSplit(n_splits=1, test_size=.25, random_state=0)
                      .split(X, y, d[ent].astype(str)))
    else:
        tr, te = train_test_split(np.arange(len(d)), test_size=.25, random_state=0,
                                  stratify=y if is_class else None)
    model = (RandomForestClassifier if is_class else RandomForestRegressor)(
        n_estimators=200, max_depth=int(params.get("max_depth", 6)), min_samples_leaf=5, random_state=0, n_jobs=-1)
    model.fit(X.iloc[tr], y.iloc[tr])

    def score(Xm):
        if ctx.target_type == "numeric":
            return r2_score(y.iloc[te], model.predict(Xm))
        if ctx.target_type == "binary":
            return roc_auc_score(y.iloc[te], model.predict_proba(Xm)[:, 1])
        return accuracy_score(y.iloc[te], model.predict(Xm))

    base = score(X.iloc[te])
    rng = np.random.default_rng(0)
    imp = []
    for c in drivers:
        drops = []
        for _ in range(5):
            shuffled = d.iloc[te].copy()
            shuffled[c] = rng.permutation(shuffled[c].to_numpy())
            Xs = stats.design(shuffled, drivers, ctx.types).reindex(columns=X.columns, fill_value=0)
            drops.append(base - score(Xs))
        imp.append({"driver": c, "importance": round(float(np.mean(drops)), 4), "sd": round(float(np.std(drops)), 4)})
    imp = pd.DataFrame(imp).sort_values("importance", ascending=False)
    metric = {"numeric": "R^2", "binary": "AUC", "categorical": "accuracy"}[ctx.target_type]
    charts_out = [charts.ci_bars(imp["driver"].tolist(), imp["importance"].tolist(),
                                 (imp["importance"] - 1.96 * imp["sd"]).tolist(), (imp["importance"] + 1.96 * imp["sd"]).tolist(),
                                 f"Permutation importance (drop in holdout {metric})", f"drop in {metric}", ctx.chart("importance"))]
    findings, coef_rows = [], []
    if ctx.target_type != "categorical":
        Xz = X.copy()
        num = [c for c in drivers if ctx.types.get(c) == "numeric"]
        Xz[num] = (Xz[num] - Xz[num].mean()) / Xz[num].std()
        yz = (y - y.mean()) / y.std() if ctx.target_type == "numeric" else y
        rank_ok = np.linalg.matrix_rank(sm.add_constant(Xz.to_numpy(float))) == sm.add_constant(Xz.to_numpy(float)).shape[1]
        fit = None
        if rank_ok:
            ols = sm.OLS(yz.to_numpy(float), sm.add_constant(Xz.to_numpy(float)))
            fit = ols.fit(cov_type="cluster", cov_kwds={"groups": d[ent]}) if ent and d[ent].nunique() >= 4 else ols.fit()
            ci = fit.conf_int(ctx.alpha)
        for i, c in enumerate(Xz.columns, start=1):
            if c not in num or not rank_ok:
                continue
            res = {"metric": "std_coef" if ctx.target_type == "numeric" else "lpm_coef_per_sd",
                   "estimate": round(float(fit.params[i]), 4), "ci_low": round(float(ci[i, 0]), 4),
                   "ci_high": round(float(ci[i, 1]), 4), "p": float(fit.pvalues[i]), "n": int(fit.nobs),
                   "direction": "positive" if fit.params[i] > 0 else "negative"}
            findings.append(_finding(f"{c} ~ {ctx.target} | all drivers together", c, ctx.target, res))
            coef_rows.append(res | {"driver": c})
    flags = []
    if ctx.target_type != "categorical" and not rank_ok:
        flags.append("RANK DEFICIENT: adjusted coefficients suppressed; product attributes may encode the same information")
    if (ctx.target_type == "numeric" and base < .1) or (ctx.target_type == "binary" and base < .6):
        flags.append(f"WEAK MODEL: holdout {metric}={base:.3f}; the drivers explain little of the target")
    top = ", ".join(imp["driver"].head(3))
    return {"summary": f"holdout {metric}={base:.3f}; top drivers by importance: {top}", "findings": findings,
            "tables": {"importance": imp, "coefficients": pd.DataFrame(coef_rows)}, "charts": charts_out, "flags": flags,
            "output_roles": {"importance": "random-forest predictive usefulness",
                             "coefficients": "separate linear model: adjusted associations, not RF directions"},
            "holdout_score": {"metric": metric, "value": round(float(base), 4)},
            "notes": ["importance measures predictive usefulness, not what would happen if a driver were changed",
                      "coefficients are associations holding the other drivers fixed (linear, so curves are missed)"]
                     + ([f"holdout = whole {ent} values not seen in training; coefficients pool all {ent} rows "
                         "(see within-between-regression for within/between)"] if ent else [])}


def multiple_testing_adjustment(ctx: Ctx, params: dict) -> dict:
    rows = []
    for path in sorted((ctx.run_dir / "results").glob("*.json")):
        res = json.loads(path.read_text(encoding="utf-8"))
        if res.get("tool") in ("multiple-testing", "multiple-testing-adjustment"):
            continue
        for f in res.get("findings", []):
            if f.get("p") is not None:
                rows.append({"result": res["label"], "label": f["label"], "metric": f["metric"], "estimate": f["estimate"],
                             "test_id": f.get("test_id") or f"legacy:{res['label']}:{f['label']}",
                                 "p": f["p"], "followup": bool(res.get("followup_reason"))})
    unique = {}
    for r in rows:
        previous = unique.setdefault(r["test_id"], r)
        if not np.isclose(previous["p"], r["p"], rtol=1e-10, atol=1e-14):
            raise ValueError("Identical test IDs have inconsistent p-values; rerun the affected analyses")
    qs = dict(zip(unique, stats.bh_qvalues([r["p"] for r in unique.values()])))
    for r in rows:
        r["q"] = qs[r["test_id"]]
        r["significant_after_fdr"] = r["q"] < ctx.alpha
    n_sig = sum(q < ctx.alpha for q in qs.values())
    return {"summary": f"{len(unique)} unique tests in the family ({len(rows)} result references); {n_sig} pass Benjamini-Hochberg FDR at {ctx.alpha}",
            "findings": [], "q_values": rows, "n_unique_tests": len(unique), "tables": {"q_values": pd.DataFrame(rows)}, "charts": []}


def pair_deep_dive(ctx: Ctx, params: dict) -> dict:
    if _xtype(ctx, params["x"]) == "numeric":
        return target_by_numeric_bins(ctx, params)
    return target_by_group(ctx, {"by": params["x"], **{k: v for k, v in params.items() if k not in ("x", "bins")}})

target_associations = feature_target_associations

segment_breakdown = target_by_group

segment_correlation = correlation_by_group

partial_correlation = adjusted_correlation

driver_importance = predictive_feature_importance

multiple_testing = multiple_testing_adjustment
