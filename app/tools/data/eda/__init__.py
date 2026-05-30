"""Statistical Profiler — EDA phase: per-column statistical profiling.

Computes the following metrics for each column in a DataFrame / Parquet file:

1. **Null rate**        : null_count / total_rows  (tỷ lệ null theo cột)
2. **Sample values**   : representative non-null sample (top-freq + random mix)
3. **Unique ratio**    : unique_count / total_rows  — used to identify PK candidates:
       • unique_ratio == 1.0        --> likely Primary Key / ID column
       • unique_ratio ≈ 1.0 < 1.0  --> has duplicates in this column — investigate
       • unique_ratio in (0.0–0.2)  --> categorical column (gender, status, type…)
       • unique_ratio in (0.2–0.8)  --> regular column (not key, not purely categorical)
4. **Current dtype**   : pandas dtype of the column as stored
5. **String patterns** : regex patterns detected from string samples (email, phone,
                         date, URL, UUID, zip-code, integer string, float string…)

Usage
-----
::

    from app.tools.data.eda import StatisticalProfiler, perform_eda

    profiler = StatisticalProfiler()

    # From a Parquet file
    report = profiler.profile_parquet("path/to/file.parquet")

    # From an in-memory DataFrame
    report = profiler.profile_dataframe(df)

    # Pretty-print to console
    profiler.print_report(report)

    # Convert to dict / JSON
    data = report.to_dict()
"""

from app.tools.data.eda.tool import perform_eda
from app.tools.data.eda.profiler import StatisticalProfiler
from app.tools.data.eda.models import ColumnStat, StatisticalReport

__all__ = ["perform_eda", "StatisticalProfiler", "ColumnStat", "StatisticalReport"]
