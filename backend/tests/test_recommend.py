"""Phase 9 test suite: evidence-backed recommendation engine.

Synthetic tests plant specific evidence configurations to validate rule
activation/suppression. Real-data verification lives in verify_phase9_real.py.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from app.recommend import (
    find_violations,
    generate_recommendations,
    get_decision_summary,
    get_recommendation,
    list_recommendations,
    validate_recommendation,
)
from app.recommend.rules import compute_priority
from app.pipeline.artifacts import write_json


# ---------------------------------------------------------------------------
# Synthetic artifact builders
# ---------------------------------------------------------------------------

def _bottleneck_artifact(
    station: str = "StationB",
    utilization_pressure: float = 1.0,
    queue_pressure: float = 1.0,
    cycle_pressure: float | None = None,
    quality: str = "HIGH_EVIDENCE",
    with_anomaly: bool = False,
    with_observed: bool = True,
) -> dict:
    components = {
        "utilization_pressure": utilization_pressure,
        "queue_pressure": queue_pressure,
        "cycle_time_pressure": cycle_pressure,
        "throughput_constraint": None,
        "root_cause_evidence": None,
        "anomaly_evidence": None,
    }
    ranking = {
        "station": station,
        "rank": 1,
        "evidence_score": 90.0,
        "status": "CANDIDATE_BOTTLENECK",
        "score_components": components,
        "utilization": {"available": True, "mean": 0.95, "max": 0.99, "samples": 500},
        "queue": {"available": True, "mean": 60.0, "max": 80.0, "samples": 500},
        "cycle_time": {"available": cycle_pressure is not None, "mean": 12.0, "samples": 500}
        if cycle_pressure is not None
        else {"available": False, "reason": "NOT AVAILABLE FROM DATASET"},
        "anomaly_evidence": {
            "available": with_anomaly,
            "rates": {"preview": {"file": "preview.csv.gz", "rows": 200, "anomalous_rows": 8, "anomaly_rate": 0.04}}
            if with_anomaly
            else {},
        },
    }
    observed = (
        {
            "observed": {
                "Units": {
                    "output_column": "Units",
                    "constrained_mean": 900.0,
                    "unconstrained_mean": 1000.0,
                    "difference": -100.0,
                }
            }
        }
        if with_observed
        else {"observed": None}
    )
    return {
        "dataset_id": "synth",
        "analysis_id": "bn1234567890",
        "status": "complete",
        "candidate_bottleneck": {
            "station": station,
            "evidence_score": 90.0,
            "evidence_quality": {"label": quality, "reason": "synthetic"},
            "status": "CANDIDATE_BOTTLENECK",
            "why": ["utilization_pressure: 1.0"],
            "unavailable_metrics": [],
        },
        "station_rankings": [ranking],
        "stations_analyzed": 3,
        "flow": {"graph": {"status": "SUPPORTED"}, "blocking_starvation": {}},
        "what_if_inputs": {
            "station": station,
            "current_utilization": {"available": True, "mean": 0.95, "samples": 500},
            "current_queue": {"available": True, "mean": 60.0, "samples": 500},
            "current_cycle_time": {"available": False, "reason": "NOT AVAILABLE FROM DATASET"},
            "observed_impact": observed,
            "throughput": None,
        },
    }


def _root_cause_artifact(
    station: str = "StationB",
    factor: str = "StationB_Util",
    drift_status: str = "NO_SIGNIFICANT_DRIFT_DETECTED",
) -> dict:
    drift_columns = (
        [{"column": factor, "drift_detected": True, "peak_ewma_z": 4.2, "direction": "increase", "change_position": 100}]
        if drift_status == "DRIFT_DETECTED"
        else []
    )
    return {
        "dataset_id": "synth",
        "analysis_id": "rc1234567890",
        "status": "complete",
        "target": {"target": "Units"},
        "station_ranking": [
            {"station": station, "factors": 2, "best_score": 95.0, "best_factor": factor, "ranked_factors": []}
        ],
        "drift": {
            "status": drift_status,
            "method": "ewma_zscore_vs_baseline + cusum_change_point",
            "configuration": {"baseline_fraction": 0.25, "z_threshold": 3.0},
            "columns": drift_columns,
        },
        "ranked_findings": [
            {
                "rank": 1,
                "factor": factor,
                "station": station,
                "evidence_score": 95.0,
                "epistemic_status": "STATISTICAL ASSOCIATION + MODEL CONTRIBUTION (hypothesis, not causation)",
            }
        ],
    }


def _scenario_artifact(delta_status: str = "CALCULATED", delta_value: float = 20000.0) -> dict:
    return {
        "dataset_id": "synth",
        "scenario_id": "sc1234567890",
        "scenario_type": "throughput_scaling",
        "parameter_changes": {"throughput_change": 0.1, "scaling_basis": "user_assumption"},
        "bottleneck": {"analysis_id": "bn1234567890", "station": "StationB", "status": "CANDIDATE_BOTTLENECK"},
        "baseline": {
            "throughput_per_hour": 1000.0,
            "throughput_source": "Phase 7 observed comparison",
            "units_per_day": 8000.0,
            "economics": {"currency": "INR"},
        },
        "economic_output": {
            "units_per_day_delta": {"status": "CALCULATED", "value": 800.0},
            "daily_contribution_delta": {"status": delta_status, "value": delta_value if delta_status == "CALCULATED" else None},
            "monthly_contribution_delta": {"status": delta_status, "value": 440000.0 if delta_status == "CALCULATED" else None},
        },
        "assumptions_snapshot": {
            "assumptions": {
                "contribution_margin_per_unit": {"value": 25.0, "unit": "currency/unit", "source": "USER_ASSUMPTION"},
                "working_hours_per_day": {"value": 8.0, "unit": "hours/day", "source": "USER_ASSUMPTION"},
            }
        },
        "limitations": ["Scenario outputs are simulations under stated assumptions."],
        "epistemic_status": "SIMULATED SCENARIO - advisory decision support only",
    }


def _assumptions_artifact(supplied: bool = True) -> dict:
    value = 25.0 if supplied else None
    source = "USER_ASSUMPTION" if supplied else "NOT_PROVIDED"
    return {
        "dataset_id": "synth",
        "currency": {"value": "INR" if supplied else None, "source": source},
        "assumptions": {
            "contribution_margin_per_unit": {"value": value, "unit": "currency/unit", "source": source},
            "working_hours_per_day": {"value": 8.0 if supplied else None, "unit": "hours/day", "source": source},
            "working_days_per_month": {"value": 22.0 if supplied else None, "unit": "days/month", "source": source},
        },
    }


def _write_artifacts(
    tmp_path: Path,
    bottleneck: dict | None = None,
    root_cause: dict | None = None,
    scenario: dict | None = None,
    assumptions: dict | None = None,
) -> Path:
    root = tmp_path / "artifacts" / "synth"
    if bottleneck:
        write_json(root / "bottleneck" / "analysis_registry.json", [{"analysis_id": bottleneck["analysis_id"]}])
        write_json(root / "bottleneck" / "findings" / f"{bottleneck['analysis_id']}.json", bottleneck)
    if root_cause:
        write_json(root / "root_cause" / "analysis_registry.json", [{"analysis_id": root_cause["analysis_id"]}])
        write_json(root / "root_cause" / "findings" / f"{root_cause['analysis_id']}.json", root_cause)
    if scenario:
        write_json(root / "economics" / "scenario_registry.json", [{"scenario_id": scenario["scenario_id"]}])
        write_json(root / "economics" / "scenarios" / f"{scenario['scenario_id']}.json", scenario)
    if assumptions:
        write_json(root / "economics" / "assumptions.json", assumptions)
    return root


def _contract(vision_available: bool = False) -> dict:
    return {
        "vision": {
            "status": "NOT_SUPPORTED" if not vision_available else "PROFILED",
            "available": vision_available,
            "reason": "No visual inspection/image training data is available in the current dataset."
            if not vision_available
            else None,
        }
    }


# ---------------------------------------------------------------------------
# A. LANGUAGE SAFETY
# ---------------------------------------------------------------------------

def test_find_violations_detects_forbidden_language():
    assert find_violations("This will increase throughput")
    assert find_violations("Guaranteed savings of 10%")
    assert find_violations("This is the root cause")
    assert find_violations("Investigate the station") == []


def test_validate_rejects_no_evidence():
    errors = validate_recommendation(
        {
            "action_type": "INVESTIGATE_HIGH_UTILIZATION",
            "title": "t",
            "why": "w",
            "evidence": [],
            "limitations": [],
            "evidence_quality": "HIGH_EVIDENCE",
            "epistemic_status": "ADVISORY",
        }
    )
    assert any("no evidence" in error for error in errors)


def test_validate_rejects_machine_control_actions():
    errors = validate_recommendation(
        {
            "action_type": "STOP_LINE",
            "title": "t",
            "why": "w",
            "evidence": [{"statement": "s", "detail": "d"}],
            "limitations": [],
            "evidence_quality": "HIGH_EVIDENCE",
            "epistemic_status": "ADVISORY",
        }
    )
    assert any("machine control" in error for error in errors)


def test_validate_rejects_forbidden_language_in_fields():
    errors = validate_recommendation(
        {
            "action_type": "INVESTIGATE_HIGH_UTILIZATION",
            "title": "This will fix the bottleneck",
            "why": "w",
            "evidence": [{"statement": "s", "detail": "d"}],
            "limitations": [],
            "evidence_quality": "HIGH_EVIDENCE",
            "epistemic_status": "ADVISORY",
        }
    )
    assert any("forbidden language" in error for error in errors)


def test_validate_allows_data_requirement_with_insufficient_evidence():
    errors = validate_recommendation(
        {
            "action_type": "REVIEW_DATA_GAP",
            "title": "Provide assumptions",
            "why": "w",
            "evidence": [{"statement": "s", "detail": "d"}],
            "limitations": [],
            "evidence_quality": "INSUFFICIENT_EVIDENCE",
            "data_requirement": True,
            "epistemic_status": "ADVISORY",
        }
    )
    assert errors == []


# ---------------------------------------------------------------------------
# B. PRIORITY
# ---------------------------------------------------------------------------

def test_compute_priority_formula_transparent():
    priority = compute_priority("HIGH_EVIDENCE", bottleneck_relevant=True, has_scenario=True, has_economics=True)
    assert priority["score"] == pytest.approx(3 * 3.0 + 2.0 + 1.0 + 1.0)
    assert priority["formula"] == "sum(weight_i * component_i)"
    assert priority["components"]["evidence_quality_rank"] == 3


# ---------------------------------------------------------------------------
# C. RULE ACTIVATION / SUPPRESSION (synthetic)
# ---------------------------------------------------------------------------

def test_high_utilization_rule_activates(tmp_path):
    root = _write_artifacts(
        tmp_path,
        bottleneck=_bottleneck_artifact(),
        root_cause=_root_cause_artifact(),
        assumptions=_assumptions_artifact(supplied=True),
    )
    payload = generate_recommendations("synth", _contract(), root)
    action_types = [r["action_type"] for r in payload["recommendations"]]
    assert "INVESTIGATE_HIGH_UTILIZATION" in action_types
    assert "INVESTIGATE_QUEUE_BOTTLENECK" in action_types


def test_high_utilization_rule_suppressed_without_pressure(tmp_path):
    root = _write_artifacts(
        tmp_path,
        bottleneck=_bottleneck_artifact(utilization_pressure=0.3, queue_pressure=0.2),
        assumptions=_assumptions_artifact(supplied=True),
    )
    payload = generate_recommendations("synth", _contract(), root)
    action_types = [r["action_type"] for r in payload["recommendations"]]
    assert "INVESTIGATE_HIGH_UTILIZATION" not in action_types
    assert "INVESTIGATE_QUEUE_BOTTLENECK" not in action_types
    trace = {entry["rule"]: entry["activated"] for entry in payload["rule_trace"]}
    assert trace["high_utilization"] is False


def test_cycle_time_rule_requires_cycle_pressure(tmp_path):
    root = _write_artifacts(tmp_path, bottleneck=_bottleneck_artifact(cycle_pressure=1.0))
    payload = generate_recommendations("synth", _contract(), root)
    assert "INVESTIGATE_CYCLE_TIME" in [r["action_type"] for r in payload["recommendations"]]
    root2 = _write_artifacts(tmp_path / "second", bottleneck=_bottleneck_artifact(cycle_pressure=None))
    payload2 = generate_recommendations("synth", _contract(), root2)
    assert "INVESTIGATE_CYCLE_TIME" not in [r["action_type"] for r in payload2["recommendations"]]


def test_drift_rule_activates_only_on_drift(tmp_path):
    root = _write_artifacts(tmp_path, root_cause=_root_cause_artifact(drift_status="DRIFT_DETECTED"))
    payload = generate_recommendations("synth", _contract(), root)
    assert "INVESTIGATE_PROCESS_DRIFT" in [r["action_type"] for r in payload["recommendations"]]
    root2 = _write_artifacts(tmp_path / "second", root_cause=_root_cause_artifact(drift_status="NO_SIGNIFICANT_DRIFT_DETECTED"))
    payload2 = generate_recommendations("synth", _contract(), root2)
    assert "INVESTIGATE_PROCESS_DRIFT" not in [r["action_type"] for r in payload2["recommendations"]]


def test_anomaly_rule_activates_with_anomaly_evidence(tmp_path):
    root = _write_artifacts(tmp_path, bottleneck=_bottleneck_artifact(with_anomaly=True))
    payload = generate_recommendations("synth", _contract(), root)
    assert "REVIEW_ANOMALOUS_RECORDS" in [r["action_type"] for r in payload["recommendations"]]
    root2 = _write_artifacts(tmp_path / "second", bottleneck=_bottleneck_artifact(with_anomaly=False))
    payload2 = generate_recommendations("synth", _contract(), root2)
    assert "REVIEW_ANOMALOUS_RECORDS" not in [r["action_type"] for r in payload2["recommendations"]]


def test_scenario_rule_activates_with_valid_economics(tmp_path):
    root = _write_artifacts(
        tmp_path,
        bottleneck=_bottleneck_artifact(),
        scenario=_scenario_artifact(delta_status="CALCULATED"),
        assumptions=_assumptions_artifact(supplied=True),
    )
    payload = generate_recommendations("synth", _contract(), root)
    scenario_recs = [r for r in payload["recommendations"] if r["action_type"] == "EVALUATE_CAPACITY_IMPROVEMENT"]
    assert scenario_recs
    rec = scenario_recs[0]
    assert rec["simulated_effect"]["epistemic_status"] == "SIMULATED"
    assert rec["economic_effect"]["daily_contribution_delta"] == 20000.0
    assert "not a forecast" in rec["why"].lower()


def test_scenario_rule_suppressed_without_economics(tmp_path):
    root = _write_artifacts(
        tmp_path,
        bottleneck=_bottleneck_artifact(),
        scenario=_scenario_artifact(delta_status="NOT_AVAILABLE"),
    )
    payload = generate_recommendations("synth", _contract(), root)
    assert "EVALUATE_CAPACITY_IMPROVEMENT" not in [r["action_type"] for r in payload["recommendations"]]


def test_data_gap_economics_rule_when_missing(tmp_path):
    root = _write_artifacts(
        tmp_path,
        bottleneck=_bottleneck_artifact(),
        assumptions=_assumptions_artifact(supplied=False),
    )
    payload = generate_recommendations("synth", _contract(), root)
    gaps = [r for r in payload["recommendations"] if r["action_type"] == "REVIEW_DATA_GAP"]
    assert any(r["target"] == "economic_assumptions" for r in gaps)
    assert payload["decision_summary"]["data_gaps"]


def test_data_gap_economics_suppressed_when_supplied_and_scenario_calculated(tmp_path):
    root = _write_artifacts(
        tmp_path,
        bottleneck=_bottleneck_artifact(),
        scenario=_scenario_artifact(delta_status="CALCULATED"),
        assumptions=_assumptions_artifact(supplied=True),
    )
    payload = generate_recommendations("synth", _contract(), root)
    gaps = [r for r in payload["recommendations"] if r["action_type"] == "REVIEW_DATA_GAP" and r["target"] == "economic_assumptions"]
    assert gaps == []


def test_data_gap_vision_rule_when_not_supported(tmp_path):
    root = _write_artifacts(tmp_path, bottleneck=_bottleneck_artifact())
    payload = generate_recommendations("synth", _contract(vision_available=False), root)
    gaps = [r for r in payload["recommendations"] if r["target"] == "vision_dataset"]
    assert gaps
    assert "NOT_SUPPORTED" in gaps[0]["evidence"][0]["statement"]
    assert gaps[0]["data_requirement"] is True


def test_data_gap_vision_suppressed_when_profiled(tmp_path):
    root = _write_artifacts(tmp_path, bottleneck=_bottleneck_artifact())
    payload = generate_recommendations("synth", _contract(vision_available=True), root)
    assert [r for r in payload["recommendations"] if r["target"] == "vision_dataset"] == []


# ---------------------------------------------------------------------------
# D. INTEGRATION, DEDUPE, TRACEABILITY
# ---------------------------------------------------------------------------

def test_multi_source_evidence_chain(tmp_path):
    root = _write_artifacts(
        tmp_path,
        bottleneck=_bottleneck_artifact(),
        root_cause=_root_cause_artifact(),
        scenario=_scenario_artifact(),
        assumptions=_assumptions_artifact(supplied=True),
    )
    payload = generate_recommendations("synth", _contract(), root)
    util_rec = next(r for r in payload["recommendations"] if r["action_type"] == "INVESTIGATE_HIGH_UTILIZATION")
    sources = {e["source_artifact"] for e in util_rec["evidence"]}
    assert "bottleneck/findings" in sources
    assert "root_cause/findings" in sources
    epistemic = {e["epistemic_status"] for e in util_rec["evidence"]}
    assert "DATA_DERIVED" in epistemic
    assert "STATISTICAL_ASSOCIATION" in epistemic


def test_recommendations_sorted_by_priority_and_ranked(tmp_path):
    root = _write_artifacts(
        tmp_path,
        bottleneck=_bottleneck_artifact(),
        root_cause=_root_cause_artifact(),
        scenario=_scenario_artifact(),
        assumptions=_assumptions_artifact(supplied=True),
    )
    payload = generate_recommendations("synth", _contract(), root)
    priorities = [r["priority"] for r in payload["recommendations"]]
    assert priorities == sorted(priorities, reverse=True)
    assert [r["rank"] for r in payload["recommendations"]] == list(range(1, len(priorities) + 1))


def test_dedupe_removes_duplicate_actions(tmp_path):
    root = _write_artifacts(tmp_path, bottleneck=_bottleneck_artifact())
    payload = generate_recommendations("synth", _contract(), root)
    keys = [(r["action_type"], r["target"]) for r in payload["recommendations"]]
    assert len(keys) == len(set(keys))


def test_deterministic_output(tmp_path):
    root = _write_artifacts(
        tmp_path,
        bottleneck=_bottleneck_artifact(),
        root_cause=_root_cause_artifact(),
        scenario=_scenario_artifact(),
        assumptions=_assumptions_artifact(supplied=True),
    )
    first = generate_recommendations("synth", _contract(), root)
    second = generate_recommendations("synth", _contract(), root)
    assert [r["recommendation_id"] for r in first["recommendations"]] == [r["recommendation_id"] for r in second["recommendations"]]
    assert [r["priority"] for r in first["recommendations"]] == [r["priority"] for r in second["recommendations"]]


def test_no_artifacts_still_yields_data_gaps(tmp_path):
    root = tmp_path / "artifacts" / "synth"
    root.mkdir(parents=True)
    payload = generate_recommendations("synth", _contract(), root)
    assert payload["status"] == "complete"
    action_types = {r["action_type"] for r in payload["recommendations"]}
    assert action_types <= {"REVIEW_DATA_GAP"}
    assert payload["recommendations"], "data-gap recommendations should still be produced"


def test_all_recommendations_pass_validation_and_language(tmp_path):
    root = _write_artifacts(
        tmp_path,
        bottleneck=_bottleneck_artifact(with_anomaly=True, cycle_pressure=1.0),
        root_cause=_root_cause_artifact(drift_status="DRIFT_DETECTED"),
        scenario=_scenario_artifact(),
        assumptions=_assumptions_artifact(supplied=True),
    )
    payload = generate_recommendations("synth", _contract(), root)
    assert payload["recommendations"]
    for recommendation in payload["recommendations"]:
        assert validate_recommendation(recommendation) == []
        assert recommendation["epistemic_status"] == "ADVISORY"
        assert recommendation["evidence"]
        assert recommendation["limitations"]
    serialized = json.dumps(payload)
    assert find_violations(serialized) == [], find_violations(serialized)


# ---------------------------------------------------------------------------
# E. PERSISTENCE
# ---------------------------------------------------------------------------

def test_artifacts_persist_and_reload(tmp_path):
    root = _write_artifacts(
        tmp_path,
        bottleneck=_bottleneck_artifact(),
        root_cause=_root_cause_artifact(),
        scenario=_scenario_artifact(),
        assumptions=_assumptions_artifact(supplied=True),
    )
    payload = generate_recommendations("synth", _contract(), root)
    for name in ("recommendation_registry.json", "decision_summary.json", "metadata.json", "latest_run.json"):
        assert (root / "recommendations" / name).exists(), name
    registry = list_recommendations(root)
    assert len(registry) == payload["recommendation_count"]
    first_id = registry[0]["recommendation_id"]
    reloaded = get_recommendation(root, first_id)
    assert reloaded is not None
    assert reloaded["recommendation_id"] == first_id
    summary = get_decision_summary(root)
    assert summary["dataset_id"] == "synth"
    assert summary["epistemic_status"] == "ADVISORY"


# ---------------------------------------------------------------------------
# F. API
# ---------------------------------------------------------------------------

def _upload_and_build_pipeline(client, tmp_path, with_bottleneck: bool = True) -> str:
    rng = np.random.default_rng(4)
    rows = 500
    frame = pd.DataFrame(
        {
            "Time_Now": np.arange(rows),
            "StationA_Util": rng.uniform(0.3, 0.5, rows),
            "StationB_Util": rng.uniform(0.85, 0.99, rows),
            "StationA_Queue": rng.uniform(0, 2, rows),
            "StationB_Queue": rng.uniform(40, 80, rows),
            "Total parts": 900 + rng.normal(0, 10, rows),
        }
    )
    path = tmp_path / "rec_api.csv"
    frame.to_csv(path, index=False)
    with open(path, "rb") as fh:
        contract = client.post("/api/upload", files={"file": (path.name, fh, "text/csv")}).json()
    dataset_id = contract["dataset_id"]
    if with_bottleneck:
        response = client.post(f"/api/datasets/{dataset_id}/bottleneck/analyze", json={})
        assert response.status_code == 200, response.text
    return dataset_id


def test_api_recommendations_flow(client, tmp_path):
    dataset_id = _upload_and_build_pipeline(client, tmp_path)

    status = client.get(f"/api/datasets/{dataset_id}/recommendations/status").json()
    assert status["status"] == "NOT_GENERATED"

    generated = client.post(f"/api/datasets/{dataset_id}/recommendations/generate").json()
    assert generated["status"] == "complete"
    assert generated["recommendation_count"] >= 1
    action_types = [r["action_type"] for r in generated["recommendations"]]
    assert "INVESTIGATE_HIGH_UTILIZATION" in action_types

    listing = client.get(f"/api/datasets/{dataset_id}/recommendations").json()
    assert listing["count"] == generated["recommendation_count"]
    assert listing["decision_summary"]["bottleneck_status"]["station"] == "StationB"

    first_id = listing["recommendations"][0]["recommendation_id"]
    detail = client.get(f"/api/datasets/{dataset_id}/recommendations/{first_id}").json()
    assert detail["recommendation_id"] == first_id

    evidence = client.get(f"/api/datasets/{dataset_id}/recommendations/{first_id}/evidence").json()
    assert evidence["evidence"]
    assert evidence["epistemic_status"] == "ADVISORY"

    assert client.get(f"/api/datasets/{dataset_id}/recommendations/nonexistent").status_code == 404


def test_api_recommendations_without_bottleneck_still_returns_gaps(client, tmp_path):
    frame = pd.DataFrame({"Demand": np.arange(300, dtype=float), "Total parts": np.arange(300, dtype=float)})
    path = tmp_path / "rec_nostation.csv"
    frame.to_csv(path, index=False)
    with open(path, "rb") as fh:
        contract = client.post("/api/upload", files={"file": (path.name, fh, "text/csv")}).json()
    dataset_id = contract["dataset_id"]
    generated = client.post(f"/api/datasets/{dataset_id}/recommendations/generate").json()
    assert generated["status"] == "complete"
    assert all(r["action_type"] == "REVIEW_DATA_GAP" for r in generated["recommendations"])


def test_api_recommendations_unknown_dataset_404(client):
    assert client.get("/api/datasets/nope/recommendations/status").status_code == 404
    assert client.post("/api/datasets/nope/recommendations/generate").status_code == 404
