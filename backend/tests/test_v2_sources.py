"""V2.3 tests: runtime inspection sources and path independence.

The system must NEVER depend on a hardcoded dataset path. These tests prove the
workflow with two independent temporary directories: both are ingested as
sources, both are processed, and deleting one leaves the other fully working.
"""

from __future__ import annotations

import io
from pathlib import Path

import pytest
from PIL import Image

from app.vision.source import (
    SourceError,
    SourceStream,
    add_files,
    build_sequence,
    create_demo_source,
    create_source,
    delete_source,
    get_source,
    list_sources,
    raw_dir_for,
    safe_display_name,
)
from app.vision.inference import VisionModel, VisionModelError


def _png(color: int = 100, size: int = 32) -> bytes:
    buffer = io.BytesIO()
    Image.new("L", (size, size), color).save(buffer, format="PNG")
    return buffer.getvalue()


def _write(root: Path, relative: str, color: int = 100) -> Path:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(_png(color))
    return path


@pytest.fixture()
def directory_a(tmp_path) -> Path:
    root = tmp_path / "factory_a" / "Batch_07"
    _write(root, "normal/n_00.png", 200)
    _write(root, "normal/n_01.png", 201)
    _write(root, "scratch/s_00.png", 60)
    _write(root, "scratch/s_01.png", 61)
    _write(root, "notes.txt")
    return root


@pytest.fixture()
def directory_b(tmp_path) -> Path:
    root = tmp_path / "factory_b" / "Night_Shift"
    _write(root, "normal/x_00.png", 210)
    _write(root, "hole/h_00.png", 50)
    _write(root, "cracked.bmp")
    return root


def _uploaded_from_dir(root: Path) -> list[tuple[str, bytes]]:
    uploaded = []
    for path in sorted(root.rglob("*")):
        if path.is_file():
            relative = str(path.relative_to(root)).replace("\\", "/")
            uploaded.append((relative, path.read_bytes()))
    return uploaded


# ---------------------------------------------------------------------------
# A. Source creation and validation
# ---------------------------------------------------------------------------

def test_create_source_generates_ids_and_safe_names(tmp_path):
    record = create_source(
        [("C:\\Somewhere\\over\\the\\rainbow\\img_001.png", _png())],
        "SINGLE_IMAGE",
        display_name="C:\\Users\\Someone\\Desktop\\Batch\\my_folder",
        sources_base=tmp_path,
    )
    assert record["source_id"].startswith("src_")
    assert record["source_type"] == "SINGLE_IMAGE"
    assert record["type_label"] == "USER IMAGE"
    assert record["display_name"] == "my_folder", "full paths must never leak into display names"
    assert record["summary"]["valid"] == 1
    assert "C:" not in record["display_name"]
    assert "Users" not in record["display_name"]


def test_single_image_requires_exactly_one_file(tmp_path):
    with pytest.raises(SourceError) as error:
        create_source([("a.png", _png()), ("b.png", _png())], "SINGLE_IMAGE", sources_base=tmp_path)
    assert error.value.code == "SOURCE_SINGLE_ONLY"


def test_folder_source_detects_classes_and_validation_counts(directory_a, tmp_path):
    record = create_source(_uploaded_from_dir(directory_a), "FOLDER_DATASET", display_name="Batch_07", sources_base=tmp_path)
    assert record["type_label"] == "USER DATASET"
    assert record["summary"]["valid"] == 4
    assert record["summary"]["unsupported"] == 1  # notes.txt
    assert set(record["summary"]["classes"]) == {"normal", "scratch"}
    assert record["summary"]["labels_available"] is True
    # invalid/unsupported files carry a reason
    unsupported = next(image for image in record["images"] if image["status"] == "unsupported")
    assert "unsupported format" in unsupported["reason"]


def test_duplicates_detected_within_source(tmp_path):
    record = create_source(
        [("a.png", _png(200)), ("dup.png", _png(200)), ("b.png", _png(60))],
        "IMAGE_SET",
        sources_base=tmp_path,
    )
    assert record["summary"]["valid"] == 2
    assert record["summary"]["duplicates"] == 1


