"""Small, consistent matplotlib charts. Every function returns the saved path."""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

BLUE, GREY, RED = "#2F6DB5", "#9AA5B1", "#C0392B"


def _save(fig, path: Path) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(path, dpi=110)
    plt.close(fig)
    return str(path)


def ci_bars(labels, est, lo, hi, title: str, xlabel: str, path: Path) -> str:
    fig, ax = plt.subplots(figsize=(7, max(2.5, .35 * len(labels) + 1)))
    y = np.arange(len(labels))[::-1]
    est = np.array(est, float)
    err = np.array([est - np.array(lo, float), np.array(hi, float) - est])
    colors = [BLUE if e >= 0 else RED for e in est]
    ax.barh(y, est, color=colors, alpha=.8)
    ax.errorbar(est, y, xerr=np.nan_to_num(err), fmt="none", ecolor="black", capsize=3, lw=1)
    ax.axvline(0, color="black", lw=.8)
    ax.set_yticks(y, labels)
    ax.set_title(title)
    ax.set_xlabel(xlabel)
    return _save(fig, path)


def heatmap(matrix: pd.DataFrame, title: str, path: Path) -> str:
    k = len(matrix)
    fig, ax = plt.subplots(figsize=(max(5, .55 * k + 2), max(4, .5 * k + 1.5)))
    im = ax.imshow(matrix.to_numpy(float), cmap="RdBu_r", vmin=-1, vmax=1)
    ax.set_xticks(range(k), matrix.columns, rotation=60, ha="right", fontsize=8)
    ax.set_yticks(range(k), matrix.index, fontsize=8)
    if k <= 14:
        for i in range(k):
            for j in range(k):
                ax.text(j, i, f"{matrix.iat[i, j]:.2f}", ha="center", va="center", fontsize=7)
    fig.colorbar(im, ax=ax, shrink=.8)
    ax.set_title(title)
    return _save(fig, path)


def binned_line(table: pd.DataFrame, x: str, y: str, title: str, path: Path) -> str:
    """table has columns bin_mid, mean, ci_low, ci_high, n."""
    fig, ax = plt.subplots(figsize=(6.5, 4))
    ax.plot(table["bin_mid"], table["mean"], "o-", color=BLUE)
    ax.fill_between(table["bin_mid"], table["ci_low"], table["ci_high"], color=BLUE, alpha=.15)
    ax.set_xlabel(x)
    ax.set_ylabel(f"mean {y}")
    ax.set_title(title)
    return _save(fig, path)


def group_bars(table: pd.DataFrame, label_col: str, title: str, ylabel: str, path: Path) -> str:
    fig, ax = plt.subplots(figsize=(max(5, .6 * len(table) + 2), 4))
    x = np.arange(len(table))
    err = np.array([table["mean"] - table["ci_low"], table["ci_high"] - table["mean"]])
    ax.bar(x, table["mean"], color=BLUE, alpha=.85)
    ax.errorbar(x, table["mean"], yerr=np.nan_to_num(err), fmt="none", ecolor="black", capsize=3)
    ax.set_xticks(x, table[label_col].astype(str), rotation=30, ha="right")
    ax.set_ylabel(ylabel)
    ax.set_title(title)
    return _save(fig, path)


def line(table: pd.DataFrame, x: str, y: str, title: str, path: Path) -> str:
    fig, ax = plt.subplots(figsize=(7, 3.8))
    ax.plot(table[x], table[y], "o-", color=BLUE, ms=3)
    ax.set_title(title)
    ax.set_ylabel(y)
    fig.autofmt_xdate()
    return _save(fig, path)


def histograms(df: pd.DataFrame, cols: list[str], title: str, path: Path) -> str:
    cols = cols[:16]
    k = max(1, len(cols))
    ncol = min(4, k)
    nrow = int(np.ceil(k / ncol))
    fig, axes = plt.subplots(nrow, ncol, figsize=(3.2 * ncol, 2.4 * nrow), squeeze=False)
    for ax, c in zip(axes.flat, cols):
        ax.hist(pd.to_numeric(df[c], errors="coerce").dropna(), bins=30, color=BLUE, alpha=.8)
        ax.set_title(c, fontsize=9)
        ax.tick_params(labelsize=7)
    for ax in list(axes.flat)[k:]:
        ax.axis("off")
    fig.suptitle(title)
    return _save(fig, path)


def missingness(pcts: dict[str, float], path: Path) -> str:
    items = sorted(((k, v) for k, v in pcts.items() if v > 0), key=lambda kv: -kv[1])[:25] or [("(none)", 0)]
    fig, ax = plt.subplots(figsize=(6.5, max(2.2, .3 * len(items) + 1)))
    ax.barh([k for k, _ in items][::-1], [v for _, v in items][::-1], color=GREY)
    ax.set_xlabel("% missing")
    ax.set_title("Missing values by column")
    return _save(fig, path)
