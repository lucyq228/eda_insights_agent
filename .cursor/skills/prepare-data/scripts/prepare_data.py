"""Build datasets/prepared.parquet from the approved scope."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[4]))

from insight_core import events, registry  # noqa: E402
from insight_core.context import Ctx  # noqa: E402
from insight_core.locking import milestone_lock  # noqa: E402
from insight_core.runner import base_parser, configure_stdout, emit_json, load_raw, read_json_file, resolve  # noqa: E402
from insight_core.scope import load_approved  # noqa: E402
from insight_core.state import milestone_done, read_artifact, write_artifact  # noqa: E402
from insight_core.tools_eda import prepare_dataset  # noqa: E402


def main() -> None:
    configure_stdout()
    p = base_parser(__doc__, "coordinator")
    p.add_argument("--params-file", help="optional JSON, e.g. {\"rare_level_share\": 0.02}")
    args = p.parse_args()
    run_dir = resolve(args)
    if milestone_done(run_dir, "prepared_data"):
        emit_json({"summary": "prepared data already complete", "next": "run_plan.py"})
    scope = load_approved(run_dir)
    if not milestone_done(run_dir, "data_quality"):
        emit_json({"error": "data quality must pass first (data_quality.py)"}, ok=False)
    with milestone_lock(run_dir, "prepared-data"):
        params = read_json_file(args.params_file) if args.params_file else {}
        profile = read_artifact(run_dir, "profile.json")
        types = {c["name"]: c["type"] for c in profile["columns"]}
        ctx = Ctx(run_dir=run_dir, df=load_raw(run_dir), types=types, scope=scope, label="prep",
                  drivers=registry.resolved_drivers(scope, profile))
        out = prepare_dataset(ctx, params)
        errors = []
        if out["n_rows"] < ctx.min_n:
            errors.append(f"only {out['n_rows']} rows after preparation (min_n {ctx.min_n})")
        art = {k: v for k, v in out.items() if k not in ("findings", "charts")} | {"params": params}
        if errors:
            art["errors"] = errors
        write_artifact(run_dir, "prepared_data.json", art, upstream="approved_scope.json")
        events.emit(run_dir, "prepared data", args.actor, out["summary"])
        emit_json({"summary": out["summary"], "log": out["log"], "errors": errors,
                   "next": "run_plan.py" if not errors else "fix needed"}, ok=not errors)


if __name__ == "__main__":
    main()
