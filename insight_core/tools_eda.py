"""EDA, data-quality, and preparation tools (phases: eda, prepare)."""

from __future__ import annotations

import re

import numpy as np
import pandas as pd

from . import charts, data, stats
from .context import Ctx


def target_series(df: pd.DataFrame, scope: dict) -> pd.Series:
    t = scope["target"]
    s = df[t["column"]]
    if t["type"] == "binary":
        return data.encode_binary(s, t["positive_class"])
    if t["type"] == "numeric":
        return pd.to_numeric(s, errors="coerce")
    return s.astype("string")


def leakage_suspects(df: pd.DataFrame, scope: dict, types: dict[str, str], threshold: float = .85) -> list[dict]:
    """Columns so close to the target that they are probably derived from it."""
    tcol = scope["target"]["column"]
    y = target_series(df, scope)
    y_type = "numeric" if scope["target"]["type"] in ("numeric", "binary") else "categorical"
    tokens = [t for t in re.split(r"[_\W]+", tcol.lower()) if len(t) > 3]
    rebuilt = _reconstructs_target(df, y, tcol, types) if scope["target"]["type"] == "numeric" else {}
    out = []
    for c, t in types.items():
        if c == tcol or t not in ("numeric", "binary", "categorical"):
            continue
        # Screening uses only the point estimate. Report-grade intervals are
        # calculated later for relationships selected by the approved plan.
        res = stats.associate_point(df[c], y, "numeric" if t == "numeric" else "categorical", y_type)
        est = abs(res["estimate"] or 0)
        name_hit = any(tok in c.lower() for tok in tokens)
        why = []
        if est >= threshold:
            why.append(f"|{res['metric']}| = {est:.2f} with the target")
        if name_hit and (est >= .3 or c in rebuilt):
            why.append("name overlaps the target")
        partner_hit = c in rebuilt and any(tok in rebuilt[c].lower() for tok in tokens)
        if c in rebuilt and (name_hit or not partner_hit):
            why.append(f"the target is almost exactly a product/ratio of {c} and {rebuilt[c]}")
        if why:
            out.append({"column": c, "reason": "; ".join(why), "blocking": bool(name_hit or c in rebuilt)})
    return out


def _reconstructs_target(df: pd.DataFrame, y: pd.Series, tcol: str, types: dict[str, str]) -> dict[str, str]:
    """Columns c for which log(target) ~ log(c) + log(other) fits with R^2 > 0.99."""
    num = [c for c, t in types.items() if t == "numeric" and c != tcol][:30]
    d = pd.concat([y.rename("__y"), df[num]], axis=1).dropna()
    d = d[(d > 0).all(axis=1)]
    if len(d) < 30:
        return {}
    logs = np.log(d)
    ly = logs["__y"].to_numpy()
    ss = ((ly - ly.mean()) ** 2).sum()
    hits = {}
    for i, a in enumerate(num):
        for b in num[i + 1:]:
            X = np.column_stack([np.ones(len(d)), logs[a], logs[b]])
            resid = ly - X @ np.linalg.lstsq(X, ly, rcond=None)[0]
            if ss > 0 and 1 - (resid ** 2).sum() / ss > .99:
                hits.setdefault(a, b)
                hits.setdefault(b, a)
    return hits


