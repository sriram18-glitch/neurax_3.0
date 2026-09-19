"""Transparent evidence scoring.

The evidence score is a documented, weighted average of NORMALISED signals.
Every component is clamped to [0, 1] before weighting, so the score is always
interpretable and bounded:

    evidence_score = 100 * sum(weight_i * component_i) / sum(weight_i over available components)

Components (weights fixed and documented here):
    correlation       0.30   |Spearman rho|
    mutual_information 0.20  MI / (MI + permutation baseline)
    group_difference  0.20   |standardised mean difference| capped at 2.0
    temporal          0.15   1.0 if factor shift precedes event onset, 0.5 if not, 0 if unknown
    anomaly           0.10   min(enrichment, 3.0) / 3.0
    model_contribution 0.05  importance / max importance among factors

Only available components participate in the denominator. If fewer than two
components are available the factor is reported but marked INSUFFICIENT_EVIDENCE.
"""

from __future__ import annotations

WEIGHTS = {
    "correlation": 0.30,
    "mutual_information": 0.20,
    "group_difference": 0.20,
    "temporal": 0.15,
    "anomaly": 0.10,
    "model_contribution": 0.05,
}

MIN_COMPONENTS_FOR_SCORE = 2


def _correlation_component(signal: dict) -> float | None:
    if not signal.get("available"):
        return None
    rho = signal.get("spearman_r")
    return None if rho is None else min(abs(float(rho)), 1.0)


def _mi_component(signal: dict) -> float | None:
    if not signal.get("available"):
        return None
    mi = float(signal.get("mi") or 0.0)
    baseline = float(signal.get("mi_permutation_baseline") or 0.0)
    if mi <= 0:
        return 0.0
    return mi / (mi + baseline) if (mi + baseline) > 0 else 0.0


def _group_component(signal: dict) -> float | None:
    if not signal.get("available"):
        return None
    effect = abs(float(signal.get("standardized_effect") or 0.0))
    return min(effect / 2.0, 1.0)


def _temporal_component(signal: dict) -> float | None:
    if not signal.get("available"):
        return None
    precedes = signal.get("factor_shift_precedes_event_onset")
    if precedes is None:
        return 0.0
    return 1.0 if precedes else 0.5


def _anomaly_component(signal: dict) -> float | None:
    if not signal.get("available"):
        return None
    enrichment = signal.get("enrichment")
    if enrichment is None:
        return 0.0
    return min(float(enrichment), 3.0) / 3.0


def _model_component(importance_value: float | None, max_importance: float | None) -> float | None:
    if importance_value is None or max_importance is None or max_importance <= 0:
        return None
    return min(float(importance_value) / float(max_importance), 1.0)


def score_factor(
    correlation: dict,
    mutual_information: dict,
    group_difference: dict,
    temporal: dict,
    anomaly: dict,
    importance_value: float | None,
    max_importance: float | None,
) -> dict:
    components = {
        "correlation": _correlation_component(correlation),
        "mutual_information": _mi_component(mutual_information),
        "group_difference": _group_component(group_difference),
        "temporal": _temporal_component(temporal),
        "anomaly": _anomaly_component(anomaly),
        "model_contribution": _model_component(importance_value, max_importance),
    }
    available = {name: value for name, value in components.items() if value is not None}

    if len(available) < MIN_COMPONENTS_FOR_SCORE:
        return {
            "score": None,
            "status": "INSUFFICIENT_EVIDENCE",
            "components": {name: (round(value, 4) if value is not None else None) for name, value in components.items()},
            "weights": WEIGHTS,
            "available_components": len(available),
            "formula": "100 * sum(weight_i * component_i) / sum(weight_i over available components)",
        }

    numerator = sum(WEIGHTS[name] * value for name, value in available.items())
    denominator = sum(WEIGHTS[name] for name in available)
    return {
        "score": round(100.0 * numerator / denominator, 3),
        "status": "SCORED",
        "components": {name: (round(value, 4) if value is not None else None) for name, value in components.items()},
        "weights": WEIGHTS,
        "available_components": len(available),
        "formula": "100 * sum(weight_i * component_i) / sum(weight_i over available components)",
    }


def status_for_score(score: float | None) -> str:
    if score is None:
        return "INSUFFICIENT_EVIDENCE"
    if score >= 60:
        return "STRONG_ASSOCIATION"
    if score >= 40:
        return "MODERATE_ASSOCIATION"
    if score >= 20:
        return "WEAK_ASSOCIATION"
    return "MINIMAL_ASSOCIATION"


def build_explanation(factor: str, target: str, event: dict, signals: dict, score: dict, station: str | None) -> str:
    parts: list[str] = []
    direction = event.get("direction")
    event_word = "low" if direction == "low" else "high"
    correlation = signals.get("correlation") or {}
    group = signals.get("group_difference") or {}
    temporal = signals.get("temporal") or {}
    anomaly = signals.get("anomaly") or {}

    if correlation.get("available"):
        rho = correlation.get("spearman_r")
        relation = "higher" if (rho or 0) > 0 else "lower"
        parts.append(
            f"'{factor}' shows a {'positive' if (rho or 0) > 0 else 'negative'} monotonic association "
            f"with '{target}' (Spearman rho={rho}); {relation} values of the factor accompany "
            f"{event_word} target values."
        )
    if group.get("available"):
        parts.append(
            f"During {event_word}-target events its mean is {group['event_mean']:.6g} vs "
            f"{group['non_event_mean']:.6g} otherwise (standardised difference {group['standardized_effect']})."
        )
    if temporal.get("available") and temporal.get("factor_shift_precedes_event_onset") is not None:
        if temporal["factor_shift_precedes_event_onset"]:
            parts.append("In record order, the factor shift occurs at or before the first sustained event onset.")
        else:
            parts.append("In record order, the factor shift does not precede the event onset.")
    if anomaly.get("available") and anomaly.get("enrichment") is not None:
        parts.append(
            f"Event rate inside anomaly-flagged rows is {anomaly['event_rate_in_anomalies']:.2%} "
            f"versus {anomaly['event_rate_overall']:.2%} overall (enrichment {anomaly['enrichment']})."
        )
    if score.get("score") is not None:
        parts.append(f"Combined evidence score {score['score']} ({status_for_score(score['score'])}).")
    if station:
        parts.append(f"Factor belongs to station '{station}'.")
    parts.append("Association does not establish causation.")
    return " ".join(parts)
