"""Cleaning and validation.

Every transformation is recorded in a processing report. Data is never dropped
silently: duplicates are counted before removal, invalid values are set to null
with a named rule, and downstream imputation happens explicitly in the model
input builder (never hidden here).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .errors import PipelineError

NUMERIC_ROLES = {"process_metric", "numeric", "input_factor", "response_candidate", "ml_variable"}
NON_NEGATIVE_METRICS = {
    "utilization",
    "queue_wait",
    "wip_storage",
    "counter",
    "cycle_time",
    "throughput",
    "time_composition",
    "activity_time",
}
ABSOLUTE_LIMIT = 1e12


def _numeric_like(series: pd.Series) -> bool:
    return pd.api.types.is_numeric_dtype(series) and not pd.api.types.is_bool_dtype(series)


def clean_table(name: str, frame: pd.DataFrame, profile: dict) -> tuple[pd.DataFrame, dict]:
    if frame is None or frame.shape[0] == 0 or frame.shape[1] == 0:
        raise PipelineError("EMPTY_TABLE", f"Table '{name}' contains no rows or columns to process.")

    report: dict = {
        "table": name,
        "original_rows": int(frame.shape[0]),
        "original_columns": int(frame.shape[1]),
        "cleaned_rows": int(frame.shape[0]),
        "cleaned_columns": int(frame.shape[1]),
        "duplicate_rows_removed": 0,
        "empty_columns_removed": [],
        "coerced_columns": [],
        "transformed_columns": [],
        "invalid_values_set_null": [],
        "missing_values": {"total_cells": 0, "by_column": {}},
        "constant_columns": [],
        "transformations": [],
        "warnings": [],
        "errors": [],
    }

    df = frame.copy()
    roles = {c["name"]: c for c in profile["columns_detail"]}

    # 1) empty columns ------------------------------------------------------
    empty_columns = [
        str(c)
        for c in df.columns
        if roles.get(str(c), {}).get("role") == "empty" or df[c].isna().all()
    ]
    if empty_columns:
        df = df.drop(columns=empty_columns)
        report["empty_columns_removed"] = empty_columns
        report["transformations"].append(f"Dropped {len(empty_columns)} empty column(s).")

    # 2) numeric coercion ---------------------------------------------------
    for column in df.columns:
        role = roles.get(str(column), {}).get("role")
        if role in NUMERIC_ROLES and not _numeric_like(df[column]):
            original_non_null = int(df[column].notna().sum())
            coerced = pd.to_numeric(df[column], errors="coerce")
            failed = original_non_null - int(coerced.notna().sum())
            df[column] = coerced
            report["coerced_columns"].append({"column": str(column), "failed_values": int(max(failed, 0))})

    # 3) duplicate rows -----------------------------------------------------
    # Duplicate-row removal is only meaningful for record-style tables.
    # - Single-column tables hold observations (duplicate values are valid data).
    # - MAT variables are aligned sample vectors; deduplicating one destroys
    #   row alignment with the other variables from the same simulation.
    source_file = str(profile.get("source_file", ""))
    is_aligned_samples = source_file.lower().endswith(".mat")
    if df.shape[1] >= 2 and not is_aligned_samples:
        duplicates = int(df.duplicated().sum())
        if duplicates:
            df = df.drop_duplicates(keep="first").reset_index(drop=True)
            report["duplicate_rows_removed"] = duplicates
            report["transformations"].append(f"Removed {duplicates} duplicate row(s).")
    else:
        report["duplicate_rows_removed"] = 0
        report["transformations"].append(
            "Duplicate-row removal skipped: "
            + ("aligned sample-vector table (MAT variable)" if is_aligned_samples else "single-column table")
            + "; duplicate values are valid observations here."
        )

    # 4) utilization scale normalization -------------------------------------
    for column in df.columns:
        info = roles.get(str(column), {})
        if info.get("metric") != "utilization" or not _numeric_like(df[column]):
            continue
        series = df[column].dropna()
        if series.empty:
            continue
        if series.min() >= 0 and series.median() > 1 and series.max() <= 100:
            df[column] = df[column] / 100.0
            report["transformed_columns"].append(
                {"column": str(column), "rule": "utilization_percent_to_ratio", "detail": "median > 1 and max <= 100"}
            )

    # 5) detectable impossible values -----------------------------------------
    for column in df.columns:
        info = roles.get(str(column), {})
        metric = info.get("metric")
        role = info.get("role")
        if not _numeric_like(df[column]):
            continue
        column_name = str(column)

        if metric in NON_NEGATIVE_METRICS or role in NON_NEGATIVE_METRICS:
            negatives = int((df[column] < 0).sum())
            if negatives:
                df.loc[df[column] < 0, column] = np.nan
                report["invalid_values_set_null"].append(
                    {"column": column_name, "rule": "negative_value", "count": negatives}
                )

        if metric == "utilization":
            out_of_range = int((df[column] > 1).sum())
            if out_of_range:
                df.loc[df[column] > 1, column] = np.nan
                report["invalid_values_set_null"].append(
                    {"column": column_name, "rule": "utilization_out_of_range", "count": out_of_range}
                )

        beyond = int((df[column].abs() > ABSOLUTE_LIMIT).sum())
        if beyond:
            report["warnings"].append(
                f"'{column_name}' contains {beyond} value(s) beyond +/-1e12; flagged for review, left untouched."
            )

    # 6) constant columns ------------------------------------------------------
    report["constant_columns"] = [str(c) for c in df.columns if df[c].nunique(dropna=True) <= 1]

    # 7) missing value summary -------------------------------------------------
    missing = {str(k): int(v) for k, v in df.isna().sum().items() if int(v) > 0}
    report["missing_values"] = {"total_cells": int(df.isna().sum().sum()), "by_column": missing}

    report["cleaned_rows"] = int(df.shape[0])
    report["cleaned_columns"] = int(df.shape[1])
    if report["cleaned_rows"] > report["original_rows"]:
        raise PipelineError(
            "ROW_COUNT_INVARIANT",
            f"Cleaning expanded table '{name}' unexpectedly ({report['original_rows']} -> {report['cleaned_rows']}).",
        )
    return df, report