def profile_dataset(df: pd.DataFrame, run_dir, label: str = "profile") -> dict:
    prof = data.profile(df)
    numeric = [c["name"] for c in prof["columns"] if c["type"] == "numeric"]
    prof["charts"] = [
        charts.histograms(df, numeric, "Numeric columns", run_dir / "charts" / f"{label}__histograms.png"),
        charts.missingness({c["name"]: c["missing_pct"] for c in prof["columns"]},
                           run_dir / "charts" / f"{label}__missingness.png"),
    ]
    flags = []
    if prof["duplicate_rows"]:
        flags.append(f"{prof['duplicate_rows']} exact duplicate rows")
    for c in prof["columns"]:
        if c["missing_pct"] >= 10:
            flags.append(f"{c['name']}: {c['missing_pct']}% missing")
        if c["type"] == "constant":
            flags.append(f"{c['name']}: constant, carries no information")
        if c.get("summary", {}).get("outliers_3iqr"):
            flags.append(f"{c['name']}: {c['summary']['outliers_3iqr']} extreme values (beyond 3 IQR)")
    for p in prof["panel_candidates"][:2]:
        flags.append(f"panel: {p['column']} repeats across {p['date_column']} ({p['n_entities']} entities, median "
                     f"{p['median_periods']} periods); within- and between-entity patterns can differ")
    prof["flags"] = flags
    return prof


def data_quality_check(ctx: Ctx, params: dict, precomputed_leakage: list[dict] | None = None) -> dict:
    df, scope = ctx.df, ctx.scope
    y = target_series(df, scope)
    checks = []

    def add(name, status, detail):
        checks.append({"check": name, "status": status, "detail": detail})

    dup = int(df.duplicated().sum())
    add("duplicate rows", "warn" if dup else "pass", f"{dup} exact duplicates (prep will drop them)")
    key_col = scope.get("entity_column") or scope.get("id_column")
    if key_col and scope.get("date_column"):
        key_dup = int(df.duplicated([key_col, scope["date_column"]]).sum())
        add("unit-of-analysis key", "warn" if key_dup else "pass",
            f"{key_dup} repeated ({key_col}, {scope['date_column']}) pairs; expected one row per {scope['unit_of_analysis']}")
    if scope.get("entity_column"):
        per = df.groupby(scope["entity_column"]).size()
        add("panel shape", "warn" if per.median() < 4 else "pass",
            f"{len(per)} {scope['entity_column']} values; rows per entity median {per.median():.0f} "
            f"(min {per.min()}, max {per.max()})")
    miss_t = float(y.isna().mean() * 100)
    add("target missing", "fail" if miss_t > 50 else "warn" if miss_t > 5 else "pass", f"{miss_t:.1f}% of rows lack the target")
    n_valid = int(y.notna().sum())
    add("sample size", "fail" if n_valid < ctx.min_n else "pass", f"{n_valid} rows with a target (min_n {ctx.min_n})")
    if ctx.target_type == "binary":
        rate = float(y.mean())
        minority = int(min(y.sum(), n_valid - y.sum()))
        add("target balance", "warn" if min(rate, 1 - rate) < .05 else "pass",
            f"positive rate {rate:.1%}; minority class n = {minority}")
    elif ctx.target_type == "categorical":
        counts = y.value_counts()
        add("target balance", "warn" if counts.min() < ctx.min_n else "pass", f"smallest class n = {int(counts.min())}")
    else:
        s = data._numeric_summary(y)
        add("target distribution", "warn" if abs(s["skew"]) > 2 or s["outliers_3iqr"] else "pass",
            f"skew {s['skew']}, {s['outliers_3iqr']} extreme values")

    for c in ctx.drivers:
        miss = float(df[c].isna().mean() * 100)
        if miss > 0:
            add(f"missing: {c}", "warn" if miss > 5 else "pass", f"{miss:.1f}% missing")
        if ctx.types[c] == "numeric":
            out = data._numeric_summary(df[c]).get("outliers_3iqr", 0)
            if out:
                add(f"outliers: {c}", "warn", f"{out} values beyond 3 IQR; Spearman and binned views are robust to them")
        if ctx.types[c] == "categorical" and df[c].nunique() > 15:
            add(f"cardinality: {c}", "warn", f"{df[c].nunique()} levels; rare levels will be grouped as 'Other'")
    leaks = precomputed_leakage if precomputed_leakage is not None else leakage_suspects(df, scope, ctx.types)
    for lk in leaks:
        used = lk["column"] in ctx.drivers and lk.get("blocking", True) and not scope.get("leakage_justifications", {}).get(lk["column"])
        add(f"leakage: {lk['column']}", "fail" if used else "pass",
            lk["reason"] + ("; still used as a driver" if used else "; excluded, justified, or association-only warning"))
    if scope.get("date_column"):
        d = pd.to_datetime(df[scope["date_column"]], errors="coerce")
        add("date parse", "warn" if d.isna().mean() > .01 else "pass",
            f"{d.isna().mean():.1%} unparseable; range {d.min().date()} to {d.max().date()}")

    summary = {s: sum(c["status"] == s for c in checks) for s in ("pass", "warn", "fail")}
    return {"summary": f"{summary['pass']} pass, {summary['warn']} warn, {summary['fail']} fail",
            "checks": checks, "counts": summary, "leakage_suspects": leaks, "findings": [], "charts": []}


