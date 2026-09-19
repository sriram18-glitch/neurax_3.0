"""Throughput impact: observed comparison only.

The engine compares observed throughput (or the closest available output
column) between constrained and unconstrained operating conditions, where
"constrained" is defined by the top-quartile of the candidate bottleneck's
utilization. This is an OBSERVED COMPARISON, not a simulation and not a
predicted improvement.

Simulated impact is explicitly NOT_AVAILABLE_FROM_DATASET here; it belongs to
the future simulation phase.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

MIN_GROUP_ROWS = 30


def throughput_impact(
    frame: pd.DataFrame,
    station: str,
    utilization_column: str | None,
    output_columns: list[str],
) -> dict:
    available_outputs = [c for c in output_columns if c in frame.columns and pd.api.types.is_numeric_dtype(frame[c])]
    if not available_outputs:
        return {
            "status": "NOT_AVAILABLE_FROM_DATASET",
            "reason": "no numeric throughput/output column exists in the source table",
            "observed": None,
            "estimated_impact": None,
            "simulated_impact": "NOT_YET_SIMULATED",
        }
    if utilization_column is None or utilization_column not in frame.columns:
        return {
            "status": "NOT_AVAILABLE_FROM_DATASET",
            "reason": f"no utilization column available for station '{station}'; constrained/unconstrained grouping is not possible",
            "observed": None,
            "estimated_impact": None,
            "simulated_impact": "NOT_YET_SIMULATED",
        }

    utilization = pd.to_numeric(frame[utilization_column], errors="coerce")
    valid_util = utilization.dropna()
    if valid_util.size < MIN_GROUP_ROWS * 2:
        return {
            "status": "INSUFFICIENT_DATA",
            "reason": f"only {valid_util.size} utilization values; at least {MIN_GROUP_ROWS * 2} required",
            "observed": None,
            "estimated_impact": None,
            "simulated_impact": "NOT_YET_SIMULATED",
        }

    threshold = float(valid_util.quantile(0.75))
    constrained = utilization >= threshold
    unconstrained = utilization < threshold

    observed: dict[str, dict] = {}
    for column in available_outputs[:3]:
        values = pd.to_numeric(frame[column], errors="coerce")
        high = values[constrained].dropna()
        low = values[unconstrained].dropna()
        if high.size < MIN_GROUP_ROWS or low.size < MIN_GROUP_ROWS:
            continue
        high_mean = float(high.mean())
        low_mean = float(low.mean())
        observed[column] = {
            "output_column": column,
            "constrained_mean": round(high_mean, 6),
            "unconstrained_mean": round(low_mean, 6),
            "difference": round(high_mean - low_mean, 6),
            "relative_difference": round((high_mean - low_mean) / low_mean, 6) if low_mean != 0 else None,
            "constrained_rows": int(high.size),
            "unconstrained_rows": int(low.size),
            "constrained_definition": f"{utilization_column} >= {threshold:.6g} (75th percentile)",
        }

    if not observed:
        return {
            "status": "INSUFFICIENT_DATA",
            "reason": "one of the constrained/unconstrained groups had fewer than 30 rows for every output column",
            "observed": None,
            "estimated_impact": None,
            "simulated_impact": "NOT_YET_SIMULATED",
        }

    return {
        "status": "OBSERVED_COMPARISON",
        "station": station,
        "utilization_column": utilization_column,
        "threshold": round(threshold, 6),
        "observed": observed,
        "estimated_impact": None,
        "simulated_impact": "NOT_YET_SIMULATED",
        "epistemic_status": "OBSERVED COMPARISON - not a simulation and not a predicted improvement",
        "note": (
            "Difference between observed output under high vs low station utilization. "
            "This is an association in the recorded data, not a guaranteed effect of relieving the station."
        ),
        "limitations": [
            "Confounded by demand: high utilization often co-occurs with high demand.",
            "No counterfactual or interventional computation was performed.",
        ],
    }
