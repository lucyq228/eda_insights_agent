"""Profile the dataset before scoping: types, missingness, distributions, candidate targets."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[4]))

from insight_core import events  # noqa: E402
from insight_core.runner import base_parser, configure_stdout, emit_json, load_raw, resolve  # noqa: E402
from insight_core.state import read_artifact, write_artifact  # noqa: E402
from insight_core.tools_eda import profile_dataset  # noqa: E402


def main() -> None:
    configure_stdout()
    args = base_parser(__doc__, "A4").parse_args()
    run_dir = resolve(args)
    prof = profile_dataset(load_raw(run_dir), run_dir)
    prof["data_sha256"] = read_artifact(run_dir, "run.json")["data_sha256"]
    write_artifact(run_dir, "profile.json", prof)
    events.emit(run_dir, "profile", args.actor, f"{prof['n_rows']} rows x {prof['n_columns']} columns; "
                f"{len(prof['flags'])} flags")
    emit_json({"rows": prof["n_rows"], "columns": prof["n_columns"], "duplicate_rows": prof["duplicate_rows"],
               "column_types": {c["name"]: f"{c['type']}, {c['missing_pct']}% missing" for c in prof["columns"]},
               "target_candidates": prof["target_candidates"], "id_columns": prof["id_columns"],
               "date_columns": prof["date_columns"], "segment_candidates": prof["segment_candidates"],
               "panel_candidates": prof["panel_candidates"], "flags": prof["flags"], "charts": [Path(c).name for c in prof["charts"]]})


if __name__ == "__main__":
    main()
