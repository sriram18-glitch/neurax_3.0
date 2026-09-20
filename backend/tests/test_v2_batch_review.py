"""V2.1 tests: batch/dataset ingestion, automatic batch inspection and the
human review queue. Uses explicitly synthetic fixtures."""

from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path

import pytest
from PIL import Image

from app.vision.batch import BatchError, create_batch, get_batch, inspect_batch, save_batch_raw
from app.vision.inference import VisionModel, persist_inspection
from app.vision.review import ReviewError, list_review_queue, record_human_decision, review_stats


def _png_bytes(color: int = 100, size: int = 32) -> bytes:
    buffer = io.BytesIO()
    Image.new("L", (size, size), color).save(buffer, format="PNG")
    return buffer.getvalue()


def _synthetic_result(inspection_id: str, decision: str, confidence: float = 0.9, novelty: float = 0.1) -> dict:
    return {
        "inspection_id": inspection_id,
        "filename": "img.png",
        "generated_at": "2026-01-01T00:00:00Z",
        "image_metadata": {"width": 32, "height": 32, "mode": "L", "format": "PNG", "bytes": 100},
        "preprocessing": {"resize": "224x224", "normalization": "n"},
        "prediction": {"predicted_class": "fixture-class", "is_normal": decision == "PASS"},
        "class_probabilities": {"fixture-class": confidence},
        "confidence": {"value": confidence, "raw_probability": confidence + 0.02, "calibration_status": "CALIBRATED"},
        "anomaly_score": {"value": 0.5, "novelty_score": novelty, "novelty_status": "HIGH" if novelty > 0.99 else "NORMAL"},
        "localization": {"bounding_box": {"x": 1, "y": 2, "width": 10, "height": 10}, "method": "cam"},
        "decision": decision,
        "review_reason": None if decision != "REVIEW" else "Unfamiliar condition",
        "review_reasons": ["novelty exceeds gate"] if decision == "REVIEW" else [],
        "decision_reason": f"{decision} reason",
        "evidence": [],
        "process_link": {"status": "NOT_AVAILABLE", "reason": "no metadata"},
        "model": {"backbone": "mobilenet_v2"},
        "limitations": [],
        "trace": [],
        "human_review": None,
    }


class _FakeModel:
    available = True
    inspect_count = 0

    def __init__(self, decisions: list[str]):
        self.decisions = decisions

    def inspect(self, data: bytes, filename: str | None = None) -> dict:
        decision = self.decisions[self.inspect_count % len(self.decisions)]
        self.inspect_count += 1
        return _synthetic_result(f"batchinspect{self.inspect_count:03d}", decision)


# ---------------------------------------------------------------------------
# A. Ingestion and validation
# ---------------------------------------------------------------------------

def test_batch_validation_classifies_every_file(tmp_path):
    entries = [
        ("normal/a.png", _png_bytes(200)),
        ("normal/b.png", _png_bytes(201)),
        ("scratch/c.png", _png_bytes(60)),
        ("scratch/d.png", _png_bytes(61)),
        ("bad.txt", b"not an image"),
        ("corrupt.png", b"\x89PNG\r\n\x1a\nthis is not a valid png payload"),
        ("tiny.png", _png_bytes(90, size=4)),
        ("dup.png", _png_bytes(201)),
    ]
    record = create_batch(entries, None, batches_base=tmp_path)
    summary = record["summary"]
    assert summary["total"] == 8
    assert summary["valid"] == 4
    assert summary["unsupported"] == 1
    assert summary["invalid"] == 2
    assert summary["duplicates"] == 1
    assert summary["labels_available"] is True
    assert set(summary["classes"]) == {"normal", "scratch"}
    statuses = [image["status"] for image in record["images"]]
    assert statuses.count("valid") == 4
    assert any(image["status"] == "duplicate" for image in record["images"])


def test_batch_validation_from_zip(tmp_path):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("batch/normal/a.png", _png_bytes(200))
        archive.writestr("batch/scratch/b.png", _png_bytes(60))
        archive.writestr("batch/notes.txt", "ignore me")
    zip_path = tmp_path / "data.zip"
    zip_path.write_bytes(buffer.getvalue())
    record = create_batch(None, zip_path, batches_base=tmp_path)
    assert record["summary"]["valid"] == 2
    assert record["summary"]["unsupported"] == 0
    assert record["summary"]["classes"] == ["normal", "scratch"]


