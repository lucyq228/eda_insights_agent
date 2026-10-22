"""Generate two demo datasets with planted patterns.

data/store_weekly_sales.csv   one row = one store-week; numeric target (weekly_sales)
data/employee_attrition.csv   one row = one employee; binary target (left_company)

The planted truth goes to synthetic/ground_truth.json, which agents must never
read: it is how the tests check that the agents find what is really there.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
rng = np.random.default_rng(42)


def store_sales() -> pd.DataFrame:
    regions = {"North": (0, 1.0), "South": (-15, 1.4), "East": (12, 0.8), "West": (-30, 2.4)}
    formats = ["Mall", "Street", "Outlet"]
    stores = []
    for i in range(80):
        region = rng.choice(list(regions), p=[.28, .26, .26, .20])
        stores.append({"store_id": f"S{i + 1:03d}", "region": region, "store_format": rng.choice(formats, p=[.4, .4, .2]),
                       "competitor_nearby": rng.choice(["Yes", "No"], p=[.45, .55]), "base": rng.normal(0, 6)})
    rows = []
    weeks = pd.date_range("2025-01-06", periods=26, freq="W-MON")
    for s in stores:
        shift, promo_level = regions[s["region"]]
        for w, week in enumerate(weeks):
            traffic = max(200, rng.normal(1500 + 40 * s["base"], 250))
            staff = max(40, rng.normal(120, 20))
            promo = max(0, rng.normal(2.0 * promo_level, 0.8))
            price = rng.uniform(8, 16)
            stockout = float(np.clip(rng.beta(2, 25), 0, .5))
            rating = float(np.clip(rng.normal(4.0, .4), 1, 5))
            temp = rng.normal(15, 8)
            staff_effect = .5 if s["store_format"] == "Mall" else .05
            sales = (60 + shift + s["base"] + .06 * traffic + staff_effect * (staff - 120) + 6.0 * promo
                     - 1.6 * (price - 12) ** 2 - 120 * stockout + 1.5 * (rating - 4)
                     - (4 if s["competitor_nearby"] == "Yes" else 0) + 4 * np.sin(w / 26 * 2 * np.pi)
                     + rng.normal(0, 5))
            rows.append({"store_id": s["store_id"], "week_start": week.date().isoformat(), "region": s["region"],
                         "store_format": s["store_format"], "competitor_nearby": s["competitor_nearby"],
                         "foot_traffic": round(traffic), "staff_hours": round(staff, 1), "promo_spend_k": round(promo, 2),
                         "avg_price": round(price, 2), "stockout_rate": round(stockout, 4),
                         "customer_rating": round(rating, 2), "avg_temp_c": round(temp, 1),
                         "weekly_sales_k": round(sales, 2)})
    df = pd.DataFrame(rows)
    df["sales_per_visitor"] = (df["weekly_sales_k"] * 1000 / df["foot_traffic"]).round(3)
    miss = rng.random(len(df)) < .12
    df.loc[miss, "customer_rating"] = np.nan
    out = rng.choice(len(df), 6, replace=False)
    df.loc[out, "promo_spend_k"] = df.loc[out, "promo_spend_k"] * 12
    return pd.concat([df, df.sample(8, random_state=1)], ignore_index=True)


def attrition() -> pd.DataFrame:
    n = 1600
    dept = rng.choice(["Sales", "Engineering", "Support", "Operations", "Finance"], n, p=[.25, .25, .2, .2, .1])
    tenure = rng.gamma(2.2, 2.0, n).round(1)
    engagement = np.clip(rng.normal(68, 12, n), 20, 100).round()
    overtime = np.clip(rng.gamma(2, 4, n) + np.where(dept == "Support", 6, 0), 0, 60).round(1)
    commute = np.clip(rng.gamma(2, 9, n), 1, 120).round(1)
    salary_band = rng.choice(["B1", "B2", "B3", "B4"], n, p=[.3, .35, .25, .1])
    remote = rng.choice(["Yes", "No"], n, p=[.4, .6])
    manager_rating = np.clip(rng.normal(3.7, .7, n), 1, 5).round(1)
    promoted = rng.choice(["Yes", "No"], n, p=[.2, .8])
    logit = (-1.2 - .05 * (engagement - 68) + .06 * (overtime - 8) + 1.1 * np.exp(-tenure / 1.5)
             - .5 * (promoted == "Yes") + .004 * (commute - 18) - .25 * (salary_band == "B4") + rng.normal(0, .3, n))
    left = rng.random(n) < 1 / (1 + np.exp(-logit))
    df = pd.DataFrame({"employee_id": [f"E{i:05d}" for i in range(n)], "department": dept, "tenure_years": tenure,
                       "salary_band": salary_band, "engagement_score": engagement, "overtime_hours_month": overtime,
                       "commute_km": commute, "remote": remote, "manager_rating": manager_rating,
                       "promoted_last_2y": promoted, "exit_interview_done": np.where(left & (rng.random(n) < .9), "Yes", "No"),
                       "left_company": np.where(left, "Yes", "No")})
    df.loc[rng.random(n) < .08, "manager_rating"] = np.nan
    return df


TRUTH = {
    "store_weekly_sales.csv": {
        "target": "weekly_sales_k",
        "strong_positive": ["foot_traffic"],
        "negative": ["stockout_rate"],
        "nonlinear_inverted_u": ["avg_price"],
        "simpsons_paradox": {"driver": "promo_spend_k", "by": "region",
                             "note": "positive within every region, near zero or negative pooled"},
        "segment_heterogeneity": {"driver": "staff_hours", "by": "store_format", "stronger_in": "Mall"},
        "null": ["avg_temp_c"],
        "leakage": ["sales_per_visitor"],
        "id": "store_id", "date": "week_start",
        "data_quality": ["8 duplicate rows", "12% missing customer_rating", "6 promo_spend_k outliers x12"],
    },
    "employee_attrition.csv": {
        "target": "left_company (Yes)",
        "protective": ["engagement_score", "promoted_last_2y=Yes"],
        "risk": ["overtime_hours_month"],
        "nonlinear": ["tenure_years (risk concentrated in the first 2 years)"],
        "weak": ["commute_km"], "null": ["remote"],
        "leakage": ["exit_interview_done"], "id": "employee_id",
    },
}


def main() -> None:
    (ROOT / "data").mkdir(exist_ok=True)
    (ROOT / "synthetic").mkdir(exist_ok=True)
    store_sales().to_csv(ROOT / "data" / "store_weekly_sales.csv", index=False)
    attrition().to_csv(ROOT / "data" / "employee_attrition.csv", index=False)
    (ROOT / "synthetic" / "ground_truth.json").write_text(json.dumps(TRUTH, indent=2), encoding="utf-8")
    print("wrote data/store_weekly_sales.csv, data/employee_attrition.csv, synthetic/ground_truth.json")


if __name__ == "__main__":
    main()
