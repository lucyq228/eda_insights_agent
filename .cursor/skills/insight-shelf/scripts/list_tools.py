"""Browse the tool shelf (tool_registry.yaml)."""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[4]))

from insight_core import registry  # noqa: E402
from insight_core.runner import configure_stdout, emit_json  # noqa: E402


def main() -> None:
    configure_stdout()
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--phase", choices=["eda", "prepare", "analysis", "report"])
    p.add_argument("--tool", help="show one tool in full")
    args = p.parse_args()
    if args.tool:
        try:
            emit_json({"tool": args.tool, **registry.get(args.tool)})
        except KeyError as exc:
            emit_json({"error": str(exc)}, ok=False)
    emit_json({"tools": registry.catalogue(args.phase)})


if __name__ == "__main__":
    main()
