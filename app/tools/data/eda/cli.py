import sys
import json
from pathlib import Path
import pandas as pd

from app.tools.data.eda.profiler import StatisticalProfiler

def _cli_main() -> None:  # pragma: no cover
    """Minimal CLI: python -m app.tools.data.eda.cli <path.parquet|path.csv>"""
    if len(sys.argv) < 2:
        print("Usage: python -m app.tools.data.eda.cli <path.parquet|path.csv>")
        sys.exit(1)

    file_path = Path(sys.argv[1])
    profiler = StatisticalProfiler()

    if file_path.suffix.lower() == ".parquet":
        report = profiler.profile_parquet(file_path)
    elif file_path.suffix.lower() in {".csv", ".tsv"}:
        sep = "\t" if file_path.suffix.lower() == ".tsv" else ","
        df = pd.read_csv(file_path, sep=sep)
        report = profiler.profile_dataframe(df, source=str(file_path))
    else:
        print(f"Unsupported file format: {file_path.suffix}")
        sys.exit(1)

    # Pretty-print to terminal
    profiler.print_report(report)

    # Optionally dump JSON if --json flag is passed
    if "--json" in sys.argv:
        print("\n" + json.dumps(report.to_dict(), indent=2, default=str))

if __name__ == "__main__":
    _cli_main()
