"""Start a run on a dataset: record the file, its fingerprint, and the user's request."""

import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[4]))

from insight_core import events  # noqa: E402
from insight_core.paths import ROOT, new_run_dir  # noqa: E402
from insight_core.runner import base_parser, configure_stdout, emit_json  # noqa: E402
from insight_core.state import sha, write_artifact  # noqa: E402


def main() -> None:
    configure_stdout()
    p = base_parser(__doc__, "coordinator")
    p.add_argument("--data", required=True, help="path to a csv, tsv, xlsx, or parquet file")
    p.add_argument("--request", required=True, help="the user's request, in their words")
    p.add_argument("--name", help="short run name (default: file name)")
    args = p.parse_args()
    data = Path(args.data)
    if not data.is_absolute():
        data = (ROOT / data) if (ROOT / data).exists() else data.resolve()
    if not data.exists():
        emit_json({"error": f"dataset not found: {args.data}"}, ok=False)
    if data.suffix.lower() not in (".csv", ".tsv", ".txt", ".xlsx", ".xls", ".parquet"):
        emit_json({"error": f"unsupported file type {data.suffix}; use csv, tsv, xlsx, or parquet"}, ok=False)
    run_dir = new_run_dir(args.name or data.stem)
    write_artifact(run_dir, "run.json", {"run_id": run_dir.name, "data_path": str(data), "data_sha256": sha(data),
                                         "data_bytes": data.stat().st_size, "request": args.request,
                                         "started_at": datetime.now().isoformat(timespec="seconds")})
    events.emit(run_dir, "run start", args.actor, f"data={data.name}; request={args.request[:200]}")
    emit_json({"run_id": run_dir.name, "data": data.name, "next": "run profile_data.py, then delegate scope + feasibility"})


if __name__ == "__main__":
    main()
