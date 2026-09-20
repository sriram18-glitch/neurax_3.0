"""Schema inference and dataset profiling.

Roles are inferred heuristically from column names and dtypes. Every role is
reported as an inference with its raw evidence (name/dtype/stats) available,
never as a hard claim about the data's meaning.
"""

from __future__ import annotations

import re
from typing import Any

import numpy as np
import pandas as pd

from .readers import IngestResult, Table

STATION_SPLIT = re.compile(r"[_\s]+")

# Order matters: first match wins.
METRIC_RULES: list[tuple[str, re.Pattern]] = [
    ("time_composition", re.compile(r"(va|nva|transport|other)[_\s]+time", re.I)),
    ("utilization", re.compile(r"util(?:ization)?", re.I)),
    ("queue_wait", re.compile(r"queue|waiting|wait[_\s]*time", re.I)),
    ("cycle_time", re.compile(r"cycle", re.I)),
    ("wip_storage", re.compile(r"stored|storage|\bwip\b", re.I)),
    ("throughput", re.compile(r"parts per hour|entities out|total parts|totalproducts|products per", re.I)),
    ("activity_time", re.compile(r"(assembly|drilling|milling|blanking|press\d?|cell\d?|paint\d?)[_\s]+time", re.I)),
]

STOP_STATION_TOKENS = {
    "util", "utilization", "queue", "waiting", "wait", "time", "cycle", "total",
    "parts", "part", "entities", "in", "out", "va", "nva", "transport", "other",
    "stored", "products", "now", "sku", "sku1", "sku2", "sku3", "sku4", "per",
    "hour", "demand", "answer", "response", "predictor",
}

QUALITY_PATTERN = re.compile(r"defect|label|class|quality|pass|fail|reject|scrap|rework", re.I)
CLASS_LIKE_PATTERN = re.compile(
    r"defect|pass|fail|reject|scrap|rework|quality|status|result|outcome|label|class|grade", re.I
)
IMAGE_COLUMN_PATTERN = re.compile(r"(image|img|photo|picture)[_\s]*(path|file|url|id)?$", re.I)
THROUGHPUT_NAMES = re.compile(r"parts per hour|total parts|entities out|totalproducts|throughput", re.I)
# QC / inspection-vocabulary roles (generic, never dataset-specific):
# defect/fault/scrap/rework/reject/pass/fail counts are output targets;
# units inspected/tested/processed are volume predictors.
QC_RESPONSE_NAMES = re.compile(r"defect|fault|scrap|rework|reject(ed)?|passed|failed|accept(ed)?|ok\b", re.I)
QC_PREDICTOR_NAMES = re.compile(r"units?[_ ]?(inspected|tested|processed|produced|checked|sampled|reviewed)", re.I)
QC_DATE_NAMES = re.compile(r"inspection[_ ]?date|qc[_ ]?date|date|period|week|month\b|shift", re.I)


