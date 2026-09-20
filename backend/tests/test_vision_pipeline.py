"""Phase 12 vision pipeline tests: real training/inference logic.

Tests the algorithm components with synthetic fixtures (fast) - the full
trained-model behaviour is verified against the real dataset in
verify_phase12_real.py.
"""

from __future__ import annotations

import io
import json
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from app.vision.inference import (
    VisionModel,
    VisionModelError,
    attempt_process_link,
    get_inspection,
    list_inspections,
    render_heatmap,
)
from app.vision.training import (
    build_grouped_splits,
    dataset_fingerprint,
    discover_class_dataset,
    fit_temperature,
    softmax,
)


# ---------------------------------------------------------------------------
# Fixtures: tiny class-folder dataset on disk
# ---------------------------------------------------------------------------

def _write_image(path: Path, color: int, size: int = 32) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("L", (size, size), color).save(path)


@pytest.fixture()
def tiny_class_dataset(tmp_path) -> Path:
    root = tmp_path / "images"
    for index in range(12):
        _write_image(root / "normal" / f"normal_{index:03d}.png", 200 + index)
    for index in range(12):
        _write_image(root / "scratch" / f"scratch_{index:03d}.png", 60 + index)
    return root


# ---------------------------------------------------------------------------
# A. DATASET DISCOVERY AND SPLITTING
# ---------------------------------------------------------------------------

def test_discover_class_dataset(tiny_class_dataset):
    classes = discover_class_dataset(tiny_class_dataset)
    assert set(classes.keys()) == {"normal", "scratch"}
    assert len(classes["normal"]) == 12


def test_grouped_split_is_disjoint_and_complete(tiny_class_dataset):
    classes = discover_class_dataset(tiny_class_dataset)
    splits = build_grouped_splits(classes, seed=1)
    train = {str(p) for p in splits["train"]}
    val = {str(p) for p in splits["validation"]}
    test = {str(p) for p in splits["test"]}
    assert train.isdisjoint(val)
    assert train.isdisjoint(test)
    assert val.isdisjoint(test)
    assert len(train) + len(val) + len(test) == 24
    assert splits["labels"]


def test_grouped_split_keeps_near_duplicates_together(tmp_path):
    root = tmp_path / "dupes"
    # two identical images must land in the same split
    for index in range(10):
        _write_image(root / "normal" / f"n{index}.png", 100)
    for index in range(10):
        _write_image(root / "defect" / f"d{index}.png", 40)
    classes = discover_class_dataset(root)
    splits = build_grouped_splits(classes, seed=3)
    location = {}
    for bucket in ("train", "validation", "test"):
        for path in splits[bucket]:
            location[str(path)] = bucket
    same_group = [str(p) for p in classes["normal"]]
    buckets = {location[p] for p in same_group}
    assert len(buckets) == 1, "identical images were spread across splits"


def test_dataset_fingerprint_stable(tiny_class_dataset):
    first = dataset_fingerprint(tiny_class_dataset)
    second = dataset_fingerprint(tiny_class_dataset)
    assert first == second


# ---------------------------------------------------------------------------
# B. CALIBRATION MATH
# ---------------------------------------------------------------------------

def test_fit_temperature_reduces_nll():
    rng = np.random.default_rng(0)
    logits = rng.normal(size=(200, 3)) * 4
    labels = logits.argmax(axis=1)

    def nll(temperature):
        scaled = logits / temperature
        probabilities = softmax(scaled)
        picked = probabilities[np.arange(len(labels)), labels]
        return float(-np.mean(np.log(np.clip(picked, 1e-12, 1.0))))

    temperature = fit_temperature(logits, labels)
    assert temperature > 0
    assert nll(temperature) <= nll(1.0) + 1e-9


def test_softmax_is_a_distribution():
    probabilities = softmax(np.array([[1.0, 2.0, 3.0]]))
    assert probabilities.sum() == pytest.approx(1.0)
    assert (probabilities >= 0).all()


# ---------------------------------------------------------------------------
# C. LOCALIZATION RENDERING
# ---------------------------------------------------------------------------

