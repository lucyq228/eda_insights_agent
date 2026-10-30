"""Panel tools (phase: analysis) for entities observed repeatedly over time: stores,
restaurants, markets, customers. Each splits an association into a within-entity part
(the same entity in its higher vs lower periods) and a between-entity part (entities
that are higher on average). CIs are clustered by entity.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import statsmodels.api as sm

from . import charts, stats
from .context import Ctx


def _flag(v, default: bool = True) -> bool:
    if v is None:
        return default
    return str(v).strip().lower() not in ("false", "0", "no", "off")


def _groups(ctx: Ctx, d: pd.DataFrame, time_effects: bool) -> tuple[np.ndarray, list[np.ndarray], bool]:
    entity = pd.factorize(d[ctx.entity].astype(str))[0]
    groups = [entity]
    date = ctx.scope.get("date_column")
    use_time = bool(time_effects and date and date in d.columns)
    if use_time:
        groups.append(pd.factorize(pd.to_datetime(d[date], errors="coerce").astype(str))[0])
    return entity, groups, use_time


def _demean(a: np.ndarray, groups: list[np.ndarray]) -> np.ndarray:
    """Remove group means; alternating passes when there are two groupings (entity and period)."""
    v = np.asarray(a, float).copy()
    tol = 1e-9 * (np.std(v) + 1e-12)
    for _ in range(1 if len(groups) == 1 else 100):
        old = v.copy()
        for g in groups:
            v = v - (np.bincount(g, v) / np.bincount(g))[g]
        if np.max(np.abs(v - old)) < tol:
            break
    return v


def _z(a: np.ndarray) -> np.ndarray:
    return (a - a.mean()) / a.std()


def _clustered_r(x: np.ndarray, y: np.ndarray, cluster: np.ndarray, alpha: float) -> dict:
    """Correlation as the slope of standardized y on standardized x, with an entity-clustered CI."""
    if x.std() < 1e-12 or y.std() < 1e-12:
        return {"estimate": None, "ci_low": None, "ci_high": None, "p": None}
    fit = sm.OLS(_z(y), sm.add_constant(_z(x))).fit(cov_type="cluster", cov_kwds={"groups": cluster})
    lo, hi = fit.conf_int(alpha)[1]
    return {"estimate": round(float(fit.params[1]), 4), "ci_low": round(float(max(lo, -1)), 4),
            "ci_high": round(float(min(hi, 1)), 4), "p": float(fit.pvalues[1])}


def _within_share(a: np.ndarray, entity: np.ndarray) -> float:
    total = a.var()
    return float(_demean(a, [entity]).var() / total) if total > 0 else 0.0


def within_between_correlation(ctx: Ctx, params: dict) -> dict:
    if ctx.target_type == "categorical":
        raise ValueError("this tool needs a numeric or binary target")
    x, ent = params["x"], ctx.entity
    date = ctx.scope.get("date_column")
    cols = [x, ctx.target, ent] + ([date] if date and date in ctx.df.columns and date not in (x, ent) else [])
    d = ctx.df[cols].dropna(subset=[x, ctx.target, ent]).reset_index(drop=True)
    entity, groups, use_time = _groups(ctx, d, _flag(params.get("time_effects")))
    n, k = len(d), int(entity.max()) + 1
    rx, ry = d[x].rank().to_numpy(float), d[ctx.target].rank().to_numpy(float)
    within_label = f"within {ent}" + (" and period" if use_time else "")

    pooled = _clustered_r(rx, ry, entity, ctx.alpha)
    naive = stats.associate(d[x], d[ctx.target], "numeric", "numeric", ctx.alpha)
    pooled.update(metric="spearman_r_pooled", n=n, n_entities=k,
                  direction="positive" if (pooled["estimate"] or 0) > 0 else "negative")
    within = _clustered_r(_demean(rx, groups), _demean(ry, groups), entity, ctx.alpha)
    within.update(metric="spearman_r_within_entity", n=n, n_entities=k,
                  direction="positive" if (within["estimate"] or 0) > 0 else "negative")
    means = d.groupby(ent)[[x, ctx.target]].mean()
    between = stats.associate(means[x], means[ctx.target], "numeric", "numeric", ctx.alpha)
    between.update(metric="spearman_r_between_entity", n_entities=k)
    findings = [
        {"label": f"{x} ~ {ctx.target} | pooled, {ent}-clustered CI", "x": x, "y": ctx.target, **pooled},
        {"label": f"{x} ~ {ctx.target} | {within_label}", "x": x, "y": ctx.target, **within},
        {"label": f"{x} ~ {ctx.target} | between {ent} averages", "x": x, "y": ctx.target,
         **{kk: between.get(kk) for kk in ("metric", "estimate", "ci_low", "ci_high", "p", "n", "direction", "n_entities")}},
    ]
    share_x, share_y = _within_share(rx, entity), _within_share(ry, entity)
    periods = d.groupby(ent).size()

    flags = []
    w, b = within["estimate"], between["estimate"]
    if w is not None and b is not None and ((np.sign(w) != np.sign(b) and max(abs(w), abs(b)) >= .1) or abs(w - b) >= .2):
        flags.append(f"PANEL SPLIT: within r={w:.2f} vs between r={b:.2f}; the pooled number mixes two different "
                     f"patterns. Lead with within-{ent} (same {ent} over time) and report between-{ent} separately")
    if share_x < .1:
        flags.append(f"LITTLE WITHIN VARIATION: only {share_x:.0%} of {x}'s variation is within {ent}; "
                     "the within estimate rests on small changes")
    if k < ctx.min_n:
        flags.append(f"FEW ENTITIES: the between estimate rests on {k} {ent} values (min_n {ctx.min_n})")
    if periods.median() < 4:
        flags.append(f"FEW PERIODS: median {periods.median():.0f} rows per {ent}; within estimates are fragile")
    if pooled["ci_low"] is not None and naive.get("ci_low") is not None:
        ratio = (pooled["ci_high"] - pooled["ci_low"]) / max(1e-9, naive["ci_high"] - naive["ci_low"])
        if ratio > 1.5:
            flags.append(f"CLUSTERING: the {ent}-clustered CI is {ratio:.1f}x wider than one that treats rows as independent; "
                         "pooled CIs from other tools are too narrow")

    seg = [f for f in findings if f["estimate"] is not None]
    chart = charts.ci_bars([f["label"].split(" | ")[1] for f in seg], [f["estimate"] for f in seg],
                           [f["ci_low"] for f in seg], [f["ci_high"] for f in seg],
                           f"{x} vs {ctx.target}: pooled, within, between {ent}", "Spearman r (95% CI)", ctx.chart("panel"))
    fmt = lambda v: "n/a" if v is None else f"{v:.3f}"  # noqa: E731
    return {"summary": f"{k} {ent} values, {n} rows: pooled r={fmt(pooled['estimate'])}, within r={fmt(w)}, "
                       f"between r={fmt(b)}",
            "findings": findings, "tables": {"decomposition": pd.DataFrame(findings)}, "charts": [chart], "flags": flags,
            "within_share_x": round(share_x, 4), "within_share_target": round(share_y, 4), "time_effects": use_time,
            "naive_pooled_ci": [naive.get("ci_low"), naive.get("ci_high")],
            "notes": [f"within = same {ent} in its higher vs lower periods"
                      + ("; period-wide swings shared by all entities removed" if use_time else ""),
                      f"between = {ent} averages compared with each other (n = {k} entities)",
                      "Spearman-type: x and the target are ranked first, so outliers have little pull"]}


def within_between_regression(ctx: Ctx, params: dict) -> dict:
    from sklearn.model_selection import GroupShuffleSplit

    if ctx.target_type == "categorical":
        raise ValueError("this tool needs a numeric or binary target")
    ent = ctx.entity
    drivers = [c for c in (params.get("drivers") or ctx.drivers) if ctx.types.get(c) == "numeric" and c != ent]
    skipped = [c for c in (params.get("drivers") or ctx.drivers) if c not in drivers and c != ent]
    date = ctx.scope.get("date_column")
    cols = [ctx.target, ent] + drivers + ([date] if date and date in ctx.df.columns else [])
    d = ctx.df[list(dict.fromkeys(cols))].dropna(subset=[ctx.target, ent]).reset_index(drop=True)
    for c in drivers:
        d[c] = pd.to_numeric(d[c], errors="coerce")
        d[c] = d[c].fillna(d[c].median())
    entity, groups, use_time = _groups(ctx, d, _flag(params.get("time_effects")))
    n, k = len(d), int(entity.max()) + 1

    y_w = _demean(d[ctx.target].to_numpy(float), groups)
    X_w = {c: _demean(d[c].to_numpy(float), groups) for c in drivers}
    invariant = [c for c in drivers if X_w[c].std() < 1e-9 * (d[c].std() + 1e-12) or _within_share(d[c].to_numpy(float), entity) < .01]
    kept = [c for c in drivers if c not in invariant]
    if not kept:
        raise ValueError(f"no numeric driver varies within {ent}")
    Xz = np.column_stack([_z(X_w[c]) for c in kept])
    yz = _z(y_w)
    fit = sm.OLS(yz, sm.add_constant(Xz)).fit(cov_type="cluster", cov_kwds={"groups": entity})
    ci = fit.conf_int(ctx.alpha)
    findings, rows = [], []
    within_label = f"within {ent}" + (" and period" if use_time else "")
    for i, c in enumerate(kept, start=1):
        res = {"metric": "within_std_coef", "estimate": round(float(fit.params[i]), 4), "ci_low": round(float(ci[i, 0]), 4),
               "ci_high": round(float(ci[i, 1]), 4), "p": float(fit.pvalues[i]), "n": n, "n_entities": k,
               "direction": "positive" if fit.params[i] > 0 else "negative"}
        findings.append({"label": f"{c} ~ {ctx.target} | {within_label}, all drivers together", "x": c, "y": ctx.target, **res})
        rows.append({"driver": c, "part": "within", **res})

    split = GroupShuffleSplit(n_splits=1, test_size=.25, random_state=0)
    tr, te = next(split.split(Xz, yz, entity)) if k >= 4 else (np.arange(n), np.arange(n))
    beta = np.linalg.lstsq(sm.add_constant(Xz[tr]), yz[tr], rcond=None)[0]
    pred = sm.add_constant(Xz[te], has_constant="add") @ beta
    holdout_r2 = float(1 - ((yz[te] - pred) ** 2).sum() / max(1e-12, ((yz[te] - yz[te].mean()) ** 2).sum()))

    between_note = None
    means = d.groupby(ent)[[ctx.target] + drivers].mean()
    bcols = [c for c in drivers if means[c].std() > 0]
    if bcols and k >= len(bcols) + 10:
        bfit = sm.OLS(_z(means[ctx.target].to_numpy(float)),
                      sm.add_constant(np.column_stack([_z(means[c].to_numpy(float)) for c in bcols]))).fit(cov_type="HC1")
        bci = bfit.conf_int(ctx.alpha)
        for i, c in enumerate(bcols, start=1):
            res = {"metric": "between_std_coef", "estimate": round(float(bfit.params[i]), 4),
                   "ci_low": round(float(bci[i, 0]), 4), "ci_high": round(float(bci[i, 1]), 4), "p": float(bfit.pvalues[i]),
                   "n": k, "n_entities": k, "direction": "positive" if bfit.params[i] > 0 else "negative"}
            findings.append({"label": f"{c} ~ {ctx.target} | between {ent} averages, all drivers together",
                             "x": c, "y": ctx.target, **res})
            rows.append({"driver": c, "part": "between", **res})
    else:
        between_note = f"between-{ent} model skipped: {k} entities is too few for {len(bcols)} drivers"

    flags = []
    if holdout_r2 < .05:
        flags.append(f"WEAK WITHIN MODEL: holdout within-{ent} R^2={holdout_r2:.3f}; the drivers explain little of "
                     f"how each {ent} moves over time")
    by = {}
    for r in rows:
        by.setdefault(r["driver"], {})[r["part"]] = r
    for c, parts in by.items():
        w, b = parts.get("within"), parts.get("between")
        if w and b and np.sign(w["estimate"]) != np.sign(b["estimate"]) and w["ci_low"] * w["ci_high"] > 0 \
                and b["ci_low"] * b["ci_high"] > 0:
            flags.append(f"PANEL SPLIT: {c} is {w['direction']} within {ent} but {b['direction']} between {ent} averages")
    if invariant:
        flags.append(f"TIME-INVARIANT within {ent}: {invariant}; only the between part can be read for them")
    if skipped:
        flags.append(f"non-numeric drivers skipped: {skipped}; if they are fixed per {ent}, entity effects absorb them "
                     "(use segment tools for them)")

    wf = sorted((f for f in findings if f["metric"] == "within_std_coef"), key=lambda f: -abs(f["estimate"]))
    chart = charts.ci_bars([f["x"] for f in wf], [f["estimate"] for f in wf], [f["ci_low"] for f in wf],
                           [f["ci_high"] for f in wf], f"Within-{ent} standardized coefficients (95% CI, clustered)",
                           "std coef", ctx.chart("within_coefs"))
    top = ", ".join(f["x"] for f in wf[:3])
    return {"summary": f"{k} {ent} values, {n} rows; within holdout R^2={holdout_r2:.3f}; top within: {top}",
            "findings": findings, "tables": {"coefficients": pd.DataFrame(rows)}, "charts": [chart], "flags": flags,
            "holdout_score": {"metric": "within R^2 on held-out entities", "value": round(holdout_r2, 4)},
            "within_r2_in_sample": round(float(fit.rsquared), 4), "time_effects": use_time,
            "notes": [n_ for n_ in [
                f"within = how each {ent} moves over time, holding the other drivers fixed"
                + ("; period-wide swings removed" if use_time else ""),
                f"between = {ent} averages compared with each other (n = {k})",
                "linear on standardized values, so curves are missed; coefficients are associations, not results of changing a driver",
                between_note] if n_]}


panel_decomposition = within_between_correlation
panel_drivers = within_between_regression
