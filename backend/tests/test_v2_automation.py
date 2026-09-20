"""V2 test suite: production stream, investigation orchestrator, process
timeline and feature-space projection.

Unit tests use small synthetic fixtures (clearly synthetic). The orchestrator
tests assert the HONESTY contract: missing inputs produce DATA_GAP /
AWAITING_INPUT stages with reasons - never fabricated results.
"""

from __future__ import annotations

import io
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from PIL import Image

from app.investigations.runner import (
    get_investigation,
    investigation_events,
    list_investigations,
    run_investigation,
)
from app.vision.inference import VisionModel, VisionModelError, persist_inspection
from app.vision.stream import InspectionStream
from app.vision.training import _build_feature_space


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _write_image(path: Path, color: int, size: int = 16) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("L", (size, size), color).save(path)


@pytest.fixture()
def image_dataset(tmp_path) -> Path:
    root = tmp_path / "images"
    for index in range(6):
        _write_image(root / "normal" / f"normal_{index:03d}.png", 200 + index)
    for class_name in ("scratch", "hole"):
        for index in range(4):
            _write_image(root / class_name / f"{class_name}_{index:03d}.png", 40 + index)
    return root


def _synthetic_inspection(decision: str = "DEFECT", class_name: str = "fixture-class") -> dict:
    """Explicitly synthetic inspection record used to test orchestration only."""
    return {
        "inspection_id": "invsynthetic01",
        "filename": "fixture.png",
        "generated_at": "2026-01-01T00:00:00Z",
        "station_id": "Camera 01",
        "image_metadata": {"width": 256, "height": 256, "mode": "L", "format": "PNG", "bytes": 1000},
        "preprocessing": {"resize": "224x224", "normalization": "mobilenet_v2.preprocess_input"},
        "prediction": {"predicted_class": class_name, "is_normal": decision == "PASS"},
        "class_probabilities": {class_name: 0.91, "normal": 0.09},
        "confidence": {"value": 0.91, "level": "HIGH", "method": "temperature_scaled softmax", "limitations": "model uncertainty"},
        "anomaly_score": {"value": 0.97, "novelty_score": 0.2, "novelty_status": "NORMAL", "method": "mahalanobis", "note": "not a probability"},
        "localization": {"type": "MODEL-DERIVED LOCALIZATION", "method": "class-activation mapping", "ground_truth": False, "bounding_box": {"x": 1, "y": 2, "width": 30, "height": 40}, "note": "model attention"},
        "decision": decision,
        "review_reason": None if decision != "REVIEW" else "sample differs from known distribution",
        "evidence": [],
        "process_link": {"status": "NOT_AVAILABLE", "reason": "PROCESS LINK NOT AVAILABLE: no per-image metadata.", "available_metadata": []},
        "model": {"backbone": "mobilenet_v2", "classes": [class_name, "normal"]},
        "limitations": [],
        "trace": [],
    }


# ---------------------------------------------------------------------------
# A. Production stream (source-backed - never a hardcoded dataset path)
# ---------------------------------------------------------------------------

def _source_from_dir(root: Path, source_type: str = "FOLDER_DATASET", name: str | None = None):
    from app.vision.source import create_source

    uploaded = []
    for path in sorted(root.rglob("*")):
        if path.is_file() and path.suffix.lower() in {".png", ".jpg", ".jpeg"}:
            relative = path.relative_to(root)
            uploaded.append((str(relative).replace("\\", "/"), path.read_bytes()))
    return create_source(uploaded, source_type, display_name=name)


def test_stream_sequence_is_deterministic(image_dataset):
    from app.vision.source import SourceStream, build_sequence

    first = _source_from_dir(image_dataset)
    second = _source_from_dir(image_dataset)
    seq_first = [(frame["class_folder"], frame["original_name"]) for frame in build_sequence(first)]
    seq_second = [(frame["class_folder"], frame["original_name"]) for frame in build_sequence(second)]
    assert seq_first == seq_second
    assert seq_first[0][0] != "normal", "first frame should be a defect frame in the deterministic plan"