def test_render_heatmap_produces_png_and_box():
    cam = np.zeros((7, 7), dtype=np.float32)
    cam[2:4, 3:5] = 1.0
    heatmap, box = render_heatmap(cam, 256, 256)
    assert heatmap
    assert box is not None
    assert box["type"] == "MODEL-DERIVED"
    assert 0 <= box["x"] < 256 and 0 <= box["y"] < 256
    assert box["width"] > 0 and box["height"] > 0


def test_render_heatmap_empty_cam_has_no_box():
    heatmap, box = render_heatmap(np.zeros((7, 7), dtype=np.float32), 256, 256)
    assert heatmap
    assert box is None


# ---------------------------------------------------------------------------
# D. DECISION / PROCESS LINK / HONESTY
# ---------------------------------------------------------------------------

def test_process_link_is_not_available_without_metadata():
    link = attempt_process_link()
    assert link["status"] == "NOT_AVAILABLE"
    assert "PROCESS LINK NOT AVAILABLE" in link["reason"]


def test_untrained_model_rejects_inspection(tmp_path):
    model = VisionModel(tmp_path / "empty_artifacts")
    assert model.available is False
    with pytest.raises(VisionModelError) as excinfo:
        model.inspect(b"not-an-image")
    assert excinfo.value.code == "VISION_MODEL_NOT_TRAINED"


# ---------------------------------------------------------------------------
# E. INSPECTION PERSISTENCE
# ---------------------------------------------------------------------------

def test_inspection_history_reads_only_real_records(tmp_path):
    assert list_inspections(tmp_path) == []
    assert get_inspection(tmp_path, "missing") is None


def test_api_vision_dataset_profile(client):
    response = client.get("/api/vision/dataset")
    if response.status_code == 404:
        pytest.skip("no image dataset present in this workspace")
    body = response.json()
    assert body["profile"]["image_count"] > 0
    assert body["class_counts"]
    assert "annotations" in body
    serialized = json.dumps(body).lower()
    assert "traceback" not in serialized


def test_api_vision_train_rejects_path_outside_project(client):
    response = client.post("/api/vision/train", json={"dataset_dir": "C:/Windows"})
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "DATASET_PATH_NOT_ALLOWED"


def test_api_vision_stream_emits_ndjson_events(client):
    """The streaming endpoint emits NDJSON. Without a trained model it must
    still stream a structured error event (never a broken connection)."""
    import io as _io
    import json as _json

    from PIL import Image

    buffer = _io.BytesIO()
    Image.new("RGB", (32, 32), (100, 100, 100)).save(buffer, format="PNG")
    response = client.post(
        "/api/vision/inspect/stream",
        files={"file": ("probe.png", buffer.getvalue(), "image/png")},
    )
    assert response.status_code == 200
    assert "ndjson" in response.headers.get("content-type", "")
    lines = [line for line in response.text.splitlines() if line.strip()]
    assert lines, "stream produced no events"
    events = [_json.loads(line) for line in lines]
    assert events[-1]["event"] in {"error", "result"}
    if events[-1]["event"] == "error":
        assert events[-1]["error"]["code"] == "VISION_MODEL_NOT_TRAINED"
    else:
        stage_ids = [event["stage"]["id"] for event in events if event["event"] == "stage"]
        assert stage_ids[0] == "image_received"
        assert stage_ids[-1] == "process_link"

        # redesign contract: the result must expose the real embedding and the
        # distance of this sample to every known class centroid
        result = events[-1]["result"]
        feature_vector = result["feature_vector"]
        assert feature_vector["dim"] == len(feature_vector["values"])
        assert feature_vector["dim"] > 0
        assert result["class_distances"].keys() == set(result["model"]["classes"])
        for distance in result["class_distances"].values():
            assert isinstance(distance, float) and distance >= 0.0

        # and the streaming feature_extraction stage must carry the same vector
        feature_stage = next(event["stage"] for event in events if event["stage"]["id"] == "feature_extraction")
        assert len(feature_stage["metrics"]["embedding"]) == feature_vector["dim"]
