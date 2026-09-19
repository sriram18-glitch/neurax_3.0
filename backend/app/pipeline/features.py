"""Feature engineering.

Derived features are created only from columns that actually exist and only
according to rules that are meaningful for the detected roles/metrics. Every
derived feature carries metadata: source columns, calculation, description,
unit. Candidate derivations that cannot be justified are recorded as skipped
with a reason - never silently invented.
"""

from __future__ import annotations

import re

import numpy as np
import pandas as pd

from .columns import base_station_name, collect_station_columns


def _sum_series(frame: pd.DataFrame, columns: list[str]) -> pd.Series:
    return frame[columns].sum(axis=1, min_count=1)


def _mean_series(frame: pd.DataFrame, columns: list[str]) -> pd.Series:
    return frame[columns].mean(axis=1)


def build_features(table_name: str, frame: pd.DataFrame, profile: dict) -> tuple[pd.DataFrame, list[dict], list[dict]]:
    derived: list[dict] = []
    skipped: list[dict] = []
    df = frame.copy()
    stations = collect_station_columns(frame, profile)

    utilization_columns = sorted(
        {col for metrics in stations.values() for col in metrics.get("utilization", [])}
    )
    queue_columns = sorted(
        {col for metrics in stations.values() for col in metrics.get("queue_wait", [])}
    )

    def add(name: str, sources: list[str], calculation: str, description: str, unit: str, values: pd.Series) -> None:
        if name in df.columns or any(col not in frame.columns for col in sources):
            return
        numeric = pd.to_numeric(values, errors="coerce")
        if np.isinf(numeric.to_numpy(dtype="float64", na_value=np.nan)).any():
            skipped.append({"feature": name, "reason": "computation produced infinite values"})
            return
        df[name] = numeric
        derived.append(
            {
                "name": name,
                "table": table_name,
                "source_columns": sources,
                "calculation": calculation,
                "description": description,
                "unit": unit,
            }
        )

    # dataset-wide aggregations ------------------------------------------------
    if len(utilization_columns) >= 2:
        add(
            "utilization_mean",
            utilization_columns,
            f"mean({', '.join(utilization_columns)})",
            "Mean of all detected station utilization columns.",
            "ratio",
            _mean_series(frame, utilization_columns),
        )
        add(
            "utilization_spread",
            utilization_columns,
            f"max({', '.join(utilization_columns)}) - min({', '.join(utilization_columns)})",
            "Spread between the most and least utilized station.",
            "ratio",
            frame[utilization_columns].max(axis=1) - frame[utilization_columns].min(axis=1),
        )
    else:
        skipped.append({"feature": "utilization_spread", "reason": "fewer than 2 utilization columns detected"})

    if len(queue_columns) >= 2:
        add(
            "queue_load_total",
            queue_columns,
            "sum(" + " + ".join(queue_columns) + ")",
            "Total queue load across all detected queue columns.",
            "parts",
            _sum_series(frame, queue_columns),
        )
    else:
        skipped.append({"feature": "queue_load_total", "reason": "fewer than 2 queue/wait columns detected"})

    # base-station groups (Press1..4 -> Press) ---------------------------------
    groups: dict[str, dict[str, object]] = {}
    for station, metrics in stations.items():
        base = base_station_name(station)
        entry = groups.setdefault(base, {"stations": set(), "util": [], "queue": []})
        entry["stations"].add(station)
        for column in metrics.get("utilization", []):
            if column not in entry["util"]:
                entry["util"].append(column)
        for column in metrics.get("queue_wait", []):
            if column not in entry["queue"]:
                entry["queue"].append(column)

    for base, entry in sorted(groups.items()):
        if len(entry["stations"]) < 2:
            continue
        util = sorted(entry["util"])
        queue = sorted(entry["queue"])
        if len(util) >= 2:
            add(
                f"{base}_utilization_mean",
                util,
                f"mean({', '.join(util)})",
                f"Mean utilization across the {base} group stations.",
                "ratio",
                _mean_series(frame, util),
            )
            add(
                f"{base}_utilization_spread",
                util,
                f"max({', '.join(util)}) - min({', '.join(util)})",
                f"Utilization imbalance across the {base} group stations.",
                "ratio",
                frame[util].max(axis=1) - frame[util].min(axis=1),
            )
        if len(queue) >= 2:
            add(
                f"{base}_queue_total",
                queue,
                "sum(" + " + ".join(queue) + ")",
                f"Total queue load across the {base} group stations.",
                "parts",
                _sum_series(frame, queue),
            )

    # SKU time composition totals ------------------------------------------------
    roles = {c["name"]: c for c in profile["columns_detail"]}
    sku_columns: dict[str, list[str]] = {}
    for column in frame.columns:
        info = roles.get(str(column))
        if info and info.get("metric") == "time_composition":
            match = re.match(r"(sku\d+)[_\s]", str(column), re.I)
            if match:
                sku_columns.setdefault(match.group(1).upper(), []).append(str(column))
    for sku, columns in sorted(sku_columns.items()):
        if len(columns) >= 2:
            add(
                f"{sku}_time_total",
                columns,
                "sum(" + " + ".join(columns) + ")",
                f"Total reported time across {sku} time components.",
                "dataset time units",
                _sum_series(frame, columns),
            )

    # rolling statistics only when an ordered time base exists --------------------
    time_columns = [str(c) for c in frame.columns if roles.get(str(c), {}).get("role") == "timestamp"]
    usable_time = [
        c
        for c in time_columns
        if frame[c].nunique(dropna=True) > 10 and frame[c].is_monotonic_increasing
    ]
    if not usable_time:
        skipped.append(
            {
                "feature": "rolling utilization statistics",
                "reason": "no monotonic timestamp column with variation in this table",
            }
        )
    else:
        for column in utilization_columns[:8]:
            add(
                f"{column}_rolling_mean_20",
                [column],
                f"rolling mean of '{column}' over previous 20 records ordered by {usable_time[0]}",
                "Short-term rolling utilization level (past-window only, no future leakage).",
                "ratio",
                frame[column].rolling(window=20, min_periods=1).mean(),
            )

    return df, derived, skipped
