"""Record what the user said: answers to scope questions and free-form context.

--answers-file JSON: {"answers": {"Q1": "..."}, "user_context": ["the target is ...", ...]}
Only record what the user actually said. Never answer on the user's behalf.
"""

import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[4]))

from insight_core import events  # noqa: E402
from insight_core.runner import base_parser, configure_stdout, emit_json, read_json_file, resolve  # noqa: E402
from insight_core.state import read_artifact, write_artifact  # noqa: E402


def main() -> None:
    configure_stdout()
    p = base_parser(__doc__, "coordinator")
    p.add_argument("--answers-file", required=True)
    args = p.parse_args()
    run_dir = resolve(args)
    if (run_dir / "approved_scope.json").exists():
        emit_json({"error": "scope already approved; new requirements need a new run"}, ok=False)
    new = read_json_file(args.answers_file)
    store = read_artifact(run_dir, "answers.json") or {"answers": {}, "user_context": [], "log": []}
    proposal = read_artifact(run_dir, "scope_proposal.json")
    known = {q["id"] for q in (proposal or {}).get("scope", {}).get("user_questions", [])}
    unknown = [k for k in new.get("answers", {}) if k not in known]
    if unknown:
        emit_json({"error": f"no such question ids in the current scope: {unknown}", "known": sorted(known)}, ok=False)
    now = datetime.now().isoformat(timespec="seconds")
    for qid, ans in new.get("answers", {}).items():
        if not str(ans).strip():
            emit_json({"error": f"empty answer for {qid}"}, ok=False)
        store["answers"][qid] = str(ans).strip()
        store["log"].append({"time": now, "id": qid, "answer": str(ans).strip()})
    for ctx in new.get("user_context", []):
        store["user_context"].append(str(ctx).strip())
        store["log"].append({"time": now, "id": "context", "answer": str(ctx).strip()})
    write_artifact(run_dir, "answers.json", store)
    events.emit(run_dir, "user answers", args.actor, f"answers={list(new.get('answers', {}))}; "
                f"context items={len(new.get('user_context', []))}")
    open_q = sorted(known - set(store["answers"]))
    emit_json({"recorded": list(new.get("answers", {})), "context_items": len(store["user_context"]),
               "still_open": open_q, "next": "send the answers to the scope-feasibility specialist for revision"})


if __name__ == "__main__":
    main()
