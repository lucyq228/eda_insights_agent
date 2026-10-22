"""Build report.md and a self-contained report.html from the saved insights."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[4]))

from insight_core import events, report  # noqa: E402
from insight_core.runner import base_parser, configure_stdout, emit_json, resolve  # noqa: E402
from insight_core.state import milestone_done, write_artifact  # noqa: E402


def main() -> None:
    configure_stdout()
    args = base_parser(__doc__, "A7").parse_args()
    run_dir = resolve(args)
    if not milestone_done(run_dir, "insights"):
        emit_json({"error": "insights are missing or stale"}, ok=False)
    out = report.build(run_dir)
    write_artifact(run_dir, "report.json", out, upstream="insights.json")
    events.emit(run_dir, "report", args.actor, f"{out['n_insights']} insights, {out['n_charts']} charts")
    emit_json({**out, "html": str(run_dir / "report.html"), "next": "manager finalize_run.py"})


if __name__ == "__main__":
    main()