def test_stream_pattern_interleaves_defects_and_normal(image_dataset):
    from app.vision.source import build_sequence

    source = _source_from_dir(image_dataset)
    kinds = [frame["class_folder"] for frame in build_sequence(source)]
    assert kinds[0] != "normal"
    assert kinds[1] == "normal" and kinds[2] == "normal"
    assert kinds[3] != "normal"


def test_stream_controls_and_status(image_dataset, tmp_path):
    from app.vision.source import SourceStream

    source = _source_from_dir(image_dataset)
    stream = SourceStream(sources_base=tmp_path / "sources")
    stream.set_source(source["source_id"])
    status = stream.start()
    assert status["running"] is True
    assert status["label"] == "SIMULATED PRODUCTION STREAM"
    assert status["station_id"] == "Camera 01"
    assert status["total_frames"] == len(stream.sequence)
    assert status["source"]["source_id"] == source["source_id"]
    paused = stream.pause()
    assert paused["running"] is False
    assert stream.set_speed(2.0)["speed"] == 2.0
    assert stream.set_speed(3.3)["speed"] in (2.0, 5.0)
    reset = stream.reset()
    assert reset["cursor"] == 0 and reset["processed"] == 0
    assert reset["running"] is False


def test_stream_without_source_reports_no_inspection_source(tmp_path):
    from app.vision.source import SourceError, SourceStream

    stream = SourceStream(sources_base=tmp_path / "sources")
    with pytest.raises(SourceError) as error:
        stream.start()
    assert error.value.code == "NO_INSPECTION_SOURCE"


def test_stream_next_frame_requires_trained_model(image_dataset, tmp_path):
    from app.vision.source import SourceStream

    source = _source_from_dir(image_dataset)
    stream = SourceStream(sources_base=tmp_path / "sources")
    stream.set_source(source["source_id"])
    model = VisionModel(tmp_path / "no_model")
    assert model.available is False
    with pytest.raises(VisionModelError) as error:
        stream.next_frame(model)
    assert error.value.code == "VISION_MODEL_NOT_TRAINED"


def test_stream_api_status_and_honest_failure(client):
    status = client.get("/api/vision/stream/status")
    assert status.status_code == 200
    body = status.json()
    assert body["label"] == "SIMULATED PRODUCTION STREAM"
    assert body["source"] is None, "no source must be active without explicit selection"
    next_frame = client.post("/api/vision/stream/next")
    # no source selected in the isolated test runtime: the endpoint must fail
    # structurally with NO_INSPECTION_SOURCE instead of a fabricated inspection
    assert next_frame.status_code == 409
    assert next_frame.json()["detail"]["code"] == "NO_INSPECTION_SOURCE"


# ---------------------------------------------------------------------------
# B. Investigation orchestrator
# ---------------------------------------------------------------------------

def test_investigation_without_dataset_is_honest(tmp_path):
    record = run_investigation(_synthetic_inspection(), None, investigations_dir=tmp_path / "inv")
    assert record["status"] == "DATA_GAP"
    stages = {stage["id"]: stage for stage in record["stages"]}
    assert stages["classifying"]["status"] == "COMPLETE"
    assert stages["process_correlation"]["status"] == "DATA_GAP"
    assert stages["root_cause"]["status"] == "DATA_GAP"
    assert stages["bottleneck"]["status"] == "DATA_GAP"
    assert stages["impact"]["status"] == "DATA_GAP"
    assert stages["recommendation"]["status"] == "DATA_GAP"
    assert stages["process_correlation"]["epistemic"] == "DATA GAP"


def test_investigation_review_decision_requires_review(tmp_path):
    record = run_investigation(_synthetic_inspection(decision="REVIEW"), None, investigations_dir=tmp_path / "inv")
    assert record["status"] == "REVIEW_REQUIRED"
    stages = {stage["id"]: stage for stage in record["stages"]}
    assert stages["checking_robustness"]["status"] == "REVIEW"


