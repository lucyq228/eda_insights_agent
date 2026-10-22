"""Lock the scope. Only after the user explicitly approved it; quote them."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[4]))

from insight_core import events  # noqa: E402
from insight_core.runner import base_parser, configure_stdout, emit_json, resolve  # noqa: E402
from insight_core.scope import approve  # noqa: E402


def main() -> None:
    configure_stdout()
    p = base_parser(__doc__, "coordinator")
    p.add_argument("--exploration", action="store_true", help="activate a feasible exploratory scope under the original request")
    p.add_argument("--user-confirmation", default="", help="the user's approval, quoted verbatim")
    args = p.parse_args()
    run_dir = resolve(args)
    try:
        scope = approve(run_dir, args.user_confirmation, exploration=args.exploration)
    except ValueError as exc:
        events.emit(run_dir, "approval refused", args.actor, str(exc))
        emit_json({"error": str(exc)}, ok=False)
    events.emit(run_dir, "scope approved", args.actor, f"version {scope['version']}; user said: {args.user_confirmation[:200]}")
    emit_json({"approved_version": scope["version"], "target": scope["target"]["column"],
               "hypotheses": [h["id"] for h in scope["hypotheses"]], "next": "advance_run.py"})


if __name__ == "__main__":
    main()
