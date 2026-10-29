"""Validate drafts/scope.json and save it as the next scope_proposal.json version."""

import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[4]))

from insight_core import events, scope  # noqa: E402
from insight_core.runner import base_parser, configure_stdout, emit_json, read_json_file, resolve  # noqa: E402
from insight_core.state import read_artifact, write_artifact  # noqa: E402


def main() -> None:
    configure_stdout()
    p = base_parser(__doc__, "scope-feasibility")
    p.add_argument("--file", help="default: drafts/scope.json")
    p.add_argument("--change-note", default="", help="what changed versus the previous version")
    args = p.parse_args()
    run_dir = resolve(args)
    if (run_dir / "approved_scope.json").exists():
        emit_json({"error": "scope is approved and locked; a different scope needs a new run"}, ok=False)
    draft = read_json_file(args.file or run_dir / "drafts" / "scope.json")
    prof = read_artifact(run_dir, "profile.json")
    if not prof:
        emit_json({"error": "no profile yet"}, ok=False)
    errors, warnings = scope.validate(draft, prof)
    if errors:
        emit_json({"error": "scope draft is invalid; fix and save again", "issues": errors, "warnings": warnings}, ok=False)
    prev = read_artifact(run_dir, "scope_proposal.json")
    version = (prev or {}).get("version", 0) + 1
    history = (prev or {}).get("history", []) + [{"version": version, "saved_at": datetime.now().isoformat(timespec="seconds"),
                                                   "note": args.change_note or ("first draft" if version == 1 else "revision")}]
    write_artifact(run_dir, "scope_proposal.json", {"version": version, "scope": draft, "warnings": warnings,
                                                    "history": history})
    (run_dir / "scope_proposal.md").write_text(scope.proposal_markdown(draft, version), encoding="utf-8")
    events.emit(run_dir, "scope saved", args.actor, f"version {version}: target={draft['target']['column']}; "
                f"{len(draft['hypotheses'])} hypotheses; {len(draft.get('user_questions', []))} questions")
    emit_json({"version": version, "target": draft["target"]["column"], "hypotheses": [h["id"] for h in draft["hypotheses"]],
               "questions": [q["id"] for q in draft.get("user_questions", [])], "warnings": warnings,
               "next": "run feasibility on this version"})


if __name__ == "__main__":
    main()
