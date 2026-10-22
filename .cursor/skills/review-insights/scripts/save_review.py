"""Validate drafts/review.json and save review.json. Rerun requests leave the review open."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[4]))

from insight_core import events  # noqa: E402
from insight_core.review import validate_review  # noqa: E402
from insight_core.runner import base_parser, configure_stdout, emit_json, read_json_file, resolve  # noqa: E402
from insight_core.state import milestone_done, write_artifact  # noqa: E402


def main() -> None:
    configure_stdout()
    p = base_parser(__doc__, "review-insights")
    p.add_argument("--file", help="default: drafts/review.json")
    args = p.parse_args()
    run_dir = resolve(args)
    if not milestone_done(run_dir, "analyses"):
        emit_json({"error": "analyses are missing, incomplete, or stale"}, ok=False)
    draft = read_json_file(args.file or run_dir / "drafts" / "review.json")
    errs = validate_review(draft, run_dir)
    if errs:
        emit_json({"error": "review draft has problems", "issues": errs}, ok=False)
    reruns = draft.get("rerun_requests", [])
    art = {**draft}
    if reruns:
        art["errors"] = [f"rerun requested: {r['tool']} {r.get('params', {})} - {r['reason']}" for r in reruns]
    write_artifact(run_dir, "review.json", art, upstream="analyses_index.json")
    verdicts = {v["id"]: v["verdict"] for v in draft["hypothesis_verdicts"]}
    events.emit(run_dir, "review", args.actor, f"verdicts={verdicts}; reruns={len(reruns)}")
    emit_json({"verdicts": verdicts, "rerun_requests": reruns,
               "next": "coordinator runs targeted follow-ups, then reviewer checks again" if reruns else "save_insights.py"})


if __name__ == "__main__":
    main()