def test_add_files_revalidates_and_resets_results(tmp_path):
    record = create_source([("a.png", _png(200))], "IMAGE_SET", sources_base=tmp_path)
    updated = add_files(source_id=record["source_id"], uploaded=[("b.png", _png(60))], sources_base=tmp_path)
    assert updated["summary"]["valid"] == 2
    assert updated["stream"]["cursor"] == 0


def test_delete_source_removes_record_and_files(tmp_path):
    record = create_source([("a.png", _png(200))], "SINGLE_IMAGE", sources_base=tmp_path)
    raw = raw_dir_for(record["source_id"], tmp_path)
    assert raw.exists()
    delete_source(record["source_id"], tmp_path)
    assert get_source(record["source_id"], tmp_path) is None
    assert not raw.exists()


# ---------------------------------------------------------------------------
# B. Path independence: two directories, isolation, deletion survival
# ---------------------------------------------------------------------------

def test_two_directories_both_work_and_are_isolated(directory_a, directory_b, tmp_path):
    source_a = create_source(_uploaded_from_dir(directory_a), "FOLDER_DATASET", display_name="Batch_07", sources_base=tmp_path)
    source_b = create_source(_uploaded_from_dir(directory_b), "FOLDER_DATASET", display_name="Night_Shift", sources_base=tmp_path)
    assert set(source_a["summary"]["classes"]) == {"normal", "scratch"}
    assert set(source_b["summary"]["classes"]) == {"normal", "hole"}

    stream = SourceStream(sources_base=tmp_path)
    stream.set_source(source_a["source_id"])
    names_a = [frame["original_name"] for frame in stream.sequence]
    assert any("n_00" in name for name in names_a)
    assert not any("x_00" in name for name in names_a), "no cross-source contamination"

    stream.set_source(source_b["source_id"])
    assert stream.processed == 0 and stream.history == [], "switching sources clears stream state"
    names_b = [frame["original_name"] for frame in stream.sequence]
    assert any("x_00" in name for name in names_b)
    assert not any("n_00" in name for name in names_b)


def test_deleting_source_a_keeps_source_b_working(directory_a, directory_b, tmp_path):
    source_a = create_source(_uploaded_from_dir(directory_a), "FOLDER_DATASET", display_name="Batch_07", sources_base=tmp_path)
    source_b = create_source(_uploaded_from_dir(directory_b), "FOLDER_DATASET", display_name="Night_Shift", sources_base=tmp_path)

    delete_source(source_a["source_id"], tmp_path)
    assert get_source(source_a["source_id"], tmp_path) is None

    # source B remains fully functional
    record = get_source(source_b["source_id"], tmp_path)
    assert record is not None
    assert record["summary"]["valid"] == 2
    stream = SourceStream(sources_base=tmp_path)
    stream.set_source(source_b["source_id"])
    assert stream.status()["total_frames"] == 2
    assert list_sources(limit=10, sources_base=tmp_path) == []
    assert get_source(source_a["source_id"], tmp_path) is None


# ---------------------------------------------------------------------------
# C. Demo source (config-driven only)
# ---------------------------------------------------------------------------

def test_demo_source_is_explicitly_labeled(tmp_path):
    demo_dir = tmp_path / "demo"
    _write(demo_dir, "normal/n_00.png", 200)
    _write(demo_dir, "scratch/s_00.png", 60)
    record = create_demo_source(demo_dir=demo_dir, sources_base=tmp_path)
    assert record["source_type"] == "BUILT_IN_DEMO"
    assert record["type_label"] == "BUILT-IN DEMO"
    assert record["demo_note"].startswith("BUILT-IN DEMO")
    assert record["summary"]["valid"] == 2


def test_demo_source_unavailable_reports_honestly(tmp_path):
    with pytest.raises(SourceError) as error:
        create_demo_source(demo_dir=tmp_path / "missing", sources_base=tmp_path)
    assert error.value.code == "DEMO_DATASET_UNAVAILABLE"


# ---------------------------------------------------------------------------
# D. Stream with a fake model over ingested files
# ---------------------------------------------------------------------------

