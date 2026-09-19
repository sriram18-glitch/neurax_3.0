"""Drift detection on ordered process data.

Methods: rolling mean z-score (EWMA-smoothed) and a CUSUM change-point scan on
each available station/process metric. Only runs when a usable ordering column
exists; otherwise returns DRIFT_ANALYSIS_NOT_SUPPORTED with the reason.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

MAX_DRIFT_COLUMNS = 25
ROLLING_WINDOW = 200
DRIFT_Z_THRESHOLD = 3.0
MIN_ROWS = 500


def _ordered_series(frame: pd.DataFrame, order_column: str, column: str) -> np.ndarray:
    values = pd.to_numeric(frame[column], errors="coerce").to_numpy(dtype="float64")
    order = pd.to_numeric(frame[order_column], errors="coerce").to_numpy(dtype="float64")
    valid = np.isfinite(values) & np.isfinite(order)
    if valid.sum() < MIN_ROWS:
        return np.array([])
    return values[valid][np.argsort(order[valid], kind="stable")]


def detect_drift(
    frame: pd.DataFrame,
    order_column: str | None,
    metric_columns: list[str],
    baseline_frac: float = 0.25,
) -> dict:
    if order_column is None or order_column not in frame.columns:
        return {
            "status": "DRIFT_ANALYSIS_NOT_SUPPORTED",
            "reason": "TEMPORAL_CAUSAL_ORDERING = NOT_AVAILABLE_FROM_DATASET (no usable ordering column)",
            "columns": [],
        }

    results: list[dict] = []
    for column in metric_columns[:MAX_DRIFT_COLUMNS]:
        if column not in frame.columns or not pd.api.types.is_numeric_dtype(frame[column]):
            continue
        series = _ordered_series(frame, order_column, column)
        n = series.size
        if n < MIN_ROWS or np.ptp(series) == 0:
            continue

        baseline_n = max(int(n * baseline_frac), 100)
        baseline = series[:baseline_n]
        baseline_mean = float(baseline.mean())
        baseline_std = float(baseline.std(ddof=0))
        if baseline_std <= 0:
            continue

        # EWMA of the z-score against the baseline
        z = (series - baseline_mean) / baseline_std
        ewma = pd.Series(z).ewm(span=ROLLING_WINDOW, adjust=False).mean().to_numpy()
        peak_abs = float(np.max(np.abs(ewma)))
        peak_position = int(np.argmax(np.abs(ewma)))

        # CUSUM change point on standardised series
        centered = z - z.mean()
        cusum = np.cumsum(centered)
        change_position = int(np.argmax(np.abs(cusum)))

        drift_detected = peak_abs >= DRIFT_Z_THRESHOLD
        results.append(
            {
                "column": column,
                "rows": int(n),
                "baseline_mean": round(baseline_mean, 6),
                "baseline_std": round(baseline_std, 6),
                "peak_ewma_z": round(peak_abs, 4),
                "peak_position": peak_position,
                "change_position": change_position,
                "drift_detected": drift_detected,
                "direction": "increase" if ewma[peak_position] > 0 else "decrease",
            }
        )

    if not results:
        return {
            "status": "DRIFT_ANALYSIS_NOT_SUPPORTED",
            "reason": "no numeric metric columns with enough ordered variation for drift analysis",
            "columns": [],
        }

    drifted = [entry for entry in results if entry["drift_detected"]]
    return {
        "status": "DRIFT_DETECTED" if drifted else "NO_SIGNIFICANT_DRIFT_DETECTED",
        "order_column": order_column,
        "method": "ewma_zscore_vs_baseline + cusum_change_point",
        "configuration": {
            "baseline_fraction": baseline_frac,
            "ewma_span": ROLLING_WINDOW,
            "z_threshold": DRIFT_Z_THRESHOLD,
            "min_rows": MIN_ROWS,
        },
        "columns_analyzed": len(results),
        "columns_drifted": len(drifted),
        "columns": results,
        "note": "Drift means the process statistic shifted relative to its own baseline; it is not a root cause.",
    }
