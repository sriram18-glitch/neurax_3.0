"""Station-level aggregation from actual detected station columns.

Unavailable metrics are represented explicitly with
{"available": false, "reason": "NOT AVAILABLE FROM DATASET"} - no fabricated
numbers are ever emitted.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .columns import collect_station_columns

NOT_AVAILABLE = {"available": False, "reason": "NOT AVAILABLE FROM DATASET"}

TRACKED_METRICS = ("utilization", "queue_wait", "wip_storage", "cycle_time", "throughput")
MISSING_METRIC_LABELS = {
    "utilization": "utilization",
    "queue_wait": "queue",
    "wip_storage": "wip",
    "cycle_time": "cycle time",
    "throughput": "throughput",
    "capacity": "capacity indicators",
    "response_stats": "station response statistics",
}


def _stats_from_frame(frame: pd.DataFrame, columns: list[str], detail: bool = False) -> dict | None:
    values = frame[columns].apply(pd.to_numeric, errors="coerce").to_numpy(dtype="float64").ravel()
    values = values[~np.isnan(values)]
    if values.size == 0:
        return None
    stats = {
        "mean": round(float(values.mean()), 6),
        "max": round(float(values.max()), 6),
        "samples": int(values.size),
    }
    if detail:
        stats["min"] = round(float(values.min()), 6)
        stats["std"] = round(float(values.std(ddof=0)), 6)
    return stats


def _dataset_output_stats(frame: pd.DataFrame, profile: dict) -> dict:
    roles = {c["name"]: c for c in profile["columns_detail"]}
    outputs = [
        str(c)
        for c in frame.columns
        if roles.get(str(c), {}).get("role") in {"response_candidate", "ml_variable"}
        or roles.get(str(c), {}).get("metric") == "throughput"
    ]
    stats: dict[str, dict] = {}
    for column in outputs:
        values = frame[column].apply(pd.to_numeric, errors="coerce").dropna()
        if values.empty:
            continue
        stats[column] = {
            "available": True,
            "mean": round(float(values.mean()), 6),
            "max": round(float(values.max()), 6),
            "min": round(float(values.min()), 6),
            "samples": int(values.size),
        }
    return {
        "output_columns": outputs,
        "stats": stats if stats else NOT_AVAILABLE,
        "note": "Dataset-level output/response columns; not attributed to a specific station.",
    }


def build_station_metrics(table_name: str | None, frame: pd.DataFrame | None, profile: dict | None) -> dict:
    if frame is None or profile is None or frame.empty:
        return {
            "table": None,
            "station_count": 0,
            "stations": [],
            "dataset_level": {"output_columns": [], "stats": NOT_AVAILABLE, "note": None},
            "note": "No station or cell identifiers were detected in this dataset.",
        }

    stations_columns = collect_station_columns(frame, profile)
    entries: list[dict] = []

    for station in sorted(stations_columns):
        metrics = stations_columns[station]
        entry: dict = {
            "station_id": station,
            "sources": {metric: sorted(columns) for metric, columns in sorted(metrics.items())},
        }
        available_metrics = 0
        for metric in TRACKED_METRICS:
            columns = metrics.get(metric, [])
            stats = _stats_from_frame(frame, columns) if columns else None
            if stats:
                entry[metric] = {"available": True, **stats}
                available_metrics += 1
            else:
                entry[metric] = dict(NOT_AVAILABLE)

        entry["capacity"] = {
            "available": False,
            "reason": "NOT AVAILABLE FROM DATASET",
            "note": "No capacity/rate specification columns detected.",
        }
        entry["response_stats"] = {
            "available": False,
            "reason": "NOT AVAILABLE FROM DATASET",
            "note": "Response variables in this dataset are dataset-level, not per-station.",
        }

        tracked = 7
        entry["data_coverage"] = {
            "available_metrics": available_metrics,
            "tracked_metrics": tracked,
            "fraction": round(available_metrics / tracked, 3),
        }
        missing = [MISSING_METRIC_LABELS[m] for m in TRACKED_METRICS if not entry[m]["available"]]
        entry["warnings"] = (
            [f"Missing metrics: {', '.join(missing)}."] if missing else []
        )
        entries.append(entry)

    return {
        "table": table_name,
        "station_count": len(entries),
        "metric_labels": MISSING_METRIC_LABELS,
        "stations": entries,
        "dataset_level": _dataset_output_stats(frame, profile),
        "note": (
            None
            if entries
            else "No station or cell identifiers were detected in this dataset."
        ),
    }