def test_investigation_events_are_business_events(tmp_path):
    record = run_investigation(_synthetic_inspection(), None, investigations_dir=tmp_path / "inv")
    types = [event["type"] for event in record["events"]]
    assert "inspection_completed" in types
    assert "defect_detected" in types
    assert "investigation_triggered" in types
    assert any(event["type"].endswith("data_gap") for event in record["events"])
    assert all(event["epistemic"] for event in record["events"])


def test_investigation_persistence_roundtrip(tmp_path):
    base = tmp_path / "inv"
    record = run_investigation(_synthetic_inspection(), None, investigations_dir=base)
    listed = list_investigations(base)
    assert listed and listed[0]["investigation_id"] == record["investigation_id"]
    loaded = get_investigation(record["investigation_id"], base)
    assert loaded is not None
    assert loaded["stages"] == record["stages"]


def test_investigation_with_process_dataset(tmp_path, analyze):
    """End-to-end orchestration over a small synthetic process dataset."""
    from app.ingest import ingest_path
    from app.ingest.contract import build_contract
    from app.ingest.profiler import profile_ingest
    from app.pipeline import run_pipeline
    from app.core.store import SessionStore

    rng = np.random.default_rng(5)
    rows = 400
    frame = pd.DataFrame(
        {
            "Drilling Utilization": rng.uniform(0.8, 0.99, rows),
            "Drilling Queue Time": rng.uniform(20, 60, rows),
            "Milling Utilization": rng.uniform(0.2, 0.5, rows),
            "Milling Queue Time": rng.uniform(0, 2, rows),
            "Assembly Utilization": rng.uniform(0.3, 0.6, rows),
            "Total parts": rng.integers(300, 500, rows),
        }
    )
    path = tmp_path / "process.csv"
    frame.to_csv(path, index=False)
    ingest_result = ingest_path(path)
    contract = build_contract(ingest_result, profile_ingest(ingest_result))
    dataset_id = contract["dataset_id"]
    artifacts = tmp_path / "artifacts"
    analysis = run_pipeline(dataset_id, "process.csv", contract, ingest_result, artifacts)
    assert analysis["status"] == "complete", analysis.get("error")

    store = SessionStore(tmp_path / "runtime")
    store.create(path, contract, ingest_result=ingest_result)
    store.set_analysis(dataset_id, analysis)

    record = run_investigation(
        _synthetic_inspection(),
        dataset_id,
        store=store,
        artifacts_dir=artifacts,
        models_dir=tmp_path / "models",
        investigations_dir=tmp_path / "inv",
    )
    stages = {stage["id"]: stage for stage in record["stages"]}
    assert stages["process_correlation"]["status"] == "PARTIAL"
    assert stages["process_correlation"]["epistemic"] == "OBSERVED"
    assert stages["bottleneck"]["status"] == "COMPLETE"
    assert stages["root_cause"]["status"] in {"COMPLETE", "DATA_GAP", "FAILED"}
    assert stages["impact"]["status"] == "AWAITING_INPUT"
    assert stages["what_if"]["status"] in {"AWAITING_INPUT", "COMPLETE"}
    assert stages["recommendation"]["status"] in {"COMPLETE", "DATA_GAP"}
    assert record["status"] in {"COMPLETE", "PARTIAL", "REVIEW_REQUIRED"}


def test_investigation_api_requires_real_inspection(client):
    missing = client.post("/api/investigations/run", json={"inspection_id": "doesnotexist"})
    assert missing.status_code == 404
    assert missing.json()["detail"]["code"] == "INSPECTION_NOT_FOUND"