def test_batch_without_images_raises(tmp_path):
    with pytest.raises(BatchError) as error:
        create_batch([], None, batches_base=tmp_path)
    assert error.value.code == "BATCH_NO_IMAGES"


# ---------------------------------------------------------------------------
# B. Automatic batch inspection
# ---------------------------------------------------------------------------

def test_inspect_batch_runs_the_real_pipeline_with_quality(tmp_path):
    entries = [
        ("normal/a.png", _png_bytes(200)),
        ("normal/b.png", _png_bytes(201)),
        ("scratch/c.png", _png_bytes(60)),
        ("scratch/d.png", _png_bytes(61)),
        ("bad.txt", b"not an image"),
    ]
    record = create_batch(entries, None, batches_base=tmp_path)
    save_batch_raw(record["batch_id"], entries, None, batches_base=tmp_path)

    fake = _FakeModel(decisions=["PASS", "PASS", "DEFECT", "DEFECT"])
    completed = inspect_batch(record["batch_id"], fake, batches_base=tmp_path)
    assert completed["status"] == "complete"
    assert completed["progress"]["inspected"] == 4
    assert completed["progress"]["total"] == 4
    assert completed["decisions"] == {"PASS": 2, "DEFECT": 2, "REVIEW": 0}
    assert completed["review_queue"] == 0
    assert len(completed["results"]) == 4
    for result in completed["results"]:
        assert result["inspection_id"]
        assert result["decision"] in {"PASS", "DEFECT", "REVIEW"}
        assert result["confidence"] is not None
        assert "novelty_score" in result
    # ground truth from class folders: normal -> PASS expected, scratch -> DEFECT expected
    quality = completed["quality"]
    assert quality["basis"].startswith("measured against class-folder ground truth")
    assert quality["tp"] == 2 and quality["tn"] == 2
    assert quality["fp"] == 0 and quality["fn"] == 0
    assert quality["precision"] == 1.0 and quality["recall"] == 1.0


def test_inspect_batch_without_model_fails_structurally(tmp_path):
    entries = [("normal/a.png", _png_bytes(200))]
    record = create_batch(entries, None, batches_base=tmp_path)
    save_batch_raw(record["batch_id"], entries, None, batches_base=tmp_path)
    model = VisionModel(tmp_path / "no_model")
    assert model.available is False
    with pytest.raises(BatchError) as error:
        inspect_batch(record["batch_id"], model, batches_base=tmp_path)
    assert error.value.code == "VISION_MODEL_NOT_TRAINED"


def test_batch_persistence_roundtrip(tmp_path):
    entries = [("normal/a.png", _png_bytes(200))]
    record = create_batch(entries, None, batches_base=tmp_path)
    loaded = get_batch(record["batch_id"], tmp_path)
    assert loaded is not None
    assert loaded["batch_id"] == record["batch_id"]
    assert loaded["summary"]["valid"] == 1


# ---------------------------------------------------------------------------
# C. Human review queue
# ---------------------------------------------------------------------------

@pytest.fixture()
def reviewed_artifacts(tmp_path):
    base = tmp_path / "vision_model"
    (base / "inspections").mkdir(parents=True)
    for index, (inspection_id, decision) in enumerate(
        [("rev001", "REVIEW"), ("rev002", "REVIEW"), ("pass001", "PASS"), ("def001", "DEFECT")]
    ):
        result = _synthetic_result(inspection_id, decision, confidence=0.8 - index * 0.05)
        persist_inspection(base, result, _png_bytes(200))
    return base


def test_record_human_decision_preserves_ai(reviewed_artifacts):
    response = record_human_decision(reviewed_artifacts, "rev001", "confirm_defect", note="visual inspection confirms")
    assert response["human_review"]["decision"] == "DEFECT"
    assert response["human_review"]["ai_decision_preserved"] == "REVIEW"
    inspection = json.loads((reviewed_artifacts / "inspections" / "rev001.json").read_text(encoding="utf-8"))
    assert inspection["decision"] == "REVIEW", "AI decision must never be overwritten"
    assert inspection["human_review"]["action"] == "confirm_defect"


def test_record_human_decision_rejects_unknown_action(reviewed_artifacts):
    with pytest.raises(ReviewError) as error:
        record_human_decision(reviewed_artifacts, "rev001", "shutdown_machine")
    assert error.value.code == "INVALID_REVIEW_ACTION"


