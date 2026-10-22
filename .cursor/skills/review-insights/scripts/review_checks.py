"""Deterministic challenges on every result, grouped by hypothesis."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[4]))

from insight_core.review import challenges  # noqa: E402
from insight_core.runner import base_parser, configure_stdout, emit_json, resolve  # noqa: E402
from insight_core.state import milestone_done  # noqa: E402


def main() -> None:
    configure_stdout()
    args = base_parser(__doc__, "review-insights").parse_args()
    run_dir = resolve(args)
    if not milestone_done(run_dir, "analyses"):
        emit_json({"error": "analyses are missing, incomplete, or stale"}, ok=False)
    emit_json(challenges(run_dir))


if __name__ == "__main__":
    main()