def eda_overview(ctx: Ctx, params: dict) -> dict:
    df = ctx.df
    y = target_series(df, ctx.scope)
    out_charts, notes = [], []
    if ctx.target_type == "numeric":
        out_charts.append(charts.histograms(pd.DataFrame({ctx.target: y}), [ctx.target], "Target distribution",
                                            ctx.chart("target")))
        s = data._numeric_summary(y)
        notes.append(f"target mean {s['mean']}, median {s['median']}, sd {s['std']}")
    else:
        counts = y.value_counts(normalize=True)
        notes.append("target shares: " + ", ".join(f"{k}={v:.1%}" for k, v in counts.items()))
    seg_tables = {}
    yy = y if ctx.target_type != "categorical" else None
    for seg in ctx.scope.get("segments", [])[:6]:
        if yy is None:
            break
        g = pd.DataFrame({"seg": df[seg].astype(str), "y": yy}).dropna().groupby("seg")["y"]
        t = g.agg(["mean", "count", "std"]).reset_index().rename(columns={"seg": seg, "count": "n"})
        half = 1.96 * t["std"] / np.sqrt(t["n"])
        t["ci_low"], t["ci_high"] = t["mean"] - half, t["mean"] + half
        seg_tables[seg] = t
        out_charts.append(charts.group_bars(t, seg, f"{ctx.target} by {seg}", f"mean {ctx.target}", ctx.chart(f"by_{seg}")))
    return {"summary": "; ".join(notes), "notes": notes, "tables": seg_tables, "findings": [], "charts": out_charts}


def prepare_dataset(ctx: Ctx, params: dict) -> dict:
    df, scope = ctx.df.copy(), ctx.scope
    rare_share = float(params.get("rare_level_share", .01))
    log = []
    n0 = len(df)
    df = df.drop_duplicates()
    log.append(f"dropped {n0 - len(df)} exact duplicate rows")
    df[ctx.target] = target_series(df, scope)
    before = len(df)
    df = df[df[ctx.target].notna()]
    log.append(f"dropped {before - len(df)} rows without a target")
    if ctx.target_type == "binary":
        log.append(f"target coded 1 = '{scope['target']['positive_class']}', 0 = other")
    # Preserve the clean base. Model exclusions are not data deletion rules.
    date = scope.get("date_column")
    if date:
        df[date] = pd.to_datetime(df[date], errors="coerce")
    types = dict(ctx.types)
    types[ctx.target] = ctx.target_type
    log.append("preserved all columns and original categories; model exclusions apply only to predictors")
    if rare_share != .01:
        log.append("rare_level_share ignored: category pooling belongs in an explicit model view")
    path = ctx.run_dir / "datasets" / "prepared.parquet"
    df.to_parquet(path, index=False)
    return {"summary": f"{len(df)} rows x {df.shape[1]} columns ready", "n_rows": int(len(df)), "columns": types,
            "date_column": date, "id_column": scope.get("id_column"), "entity_column": scope.get("entity_column"),
            "log": log, "path": str(path),
            "findings": [], "charts": []}