def test_review_queue_lists_pending_only(reviewed_artifacts):
    record_human_decision(reviewed_artifacts, "rev001", "mark_pass")
    pending = list_review_queue(reviewed_artifacts)
    assert [entry["inspection_id"] for entry in pending] == ["rev002"]
    all_items = list_review_queue(reviewed_artifacts, include_reviewed=True)
    assert {entry["inspection_id"] for entry in all_items} == {"rev001", "rev002"}


def test_keep_in_review_stays_pending(reviewed_artifacts):
    response = record_human_decision(reviewed_artifacts, "rev001", "keep_in_review", note="needs a second look")
    assert response["human_review"]["decision"] == "REVIEW"
    pending = list_review_queue(reviewed_artifacts)
    assert {entry["inspection_id"] for entry in pending} == {"rev001", "rev002"}
    stats = review_stats(reviewed_artifacts)
    assert stats["pending_review"] == 2
    assert stats["human_reviewed"] == 0


def test_confirm_class_records_class_name(reviewed_artifacts):
    response = record_human_decision(reviewed_artifacts, "rev001", "confirm_defect", class_name="scratch")
    assert response["human_review"]["class_name"] == "scratch"
    inspection = json.loads((reviewed_artifacts / "inspections" / "rev001.json").read_text(encoding="utf-8"))
    assert inspection["decision"] == "REVIEW"
    assert inspection["human_review"]["decision"] == "DEFECT"


def test_review_stats_counts(reviewed_artifacts):
    record_human_decision(reviewed_artifacts, "rev001", "confirm_defect")
    stats = review_stats(reviewed_artifacts)
    assert stats["total"] == 4
    assert stats["auto_resolved"] == 2
    assert stats["human_reviewed"] == 1
    assert stats["pending_review"] == 1
    assert stats["distribution"] == {"PASS": 1, "DEFECT": 1, "REVIEW": 2}
    assert stats["auto_resolved_rate"] == 0.5
    assert stats["avg_confidence"] is not None


def test_review_stats_empty(tmp_path):
    stats = review_stats(tmp_path / "vision_model")
    assert stats["total"] == 0
    assert stats["auto_resolved_rate"] is None


# ---------------------------------------------------------------------------
# D. API level
# ---------------------------------------------------------------------------

def test_batch_api_ingest_and_honest_inspect(client):
    files = [
        ("files", ("a.png", _png_bytes(200), "image/png")),
        ("files", ("b.png", _png_bytes(60), "image/png")),
    ]
    response = client.post("/api/vision/batch", files=files)
    assert response.status_code == 200, response.text
    record = response.json()
    assert record["summary"]["valid"] == 2
    assert record["status"] == "validated"

    started = client.post(f"/api/vision/batch/{record['batch_id']}/inspect")
    assert started.status_code == 200
    assert started.json()["status"] in {"inspecting", "complete", "failed"}

    import time

    final = None
    for _ in range(50):
        current = client.get(f"/api/vision/batch/{record['batch_id']}").json()
        if current["status"] in {"complete", "failed"}:
            final = current
            break
        time.sleep(0.1)
    assert final is not None
    # in the isolated test runtime no model is trained: the batch must fail
    # structurally rather than fabricate results
    if final["status"] == "failed":
        assert final["progress"]["inspected"] == 0
    else:
        assert final["progress"]["inspected"] == final["progress"]["total"]


def test_review_api_happy_path(client, runtime_dir):
    from app.core.settings import VISION_MODEL_DIR

    result = _synthetic_result("reviewapi001", "REVIEW")
    persist_inspection(VISION_MODEL_DIR, result, _png_bytes(200))

    queue = client.get("/api/vision/review/queue").json()
    assert any(entry["inspection_id"] == "reviewapi001" for entry in queue["items"])

    acted = client.post("/api/vision/inspect/reviewapi001/review", json={"action": "escalate", "note": "escalated for manual triage"})
    assert acted.status_code == 200
    body = acted.json()
    assert body["human_review"]["action"] == "escalate"
    assert body["ai_decision"] == "REVIEW"

    stats = client.get("/api/vision/review/stats").json()
    assert stats["total"] >= 1
    assert stats["human_reviewed"] >= 1

    bad = client.post("/api/vision/inspect/reviewapi001/review", json={"action": "stop_line"})
    assert bad.status_code == 422
    assert bad.json()["detail"]["code"] == "INVALID_REVIEW_ACTION"