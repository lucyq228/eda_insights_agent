"""Render a reviewer-approved storyline against the saved analytical checkpoint."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[4]))
from insight_core.executive import build
from insight_core.locking import milestone_lock
from insight_core.runner import base_parser, configure_stdout, emit_json, read_json_file, resolve


def main():
    configure_stdout()
    parser = base_parser(__doc__, "review-insights")
    parser.add_argument("--file", help="default: drafts/executive_story.json")
    args = parser.parse_args()
    run_dir = resolve(args)
    draft = read_json_file(args.file or run_dir / "drafts" / "executive_story.json")
    try:
        with milestone_lock(run_dir, "executive_report"):
            result = build(run_dir, draft)
    except (ValueError, KeyError, TypeError, OSError) as exc:
        emit_json({"error": str(exc)}, ok=False)
    emit_json({"files": result["files"], "next": "finalize_run.py; deliver BOTH reports"})


if __name__ == "__main__":
    main()
