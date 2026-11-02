"""Descriptive business evidence with explicit denominators; no causal estimates."""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import charts


def finding(label, metric, value, n, **details):
    return {"label": label, "metric": metric, "estimate": None if pd.isna(value) else float(value),
            "n": int(n), "p": None, "ci_low": None, "ci_high": None,
            "evidence_type": "descriptive", "direction": "observed", **details}


def _roles(ctx):
    roles = ctx.scope.get("roles", {})
    return roles.get("customer"), roles.get("transaction", []), roles.get("quantity")


def _metrics(df, target, customer, txn, qty):
    out = {"sales": df[target].sum(min_count=1), "lines": len(df)}
    if customer:
        out["customers"] = df[customer].nunique()
        out["sales_per_customer"] = out["sales"] / out["customers"] if out["customers"] else np.nan
    if txn:
        keys = [txn] if isinstance(txn, str) else txn
        out["transactions"] = len(df[keys].drop_duplicates())
        out["sales_per_transaction"] = out["sales"] / out["transactions"] if out["transactions"] else np.nan
        if customer:
            out["transactions_per_customer"] = out["transactions"] / out["customers"] if out["customers"] else np.nan
    if qty:
        out["units"] = df[qty].sum(min_count=1)
        out["price_per_unit"] = out["sales"] / out["units"] if out["units"] else np.nan
        out["single_unit_line_share"] = (df[qty] == 1).mean()
        if txn:
            out["units_per_transaction"] = out["units"] / out["transactions"] if out["transactions"] else np.nan
    return out


def business_summary(ctx, params):
    """All categories and requested intersections; total = reach x frequency x quantity x price."""
    dimensions = params.get("dimensions", [])
    customer, txn, qty = _roles(ctx)
    required = [ctx.target] + ([customer] if customer else []) + ([qty] if qty else [])
    required += ([txn] if isinstance(txn, str) else txn)
    d = ctx.df.dropna(subset=list(dict.fromkeys(required)))
    groups = d.groupby(dimensions, dropna=False, observed=True) if dimensions else [("All", d)]
    rows, findings = [], []
    total = d[ctx.target].sum()
    for key, g in groups:
        key = key if isinstance(key, tuple) else (key,)
        names = dict(zip(dimensions, key)) if dimensions else {"group": "All"}
        metrics = _metrics(g, ctx.target, customer, txn, qty)
        metrics["sales_share"] = metrics["sales"] / total if total else np.nan
        rows.append({**names, **metrics})
        label = "; ".join(f"{k}={v}" for k, v in names.items())
        for metric, value in metrics.items():
            findings.append(finding(f"{label}: {metric}", metric, value, len(g), group=names,
                                    denominator="observed purchases in the dataset"))
    table = pd.DataFrame(rows).sort_values("sales", ascending=False)
    return {"summary": f"{len(table)} groups; sales decomposed across observed customers, transactions, units and price",
            "findings": findings, "tables": {"business_metrics": table}, "charts": [],
            "flags": [f"excluded {len(ctx.df)-len(d)} rows missing required metric keys/components"] if len(d) < len(ctx.df) else [],
            "notes": ["Descriptive accounting, not causal contribution or expected intervention lift.",
                      "Customers and transactions may overlap across product groups; distinct counts are not additive.",
                      "Customer frequency uses the observed dataset window, not individual tenure or all shopping visits.",
                      "Average unit price includes product mix; it is not a price elasticity."]}


