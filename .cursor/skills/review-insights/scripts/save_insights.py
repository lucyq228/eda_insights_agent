"""Validate drafts/insights.json (evidence exists, no causal wording) and save insights.json."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[4]))

from insight_core import events  # noqa: E402
from insight_core.review import validate_insights  # noqa: E402
from insight_core.runner import base_parser, configure_stdout, emit_json, read_json_file, resolve  # noqa: E402
from insight_core.state import milestone_done, write_artifact  # noqa: E402


def main() -> None:
    configure_stdout()
    p = base_parser(__doc__, "A7")
    p.add_argument("--file", help="default: drafts/insights.json")
    args = p.parse_args()
    run_dir = resolve(args)
    if not milestone_done(run_dir, "review"):
        emit_json({"error": "review is missing, stale, or waiting on reruns"}, ok=False)
    draft = read_json_file(args.file or run_dir / "drafts" / "insights.json")
    errs = validate_insights(draft, run_dir)
    if errs:
        emit_json({"error": "insights draft has problems", "issues": errs}, ok=False)
    write_artifact(run_dir, "insights.json", draft, upstream="review.json")
    events.emit(run_dir, "insights", args.actor, f"{len(draft['insights'])} insights")
    emit_json({"insights": [f"{i['id']}: {i['title']}" for i in draft["insights"]], "next": "A7 build_report.py"})


if __name__ == "__main__":
    main()