def test_investigation_api_over_persisted_inspection(client, runtime_dir):
    from app.core.settings import VISION_MODEL_DIR

    buffer = io.BytesIO()
    Image.new("L", (32, 32), 90).save(buffer, format="PNG")
    result = _synthetic_inspection()
    result["inspection_id"] = "invapitest0001"
    persist_inspection(VISION_MODEL_DIR, result, buffer.getvalue())

    response = client.post("/api/investigations/run", json={"inspection_id": "invapitest0001"})
    assert response.status_code == 200, response.text
    record = response.json()
    assert record["inspection_id"] == "invapitest0001"
    assert record["status"] in {"DATA_GAP", "REVIEW_REQUIRED", "COMPLETE", "PARTIAL"}

    listing = client.get("/api/investigations").json()
    assert any(entry["investigation_id"] == record["investigation_id"] for entry in listing["investigations"])
    fetched = client.get(f"/api/investigations/{record['investigation_id']}")
    assert fetched.status_code == 200
    assert fetched.json()["stages"]


# ---------------------------------------------------------------------------
# C. Process timeline
# ---------------------------------------------------------------------------

def test_timeline_bins_real_processed_data(tmp_path):
    from app.flow.timeline import build_timeline

    rows = 240
    rng = np.random.default_rng(3)
    frame = pd.DataFrame(
        {
            "Drilling Utilization": np.linspace(0.3, 0.95, rows),
            "Drilling Queue Time": rng.uniform(0, 30, rows),
            "Total parts": np.linspace(500, 380, rows),
        }
    )
    root = tmp_path / "artifacts" / "ds1"
    (root / "processed_data").mkdir(parents=True)
    frame.to_csv(root / "processed_data" / "process.csv.gz", index=False, compression="gzip")
    (root / "processed_data" / "manifest.json").write_text(json.dumps({"process": {"file": "process.csv.gz"}}), encoding="utf-8")

    payload = build_timeline("ds1", root, stations=["Drilling"], preferred_table="process", bins=24)
    assert payload["status"] == "AVAILABLE"
    assert payload["bins"] == 24
    series = payload["series"][0]
    assert series["station"] == "Drilling"
    assert series["metric"] == "utilization"
    assert len(series["values"]) == 24
    assert series["values"][0] < series["values"][-1], "planted rising utilization must be visible"


def test_timeline_reports_unavailable_without_artifact(tmp_path):
    from app.flow.timeline import build_timeline

    payload = build_timeline("ds1", tmp_path / "empty", stations=[], bins=16)
    assert payload["status"] == "NOT_AVAILABLE"
    assert payload["series"] == []
    assert "No processed-data artifact" in payload["reason"]


# ---------------------------------------------------------------------------
# D. Feature space projection
# ---------------------------------------------------------------------------

def test_feature_space_projection_is_deterministic_and_valid():
    rng = np.random.default_rng(4)
    embeddings = rng.normal(0, 1, (120, 32))
    labels = np.repeat(np.arange(3), 40)
    names = ["a", "b", "c"]
    first = _build_feature_space(embeddings, labels, names)
    second = _build_feature_space(embeddings, labels, names)
    assert first["components"].shape == (2, 32)
    assert np.allclose(first["components"], second["components"])
    assert first["payload"] == second["payload"]
    explained = sum(first["payload"]["explained_variance_ratio"])
    assert 0.0 < explained <= 1.0
    assert set(first["payload"]["clouds"].keys()) == set(names)
    assert all(len(points) <= 90 for points in first["payload"]["clouds"].values())


def test_projection_of_new_sample_uses_stored_components(tmp_path):
    model = VisionModel(tmp_path / "no_model")
    assert model.project_feature_space(np.zeros((1, 4))) is None
    model.feature_space_components = np.array([[1.0, 0.0, 0.0, 0.0], [0.0, 1.0, 0.0, 0.0]])
    model.feature_space_mean = np.zeros(4)
    point = model.project_feature_space(np.array([[3.0, -2.0, 9.0, 9.0]]))
    assert point == [3.0, -2.0]


def test_feature_space_api_reports_not_trained(client):
    response = client.get("/api/vision/feature-space")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] in {"NOT_TRAINED", "NOT_AVAILABLE", "AVAILABLE"}
    if body["status"] != "AVAILABLE":
        assert body["reason"]
        assert body["clouds"] == {}
