"""Run every pathway step of the approved scope, then multiple testing, then write the index (A6)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[4]))

from insight_core import registry  # noqa: E402
from insight_core.runner import (base_parser, compact, configure_stdout, emit_json, execute,  # noqa: E402
                                 refresh_multiple_testing, resolve, write_analyses_index)
from insight_core.scope import load_approved  # noqa: E402
from insight_core.state import milestone_done  # noqa: E402


def main() -> None:
    configure_stdout()
    p = base_parser(__doc__, "A6")
    p.add_argument("--force", action="store_true", help="rerun steps that already have results")
    args = p.parse_args()
    run_dir = resolve(args)
    scope = load_approved(run_dir)
    if not milestone_done(run_dir, "prepared_data"):
        emit_json({"error": "prepared data is missing or stale; A5 prepare_data.py first"}, ok=False)
    out = []
    for step in registry.plan_steps(scope):
        if not args.force and (run_dir / "results" / f"{step['step_id']}.json").exists():
            out.append({"label": step["step_id"], "tool": step["tool"], "summary": "already done (use --force to rerun)"})
            continue
        out.append(compact(execute(run_dir, step["tool"], step["params"], step["step_id"], args.actor, step=step)))
    mt = refresh_multiple_testing(run_dir, args.actor)
    index = write_analyses_index(run_dir)
    emit_json({"steps": out, "multiple_testing": mt.get("summary"), "errors": index["errors"],
               "next": "A7 review" if not index["errors"] else "report the errors to the manager"},
              ok=not index["errors"])


if __name__ == "__main__":
    main()
