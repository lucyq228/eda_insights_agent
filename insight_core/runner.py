"""Shared CLI plumbing and the guarded tool executor used by every skill script."""

from __future__ import annotations

import argparse
import json
import sys
import traceback
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

from . import events, registry
from .context import Ctx
from .paths import refuse, run_dir_for
from .scope import load_approved
from .state import read_artifact, write_artifact


def configure_stdout() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass


def emit_json(obj: dict, ok: bool | None = None) -> None:
    ok = obj.get("ok", True) if ok is None else ok
    print(json.dumps({"ok": ok, **obj}, indent=1, default=_default))
    sys.exit(0 if ok else 1)


def _default(o):
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.floating,)):
        return None if not np.isfinite(o) else float(o)
    if isinstance(o, (pd.Timestamp, datetime)):
        return o.isoformat()
    if isinstance(o, np.ndarray):
        return o.tolist()
    return str(o)


def base_parser(description: str, actor: str) -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=description)
    p.add_argument("--run", help="run id (default: runs/CURRENT)")
    p.add_argument("--actor", default=actor)
    return p


def resolve(args) -> Path:
    return run_dir_for(args.run)


def read_json_file(path: str | Path) -> dict:
    path = Path(path)
    if not path.exists():
        emit_json({"error": f"file not found: {path}"}, ok=False)
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as exc:
        emit_json({"error": f"{path} is not valid JSON: {exc}"}, ok=False)


def load_raw(run_dir: Path) -> pd.DataFrame:
    from .data import load_table

    return load_table(read_artifact(run_dir, "run.json")["data_path"])


def load_prepared(run_dir: Path) -> tuple[pd.DataFrame, dict]:
    meta = read_artifact(run_dir, "prepared_data.json")
    if not meta:
        refuse("no prepared dataset yet; run A5 prepare_data.py first")
    return pd.read_parquet(run_dir / "datasets" / "prepared.parquet"), meta


def leakage_columns(run_dir: Path) -> list[str]:
    for name in ("data_quality.json", "feasibility.json"):
        art = read_artifact(run_dir, name)
        if art and "leakage_suspects" in art:
            return [x["column"] for x in art["leakage_suspects"]]
    return []


def _jsonable(out: dict) -> dict:
    return {k: v for k, v in out.items() if k != "tables"}


def save_result(run_dir: Path, label: str, tool_id: str, params: dict, out: dict, meta: dict) -> dict:
    tables = {}
    for name, table in (out.get("tables") or {}).items():
        if isinstance(table, pd.DataFrame) and not table.empty:
            path = run_dir / "results" / f"{label}__{name}.csv"
            table.to_csv(path, index=False)
            tables[name] = {"file": path.name, "rows": int(len(table)), "columns": [str(c) for c in table.columns]}
    record = {"label": label, "tool": tool_id, "params": params, **meta, "saved_at": datetime.now().isoformat(timespec="seconds"),
              **_jsonable(out), "tables": tables}
    (run_dir / "results" / f"{label}.json").write_text(json.dumps(record, indent=1, default=_default), encoding="utf-8")
    return record


def compact(record: dict) -> dict:
    keep = {"label": record["label"], "tool": record["tool"], "summary": record.get("summary"),
            "flags": record.get("flags", []), "n_findings": len(record.get("findings", []))}
    if record.get("error"):
        keep["error"] = record["error"]
    return keep


def execute(run_dir: Path, tool_id: str, params: dict, label: str, actor: str, step: dict | None = None,
            followup_reason: str | None = None) -> dict:
    """Run one analysis tool under the locked scope. Refuses blocked steps."""
    scope = load_approved(run_dir)
    if step is None and not followup_reason and tool_id != "multiple-testing":
        refuse("analyses outside the approved plan need --followup-reason")
    df, meta = load_prepared(run_dir)
    profile = read_artifact(run_dir, "profile.json")
    if tool_id != "multiple-testing":
        check = registry.check_step(tool_id, params, scope, profile, leakage_columns(run_dir))
        if check["verdict"] == "blocked":
            events.emit(run_dir, "refused", actor, f"{label} {tool_id}: {check['reasons']}")
            return {"label": label, "tool": tool_id, "error": "blocked by feasibility", "reasons": check["reasons"],
                    "summary": None, "flags": []}
    types = meta["columns"]
    drivers = [c for c in registry.resolved_drivers(scope, profile) if c in df.columns]
    ctx = Ctx(run_dir=run_dir, df=df, types=types, scope=scope, label=label, drivers=drivers)
    run_meta = {"step_id": (step or {}).get("step_id"), "hypothesis": (step or {}).get("hypothesis"),
                "purpose": (step or {}).get("purpose"), "followup_reason": followup_reason}
    try:
        out = registry.function(tool_id)(ctx, params)
    except Exception as exc:
        out = {"error": f"{type(exc).__name__}: {exc}", "trace": traceback.format_exc(limit=3), "findings": []}
    record = save_result(run_dir, label, tool_id, params, out, run_meta)
    events.emit(run_dir, "tool", actor, f"{label} {tool_id}: {record.get('summary') or record.get('error')}")
    return record


def write_analyses_index(run_dir: Path) -> dict:
    scope = read_artifact(run_dir, "approved_scope.json")
    results = {}
    for path in sorted((run_dir / "results").glob("*.json")):
        r = json.loads(path.read_text(encoding="utf-8"))
        results[r["label"]] = r
    errors, steps = [], []
    for s in registry.plan_steps(scope):
        r = results.get(s["step_id"])
        status = "missing" if r is None else "error" if r.get("error") else "done"
        if status != "done":
            errors.append(f"{s['step_id']} ({s['tool']}): {status}" + (f" - {r['error']}" if r and r.get("error") else ""))
        steps.append({**s, "status": status, "summary": (r or {}).get("summary"), "flags": (r or {}).get("flags", [])})
    followups = [{"label": k, "tool": r["tool"], "params": r["params"], "reason": r["followup_reason"],
                  "summary": r.get("summary"), "flags": r.get("flags", []), "error": r.get("error")}
                 for k, r in results.items() if r.get("followup_reason")]
    mt = results.get("multiple-testing")
    if not mt:
        errors.append("multiple-testing has not been run")
    index = {"steps": steps, "followups": followups,
             "multiple_testing": (mt or {}).get("summary"), "errors": errors,
             "n_results": len(results), "written_at": datetime.now().isoformat(timespec="seconds")}
    write_artifact(run_dir, "analyses_index.json", index, upstream="prepared_data.json")
    return index


def refresh_multiple_testing(run_dir: Path, actor: str) -> dict:
    return execute(run_dir, "multiple-testing", {}, "multiple-testing", actor)
