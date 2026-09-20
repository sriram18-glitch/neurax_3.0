"""Process timeline for the control-room visualization.

Builds binned series from the REAL processed-data artifact: utilization and
queue means per station, drift markers from the stored root-cause analysis and
event markers where the analyzed target crosses its stored event threshold.
Everything is aggregated server-side; the browser never receives raw rows.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from ..pipeline.artifacts import sanitize_name

MAX_STATIONS = 4
# (metric id, unit, column-name aliases) - matched case-insensitively together
# with the station name, so real column conventions like "Assembly Util" or
# "Drilling Waiting Time" are recognized without hardcoding a dataset.
METRIC_PATTERNS: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    ("utilization", "ratio", ("utilization", "utilisation", "util")),
    ("queue", "time", ("queue", "waiting")),
    ("cycle", "time", ("cycle", "va time", "processing time")),
    ("throughput", "units", ("throughput", "parts per hour", "output rate")),
)


def _manifest_names(artifact_root: Path) -> list[str]:
    path = artifact_root / "processed_data" / "manifest.json"
    if not path.exists():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return []
    if isinstance(payload, dict):
        return list(payload.keys())
    return []


def resolve_table(artifact_root: Path, preferred: str | None) -> tuple[str | None, pd.DataFrame | None]:
    names: list[str] = []
    if preferred:
        names.append(preferred)
    names.extend(name for name in _manifest_names(artifact_root) if name not in names)
    for name in names:
        path = artifact_root / "processed_data" / f"{sanitize_name(name)}.csv.gz"
        if path.exists():
            return name, pd.read_csv(path)
    return None, None


def _find_column(frame: pd.DataFrame, station: str, aliases: tuple[str, ...]) -> str | None:
    for alias in aliases:
        for column in frame.columns:
            lowered = str(column).lower()
            if station.lower() in lowered and alias in lowered:
                return str(column)
    return None


def build_timeline(
    dataset_id: str,
    artifact_root: Path,
    *,
    stations: list[str] | None = None,
    preferred_table: str | None = None,
    bins: int = 48,
) -> dict:
    artifact_root = Path(artifact_root)
    table_name, frame = resolve_table(artifact_root, preferred_table)
    if frame is None:
        return {
            "dataset_id": dataset_id,
            "status": "NOT_AVAILABLE",
            "reason": "No processed-data artifact is stored for this dataset yet.",
            "series": [],
            "drift_markers": [],
            "event_markers": [],
        }

    bins = max(8, min(int(bins), 120))
    station_names = [str(name) for name in (stations or [])][:MAX_STATIONS]
    series: list[dict] = []
    for station in station_names:
        for metric_id, unit, aliases in METRIC_PATTERNS:
            column = _find_column(frame, station, aliases)
            if column is None:
                continue
            values = pd.to_numeric(frame[column], errors="coerce")
            if values.notna().sum() < bins:
                continue
            binned = values.groupby(np.arange(len(values)) // max(1, len(values) // bins)).mean().dropna()
            series.append(
                {
                    "station": station,
                    "metric": metric_id,
                    "unit": unit,
                    "column": column,
                    "values": [round(float(value), 4) for value in binned.to_numpy()],
                }
            )
            break  # one metric per station keeps the payload small; utilization preferred

    drift_markers: list[dict] = []
    event_markers: list[dict] = []
    event_definition: dict | None = None
    root_cause_dir = artifact_root / "root_cause"
    if root_cause_dir.exists():
        analyses = sorted(root_cause_dir.glob("rca_*.json"))
        if analyses:
            try:
                payload = json.loads(analyses[-1].read_text(encoding="utf-8"))
            except Exception:  # noqa: BLE001
                payload = {}
            drift = payload.get("drift") or {}
            rows = int(frame.shape[0]) or 1
            for column_info in (drift.get("columns") or [])[:4]:
                if not column_info.get("drift_detected"):
                    continue
                position = int(column_info.get("change_position") or 0)
                drift_markers.append(
                    {
                        "column": column_info.get("column"),
                        "bin": int(round((position / rows) * bins)),
                        "direction": column_info.get("direction"),
                        "peak_ewma_z": column_info.get("peak_ewma_z"),
                        "epistemic": "STATISTICAL ASSOCIATION",
                    }
                )
            event = payload.get("event") or {}
            target = event.get("target")
            threshold = event.get("threshold")
            direction = event.get("direction")
            if target and threshold is not None and target in frame.columns:
                values = pd.to_numeric(frame[target], errors="coerce")
                mask = values <= threshold if direction == "low" else values >= threshold
                hit_bins = sorted(set((np.flatnonzero(mask.fillna(False).to_numpy()) // max(1, rows // bins)).tolist()))
                event_markers = [{"bin": int(hit), "label": f"{target} {direction} tail"} for hit in hit_bins[:60]]
                event_definition = {
                    "target": target,
                    "direction": direction,
                    "threshold": threshold,
                    "definition": event.get("definition"),
                    "epistemic": "OBSERVED",
                }

    return {
        "dataset_id": dataset_id,
        "status": "AVAILABLE",
        "table": table_name,
        "bins": bins,
        "order_basis": "recorded row order of the processed dataset (sequence position, not wall-clock time)",
        "series": series,
        "drift_markers": drift_markers,
        "event_markers": event_markers,
        "event_definition": event_definition,
        "note": "Series are server-side aggregates of the real processed data; the browser never receives raw rows.",
        "limitations": [
            "Row order follows the dataset's recorded sequence; no wall-clock timestamps are assumed.",
            "Only stations with a recognizable utilization/queue/cycle column are plotted.",
        ],
    }
