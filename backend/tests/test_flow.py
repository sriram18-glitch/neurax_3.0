"""Phase 7 test suite: bottleneck / flow analysis engine.

Unit tests use small synthetic datasets with INTENTIONALLY PLANTED structure
(a station with high utilization + persistent queue vs a light station) to
validate the algorithm. Real-data verification lives in verify_phase7_real.py.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from app.flow.errors import FlowError
from app.flow.graph import build_flow_graph, infer_sequence
from app.flow.impact import throughput_impact
from app.flow.runner import get_analysis, list_analyses, run_bottleneck_analysis
from app.flow.scoring import evidence_quality, percentile_rank, score_station, station_status


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _planted_station_frame(rows: int = 600, seed: int = 11) -> pd.DataFrame:
    """Station B is the planted constraint: high utilization + persistent queue."""
    rng = np.random.default_rng(seed)
    a_util = rng.uniform(0.3, 0.5, rows)
    b_util = rng.uniform(0.85, 0.99, rows)
    c_util = rng.uniform(0.2, 0.4, rows)
    a_queue = rng.uniform(0, 2, rows)
    b_queue = rng.uniform(40, 80, rows)
    c_queue = rng.uniform(0, 1, rows)
    throughput = 400 - 150 * (b_util - 0.85) * 10 + rng.normal(0, 2, rows)
    return pd.DataFrame(
        {
            "Time_Now": np.arange(rows),
            "StationA_Util": a_util,
            "StationB_Util": b_util,
            "StationC_Util": c_util,
            "StationA_Queue": a_queue,
            "StationB_Queue": b_queue,
            "StationC_Queue": c_queue,
            "Total parts": throughput,
        }
    )


def _setup(tmp_path: Path, frame: pd.DataFrame, name: str = "flow.csv") -> tuple[str, dict, Path]:
    from app.ingest import ingest_path
    from app.ingest.contract import build_contract
    from app.ingest.profiler import profile_ingest
    from app.pipeline import run_pipeline

    path = tmp_path / name
    frame.to_csv(path, index=False)
    result = ingest_path(path)
    profiles = profile_ingest(result)
    contract = build_contract(result, profiles)
    dataset_id = contract["dataset_id"]
    artifacts = tmp_path / "artifacts"
    analysis = run_pipeline(dataset_id, name, contract, result, artifacts)
    assert analysis["status"] == "complete", analysis.get("error")
    return dataset_id, analysis, artifacts / dataset_id


# ---------------------------------------------------------------------------
# A. SCORING PRIMITIVES
# ---------------------------------------------------------------------------

def test_percentile_rank_orders_correctly():
    values = {"A": 0.3, "B": 0.9, "C": 0.5}
    assert percentile_rank(values, "A") == 0.0
    assert percentile_rank(values, "C") == 0.5
    assert percentile_rank(values, "B") == 1.0
    assert percentile_rank(values, "missing") is None


def test_percentile_rank_single_station():
    assert percentile_rank({"A": 0.5}, "A") == 1.0


def test_score_station_requires_two_components():
    score = score_station({"utilization_pressure": 0.9, "queue_pressure": None, "cycle_time_pressure": None,
                           "throughput_constraint": None, "root_cause_evidence": None, "anomaly_evidence": None})
    assert score["status"] == "INSUFFICIENT_EVIDENCE"
    assert score["score"] is None


def test_score_station_weighted_and_bounded():
    score = score_station({"utilization_pressure": 1.0, "queue_pressure": 1.0, "cycle_time_pressure": 0.5,
                           "throughput_constraint": 0.5, "root_cause_evidence": 0.8, "anomaly_evidence": 0.0})
    assert score["status"] == "SCORED"
    assert 0 < score["score"] <= 100
    assert score["available_components"] == 6
    # all-high components must produce a high score
    high = score_station({"utilization_pressure": 1.0, "queue_pressure": 1.0, "cycle_time_pressure": 1.0,
                          "throughput_constraint": 1.0, "root_cause_evidence": 1.0, "anomaly_evidence": 1.0})
    assert high["score"] == 100.0


def test_score_station_weights_sum_normalized():
    score = score_station({"utilization_pressure": 0.5, "queue_pressure": 0.5, "cycle_time_pressure": None,
                           "throughput_constraint": None, "root_cause_evidence": None, "anomaly_evidence": None})
    # with only two equal-weight-ratio components at 0.5, score must be 50
    assert score["score"] == pytest.approx(50.0)


def test_evidence_quality_labels():
    scored = {"status": "SCORED", "available_components": 5, "consistency": 0.9, "score": 80}
    assert evidence_quality(scored, 1000, False)["label"] == "HIGH_EVIDENCE"
    moderate = {"status": "SCORED", "available_components": 3, "consistency": 0.7, "score": 60}
    assert evidence_quality(moderate, 1000, False)["label"] == "MODERATE_EVIDENCE"
    limited = {"status": "SCORED", "available_components": 3, "consistency": 0.9, "score": 60}
    assert evidence_quality(limited, 50, False)["label"] == "LIMITED_EVIDENCE"
    assert evidence_quality(scored, 1000, True)["label"] == "LIMITED_EVIDENCE"
    insufficient = {"status": "INSUFFICIENT_EVIDENCE", "available_components": 1, "consistency": None, "score": None}
    assert evidence_quality(insufficient, 1000, False)["label"] == "INSUFFICIENT_EVIDENCE"


def test_station_status_logic():
    scored = {"status": "SCORED", "score": 80}
    assert station_status(1, scored, {"label": "HIGH_EVIDENCE"}) == "CANDIDATE_BOTTLENECK"
    assert station_status(2, scored, {"label": "HIGH_EVIDENCE"}) == "POSSIBLE_CONTRIBUTOR"
    low = {"status": "SCORED", "score": 10}
    assert station_status(1, low, {"label": "HIGH_EVIDENCE"}) == "NOT_CONSTRAINED"
    assert station_status(1, {"status": "INSUFFICIENT_EVIDENCE", "score": None}, {"label": "INSUFFICIENT_EVIDENCE"}) == "INSUFFICIENT_EVIDENCE"


# ---------------------------------------------------------------------------
# B. FLOW GRAPH
# ---------------------------------------------------------------------------

def test_infer_sequence_from_documented_structure():
    stations = ["Drilling", "Milling", "Assembly"]
    sequence, rationale = infer_sequence(stations, "Model_1.csv")
    assert sequence == ["Drilling", "Milling", "Assembly"]
    assert "documented process structure" in rationale


def test_infer_sequence_partial_match():
    stations = ["Drilling", "Assembly"]
    sequence, _ = infer_sequence(stations, "Model_2.csv")
    assert sequence == ["Drilling", "Assembly"]


def test_infer_sequence_numeric_suffix_fallback():
    stations = ["Press3", "Press1", "Press2"]
    sequence, rationale = infer_sequence(stations, "unknown.csv")
    assert sequence == ["Press1", "Press2", "Press3"]
    assert "numeric station suffixes" in rationale


def test_flow_graph_unsupported_without_order():
    graph = build_flow_graph(["Alpha", "Beta"], {}, "mystery.csv")
    assert graph["status"] == "PARTIALLY_SUPPORTED"
    assert graph["edges"] == []
    assert "ordering" in graph["reason"]


def test_flow_graph_supported_edges():
    evidence = {"Drilling": {"rank": 1}, "Milling": {"rank": 2}, "Assembly": {"rank": 3}}
    graph = build_flow_graph(["Drilling", "Milling", "Assembly"], evidence, "Model_1.csv")
    assert graph["status"] == "SUPPORTED"
    assert graph["edges"] == [
        {"from": "Drilling", "to": "Milling"},
        {"from": "Milling", "to": "Assembly"},
    ]
    assert graph["nodes"][0]["position"] == 0


# ---------------------------------------------------------------------------
# C. THROUGHPUT IMPACT
# ---------------------------------------------------------------------------

def test_throughput_impact_observed_comparison():
    frame = _planted_station_frame()
    impact = throughput_impact(frame, "StationB", "StationB_Util", ["Total parts"])
    assert impact["status"] == "OBSERVED_COMPARISON"
    observed = impact["observed"]["Total parts"]
    assert observed["constrained_mean"] < observed["unconstrained_mean"]
    assert impact["simulated_impact"] == "NOT_YET_SIMULATED"
    assert "not a simulation" in impact["epistemic_status"].lower()


def test_throughput_impact_missing_output_column():
    frame = pd.DataFrame({"StationB_Util": np.random.default_rng(0).uniform(0.2, 0.9, 300)})
    impact = throughput_impact(frame, "StationB", "StationB_Util", ["Total parts"])
    assert impact["status"] == "NOT_AVAILABLE_FROM_DATASET"


def test_throughput_impact_missing_utilization_column():
    frame = pd.DataFrame({"Total parts": np.arange(300, dtype=float)})
    impact = throughput_impact(frame, "StationB", None, ["Total parts"])
    assert impact["status"] == "NOT_AVAILABLE_FROM_DATASET"
    assert "utilization" in impact["reason"].lower()


# ---------------------------------------------------------------------------
# D. FULL ANALYSIS (synthetic algorithm test)
# ---------------------------------------------------------------------------

def test_full_analysis_identifies_planted_bottleneck(tmp_path):
    dataset_id, analysis, artifact_root = _setup(tmp_path, _planted_station_frame())
    result = run_bottleneck_analysis(dataset_id, analysis, artifact_root)
    assert result["status"] == "complete", result.get("error")
    ranked = result["station_rankings"]
    assert ranked, "expected station rankings"
    assert ranked[0]["station"] == "StationB", [(f["station"], f["evidence_score"]) for f in ranked]
    assert ranked[0]["status"] in {"CANDIDATE_BOTTLENECK", "POSSIBLE_CONTRIBUTOR"}
    assert ranked[0]["evidence_score"] > ranked[1]["evidence_score"]
    candidate = result["candidate_bottleneck"]
    assert candidate["station"] == "StationB"
    assert candidate["why"], "candidate must explain why it was identified"


def test_full_analysis_never_uses_utilization_alone(tmp_path):
    dataset_id, analysis, artifact_root = _setup(tmp_path, _planted_station_frame())
    result = run_bottleneck_analysis(dataset_id, analysis, artifact_root)
    for finding in result["station_rankings"]:
        assert "queue_pressure" in finding["score_components"]
        assert "utilization_pressure" in finding["score_components"]


def test_full_analysis_unavailable_metrics_explicit(tmp_path):
    dataset_id, analysis, artifact_root = _setup(tmp_path, _planted_station_frame())
    result = run_bottleneck_analysis(dataset_id, analysis, artifact_root)
    for finding in result["station_rankings"]:
        assert isinstance(finding["unavailable_metrics"], list)
        # planted frame has no cycle time -> must be reported unavailable
        assert "cycle_time" in finding["unavailable_metrics"]
        assert finding["cycle_time"] == {"available": False, "reason": "NOT AVAILABLE FROM DATASET"}
        assert finding["capacity"]["available"] is False


def test_full_analysis_flow_and_blocking(tmp_path):
    dataset_id, analysis, artifact_root = _setup(tmp_path, _planted_station_frame())
    result = run_bottleneck_analysis(dataset_id, analysis, artifact_root)
    flow = result["flow"]
    assert flow["graph"]["status"] in {"SUPPORTED", "PARTIALLY_SUPPORTED"}
    bs = flow["blocking_starvation"]
    assert bs["blocking"]["status"] == "NOT_SUPPORTED"
    assert bs["starvation"]["status"] == "NOT_SUPPORTED"
    assert bs["blocking"]["reason"]


def test_full_analysis_epistemic_labels(tmp_path):
    dataset_id, analysis, artifact_root = _setup(tmp_path, _planted_station_frame())
    result = run_bottleneck_analysis(dataset_id, analysis, artifact_root)
    assert result["epistemic_summary"]["causal_claim"].startswith("NOT SUPPORTED")
    assert result["epistemic_summary"]["simulated_effect"] == "NOT YET SIMULATED (future phase)."
    for finding in result["station_rankings"]:
        assert "hypothesis" in finding["epistemic_status"].lower()
        assert any("not a proven constraint" in limitation for limitation in finding["limitations"])
    serialized = json.dumps(result).lower()
    for forbidden in ("is the bottleneck", "proven bottleneck", "guaranteed improvement", "will increase throughput"):
        assert forbidden not in serialized, forbidden


def test_full_analysis_what_if_inputs_prepared(tmp_path):
    dataset_id, analysis, artifact_root = _setup(tmp_path, _planted_station_frame())
    result = run_bottleneck_analysis(dataset_id, analysis, artifact_root)
    what_if = result["what_if_inputs"]
    assert what_if["station"] == "StationB"
    assert what_if["expected_effect"] == "NOT YET SIMULATED"
    assert what_if["potential_interventions"]
    assert "no economic values" in what_if["note"].lower()


def test_full_analysis_persists_and_reloads(tmp_path):
    dataset_id, analysis, artifact_root = _setup(tmp_path, _planted_station_frame())
    result = run_bottleneck_analysis(dataset_id, analysis, artifact_root)
    analysis_id = result["analysis_id"]
    for name in ("analysis_registry.json", "station_scores.json", "flow.json", "metadata.json"):
        assert (artifact_root / "bottleneck" / name).exists(), name
    assert (artifact_root / "bottleneck" / "findings" / f"{analysis_id}.json").exists()
    reloaded = get_analysis(artifact_root / "bottleneck", analysis_id)
    assert reloaded is not None
    assert [f["station"] for f in reloaded["station_rankings"]] == [f["station"] for f in result["station_rankings"]]
    registry = list_analyses(artifact_root / "bottleneck")
    assert any(entry["analysis_id"] == analysis_id for entry in registry)


def test_full_analysis_reproducible(tmp_path):
    dataset_id, analysis, artifact_root = _setup(tmp_path, _planted_station_frame())
    first = run_bottleneck_analysis(dataset_id, analysis, artifact_root)
    second = run_bottleneck_analysis(dataset_id, analysis, artifact_root)
    assert first["analysis_id"] == second["analysis_id"]
    assert [f["evidence_score"] for f in first["station_rankings"]] == [f["evidence_score"] for f in second["station_rankings"]]


def test_analysis_without_station_data_fails_structurally(tmp_path):
    frame = pd.DataFrame({"Demand": np.arange(300, dtype=float), "Total parts": np.arange(300, dtype=float) * 2})
    dataset_id, analysis, artifact_root = _setup(tmp_path, frame, name="nostations.csv")
    result = run_bottleneck_analysis(dataset_id, analysis, artifact_root)
    assert result["status"] == "failed"
    assert result["error"]["code"] == "NO_STATION_DATA"


def test_single_station_dataset_limited_evidence(tmp_path):
    rng = np.random.default_rng(5)
    frame = pd.DataFrame(
        {
            "Solo_Util": rng.uniform(0.5, 0.9, 400),
            "Solo_Queue": rng.uniform(0, 5, 400),
            "Total parts": rng.normal(100, 5, 400),
        }
    )
    dataset_id, analysis, artifact_root = _setup(tmp_path, frame, name="solo.csv")
    result = run_bottleneck_analysis(dataset_id, analysis, artifact_root)
    assert result["status"] == "complete"
    finding = result["station_rankings"][0]
    assert finding["evidence_quality"]["label"] == "LIMITED_EVIDENCE"
    assert "single station" in finding["evidence_quality"]["reason"]


def test_analysis_without_utilization_uses_queue_only(tmp_path):
    rng = np.random.default_rng(6)
    frame = pd.DataFrame(
        {
            "Alpha_Queue": rng.uniform(0, 2, 400),
            "Beta_Queue": rng.uniform(30, 60, 400),
            "Total parts": rng.normal(100, 5, 400),
        }
    )
    dataset_id, analysis, artifact_root = _setup(tmp_path, frame, name="queueonly.csv")
    result = run_bottleneck_analysis(dataset_id, analysis, artifact_root)
    assert result["status"] == "complete"
    top = result["station_rankings"][0]
    assert top["station"] == "Beta"
    assert top["score_components"]["utilization_pressure"] is None
    assert top["score_components"]["queue_pressure"] == 1.0


# ---------------------------------------------------------------------------
# E. API
# ---------------------------------------------------------------------------

def _upload(client, frame: pd.DataFrame, tmp_path: Path, name: str) -> str:
    path = tmp_path / name
    frame.to_csv(path, index=False)
    with open(path, "rb") as fh:
        response = client.post("/api/upload", files={"file": (path.name, fh, "text/csv")})
    assert response.status_code == 200, response.text
    return response.json()["dataset_id"]


def test_api_bottleneck_flow(client, tmp_path):
    dataset_id = _upload(client, _planted_station_frame(), tmp_path, "flow_api.csv")

    status = client.get(f"/api/datasets/{dataset_id}/bottleneck/status").json()
    assert status["status"] == "READY"
    assert status["stations_available"] == 3

    stations = client.get(f"/api/datasets/{dataset_id}/bottleneck/stations").json()
    assert stations["count"] == 3

    response = client.post(f"/api/datasets/{dataset_id}/bottleneck/analyze", json={})
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["status"] == "complete"
    analysis_id = result["analysis_id"]
    assert result["candidate_bottleneck"]["station"] == "StationB"

    findings = client.get(f"/api/datasets/{dataset_id}/bottleneck/findings").json()
    assert any(entry["analysis_id"] == analysis_id for entry in findings["analyses"])

    flow = client.get(f"/api/datasets/{dataset_id}/bottleneck/flow").json()
    assert "graph" in flow or "status" in flow

    fetched = client.get(f"/api/datasets/{dataset_id}/bottleneck/{analysis_id}").json()
    assert fetched["analysis_id"] == analysis_id
    assert fetched["candidate_bottleneck"]["station"] == "StationB"

    assert client.get(f"/api/datasets/{dataset_id}/bottleneck/nonexistent").status_code == 404


def test_api_bottleneck_unsupported_dataset_422(client, tmp_path):
    frame = pd.DataFrame({"Demand": np.arange(300, dtype=float), "Total parts": np.arange(300, dtype=float)})
    dataset_id = _upload(client, frame, tmp_path, "no_station_api.csv")
    status = client.get(f"/api/datasets/{dataset_id}/bottleneck/status").json()
    assert status["status"] == "NOT_SUPPORTED"
    response = client.post(f"/api/datasets/{dataset_id}/bottleneck/analyze", json={})
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "NO_STATION_DATA"


def test_api_bottleneck_unknown_dataset_404(client):
    assert client.get("/api/datasets/nope/bottleneck/status").status_code == 404
    assert client.get("/api/datasets/nope/bottleneck/stations").status_code == 404
