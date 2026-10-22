"""Read a bounded page of a saved aggregate result table; never a raw dataset."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[4]))
import pandas as pd
from insight_core.runner import base_parser, configure_stdout, emit_json, resolve
from insight_core.state import read_artifact


def main():
    configure_stdout()
    p = base_parser(__doc__, "analyst")
    p.add_argument("--label", required=True)
    p.add_argument("--table", required=True)
    p.add_argument("--sort-by", help="optional aggregate column to sort before paging")
    p.add_argument("--descending", action="store_true")
    p.add_argument("--offset", type=int, default=0)
    p.add_argument("--limit", type=int, default=50)
    args = p.parse_args()
    run = resolve(args)
    if Path(args.label).name != args.label or args.offset < 0 or not 1 <= args.limit <= 200:
        emit_json({"error": "invalid label or page bounds"}, ok=False)
    result = read_artifact(run, f"results/{args.label}.json") or {}
    table = result.get("tables", {}).get(args.table)
    if not table:
        emit_json({"error": "unknown saved aggregate table"}, ok=False)
    path = (run / "results" / table["file"]).resolve()
    if path.parent != (run / "results").resolve():
        emit_json({"error": "table path is outside results"}, ok=False)
    df = pd.read_csv(path)
    if args.sort_by:
        if args.sort_by not in df.columns:
            emit_json({"error": "unknown sort column"}, ok=False)
        df = df.sort_values(args.sort_by, ascending=not args.descending, kind="stable", na_position="last")
    emit_json({"label": args.label, "table": args.table, "total_rows": len(df), "offset": args.offset,
               "rows": df.iloc[args.offset:args.offset+args.limit].to_dict("records"),
               "more": args.offset+args.limit < len(df)})


if __name__ == "__main__":
    main()
