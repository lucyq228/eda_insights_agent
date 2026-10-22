"""Close the run once every milestone is done and current."""

import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[4]))

from insight_core import events  # noqa: E402
from insight_core.runner import base_parser, configure_stdout, emit_json, resolve  # noqa: E402
from insight_core.state import milestone_status, read_artifact, write_artifact  # noqa: E402


def main() -> None:
    configure_stdout()
    args = base_parser(__doc__, "coordinator").parse_args()
    run_dir = resolve(args)
    rows = milestone_status(run_dir)
    pending = [f"{r['milestone']}: {r['status']}" for r in rows if r["status"] != "done"]
    if pending:
        emit_json({"error": "run is not complete", "pending": pending}, ok=False)
    insights = read_artifact(run_dir, "insights.json")
    write_artifact(run_dir, "final.json", {"finalized_at": datetime.now().isoformat(timespec="seconds"),
                                           "headline": insights["headline_summary"],
                                           "report": str(run_dir / "report.html")})
    events.emit(run_dir, "run finalized", args.actor, insights["headline_summary"][:200])
    emit_json({"report_html": str(run_dir / "report.html"), "report_md": str(run_dir / "report.md"),
               "headline": insights["headline_summary"], "insights": [i["title"] for i in insights["insights"]]})


if __name__ == "__main__":
    main()
