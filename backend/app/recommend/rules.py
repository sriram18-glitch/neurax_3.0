"""Recommendation rules.

Each rule inspects real upstream evidence and emits a recommendation only when
its required evidence exists. Rules never invent values: every evidence entry
carries the source artifact reference and the epistemic label of the underlying
finding.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone

ENGINE_VERSION = "1.0.0"

EVIDENCE_QUALITY_ORDER = {
    "HIGH_EVIDENCE": 3,
    "MODERATE_EVIDENCE": 2,
    "LIMITED_EVIDENCE": 1,
    "INSUFFICIENT_EVIDENCE": 0,
}


def _recommendation_id(dataset_id: str, action_type: str, target: str, analysis_id: str | None) -> str:
    digest = hashlib.sha256(
        json.dumps(
            {"d": dataset_id, "a": action_type, "t": target, "r": analysis_id},
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()
    return digest[:12]


def _evidence(statement: str, detail: str, source: str, epistemic: str, value=None) -> dict:
    return {
        "statement": statement,
        "detail": detail,
        "source_artifact": source,
        "epistemic_status": epistemic,
        "value": value,
    }


def build_recommendation(
    dataset_id: str,
    action_type: str,
    title: str,
    target: str,
    station: str | None,
    why: str,
    evidence: list[dict],
    assumptions: list[dict],
    simulated_effect: dict | None,
    economic_effect: dict | None,
    limitations: list[str],
    evidence_quality: str,
    source_artifacts: list[str],
    analysis_id: str | None = None,
    data_requirement: bool = False,
) -> dict:
    return {
        "recommendation_id": _recommendation_id(dataset_id, action_type, target, analysis_id),
        "dataset_id": dataset_id,
        "analysis_id": analysis_id,
        "action_type": action_type,
        "title": title,
        "target": target,
        "station": station,
        "priority": None,
        "priority_components": None,
        "evidence_quality": evidence_quality,
        "why": why,
        "evidence": evidence,
        "assumptions": assumptions,
        "simulated_effect": simulated_effect,
        "economic_effect": economic_effect,
        "limitations": limitations,
        "epistemic_status": "ADVISORY",
        "data_requirement": data_requirement,
        "source_artifacts": source_artifacts,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "engine_version": ENGINE_VERSION,
    }


def compute_priority(evidence_quality: str, bottleneck_relevant: bool, has_scenario: bool, has_economics: bool) -> dict:
    """Transparent priority: weighted sum of binary/ordinal components, all persisted."""
    components = {
        "evidence_quality_rank": EVIDENCE_QUALITY_ORDER.get(evidence_quality, 0),
        "bottleneck_relevant": 1 if bottleneck_relevant else 0,
        "has_simulated_scenario": 1 if has_scenario else 0,
        "has_economic_context": 1 if has_economics else 0,
    }
    weights = {
        "evidence_quality_rank": 3.0,
        "bottleneck_relevant": 2.0,
        "has_simulated_scenario": 1.0,
        "has_economic_context": 1.0,
    }
    score = sum(weights[key] * value for key, value in components.items())
    return {
        "score": round(score, 3),
        "components": components,
        "weights": weights,
        "formula": "sum(weight_i * component_i)",
    }


# ---------------------------------------------------------------------------
# Rules
# ---------------------------------------------------------------------------

def rule_high_utilization(dataset_id: str, bottleneck: dict, root_cause: dict | None) -> dict | None:
    candidate = bottleneck.get("candidate_bottleneck") or {}
    station = candidate.get("station")
    if not station:
        return None
    ranking = next((s for s in bottleneck.get("station_rankings", []) if s["station"] == station), None)
    if not ranking:
        return None
    utilization_pressure = (ranking.get("score_components") or {}).get("utilization_pressure")
    if utilization_pressure is None or utilization_pressure < 0.8:
        return None
    quality = (candidate.get("evidence_quality") or {}).get("label", "LIMITED_EVIDENCE")
    utilization = ranking.get("utilization") or {}
    evidence = [
        _evidence(
            f"Station '{station}' shows utilization pressure {utilization_pressure:.2f} (dataset-relative percentile).",
            f"mean utilization {utilization.get('mean')} over {utilization.get('samples')} records",
            "bottleneck/findings",
            "DATA_DERIVED",
            utilization.get("mean"),
        )
    ]
    if root_cause:
        rca_station = next(
            (s for s in root_cause.get("station_ranking", []) if s.get("station") == station), None
        )
        if rca_station and rca_station.get("best_factor"):
            evidence.append(
                _evidence(
                    f"Root-cause analysis associates '{rca_station['best_factor']}' at {station} with the analyzed event.",
                    f"evidence score {rca_station.get('best_score')}",
                    "root_cause/findings",
                    "STATISTICAL_ASSOCIATION",
                    rca_station.get("best_score"),
                )
            )
    return build_recommendation(
        dataset_id,
        "INVESTIGATE_HIGH_UTILIZATION",
        f"Investigate high utilization at {station}",
        target=station,
        station=station,
        why=(
            f"{station} is the highest-ranked station with strong utilization pressure, and the bottleneck analysis "
            "identifies it as the leading candidate constraint. Investigation is advised; the analysis does not prove "
            "that changing this station will change throughput."
        ),
        evidence=evidence,
        assumptions=[{"name": "dataset_station_metrics", "source": "Phase 3", "note": "utilization measured from the uploaded dataset"}],
        simulated_effect=None,
        economic_effect=None,
        limitations=[
            "High utilization alone is not treated as proof of a bottleneck.",
            "Association does not establish causation.",
        ],
        evidence_quality=quality,
        source_artifacts=["bottleneck/findings", "root_cause/findings"] if root_cause else ["bottleneck/findings"],
        analysis_id=bottleneck.get("analysis_id"),
    )


def rule_queue_bottleneck(dataset_id: str, bottleneck: dict) -> dict | None:
    candidate = bottleneck.get("candidate_bottleneck") or {}
    station = candidate.get("station")
    if not station:
        return None
    ranking = next((s for s in bottleneck.get("station_rankings", []) if s["station"] == station), None)
    if not ranking:
        return None
    queue_pressure = (ranking.get("score_components") or {}).get("queue_pressure")
    if queue_pressure is None or queue_pressure < 0.8:
        return None
    queue = ranking.get("queue") or {}
    quality = (candidate.get("evidence_quality") or {}).get("label", "LIMITED_EVIDENCE")
    return build_recommendation(
        dataset_id,
        "INVESTIGATE_QUEUE_BOTTLENECK",
        f"Investigate queue buildup at {station}",
        target=station,
        station=station,
        why=(
            f"{station} carries the highest queue/wait pressure in this dataset and is the leading candidate constraint. "
            "Queue persistence suggests investigating flow balance upstream and downstream of this station."
        ),
        evidence=[
            _evidence(
                f"Queue pressure {queue_pressure:.2f} at '{station}' (dataset-relative percentile).",
                f"mean queue/wait {queue.get('mean')} over {queue.get('samples')} records",
                "bottleneck/findings",
                "DATA_DERIVED",
                queue.get("mean"),
            )
        ],
        assumptions=[{"name": "queue_metric_definition", "source": "Phase 3 profiler", "note": "queue/wait column as detected in the dataset"}],
        simulated_effect=None,
        economic_effect=None,
        limitations=[
            "Queue pressure is dataset-relative and not comparable across datasets.",
            "Blocking/starvation cannot be measured from aggregate counters.",
        ],
        evidence_quality=quality,
        source_artifacts=["bottleneck/findings"],
        analysis_id=bottleneck.get("analysis_id"),
    )


def rule_cycle_time(dataset_id: str, bottleneck: dict) -> dict | None:
    candidate = bottleneck.get("candidate_bottleneck") or {}
    station = candidate.get("station")
    if not station:
        return None
    ranking = next((s for s in bottleneck.get("station_rankings", []) if s["station"] == station), None)
    if not ranking:
        return None
    cycle_pressure = (ranking.get("score_components") or {}).get("cycle_time_pressure")
    if cycle_pressure is None or cycle_pressure < 0.8:
        return None
    cycle = ranking.get("cycle_time") or {}
    return build_recommendation(
        dataset_id,
        "INVESTIGATE_CYCLE_TIME",
        f"Investigate cycle-time reduction at {station}",
        target=station,
        station=station,
        why=(
            f"{station} shows the highest cycle-time pressure among stations with cycle-time data. "
            "Cycle-time reduction is a candidate investigation, not a proven fix."
        ),
        evidence=[
            _evidence(
                f"Cycle-time pressure {cycle_pressure:.2f} at '{station}'.",
                f"mean cycle time {cycle.get('mean')} over {cycle.get('samples')} records",
                "bottleneck/findings",
                "DATA_DERIVED",
                cycle.get("mean"),
            )
        ],
        assumptions=[],
        simulated_effect=None,
        economic_effect=None,
        limitations=["Cycle-time metrics are dataset aggregates, not per-unit process times."],
        evidence_quality="MODERATE_EVIDENCE",
        source_artifacts=["bottleneck/findings"],
        analysis_id=bottleneck.get("analysis_id"),
    )


def rule_drift(dataset_id: str, root_cause: dict | None) -> dict | None:
    if not root_cause:
        return None
    drift = root_cause.get("drift") or {}
    if drift.get("status") != "DRIFT_DETECTED":
        return None
    drifted = [c for c in drift.get("columns", []) if c.get("drift_detected")]
    if not drifted:
        return None
    top = max(drifted, key=lambda c: abs(c.get("peak_ewma_z") or 0))
    return build_recommendation(
        dataset_id,
        "INVESTIGATE_PROCESS_DRIFT",
        f"Investigate process drift in {top['column']}",
        target=top["column"],
        station=None,
        why=(
            f"Drift analysis detected a statistically significant shift in '{top['column']}' "
            f"(peak EWMA z = {top['peak_ewma_z']}, direction {top['direction']}). "
            "The metric moved relative to its own baseline; the cause of the shift is not established."
        ),
        evidence=[
            _evidence(
                f"EWMA z-score crossed the drift threshold for '{top['column']}'.",
                f"method {drift.get('method')}, baseline fraction {((drift.get('configuration') or {}).get('baseline_fraction'))}",
                "root_cause/findings",
                "STATISTICAL_ASSOCIATION",
                top.get("peak_ewma_z"),
            )
        ],
        assumptions=[{"name": "drift_threshold", "source": "Phase 6 configuration", "note": str((drift.get("configuration") or {}).get("z_threshold"))}],
        simulated_effect=None,
        economic_effect=None,
        limitations=[
            "Drift detection compares a metric to its own baseline; it does not identify a cause.",
            "Ordering is record order, not guaranteed wall-clock time.",
        ],
        evidence_quality="MODERATE_EVIDENCE",
        source_artifacts=["root_cause/findings"],
        analysis_id=root_cause.get("analysis_id"),
    )


def rule_anomaly_review(dataset_id: str, bottleneck: dict, root_cause: dict | None) -> dict | None:
    candidate = bottleneck.get("candidate_bottleneck") or {}
    station = candidate.get("station")
    if not station:
        return None
    ranking = next((s for s in bottleneck.get("station_rankings", []) if s["station"] == station), None)
    if not ranking:
        return None
    anomaly = ranking.get("anomaly_evidence") or {}
    if not anomaly.get("available"):
        return None
    rates = anomaly.get("rates") or {}
    if not rates:
        return None
    top = max(rates.values(), key=lambda r: r.get("anomaly_rate") or 0)
    if (top.get("anomaly_rate") or 0) <= 0:
        return None
    return build_recommendation(
        dataset_id,
        "REVIEW_ANOMALOUS_RECORDS",
        f"Review anomalous process records related to {station}",
        target=station,
        station=station,
        why=(
            f"Phase 4 anomaly detection flagged {top['anomalous_rows']} of {top['rows']} scored test records "
            f"({top['anomaly_rate']:.2%}) as anomalous. Reviewing those operating conditions is advised. "
            "Anomaly is an association, not a cause."
        ),
        evidence=[
            _evidence(
                "Anomaly-flagged records exist in the Phase 4 scored sample.",
                f"{top['anomalous_rows']}/{top['rows']} anomalous in {top.get('file')}",
                "predictions/previews",
                "MODEL_CONTRIBUTION",
                top.get("anomaly_rate"),
            )
        ],
        assumptions=[],
        simulated_effect=None,
        economic_effect=None,
        limitations=[
            "Anomaly means unusual in process feature space; it is not a validated defect label.",
            "Anomaly rows are an association, not evidence of a cause.",
        ],
        evidence_quality="LIMITED_EVIDENCE",
        source_artifacts=["predictions/previews"],
        analysis_id=bottleneck.get("analysis_id"),
    )


def rule_scenario(dataset_id: str, scenario: dict | None) -> dict | None:
    if not scenario:
        return None
    economic = scenario.get("economic_output") or {}
    delta = (economic.get("daily_contribution_delta") or {})
    if delta.get("status") != "CALCULATED":
        return None
    station = (scenario.get("bottleneck") or {}).get("station")
    currency = scenario["baseline"]["economics"].get("currency") if scenario.get("baseline") else None
    return build_recommendation(
        dataset_id,
        "EVALUATE_CAPACITY_IMPROVEMENT",
        f"Evaluate the simulated improvement scenario for {station or 'the candidate constraint'}",
        target=station or "candidate_constraint",
        station=station,
        why=(
            "A user-defined scenario was simulated against the observed baseline. The simulated result is shown for "
            "evaluation under the supplied assumptions; it is not a forecast."
        ),
        evidence=[
            _evidence(
                f"Scenario type '{scenario.get('scenario_type')}' was simulated.",
                f"parameter changes: {scenario.get('parameter_changes')}",
                f"economics/scenarios/{scenario.get('scenario_id')}",
                "SIMULATED",
                delta.get("value"),
            ),
            _evidence(
                "Baseline throughput came from observed data.",
                str(scenario.get("baseline", {}).get("throughput_source")),
                "bottleneck/findings",
                "DATA_DERIVED",
                scenario.get("baseline", {}).get("throughput_per_hour"),
            ),
        ],
        assumptions=[
            {
                "name": field,
                "value": (entry or {}).get("value"),
                "unit": (entry or {}).get("unit"),
                "source": (entry or {}).get("source"),
            }
            for field, entry in ((scenario.get("assumptions_snapshot") or {}).get("assumptions") or {}).items()
            if (entry or {}).get("value") is not None
        ],
        simulated_effect={
            "scenario_id": scenario.get("scenario_id"),
            "scenario_type": scenario.get("scenario_type"),
            "units_per_day_delta": (economic.get("units_per_day_delta") or {}).get("value"),
            "daily_contribution_delta": delta.get("value"),
            "monthly_contribution_delta": (economic.get("monthly_contribution_delta") or {}).get("value"),
            "epistemic_status": "SIMULATED",
        },
        economic_effect={
            "currency": currency,
            "daily_contribution_delta": delta.get("value"),
            "monthly_contribution_delta": (economic.get("monthly_contribution_delta") or {}).get("value"),
            "epistemic_status": "SIMULATED + ASSUMPTION-DEPENDENT",
        },
        limitations=scenario.get("limitations", []),
        evidence_quality="MODERATE_EVIDENCE",
        source_artifacts=[f"economics/scenarios/{scenario.get('scenario_id')}", "bottleneck/findings"],
        analysis_id=(scenario.get("bottleneck") or {}).get("analysis_id"),
    )


def rule_data_gap_economics(dataset_id: str, assumptions: dict | None, scenario: dict | None) -> dict | None:
    if scenario and (scenario.get("economic_output") or {}).get("daily_contribution_delta", {}).get("status") == "CALCULATED":
        return None
    if not assumptions:
        # No assumptions file exists yet: every economic field is missing.
        key_fields = ["contribution_margin_per_unit", "working_hours_per_day", "currency"]
    else:
        missing = [
            field
            for field, entry in ((assumptions or {}).get("assumptions") or {}).items()
            if (entry or {}).get("value") is None
        ]
        key_fields = [f for f in missing if f in {"contribution_margin_per_unit", "working_hours_per_day", "currency"}]
    if not key_fields:
        return None
    return build_recommendation(
        dataset_id,
        "REVIEW_DATA_GAP",
        "Provide economic assumptions to quantify impact",
        target="economic_assumptions",
        station=None,
        why=(
            "The dataset contains no economic columns, so economic impact cannot be calculated. "
            "Supplying contribution margin, working hours and currency enables the transparent what-if model."
        ),
        evidence=[
            _evidence(
                "Economic assumptions are missing.",
                f"missing fields: {', '.join(key_fields)}",
                "economics/assumptions.json",
                "USER_ASSUMPTION",
                None,
            )
        ],
        assumptions=[],
        simulated_effect=None,
        economic_effect=None,
        limitations=["No economic values are invented by the system; all require user input."],
        evidence_quality="INSUFFICIENT_EVIDENCE",
        source_artifacts=["economics/assumptions.json"],
        data_requirement=True,
    )


def rule_data_gap_vision(dataset_id: str, vision: dict | None) -> dict | None:
    if not vision or vision.get("available"):
        return None
    return build_recommendation(
        dataset_id,
        "REVIEW_DATA_GAP",
        "Provide visual inspection images to enable vision capabilities",
        target="vision_dataset",
        station=None,
        why=(
            "No image data is available in the current dataset, so defect classification, localization and visual "
            "novelty detection cannot be implemented. Supplying labeled images enables the vision layer."
        ),
        evidence=[
            _evidence(
                "Vision capability is NOT_SUPPORTED for this dataset.",
                str(vision.get("reason")),
                "dataset contract vision block",
                "OBSERVED",
                None,
            )
        ],
        assumptions=[],
        simulated_effect=None,
        economic_effect=None,
        limitations=["Vision status remains NOT_SUPPORTED until a real image dataset is supplied."],
        evidence_quality="INSUFFICIENT_EVIDENCE",
        source_artifacts=["profile.json"],
        data_requirement=True,
    )