def temporal_diagnostics(ctx, params):
    date = ctx.scope["date_column"]
    freq = params.get("freq", "M")
    customer, txn, qty = _roles(ctx)
    required = [date, ctx.target] + ([customer] if customer else []) + ([qty] if qty else [])
    required += [txn] if isinstance(txn, str) else txn
    d = ctx.df.dropna(subset=list(dict.fromkeys(required))).copy()
    d["__period"] = d[date].dt.to_period(freq)
    rows = []
    if d.empty:
        raise ValueError("no usable dated observations")
    groups = {p:g for p,g in d.groupby("__period", observed=True)}
    for period in pd.period_range(d["__period"].min(), d["__period"].max(), freq=freq):
        g = groups.get(period, d.iloc[:0])
        start, end = period.start_time, period.end_time.normalize()
        observed_start = max(start, d[date].min().normalize())
        observed_end = min(end, d[date].max().normalize())
        days = (observed_end - observed_start).days + 1
        rows.append({"period": str(period), "calendar_days_in_window": days,
                     "observed_days": g[date].dt.normalize().nunique(),
                     "partial_boundary": observed_start != start or observed_end != end, "no_observations": g.empty,
                     **_metrics(g, ctx.target, customer, txn, qty)})
    table = pd.DataFrame(rows)
    if table.empty:
        raise ValueError("no usable dated observations")
    table["sales_per_calendar_day"] = table.sales / table.calendar_days_in_window
    table["sales_change_pct"] = table.sales.pct_change(fill_method=None) * 100
    rate = table.sales_per_calendar_day
    med = rate.median()
    mad = (rate - med).abs().median()
    table["robust_deviation"] = (rate-med) / (1.4826*mad) if mad > 0 else np.nan
    table["candidate_anomaly"] = table.robust_deviation.abs() > float(params.get("threshold", 3))
    findings = []
    for row in table.to_dict("records"):
        for metric in ("sales", "sales_per_calendar_day", "transactions", "units_per_transaction", "single_unit_line_share"):
            if metric in row:
                findings.append(finding(f"{row['period']}: {metric}", metric, row[metric], row["lines"],
                                        period=row["period"], partial_boundary=row["partial_boundary"]))
    chart = charts.line(table, "period", "sales_per_calendar_day", "Sales per calendar day in each period", ctx.chart("period_sales"))
    return {"summary": f"{len(table)} periods; {int(table.candidate_anomaly.sum())} descriptive anomaly candidates",
            "findings": findings, "tables": {"period_metrics": table}, "charts": [chart],
            "flags": ["Missing dates are not assumed to be closures or zero demand; verify coverage.",
                      "Anomaly flags use a median/MAD baseline, not a seasonal model or significance test."],
            "notes": ["Boundary periods are marked; calendar normalization does not adjust for open-store exposure.",
                      "One annual cycle cannot establish recurring seasonality."]}


def period_comparison(ctx, params):
    """Two explicit, non-overlapping windows, with exact symmetric accounting decomposition."""
    date = ctx.scope["date_column"]
    windows = []
    for prefix in ("baseline", "comparison"):
        start, end = (pd.Timestamp(params[f"{prefix}_{k}"]) for k in ("start", "end"))
        if start > end:
            raise ValueError("window start must precede end")
        windows.append((start.normalize(), end.normalize()))
    if max(windows[0][0], windows[1][0]) <= min(windows[0][1], windows[1][1]):
        raise ValueError("comparison windows must not overlap")
    customer, txn, qty = _roles(ctx)
    if not (customer and txn and qty):
        raise ValueError("decomposition requires customer, transaction and quantity roles")
    required = [ctx.target, customer, qty] + ([txn] if isinstance(txn, str) else txn)
    rows = []
    for name, (start, end) in zip(("baseline", "comparison"), windows):
        g = ctx.df[ctx.df[date].between(start, end + pd.Timedelta(days=1), inclusive="left")].dropna(subset=required)
        if g.empty:
            raise ValueError(f"empty {name} window")
        rows.append({"window": name, "calendar_days": (end-start).days+1, **_metrics(g, ctx.target, customer, txn, qty)})
    factors = ["customers", "transactions_per_customer", "units_per_transaction", "price_per_unit"]
    # Shapley allocation over all 4! orderings: exact, order-independent arithmetic.
    from itertools import permutations
    a, b = rows
    if any(not np.isfinite(row[f]) for row in rows for f in factors):
        raise ValueError("undefined decomposition factor (zero denominator or nonfinite metric)")
    contributions = dict.fromkeys(factors, 0.)
    for order in permutations(factors):
        state = {f: a[f] for f in factors}
        for f in order:
            before = np.prod(list(state.values()))
            state[f] = b[f]
            contributions[f] += (np.prod(list(state.values()))-before)/24
    findings = [finding(f"sales difference: {f}", "accounting_contribution", v, a["lines"]+b["lines"], component=f)
                for f, v in contributions.items()]
    findings.append(finding("comparison minus baseline sales", "sales_difference", b["sales"]-a["sales"], a["lines"]+b["lines"]))
    return {"summary": f"Sales difference {b['sales']-a['sales']:.2f}; decomposed into four accounting components",
            "findings": findings, "tables": {"windows": pd.DataFrame(rows),
            "contributions": pd.DataFrame([{"component": f, "contribution": v} for f, v in contributions.items()])},
            "charts": [], "flags": ["Unequal calendar windows; totals include exposure differences"] if a["calendar_days"] != b["calendar_days"] else [],
            "notes": ["Exact accounting attribution, not causal effects or a forecast of intervention lift."]}


