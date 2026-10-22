"""Run one shelf tool outside the plan as a recorded follow-up (reruns requested by review)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[4]))

from insight_core.locking import milestone_lock  # noqa: E402
from insight_core.runner import (base_parser, compact, configure_stdout, emit_json, execute,  # noqa: E402
                                 read_json_file, refresh_multiple_testing, resolve, write_analyses_index)
from insight_core.state import milestone_done  # noqa: E402


def main() -> None:
    configure_stdout()
    p = base_parser(__doc__, "coordinator")
    p.add_argument("--tool", required=True)
    p.add_argument("--params-file", help="JSON file with the tool params")
    p.add_argument("--followup-reason", required=True, help="why this analysis is needed (shown in the report)")
    args = p.parse_args()
    run_dir = resolve(args)
    if not milestone_done(run_dir, "prepared_data"):
        emit_json({"error": "prepared data is missing or stale"}, ok=False)
    with milestone_lock(run_dir, "analysis"):
        params = read_json_file(args.params_file) if args.params_file else {}
        n = len(list((run_dir / "results").glob("F*.json"))) + 1
        label = f"F{n}"
        record = execute(run_dir, args.tool, params, label, args.actor, followup_reason=args.followup_reason)
        if record.get("error"):
            emit_json(compact(record) | {"reasons": record.get("reasons", [])}, ok=False)
        mt = refresh_multiple_testing(run_dir, args.actor)
        index = write_analyses_index(run_dir)
        emit_json({"result": compact(record), "findings": record.get("findings", [])[:8],
                   "multiple_testing": mt.get("summary"), "index_errors": index["errors"]})


if __name__ == "__main__":
    main()
