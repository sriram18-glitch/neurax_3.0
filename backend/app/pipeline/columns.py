from __future__ import annotations

import re

import pandas as pd

_BASE_RE = re.compile(r"[_ ]?\d+$")


def collect_station_columns(frame: pd.DataFrame, profile: dict) -> dict[str, dict[str, list[str]]]:
    """Map station -> metric -> source column names using the profiled roles."""
    roles = {c["name"]: c for c in profile["columns_detail"]}
    stations: dict[str, dict[str, list[str]]] = {}
    for column in frame.columns:
        info = roles.get(str(column))
        if not info:
            continue
        station, metric = info.get("station"), info.get("metric")
        if station and metric:
            stations.setdefault(station, {}).setdefault(metric, []).append(str(column))
    return stations


def base_station_name(station: str) -> str:
    return _BASE_RE.sub("", station) or station
