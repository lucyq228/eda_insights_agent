"""Load any tabular file and describe it with aggregates only (no raw rows)."""

from __future__ import annotations

import re
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

MAX_LEVELS_SHOWN = 30
ID_HINT = re.compile(r"(^id$|_id$|^id_|uuid|guid|key$|number$|^name$|email|phone)", re.I)
DATE_HINT = re.compile(r"(date|time|week|month|day|period|_at$|timestamp)", re.I)


def load_table(path: str | Path) -> pd.DataFrame:
    path = Path(path)
    suffix = path.suffix.lower()
    if suffix == ".csv":
        return pd.read_csv(path)
    if suffix in (".tsv", ".txt"):
        return pd.read_csv(path, sep="\t")
    if suffix in (".xlsx", ".xls"):
        return pd.read_excel(path)
    if suffix == ".parquet":
        return pd.read_parquet(path)
    from .paths import refuse

    refuse(f"unsupported file type: {suffix} (use csv, tsv, xlsx, or parquet)")


def _as_datetime(s: pd.Series) -> pd.Series | None:
    if pd.api.types.is_datetime64_any_dtype(s):
        return s
    if s.dtype != object and not pd.api.types.is_string_dtype(s):
        return None
    sample = s.dropna().astype(str).head(200)
    if sample.empty or not sample.str.contains(r"\d{4}|\d{1,2}[/-]\d{1,2}", regex=True).mean() > .9:
        return None
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        parsed = pd.to_datetime(s, errors="coerce")
    return parsed if parsed.notna().sum() >= .9 * s.notna().sum() else None


def infer_type(s: pd.Series, name: str = "") -> str:
    """numeric | binary | categorical | datetime | id | text | constant"""
    non_null = s.dropna()
    n_unique = non_null.nunique()
    if n_unique <= 1:
        return "constant"
    if n_unique == 2:
        return "binary"
    if _as_datetime(s) is not None:
        return "datetime"
    if pd.api.types.is_numeric_dtype(s):
        if ID_HINT.search(name) and n_unique > .9 * len(non_null):
            return "id"
        return "numeric"
    if n_unique > .9 * len(non_null) and len(non_null) > 50:
        return "id" if ID_HINT.search(name) or non_null.astype(str).str.len().mean() < 40 else "text"
    if ID_HINT.search(name) and n_unique > 50:
        return "id"
    if non_null.astype(str).str.len().mean() > 60:
        return "text"
    return "categorical"


def column_types(df: pd.DataFrame) -> dict[str, str]:
    return {c: infer_type(df[c], c) for c in df.columns}


def _numeric_summary(s: pd.Series) -> dict:
    s = pd.to_numeric(s, errors="coerce").dropna()
    q = s.quantile([0, .25, .5, .75, 1]).tolist()
    iqr = q[3] - q[1]
    outliers = int(((s < q[1] - 3 * iqr) | (s > q[3] + 3 * iqr)).sum()) if iqr > 0 else 0
    return {"mean": round(float(s.mean()), 4), "std": round(float(s.std()), 4), "min": q[0], "p25": q[1],
            "median": q[2], "p75": q[3], "max": q[4], "skew": round(float(s.skew()), 3), "outliers_3iqr": outliers}


def profile(df: pd.DataFrame) -> dict:
    types = column_types(df)
    columns = []
    for c in df.columns:
        s = df[c]
        info = {"name": c, "type": types[c], "dtype": str(s.dtype), "missing_pct": round(float(s.isna().mean() * 100), 2),
                "n_unique": int(s.nunique())}
        if types[c] == "numeric":
            info["summary"] = _numeric_summary(s)
        elif types[c] in ("binary", "categorical") and info["n_unique"] <= MAX_LEVELS_SHOWN:
            counts = s.value_counts()
            info["levels"] = [{"level": str(k), "count": int(v)} for k, v in counts.items()]
        elif types[c] == "datetime":
            d = _as_datetime(s)
            info["range"] = [str(d.min().date()), str(d.max().date())]
            info["distinct_dates"] = int(d.nunique())
        columns.append(info)
    return {"n_rows": int(len(df)), "n_columns": int(df.shape[1]), "duplicate_rows": int(df.duplicated().sum()),
            "columns": columns, "target_candidates": target_candidates(df, types),
            "id_columns": [c for c, t in types.items() if t == "id"],
            "date_columns": [c for c, t in types.items() if t == "datetime"],
            "segment_candidates": [c for c, t in types.items() if t in ("categorical", "binary")
                                   and 2 <= df[c].nunique() <= 15],
            "panel_candidates": panel_candidates(df, types)}


def panel_candidates(df: pd.DataFrame, types: dict[str, str]) -> list[dict]:
    """Columns whose values repeat across dates with about one row per (value, date): stores, markets, customers."""
    dates = [c for c, t in types.items() if t == "datetime"]
    if not dates:
        return []
    date = max(dates, key=lambda c: df[c].nunique())
    d = _as_datetime(df[date])
    out = []
    for c, t in types.items():
        if c == date or t not in ("id", "categorical", "binary", "numeric"):
            continue
        s = df[c]
        if t == "numeric" and not (ID_HINT.search(c) and (s.dropna() % 1 == 0).all()):
            continue
        n_ent = int(s.nunique())
        if n_ent < 2 or n_ent > len(df) / 3:
            continue
        key = pd.DataFrame({"e": s, "d": d}).dropna()
        if key.empty or key.duplicated().mean() > .05:
            continue
        periods = key.groupby("e")["d"].nunique()
        if periods.median() < 3:
            continue
        out.append({"column": c, "date_column": date, "n_entities": n_ent, "median_periods": int(periods.median()),
                    "min_periods": int(periods.min()), "max_periods": int(periods.max()),
                    "balanced_share": round(float((periods == periods.max()).mean()), 3)})
    return sorted(out, key=lambda p: -p["n_entities"])


OUTCOME_HINT = re.compile(r"(sales|revenue|profit|churn|left|attrition|conversion|converted|score|rating|satisf|"
                          r"nps|csat|retention|retained|outcome|target|label|default|price|cost|spend|amount|"
                          r"duration|time_to|success|win|result|y$)", re.I)


def target_candidates(df: pd.DataFrame, types: dict[str, str]) -> list[dict]:
    """Columns that look like outcomes; the user still decides."""
    out = []
    for c, t in types.items():
        if t not in ("numeric", "binary", "categorical"):
            continue
        reasons = []
        if OUTCOME_HINT.search(c):
            reasons.append("name looks like an outcome")
        if c == df.columns[-1]:
            reasons.append("last column")
        if t == "binary":
            reasons.append("binary (yes/no style outcome)")
        if reasons:
            out.append({"column": c, "type": t, "reasons": reasons})
    return sorted(out, key=lambda r: -len(r["reasons"]))[:8]


def encode_binary(s: pd.Series, positive_class) -> pd.Series:
    if pd.api.types.is_numeric_dtype(s) and set(s.dropna().unique()) <= {0, 1}:
        return s.astype(float)
    return s.map(lambda v: np.nan if pd.isna(v) else float(str(v) == str(positive_class)))
