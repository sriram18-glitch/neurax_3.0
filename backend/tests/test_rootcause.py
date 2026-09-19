"""Phase 6 test suite: root-cause analysis engine.

Unit tests use small synthetic datasets with INTENTIONALLY PLANTED
relationships (a known driver, a known constant, a known noise feature) to
validate the algorithm itself. Real-data verification lives in
verify_phase6_real.py.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from app.rootcause.drift import detect_drift
from app.rootcause.errors import RootCauseError
from app.rootcause.runner import get_analysis, list_analyses, run_root_cause
from app.rootcause.scoring import score_factor, status_for_score
from app.rootcause.signals import (
    correlation_signal,
    group_comparison_signal,
    mutual_information_signal,
    select_factors,
    temporal_signal,
)
from app.rootcause.targets import define_event, discover_targets, resolve_target


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _planted_frame(rows: int = 800, seed: int = 7) -> pd.DataFrame:
    """driver_util strongly (negatively) drives throughput; noise_col does not."""
    rng = np.random.default_rng(seed)
    driver = rng.uniform(0.3, 1.0, rows)
    noise = rng.normal(0, 1, rows)
    demand = rng.integers(1, 20, rows).astype(float)
    throughput = 500 - 400 * driver + 5 * demand + rng.normal(0, 3, rows)
    return pd.DataFrame(
        {
            "Demand": demand,
            "Line1_Util": driver,
            "Noise_Sensor": noise,
            "Total parts": throughput,
        }
    )


def _setup(tmp_path: Path, frame: pd.DataFrame, name: str = "planted.csv") -> tuple[str, Path, Path]:
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
    return dataset_id, artifacts / dataset_id, tmp_path / "models"


# ---------------------------------------------------------------------------
# A. TARGETS AND EVENTS
# ---------------------------------------------------------------------------

def test_discover_targets_from_planted_data(tmp_path):
    dataset_id, artifact_root, _ = _setup(tmp_path, _planted_frame())
    analysis = json.loads((artifact_root / "analysis.json").read_text(encoding="utf-8"))
    targets = discover_targets(dataset_id, analysis, artifact_root)
    names = {t["target"] for t in targets}
    assert "Total parts" in names
    target = next(t for t in targets if t["target"] == "Total parts")
    assert target["rows_with_target"] >= 700
    assert target["mode"] == "model_input"


def test_resolve_target_missing_raises():
    with pytest.raises(RootCauseError) as excinfo:
        resolve_target([], "NotAColumn")
    assert excinfo.value.code == "TARGET_NOT_FOUND"


def test_define_event_low_and_high():
    frame = pd.DataFrame({"y": np.arange(1000, dtype=float)})
    low = define_event(frame, "y", "low", 0.10)
    assert low["event_rows"] == pytest.approx(100, abs=15)
    assert low["threshold"] < 200
    high = define_event(frame, "y", "high", 0.10)
    assert high["threshold"] > 800
    assert ">=" in high["definition"]


def test_define_event_rejects_bad_input():
    frame = pd.DataFrame({"y": np.arange(1000, dtype=float)})
    with pytest.raises(RootCauseError):
        define_event(frame, "y", "sideways", 0.1)
    with pytest.raises(RootCauseError):
        define_event(frame, "y", "low", 0.9)


def test_define_event_insufficient_rows():
    frame = pd.DataFrame({"y": np.arange(10, dtype=float)})
    with pytest.raises(RootCauseError) as excinfo:
        define_event(frame, "y", "low", 0.1)
    assert excinfo.value.code == "INSUFFICIENT_DATA"


# ---------------------------------------------------------------------------
# B. SIGNALS
# ---------------------------------------------------------------------------

def test_correlation_signal_detects_planted_relationship():
    frame = _planted_frame()
    x = frame["Line1_Util"].to_numpy(dtype=float)
    y = frame["Total parts"].to_numpy(dtype=float)
    signal = correlation_signal(x, y)
    assert signal["available"] is True
    assert signal["spearman_r"] < -0.9, signal
    noise_signal = correlation_signal(frame["Noise_Sensor"].to_numpy(dtype=float), y)
    assert abs(noise_signal["spearman_r"]) < 0.2


def test_correlation_signal_unavailable_for_constant():
    constant = np.ones(100)
    signal = correlation_signal(constant, np.arange(100, dtype=float))
    assert signal["available"] is False
    assert "variation" in signal["reason"]


def test_mutual_information_ranks_driver_above_noise():
    frame = _planted_frame()
    y = frame["Total parts"].to_numpy(dtype=float)
    driver_mi = mutual_information_signal(frame["Line1_Util"].to_numpy(dtype=float), y)
    noise_mi = mutual_information_signal(frame["Noise_Sensor"].to_numpy(dtype=float), y)
    assert driver_mi["available"] and noise_mi["available"]
    assert driver_mi["mi"] > noise_mi["mi"]


def test_group_comparison_direction_correct():
    frame = _planted_frame()
    y = pd.to_numeric(frame["Total parts"], errors="coerce")
    event_mask = (y <= y.quantile(0.1)).to_numpy()
    signal = group_comparison_signal(frame["Line1_Util"].to_numpy(dtype=float), event_mask)
    assert signal["available"] is True
    assert signal["event_mean"] > signal["non_event_mean"], signal
    assert signal["standardized_effect"] > 1.0


def test_temporal_signal_requires_enough_rows():
    x = np.arange(100, dtype=float)
    y = np.arange(100, dtype=float)
    order = np.arange(100, dtype=float)
    mask = np.zeros(100, dtype=bool)
    mask[:10] = True
    signal = temporal_signal(x, y, order, mask)
    assert signal["available"] is False
    assert "200" in signal["reason"]


def test_select_factors_excludes_target_responses_and_constants():
    frame = _planted_frame()
    frame["const_col"] = 5.0
    frame["Total parts 2"] = frame["Total parts"] * 0.5
    factors, excluded = select_factors(frame, "Total parts", ["Total parts 2"])
    assert "Line1_Util" in factors
    assert "Total parts" not in factors
    assert "Total parts 2" not in factors
    assert "const_col" in excluded


# ---------------------------------------------------------------------------
# C. SCORING
# ---------------------------------------------------------------------------

def test_score_factor_bounded_and_weighted():
    score = score_factor(
        {"available": True, "spearman_r": -0.95},
        {"available": True, "mi": 0.9, "mi_permutation_baseline": 0.1},
        {"available": True, "standardized_effect": -3.0},
        {"available": True, "factor_shift_precedes_event_onset": True},
        {"available": True, "enrichment": 5.0},
        0.5,
        1.0,
    )
    assert score["status"] == "SCORED"
    assert 0 <= score["score"] <= 100
    assert score["score"] > 60, score
    assert score["components"]["correlation"] == 0.95
    assert score["components"]["group_difference"] == 1.0
    assert score["components"]["anomaly"] == 1.0
    assert score["components"]["model_contribution"] == 0.5


def test_score_factor_insufficient_evidence():
    score = score_factor(
        {"available": False, "reason": "x"},
        {"available": False, "reason": "x"},
        {"available": False, "reason": "x"},
        {"available": False, "reason": "x"},
        {"available": False, "reason": "x"},
        None,
        None,
    )
    assert score["status"] == "INSUFFICIENT_EVIDENCE"
    assert score["score"] is None


def test_status_thresholds():
    assert status_for_score(75) == "STRONG_ASSOCIATION"
    assert status_for_score(50) == "MODERATE_ASSOCIATION"
    assert status_for_score(25) == "WEAK_ASSOCIATION"
    assert status_for_score(5) == "MINIMAL_ASSOCIATION"
    assert status_for_score(None) == "INSUFFICIENT_EVIDENCE"


# ---------------------------------------------------------------------------
# D. FULL ANALYSIS (synthetic algorithm test)
# ---------------------------------------------------------------------------

def test_full_analysis_ranks_planted_driver_first(tmp_path):
    dataset_id, artifact_root, models_dir = _setup(tmp_path, _planted_frame())
    analysis = json.loads((artifact_root / "analysis.json").read_text(encoding="utf-8"))
    result = run_root_cause(dataset_id, "Total parts", "low", 0.10, analysis, artifact_root, models_dir)
    assert result["status"] == "complete", result.get("error")
    ranked = result["ranked_findings"]
    assert ranked, "expected ranked findings"
    assert ranked[0]["factor"] == "Line1_Util", [f["factor"] for f in ranked[:3]]
    assert ranked[0]["evidence_score"] > 50
    noise = next((f for f in ranked if f["factor"] == "Noise_Sensor"), None)
    assert noise is not None
    assert (noise["evidence_score"] or 0) < ranked[0]["evidence_score"]
    assert result["event"]["direction"] == "low"
    assert result["factors_analyzed"] >= 3


def test_full_analysis_epistemic_labels_present(tmp_path):
    dataset_id, artifact_root, models_dir = _setup(tmp_path, _planted_frame())
    analysis = json.loads((artifact_root / "analysis.json").read_text(encoding="utf-8"))
    result = run_root_cause(dataset_id, "Total parts", "low", 0.10, analysis, artifact_root, models_dir)
    for finding in result["ranked_findings"]:
        assert "not causation" in finding["epistemic_status"].lower() or "hypothesis" in finding["epistemic_status"].lower()
        assert any("does not establish causation" in limitation for limitation in finding["limitations"])
        assert "Association does not establish causation." in finding["explanation"]
    assert result["epistemic_summary"]["causal_claim"].startswith("NOT SUPPORTED")


def test_full_analysis_high_direction(tmp_path):
    dataset_id, artifact_root, models_dir = _setup(tmp_path, _planted_frame())
    analysis = json.loads((artifact_root / "analysis.json").read_text(encoding="utf-8"))
    result = run_root_cause(dataset_id, "Total parts", "high", 0.10, analysis, artifact_root, models_dir)
    assert result["status"] == "complete"
    top = result["ranked_findings"][0]
    assert top["factor"] == "Line1_Util"
    rho = top["evidence"]["correlation"]["spearman_r"]
    assert rho < 0, "high throughput events should associate with LOW utilization"


def test_analysis_persists_and_reloads(tmp_path):
    dataset_id, artifact_root, models_dir = _setup(tmp_path, _planted_frame())
    analysis = json.loads((artifact_root / "analysis.json").read_text(encoding="utf-8"))
    result = run_root_cause(dataset_id, "Total parts", "low", 0.10, analysis, artifact_root, models_dir)
    analysis_id = result["analysis_id"]
    reloaded = get_analysis(artifact_root / "root_cause", analysis_id)
    assert reloaded is not None
    assert reloaded["analysis_id"] == analysis_id
    assert reloaded["ranked_findings"][0]["factor"] == "Line1_Util"
    registry = list_analyses(artifact_root / "root_cause")
    assert any(entry["analysis_id"] == analysis_id for entry in registry)
    assert (artifact_root / "root_cause" / "metadata.json").exists()


def test_analysis_reproducible(tmp_path):
    dataset_id, artifact_root, models_dir = _setup(tmp_path, _planted_frame())
    analysis = json.loads((artifact_root / "analysis.json").read_text(encoding="utf-8"))
    first = run_root_cause(dataset_id, "Total parts", "low", 0.10, analysis, artifact_root, models_dir)
    second = run_root_cause(dataset_id, "Total parts", "low", 0.10, analysis, artifact_root, models_dir)
    assert first["analysis_id"] == second["analysis_id"]
    assert [f["factor"] for f in first["ranked_findings"]] == [f["factor"] for f in second["ranked_findings"]]
    assert [f["evidence_score"] for f in first["ranked_findings"]] == [f["evidence_score"] for f in second["ranked_findings"]]


def test_analysis_no_model_contribution_marked(tmp_path):
    dataset_id, artifact_root, models_dir = _setup(tmp_path, _planted_frame())
    analysis = json.loads((artifact_root / "analysis.json").read_text(encoding="utf-8"))
    result = run_root_cause(dataset_id, "Total parts", "low", 0.10, analysis, artifact_root, models_dir)
    for finding in result["ranked_findings"]:
        contribution = finding["evidence"]["model_contribution"]
        assert "available" in contribution
        if not contribution["available"]:
            assert contribution["reason"]


def test_analysis_unknown_target_returns_structured_failure(tmp_path):
    dataset_id, artifact_root, models_dir = _setup(tmp_path, _planted_frame())
    analysis = json.loads((artifact_root / "analysis.json").read_text(encoding="utf-8"))
    result = run_root_cause(dataset_id, "Missing Column", "low", 0.10, analysis, artifact_root, models_dir)
    assert result["status"] == "failed"
    assert result["error"]["code"] == "TARGET_NOT_FOUND"


# ---------------------------------------------------------------------------
# E. DRIFT
# ---------------------------------------------------------------------------

def test_drift_detects_planted_shift():
    rows = 4000
    first = np.random.default_rng(0).normal(0.5, 0.02, rows // 2)
    second = np.random.default_rng(1).normal(0.9, 0.02, rows // 2)
    frame = pd.DataFrame({"Time_Now": np.arange(rows), "Line1_Util": np.concatenate([first, second])})
    result = detect_drift(frame, "Time_Now", ["Line1_Util"])
    assert result["status"] == "DRIFT_DETECTED"
    column = result["columns"][0]
    assert column["direction"] == "increase"
    assert column["peak_ewma_z"] >= 3.0


def test_drift_reports_no_drift_for_stable_process():
    rows = 4000
    rng = np.random.default_rng(2)
    frame = pd.DataFrame({"Time_Now": np.arange(rows), "Line1_Util": rng.normal(0.5, 0.02, rows)})
    result = detect_drift(frame, "Time_Now", ["Line1_Util"])
    assert result["status"] == "NO_SIGNIFICANT_DRIFT_DETECTED"


def test_drift_not_supported_without_ordering():
    frame = pd.DataFrame({"Line1_Util": np.random.default_rng(3).normal(0.5, 0.02, 2000)})
    result = detect_drift(frame, None, ["Line1_Util"])
    assert result["status"] == "DRIFT_ANALYSIS_NOT_SUPPORTED"
    assert "NOT_AVAILABLE_FROM_DATASET" in result["reason"]


def test_drift_not_supported_with_insufficient_rows():
    frame = pd.DataFrame({"Time_Now": np.arange(100), "Line1_Util": np.random.default_rng(4).normal(0.5, 0.02, 100)})
    result = detect_drift(frame, "Time_Now", ["Line1_Util"])
    assert result["status"] == "DRIFT_ANALYSIS_NOT_SUPPORTED"


# ---------------------------------------------------------------------------
# F. EDGE CASES / NO-FABRICATION
# ---------------------------------------------------------------------------

def test_analysis_without_station_columns_has_no_station_ranking(tmp_path):
    dataset_id, artifact_root, models_dir = _setup(tmp_path, _planted_frame())
    analysis = json.loads((artifact_root / "analysis.json").read_text(encoding="utf-8"))
    result = run_root_cause(dataset_id, "Total parts", "low", 0.10, analysis, artifact_root, models_dir)
    for finding in result["ranked_findings"]:
        if finding["station"] is None:
            assert finding["evidence"]["correlation"] is not None
    assert isinstance(result["station_ranking"], list)


def test_analysis_with_tiny_dataset_reports_insufficient(tmp_path):
    frame = pd.DataFrame(
        {
            "Demand": np.arange(40, dtype=float),
            "Line1_Util": np.linspace(0.1, 0.9, 40),
            "Total parts": np.linspace(500, 100, 40),
        }
    )
    dataset_id, artifact_root, models_dir = _setup(tmp_path, frame, name="tiny.csv")
    analysis = json.loads((artifact_root / "analysis.json").read_text(encoding="utf-8"))
    result = run_root_cause(dataset_id, "Total parts", "low", 0.10, analysis, artifact_root, models_dir)
    # A 40-row dataset is below the 100-row reliability floor: the engine must
    # refuse with a structured, honest error rather than produce weak findings.
    assert result["status"] == "failed"
    assert result["error"]["code"] in {"TARGET_NOT_FOUND", "INSUFFICIENT_DATA"}
    assert result["error"]["message"]


def test_no_fabricated_causal_language_anywhere(tmp_path):
    dataset_id, artifact_root, models_dir = _setup(tmp_path, _planted_frame())
    analysis = json.loads((artifact_root / "analysis.json").read_text(encoding="utf-8"))
    result = run_root_cause(dataset_id, "Total parts", "low", 0.10, analysis, artifact_root, models_dir)
    serialized = json.dumps(result).lower()
    # Positive causal assertions must never appear.
    for forbidden in (
        "confirmed root cause",
        "is the root cause",
        "causes the",
        "caused by",
        "proven cause of",
        "definitely caused",
    ):
        assert forbidden not in serialized, forbidden
    # Negated disclaimers must appear instead.
    assert "does not establish causation" in serialized
    assert "not proven causes" in serialized or "hypothesis" in serialized
    assert result["epistemic_summary"]["causal_claim"].startswith("NOT SUPPORTED")


# ---------------------------------------------------------------------------
# G. API
# ---------------------------------------------------------------------------

def _upload(client, frame: pd.DataFrame, tmp_path: Path, name: str) -> str:
    path = tmp_path / name
    frame.to_csv(path, index=False)
    with open(path, "rb") as fh:
        response = client.post("/api/upload", files={"file": (path.name, fh, "text/csv")})
    assert response.status_code == 200, response.text
    return response.json()["dataset_id"]


def test_api_root_cause_flow(client, tmp_path):
    dataset_id = _upload(client, _planted_frame(), tmp_path, "planted_api.csv")

    status = client.get(f"/api/datasets/{dataset_id}/root-cause/status").json()
    assert status["status"] == "READY"
    assert status["targets_available"] >= 1

    targets = client.get(f"/api/datasets/{dataset_id}/root-cause/targets").json()
    assert targets["count"] >= 1
    target_name = next(t["target"] for t in targets["targets"] if t["target"] == "Total parts")

    response = client.post(
        f"/api/datasets/{dataset_id}/root-cause/analyze",
        json={"target": target_name, "direction": "low", "quantile": 0.1},
    )
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["status"] == "complete"
    analysis_id = result["analysis_id"]
    assert result["ranked_findings"][0]["factor"] == "Line1_Util"

    findings = client.get(f"/api/datasets/{dataset_id}/root-cause/findings").json()
    assert any(entry["analysis_id"] == analysis_id for entry in findings["analyses"])

    fetched = client.get(f"/api/datasets/{dataset_id}/root-cause/{analysis_id}").json()
    assert fetched["analysis_id"] == analysis_id

    drift = client.get(f"/api/datasets/{dataset_id}/root-cause/drift").json()
    assert "status" in drift

    assert client.get(f"/api/datasets/{dataset_id}/root-cause/nonexistent").status_code == 404


def test_api_root_cause_missing_target_422(client, tmp_path):
    dataset_id = _upload(client, _planted_frame(), tmp_path, "planted_api2.csv")
    response = client.post(f"/api/datasets/{dataset_id}/root-cause/analyze", json={})
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "TARGET_REQUIRED"

    response = client.post(
        f"/api/datasets/{dataset_id}/root-cause/analyze",
        json={"target": "Not A Column", "direction": "low"},
    )
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "TARGET_NOT_FOUND"


def test_api_root_cause_unknown_dataset_404(client):
    assert client.get("/api/datasets/nope/root-cause/status").status_code == 404
    assert client.get("/api/datasets/nope/root-cause/targets").status_code == 404
