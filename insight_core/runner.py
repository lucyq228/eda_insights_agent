"""Shared CLI plumbing and the guarded tool executor used by every skill script."""

from __future__ import annotations

import argparse
import json
import sys
import time
import traceback
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

from . import events, registry
from .context import Ctx
from .paths import refuse, run_dir_for
from .scope import load_approved
from .state import read_artifact, sha, write_artifact


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
        refuse("no prepared dataset yet; run prepare_data.py first")
    return pd.read_parquet(run_dir / "datasets" / "prepared.parquet"), meta


def leakage_columns(run_dir: Path) -> list[str]:
    for name in ("data_quality.json", "feasibility.json"):
        art = read_artifact(run_dir, name)
        if art and "leakage_suspects" in art:
            return [x["column"] for x in art["leakage_suspects"] if x.get("blocking", True) and not (read_artifact(run_dir, "approved_scope.json") or {}).get("leakage_justifications", {}).get(x["column"])]
    return []


def _jsonable(out: dict) -> dict:
    return {k: v for k, v in out.items() if k != "tables"}


def save_result(run_dir: Path, label: str, tool_id: str, params: dict, out: dict, meta: dict) -> dict:
    tables = {}
    for name, table in (out.get("tables") or {}).items():
        if isinstance(table, pd.DataFrame) and not table.empty:
            path = run_dir / "results" / f"{label}__{name}.csv"
            table.to_csv(path, index=False)
            tables[name] = {"file": path.name, "rows": int(len(table)), "columns": [str(c) for c in table.columns],
                            "preview": json.loads(table.head(30).to_json(orient="records", date_format="iso")),
                            "preview_truncated": len(table) > 30}
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
            followup_reason: str | None = None, hypothesis: str | None = None) -> dict:
    """Run one analysis tool under the locked scope. Refuses blocked steps."""
    scope = load_approved(run_dir)
    if step is None and not followup_reason and tool_id != "multiple-testing":
        refuse("analyses outside the approved plan need --followup-reason")
    if hypothesis and (not followup_reason or hypothesis not in {h["id"] for h in scope["hypotheses"]}):
        refuse("follow-up hypothesis must name a question in the approved scope and needs a reason")
    if followup_reason:
        existing = [json.loads(p.read_text()) for p in (run_dir / "results").glob("*.json")]
        count = sum(bool(r.get("followup_reason")) for r in existing if r.get("label") != label)
        if count >= int(scope.get("max_followups", 12)):
            refuse("follow-up budget reached; summarize unresolved questions and agree a new run if needed")
    df, meta = load_prepared(run_dir)
    profile = read_artifact(run_dir, "profile.json")
    if tool_id != "multiple-testing":
        check = registry.check_step(tool_id, params, scope, profile, leakage_columns(run_dir))
        if check["verdict"] == "blocked":
            events.emit(run_dir, "refused", actor, f"{label} {tool_id}: {check['reasons']}")
            return {"label": label, "tool": tool_id, "error": "blocked by feasibility", "reasons": check["reasons"],
                    "summary": None, "flags": []}
    types = meta["columns"]
    if params.get("view"):
        from .views import build_view, view_scope_profile
        from .data import column_types, profile as describe
        name = params["view"]
        df = build_view(df, scope, name)
        scope, profile = view_scope_profile(scope, profile, name)
        types = column_types(df)
        for c in scope.get("drivers", []):
            types[c] = next(x["type"] for x in profile["columns"] if x["name"] == c)
        actual_profile = describe(df)
        for info in actual_profile["columns"]:
            info["type"] = types.get(info["name"], info["type"])
        checked = registry.check_step(tool_id, {k:v for k,v in params.items() if k != "view"}, scope, actual_profile, [])
        if checked["verdict"] == "blocked":
            refuse("view fails actual-grain feasibility: " + str(checked["reasons"]))
        if len(df) < int(scope.get("min_n", 30)):
            refuse(f"view {name} has only {len(df)} rows; below min_n")
    drivers = [c for c in registry.resolved_drivers(scope, profile) if c in df.columns]
    ctx = Ctx(run_dir=run_dir, df=df, types=types, scope=scope, label=label, drivers=drivers)
    run_meta = {"step_id": (step or {}).get("step_id"), "hypothesis": hypothesis or (step or {}).get("hypothesis"),
                "purpose": (step or {}).get("purpose"), "followup_reason": followup_reason,
                "view": params.get("view"), "unit_of_analysis": scope["unit_of_analysis"],
                "analysis_mode": scope.get("mode", "confirmatory")}
    events.emit(run_dir, "tool start", actor, f"{label} {tool_id}",
                {"label": label, "tool": tool_id, "n_rows": len(df)})
    started = time.perf_counter()
    try:
        out = registry.function(tool_id)(ctx, params)
        repeated_key = ctx.entity or scope.get("roles", {}).get("customer")
        if repeated_key in df.columns and df[repeated_key].duplicated().any() and tool_id not in registry.panel_tools() and not registry.get(tool_id).get("descriptive"):
            out.setdefault("flags", []).append("REPEATED ENTITIES: ordinary intervals assume independent rows; do not claim cluster-valid precision")
    except Exception as exc:
        out = {"error": f"{type(exc).__name__}: {exc}", "trace": traceback.format_exc(limit=3), "findings": []}
    elapsed = round(time.perf_counter() - started, 3)
    run_meta["runtime_seconds"] = elapsed
    record = save_result(run_dir, label, tool_id, params, out, run_meta)
    events.emit(run_dir, "tool complete", actor,
                f"{label} {tool_id} ({elapsed}s): {record.get('summary') or record.get('error')}",
                {"label": label, "tool": tool_id, "runtime_seconds": elapsed, "n_rows": len(df),
                 "ok": not bool(record.get("error"))})
    return record


def waived_steps(run_dir: Path) -> dict[str, dict]:
    artifact = read_artifact(run_dir, "step_waivers.json") or {}
    if artifact and (artifact.get("upstream") or {}).get("sha256") != sha(run_dir / "approved_scope.json"):
        return {}
    return {item["step_id"]: item for item in artifact.get("waivers", [])}


def write_analyses_index(run_dir: Path) -> dict:
    scope = read_artifact(run_dir, "approved_scope.json")
    results = {}
    for path in sorted((run_dir / "results").glob("*.json")):
        r = json.loads(path.read_text(encoding="utf-8"))
        results[r["label"]] = r
    errors, steps = [], []
    waivers = waived_steps(run_dir)
    for s in registry.plan_steps(scope):
        r = results.get(s["step_id"])
        waived = waivers.get(s["step_id"])
        status = "skipped" if waived and r is None else "missing" if r is None else "error" if r.get("error") else "done"
        if status not in ("done", "skipped"):
            errors.append(f"{s['step_id']} ({s['tool']}): {status}" + (f" - {r['error']}" if r and r.get("error") else ""))
        steps.append({**s, "status": status, "summary": (r or {}).get("summary"), "flags": (r or {}).get("flags", []),
                      "skip_reason": (waived or {}).get("reason")})
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