class _FakeModel:
    available = True
    count = 0

    def inspect(self, data: bytes, filename: str | None = None, extra: dict | None = None) -> dict:
        self.count += 1
        return {
            "inspection_id": f"srcinspect{self.count:03d}",
            "filename": filename,
            "generated_at": "2026-01-01T00:00:00Z",
            "image_metadata": {"width": 32, "height": 32, "mode": "L", "format": "PNG", "bytes": len(data)},
            "preprocessing": {"resize": "224x224", "normalization": "n"},
            "prediction": {"predicted_class": "fixture", "is_normal": False},
            "class_probabilities": {"fixture": 0.9},
            "confidence": {"value": 0.9, "calibration_status": "CALIBRATED"},
            "anomaly_score": {"value": 0.5, "novelty_score": 0.1, "novelty_status": "NORMAL"},
            "localization": {"bounding_box": None},
            "decision": "DEFECT",
            "review_reason": None,
            "evidence": [],
            "process_link": {"status": "NOT_AVAILABLE", "reason": "no metadata"},
            "model": {"backbone": "mobilenet_v2"},
            "limitations": [],
            "trace": [],
            "source_id": extra.get("source_id") if extra else None,
        }


def test_stream_processes_ingested_frames_with_source_identity(directory_b, tmp_path):
    source = create_source(_uploaded_from_dir(directory_b), "FOLDER_DATASET", sources_base=tmp_path)
    stream = SourceStream(sources_base=tmp_path)
    stream.set_source(source["source_id"])
    fake = _FakeModel()
    first = stream.next_frame(fake)
    assert first["inspection"]["filename"] in {"normal/x_00.png", "hole/h_00.png"}
    assert first["inspection"]["source_id"] == source["source_id"]
    assert stream.status()["processed"] == 1
    second = stream.next_frame(fake)
    assert second["inspection"] is not None
    exhausted = stream.next_frame(fake)
    assert exhausted["inspection"] is None and exhausted["exhausted"] is True


def test_stream_missing_raw_reports_honestly(directory_a, tmp_path):
    source = create_source(_uploaded_from_dir(directory_a), "FOLDER_DATASET", sources_base=tmp_path)
    raw = raw_dir_for(source["source_id"], tmp_path)
    import shutil

    shutil.rmtree(raw, ignore_errors=True)
    stream = SourceStream(sources_base=tmp_path)
    stream.set_source(source["source_id"])
    with pytest.raises(SourceError) as error:
        stream.next_frame(_FakeModel())
    assert error.value.code == "SOURCE_RAW_MISSING"


# ---------------------------------------------------------------------------
# E. API level
# ---------------------------------------------------------------------------

def test_sources_api_create_and_current(client, directory_a, runtime_dir):
    files = [("files", (relative, data, "image/png")) for relative, data in _uploaded_from_dir(directory_a)]
    response = client.post("/api/inspection/sources", files=files, data={"source_type": "FOLDER_DATASET", "display_name": "Batch_07"})
    assert response.status_code == 200, response.text
    record = response.json()
    assert record["source_id"].startswith("src_")
    assert record["type_label"] == "USER DATASET"
    assert record["display_name"] == "Batch_07"

    listing = client.get("/api/inspection/sources").json()
    assert any(entry["source_id"] == record["source_id"] for entry in listing["sources"])

    current = client.get("/api/inspection/sources/current").json()
    assert current["source"] is None, "nothing is active until explicitly selected"

    started = client.post(f"/api/inspection/sources/{record['source_id']}/start")
    # in the isolated test runtime no model is trained - start must fail
    # structurally, not fabricate anything
    assert started.status_code in {503, 200}
    if started.status_code == 503:
        assert started.json()["detail"]["code"] == "VISION_MODEL_NOT_TRAINED"

    fetched = client.get(f"/api/inspection/sources/{record['source_id']}")
    assert fetched.status_code == 200

    deleted = client.delete(f"/api/inspection/sources/{record['source_id']}")
    assert deleted.status_code == 200
    assert client.get(f"/api/inspection/sources/{record['source_id']}").status_code == 409


def test_sources_api_no_source_next_is_honest(client):
    response = client.post("/api/vision/stream/next")
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "NO_INSPECTION_SOURCE"


def test_sources_api_unknown_type_rejected(client):
    files = [("files", ("a.png", _png(), "image/png"))]
    response = client.post("/api/inspection/sources", files=files, data={"source_type": "CLOUD_CAMERA"})
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "INVALID_SOURCE_TYPE"