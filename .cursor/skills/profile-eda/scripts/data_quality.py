"""Data-quality checks and a target overview under the approved scope."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[4]))

from insight_core import events, registry  # noqa: E402
from insight_core.context import Ctx  # noqa: E402
from insight_core.locking import milestone_lock  # noqa: E402
from insight_core.runner import base_parser, configure_stdout, emit_json, load_raw, resolve  # noqa: E402
from insight_core.scope import load_approved  # noqa: E402
from insight_core.state import milestone_done, read_artifact, write_artifact  # noqa: E402
from insight_core.tools_eda import data_quality_check, eda_overview  # noqa: E402


def main() -> None:
    configure_stdout()
    args = base_parser(__doc__, "coordinator").parse_args()
    run_dir = resolve(args)
    if milestone_done(run_dir, "data_quality"):
        emit_json({"summary": "data quality already complete", "next": "prepare_data.py"})
    with milestone_lock(run_dir, "data-quality"):
        scope = load_approved(run_dir)
        df = load_raw(run_dir)
        profile = read_artifact(run_dir, "profile.json")
        feasibility = read_artifact(run_dir, "feasibility.json") or {}
        types = {c["name"]: c["type"] for c in profile["columns"]}
        ctx = Ctx(run_dir=run_dir, df=df, types=types, scope=scope, label="dq",
                  drivers=registry.resolved_drivers(scope, profile))
        dq = data_quality_check(ctx, {}, precomputed_leakage=feasibility.get("leakage_suspects"))
        eda = eda_overview(ctx, {})
        fails = [f"{c['check']}: {c['detail']}" for c in dq["checks"] if c["status"] == "fail"]
        art = {"summary": dq["summary"], "checks": dq["checks"], "leakage_suspects": dq["leakage_suspects"],
               "target_overview": eda["notes"], "segment_tables": {k: v.round(4).to_dict("records") for k, v in eda["tables"].items()},
               "charts": eda["charts"], "drivers": ctx.drivers}
        if fails:
            art["errors"] = fails
        write_artifact(run_dir, "data_quality.json", art, upstream="approved_scope.json")
        events.emit(run_dir, "data quality", args.actor, dq["summary"])
        emit_json({"summary": dq["summary"], "fails": fails,
                   "warnings": [f"{c['check']}: {c['detail']}" for c in dq["checks"] if c["status"] == "warn"],
                   "target_overview": eda["notes"], "charts": [Path(c).name for c in eda["charts"]],
                   "next": "prepare_data.py" if not fails else "a failed check needs a new run with a fixed scope"},
                  ok=not fails)


if __name__ == "__main__":
    main()
