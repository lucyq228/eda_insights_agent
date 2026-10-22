"""Per-run cache for repeated driver/target association calculations."""

from __future__ import annotations

import hashlib
import json
import os

import pandas as pd

from . import stats
from .context import Ctx
from .state import sha

CACHE_VERSION = 2


def associate_cached(ctx: Ctx, column: str, x_type: str, *, with_interval: bool,
                     values: pd.Series | None = None, variant: str = "raw") -> dict:
    cache_dir = ctx.run_dir / "cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    path = cache_dir / "associations.json"
    identity = {
        "version": CACHE_VERSION,
        "prepared_sha256": sha(ctx.run_dir / "datasets" / "prepared.parquet"),
        "target": ctx.target,
        "target_type": ctx.target_type,
        "driver": column,
        "driver_type": x_type,
        "alpha": ctx.alpha,
        "with_interval": with_interval,
        "variant": variant,
        "scope_view": ctx.scope.get("active_view"),
        "data_digest": hashlib.sha256(pd.util.hash_pandas_object(ctx.df[[column, ctx.target]], index=True).values.tobytes()).hexdigest(),
    }
    key = hashlib.sha256(json.dumps(identity, sort_keys=True).encode("utf-8")).hexdigest()
    try:
        cache = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    except (json.JSONDecodeError, OSError):
        cache = {}
    if key in cache:
        return {**cache[key]["result"], "cache_hit": True}

    x = ctx.df[column] if values is None else values
    fn = stats.associate_with_interval if with_interval else stats.associate_point
    result = fn(x, ctx.df[ctx.target], x_type, ctx.target_type, ctx.alpha)
    cache[key] = {"identity": identity, "result": result}
    temp = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    temp.write_text(json.dumps(cache, indent=1), encoding="utf-8")
    temp.replace(path)
    return {**result, "cache_hit": False}
