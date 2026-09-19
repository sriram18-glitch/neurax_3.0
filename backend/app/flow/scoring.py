"""Transparent bottleneck evidence scoring.

A station is scored on the evidence components that actually exist for it.
No single metric decides the bottleneck; the top-utilization station is never
declared a bottleneck on utilization alone.

Components (weights fixed and documented):
    utilization_pressure   0.28   percentile of station mean utilization across stations
    queue_pressure         0.24   percentile of station mean queue/wait across stations
    cycle_time_pressure    0.14   percentile of station mean cycle time across stations
    throughput_constraint  0.14   inverse percentile of station throughput (low throughput = pressure)
    root_cause_evidence    0.12   Phase 6 best evidence score for factors mapped to the station
    anomaly_evidence       0.08   Phase 6 anomaly enrichment for factors mapped to the station

Percentiles are computed within the dataset's own station set (rank / (n-1)),
so the score is dataset-relative, not an absolute claim. Components are only
included when their underlying metric exists; the denominator covers available
components only. A station with fewer than 2 available components cannot be
scored (INSUFFICIENT_EVIDENCE).
"""

from __future__ import annotations

WEIGHTS = {
    "utilization_pressure": 0.28,
    "queue_pressure": 0.24,
    "cycle_time_pressure": 0.14,
    "throughput_constraint": 0.14,
    "root_cause_evidence": 0.12,
    "anomaly_evidence": 0.08,
}

MIN_COMPONENTS_FOR_SCORE = 2
CONSISTENT_THRESHOLD = 0.5


def percentile_rank(values: dict[str, float], station: str) -> float | None:
    """Rank-based percentile of `station` among stations (0 = lowest, 1 = highest)."""
    if station not in values:
        return None
    ordered = sorted(values.values())
    n = len(ordered)
    if n <= 1:
        return 1.0
    rank = ordered.index(values[station])
    # ties: use the highest position so ties do not understate pressure
    rank = max(index for index, value in enumerate(ordered) if value == values[station])
    return rank / (n - 1)


def score_station(components: dict[str, float | None]) -> dict:
    available = {name: value for name, value in components.items() if value is not None}
    if len(available) < MIN_COMPONENTS_FOR_SCORE:
        return {
            "score": None,
            "status": "INSUFFICIENT_EVIDENCE",
            "components": {name: (round(value, 4) if value is not None else None) for name, value in components.items()},
            "weights": WEIGHTS,
            "available_components": len(available),
            "consistency": None,
            "formula": "100 * sum(weight_i * component_i) / sum(weight_i over available components)",
        }
    numerator = sum(WEIGHTS[name] * value for name, value in available.items())
    denominator = sum(WEIGHTS[name] for name in available)
    high = sum(1 for value in available.values() if value >= CONSISTENT_THRESHOLD)
    low = len(available) - high
    consistency = max(high, low) / len(available)
    return {
        "score": round(100.0 * numerator / denominator, 3),
        "status": "SCORED",
        "components": {name: (round(value, 4) if value is not None else None) for name, value in components.items()},
        "weights": WEIGHTS,
        "available_components": len(available),
        "consistency": round(consistency, 4),
        "formula": "100 * sum(weight_i * component_i) / sum(weight_i over available components)",
    }


def evidence_quality(score: dict, sample_size: int, single_station: bool) -> dict:
    if score["status"] != "SCORED":
        return {
            "label": "INSUFFICIENT_EVIDENCE",
            "reason": f"only {score['available_components']} evidence component(s) available; at least {MIN_COMPONENTS_FOR_SCORE} required",
        }
    components = score["available_components"]
    consistency = score.get("consistency") or 0.0
    if single_station:
        return {
            "label": "LIMITED_EVIDENCE",
            "reason": "dataset contains a single station; cross-station comparison is not possible",
        }
    if sample_size < 200:
        return {
            "label": "LIMITED_EVIDENCE",
            "reason": f"only {sample_size} samples; below the 200-sample reliability floor",
        }
    if components >= 4 and consistency >= 0.75:
        return {
            "label": "HIGH_EVIDENCE",
            "reason": f"{components} components available with {consistency:.0%} directional consistency",
        }
    if components >= 3 and consistency >= 0.6:
        return {
            "label": "MODERATE_EVIDENCE",
            "reason": f"{components} components available with {consistency:.0%} directional consistency",
        }
    return {
        "label": "LIMITED_EVIDENCE",
        "reason": f"{components} components available with {consistency:.0%} directional consistency",
    }


def station_status(rank: int, score: dict, quality: dict) -> str:
    if score["status"] != "SCORED":
        return "INSUFFICIENT_EVIDENCE"
    if rank == 1 and quality["label"] in {"HIGH_EVIDENCE", "MODERATE_EVIDENCE"} and score["score"] >= 40:
        return "CANDIDATE_BOTTLENECK"
    if quality["label"] == "INSUFFICIENT_EVIDENCE":
        return "INSUFFICIENT_EVIDENCE"
    if score["score"] >= 40:
        return "POSSIBLE_CONTRIBUTOR"
    return "NOT_CONSTRAINED"