def _py(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        v = float(value)
        return None if (np.isnan(v) or np.isinf(v)) else round(v, 6)
    if isinstance(value, (np.bool_,)):
        return bool(value)
    if isinstance(value, float):
        return None if (np.isnan(value) or np.isinf(value)) else value
    return value


def _station_metric(name: str) -> tuple[str | None, str | None]:
    metric = None
    for label, rx in METRIC_RULES:
        if rx.search(name):
            metric = label
            break
    if metric is None:
        return None, None

    if name.lower().startswith("c_"):
        rest = name[2:]
        cycle = re.match(r"cycle(\d+)", rest, re.I)
        if cycle:
            return f"Cell{cycle.group(1)}", "cycle_time"
        cell = re.match(r"(cell|press|blanking|paint|quality|forklift|warehouse)[_ ]?(\d*)", rest, re.I)
        if cell:
            number = cell.group(2)
            return (cell.group(1) + number) if number else cell.group(1), "counter"
        return None, "counter"

    tokens = [t for t in STATION_SPLIT.split(name) if t]
    if not tokens:
        return None, metric
    idx = 1 if tokens[0].lower() == "c" and len(tokens) > 1 else 0
    candidate = tokens[idx]
    low = candidate.lower()
    if low in STOP_STATION_TOKENS or low.startswith("sku") or low.startswith("total") or low.startswith("part"):
        return None, metric
    if idx + 1 < len(tokens) and tokens[idx + 1].isdigit():
        candidate = f"{candidate}_{tokens[idx + 1]}"
    return candidate, metric


def classify_column(name: str, series: pd.Series) -> tuple[str, str | None, str | None]:
    low = name.strip().lower()
    nonnull = series.dropna()
    if nonnull.empty:
        return "empty", None, None
    if pd.api.types.is_datetime64_any_dtype(series):
        return "timestamp", None, None
    if low in {"time_now", "time", "timestamp", "datetime"}:
        return "timestamp", None, None

    if pd.api.types.is_object_dtype(series) or pd.api.types.is_string_dtype(series):
        converted = pd.to_numeric(nonnull, errors="coerce")
        if converted.notna().mean() >= 0.6:
            series = converted
            nonnull = converted

    if QC_DATE_NAMES.search(low):
        try:
            pd.to_datetime(nonnull.head(50), errors="raise")
            return "timestamp", None, None
        except (ValueError, TypeError):
            pass

    if THROUGHPUT_NAMES.search(low):
        return "response_candidate", None, None

    station, metric = _station_metric(name)
    if metric:
        return "process_metric", station, metric

    if QC_RESPONSE_NAMES.search(low) and pd.api.types.is_numeric_dtype(series):
        return "response_candidate", None, None
    if QC_PREDICTOR_NAMES.search(low) and pd.api.types.is_numeric_dtype(series):
        return "input_factor", None, None

    if "predictor" in low:
        return "input_factor", None, None
    if re.search(r"demand|arrival|rate", low) and pd.api.types.is_numeric_dtype(series):
        return "input_factor", None, None
    if "response" in low or "answer" in low:
        return "ml_variable", None, None
    if IMAGE_COLUMN_PATTERN.search(low):
        return "image_reference", None, None
    if CLASS_LIKE_PATTERN.search(low) and pd.api.types.is_numeric_dtype(series):
        return "ml_variable", None, None
    if pd.api.types.is_numeric_dtype(series):
        if re.search(r"^va[_\s]*time$", low):
            return "response_candidate", None, None
        return "numeric", None, None
    return "categorical", None, None


def _column_detail(name: str, series: pd.Series, role: str, station: str | None, metric: str | None) -> dict:
    detail: dict[str, Any] = {
        "name": name,
        "dtype": str(series.dtype),
        "role": role,
        "station": station,
        "metric": metric,
        "nulls": int(series.isna().sum()),
        "unique": int(series.nunique(dropna=True)),
    }
    if pd.api.types.is_numeric_dtype(series):
        desc = series.describe()
        detail.update(
            {
                "min": _py(desc.get("min")),
                "max": _py(desc.get("max")),
                "mean": _py(desc.get("mean")),
                "std": _py(desc.get("std")),
            }
        )
    samples = series.dropna().head(3).tolist()
    detail["samples"] = [_py(s) for s in samples]
    return detail


def profile_table(table: Table, max_unique: int = 50) -> dict:
    frame = table.frame
    rows, cols = frame.shape
    columns_detail: list[dict] = []
    stations: dict[str, dict[str, list[str]]] = {}
    role_counts: dict[str, int] = {}
    constants: list[str] = []
    warnings: list[str] = []

    for name in frame.columns:
        series = frame[name]
        role, station, metric = classify_column(str(name), series)
        detail = _column_detail(str(name), series, role, station, metric)
        if detail["unique"] <= max_unique:
            detail["common_values"] = [_py(v) for v in series.dropna().value_counts().head(8).index.tolist()]
        columns_detail.append(detail)
        role_counts[role] = role_counts.get(role, 0) + 1
        if station and metric:
            stations.setdefault(station, {}).setdefault(metric, []).append(str(name))
        if role != "empty" and detail["unique"] == 1:
            constants.append(str(name))

    null_cells = int(frame.isna().sum().sum())
    duplicate_rows = int(frame.duplicated().sum()) if rows <= 700_000 else None

    if constants:
        warnings.append(
            f"{len(constants)} constant column(s) carry no information for analysis: "
            + ", ".join(constants[:8]) + ("..." if len(constants) > 8 else "")
        )
    if role_counts.get("empty"):
        warnings.append(f"{role_counts['empty']} empty column(s) detected (no usable values).")

    numeric = int(frame.select_dtypes(include=[np.number]).shape[1])
    categorical = int(frame.select_dtypes(include=["object", "category", "bool"]).shape[1])
    datetime_cols = int(frame.select_dtypes(include=["datetime"]).shape[1])

    return {
        "name": table.name,
        "source_file": table.source_file,
        "rows": int(rows),
        "columns": int(cols),
        "numeric_columns": numeric,
        "categorical_columns": categorical,
        "datetime_columns": datetime_cols,
        "null_cells": null_cells,
        "null_rate": round(null_cells / (rows * cols), 4) if rows * cols else 0.0,
        "duplicate_rows": duplicate_rows,
        "constant_columns": constants,
        "stations": stations,
        "role_counts": role_counts,
        "columns_detail": columns_detail,
        "warnings": warnings,
    }


def profile_ingest(result: IngestResult) -> list[dict]:
    return [profile_table(t) for t in result.tables]