def rate_change_decomposition(ctx, params):
    """Standardize the comparison cohort to baseline group rates on the prepared binary target."""
    cohort, by = params["cohort"], params["by"]
    labels = ctx.df[cohort].astype("string")
    flags = []
    if labels.isna().any():
        flags.append(f"{labels.isna().sum()} prepared rows lack a cohort and cannot be assigned.")
    unit_id = ctx.scope.get("id_column")
    if unit_id:
        keys = ctx.df.loc[labels.isin([params["baseline"], params["comparison"]]), unit_id]
        if keys.isna().any() or keys.duplicated().any():
            raise ValueError("The declared unit ID must be present and unique across the selected cohorts")
    cohorts, groups = [], []
    for role in ("baseline", "comparison"):
        label = params[role]
        selected = ctx.df.loc[labels.eq(label)]
        if selected.empty:
            raise ValueError(f"No eligible rows in {role} cohort {label!r}")
        outcomes = selected[ctx.target]
        if not outcomes.isin([0, 1]).all():
            raise ValueError("Expected one observed binary outcome per eligible unit")
        counts = selected.groupby(by, dropna=False, observed=True)[ctx.target].agg(["size", "sum"])
        counts.columns = [f"{role}_n", f"{role}_events"]
        groups.append(counts)
        cohorts.append({"role": role, "cohort": label, "n": len(selected),
                        "events": int(outcomes.sum()), "rate": outcomes.mean()})

    table = pd.concat(groups, axis=1).fillna(0).astype(int)
    base, comp = cohorts
    for row in cohorts:
        role = row["role"]
        n = table[f"{role}_n"]
        table[f"{role}_share"] = n / row["n"]
        table[f"{role}_rate"] = table[f"{role}_events"] / n.where(n > 0)
        if ((n > 0) & (n < ctx.min_n)).any():
            flags.append(f"Small {role} groups retained for reconciliation; interpret their rates cautiously.")
    table["expected_events"] = (table.comparison_n * table.baseline_rate).where(table.comparison_n > 0, 0)
    table["within_pp"] = 100 * (table.comparison_events - table.expected_events) / comp["n"]
    table["mix_pp"] = 100 * (table.comparison_share - table.baseline_share) * table.baseline_rate
    delta = 100 * (comp["rate"] - base["rate"])
    n = base["n"] + comp["n"]
    findings = [finding("Observed rate change (pp)", "rate_change_pp", delta, n)]
    if table.expected_events.isna().any():
        flags.append("A comparison group has no baseline rate. Full attribution is undefined.")
    else:
        benchmark = table.expected_events.sum() / comp["n"]
        mix, within = table.mix_pp.sum(), table.within_pp.sum()
        if not np.isclose(mix + within, delta, rtol=0, atol=1e-10):
            raise ValueError("Group contributions do not reconcile to the observed change")
        findings.extend([finding("Comparison rate at baseline group rates", "benchmark_rate", benchmark, comp["n"]),
                         finding("Mix contribution (pp)", "mix_pp", mix, n),
                         finding("Within-group contribution (pp)", "within_pp", within, n)])
    return {"summary": f"Rate change {delta:+.2f} pp, grouped by {by} using baseline reference rates",
            "findings": findings, "tables": {"cohorts": pd.DataFrame(cohorts),
            "groups": table.rename_axis("group").reset_index()}, "flags": flags, "charts": [],
            "notes": ["Rates and shares are fractions. Contributions are percentage points.",
                      "Descriptive attribution uses one eligible prepared row per unit."]}
