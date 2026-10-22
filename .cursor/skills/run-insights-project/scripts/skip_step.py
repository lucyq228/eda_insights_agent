"""Record a user-approved waiver for one planned analysis step without blocking the report."""

import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[4]))

from insight_core import events, registry  # noqa: E402
from insight_core.locking import milestone_lock  # noqa: E402
from insight_core.runner import base_parser, configure_stdout, emit_json, resolve  # noqa: E402
from insight_core.scope import load_approved  # noqa: E402
from insight_core.state import read_artifact, sha, write_artifact  # noqa: E402


def main() -> None:
    configure_stdout()
    p = base_parser(__doc__, "coordinator")
    p.add_argument("--step", required=True, help="approved step id, e.g. H2.S1")
    p.add_argument("--reason", required=True, help="why the step is being omitted")
    p.add_argument("--user-confirmation", required=True, help="quote the user's instruction to omit it")
    args = p.parse_args()
    run_dir = resolve(args)
    with milestone_lock(run_dir, "analysis"):
        scope = load_approved(run_dir)
        planned = {s["step_id"]: s for s in registry.plan_steps(scope)}
        if args.step not in planned:
            emit_json({"error": f"'{args.step}' is not an approved plan step"}, ok=False)
        if len(args.reason.strip()) < 3 or len(args.user_confirmation.strip()) < 2:
            emit_json({"error": "give a reason and quote the user's explicit confirmation"}, ok=False)
        if (run_dir / "results" / f"{args.step}.json").exists():
            emit_json({"error": f"{args.step} already has a saved result; it does not need a waiver"}, ok=False)
        artifact = read_artifact(run_dir, "step_waivers.json") or {"waivers": []}
        if artifact.get("upstream") and artifact["upstream"].get("sha256") != sha(run_dir / "approved_scope.json"):
            artifact = {"waivers": []}
        waivers = [w for w in artifact.get("waivers", []) if w["step_id"] != args.step]
        waivers.append({"step_id": args.step, "tool": planned[args.step]["tool"], "reason": args.reason.strip(),
                        "user_confirmation": args.user_confirmation.strip(),
                        "skipped_at": datetime.now().isoformat(timespec="seconds")})
        write_artifact(run_dir, "step_waivers.json", {"waivers": waivers}, upstream="approved_scope.json")
        events.emit(run_dir, "step skipped", args.actor, f"{args.step}: {args.reason.strip()}")
        emit_json({"skipped": args.step, "reason": args.reason.strip(), "next": "continue the approved analysis plan"})


if __name__ == "__main__":
    main()
