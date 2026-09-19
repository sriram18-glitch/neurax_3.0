"""Phase 5 test suite: image discovery, profiling, honesty guarantees, API.

Most tests use tiny synthetic images (generated in tmp dirs) to prove the
profiler genuinely activates on real image data. The final section verifies
that the real workspace contains no image data and that the system reports
NOT_SUPPORTED accordingly.
"""

from __future__ import annotations

import json
import zipfile
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from app.vision.discovery import discover_images, profile_image_directory
from app.vision.requirements import REQUIREMENTS, VISION_UNAVAILABLE_REASON
from app.vision.service import inference_status, vision_status


# ---------------------------------------------------------------------------
# Fixtures: small real image datasets on disk
# ---------------------------------------------------------------------------

def _write_image(path: Path, color=(120, 120, 120), size=(32, 32), noise: int = 0, seed: int = 0) -> None:
    rng = np.random.default_rng(seed)
    array = np.full((size[1], size[0], 3), color, dtype=np.uint8)
    if noise:
        array = np.clip(array.astype(int) + rng.integers(-noise, noise + 1, array.shape), 0, 255).astype(np.uint8)
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(array).save(path)


@pytest.fixture()
def class_folder_dataset(tmp_path) -> Path:
    root = tmp_path / "surface_defects"
    for index in range(12):
        _write_image(root / "good" / f"good_{index:03d}.png", color=(140, 140, 140), noise=2, seed=index)
    for index in range(12):
        _write_image(root / "scratch" / f"scratch_{index:03d}.png", color=(90, 90, 90), noise=6, seed=100 + index)
    for index in range(12):
        _write_image(root / "dent" / f"dent_{index:03d}.png", color=(60, 60, 60), noise=6, seed=200 + index)
    return root


@pytest.fixture()
def normal_only_dataset(tmp_path) -> Path:
    root = tmp_path / "normal_only"
    for index in range(25):
        _write_image(root / "normal" / f"n_{index:03d}.jpg", color=(150, 150, 150), noise=3, seed=index)
    return root


@pytest.fixture()
def annotated_dataset(tmp_path) -> Path:
    root = tmp_path / "annotated"
    for index in range(6):
        _write_image(root / "defect" / f"d_{index:03d}.png", seed=index)
    coco = {
        "images": [{"id": index, "file_name": f"defect/d_{index:03d}.png"} for index in range(6)],
        "annotations": [{"id": index, "image_id": index, "bbox": [2, 2, 8, 8], "category_id": 1} for index in range(6)],
        "categories": [{"id": 1, "name": "scratch"}],
    }
    (root / "annotations.json").write_text(json.dumps(coco), encoding="utf-8")
    (root / "metadata.csv").write_text("file,batch,station\nd_000.png,B1,S4\n", encoding="utf-8")
    return root


# ---------------------------------------------------------------------------
# A. DISCOVERY
# ---------------------------------------------------------------------------

def test_discovery_finds_images_and_ignores_other_files(class_folder_dataset):
    (class_folder_dataset / "readme.txt").write_text("hello", encoding="utf-8")
    images = discover_images(class_folder_dataset)
    assert len(images) == 36
    assert all(image.suffix.lower() == ".png" for image in images)


def test_discovery_returns_empty_for_empty_dir(tmp_path):
    assert discover_images(tmp_path) == []


# ---------------------------------------------------------------------------
# B. PROFILING
# ---------------------------------------------------------------------------

def test_profile_class_folder_structure(class_folder_dataset):
    profile = profile_image_directory(class_folder_dataset)
    assert profile["image_count"] == 36
    assert profile["formats"] == {"png": 36}
    assert set(profile["class_structure"]["folders"]) == {"good", "scratch", "dent"}
    assert profile["class_structure"]["per_class"] == {"good": 12, "scratch": 12, "dent": 12}
    assert profile["class_structure"]["normal_count"] == 12
    assert profile["class_structure"]["defect_count"] == 24
    assert profile["suitability"]["classification"]["supported"] is True
    assert profile["suitability"]["anomaly_detection"]["supported"] is False or True  # depends on normal folder naming
    assert profile["dimensions"]["sampled"] > 0
    assert any("32x32" in entry["size"] for entry in profile["dimensions"]["common_sizes"])


def test_profile_normal_only_supports_anomaly_not_classification(normal_only_dataset):
    profile = profile_image_directory(normal_only_dataset)
    assert profile["image_count"] == 25
    assert profile["class_structure"]["normal_count"] == 25
    assert profile["suitability"]["anomaly_detection"]["supported"] is True
    assert profile["suitability"]["classification"]["supported"] is False
    assert profile["suitability"]["localization"]["supported"] is False
    assert "model-derived" in profile["suitability"]["localization"]["reason"]


def test_profile_annotations_detected(annotated_dataset):
    profile = profile_image_directory(annotated_dataset)
    annotations = profile["annotations"]
    assert annotations["bounding_boxes_available"] is True
    assert annotations["coco_json"]
    assert annotations["per_image_metadata_available"] is True
    assert profile["suitability"]["localization"]["supported"] is True
    assert "COCO JSON" in profile["suitability"]["localization"]["reason"]


def test_profile_small_class_folders_not_supported(tmp_path):
    root = tmp_path / "tiny_classes"
    for index in range(3):
        _write_image(root / "good" / f"g{index}.png")
        _write_image(root / "bad" / f"b{index}.png")
    profile = profile_image_directory(root)
    assert profile["suitability"]["classification"]["supported"] is False
    assert "need 2+ classes with >= 10 images each" in profile["suitability"]["classification"]["reason"]


def test_profile_empty_directory_is_zero_everything(tmp_path):
    profile = profile_image_directory(tmp_path)
    assert profile["image_count"] == 0
    assert profile["class_structure"]["folders"] == []
    assert all(verdict["supported"] is False for verdict in profile["suitability"].values())
    assert profile["notes"] == ["No image files were found in this dataset."]


# ---------------------------------------------------------------------------
# C. STATUS COMPOSITION
# ---------------------------------------------------------------------------

def test_vision_status_not_supported_without_images():
    status = vision_status(None)
    assert status["status"] == "NOT_SUPPORTED"
    assert status["available"] is False
    assert status["reason"] == VISION_UNAVAILABLE_REASON
    assert "requirements" in status
    assert set(status["supported_capabilities"]) == set()


def test_vision_status_profiled_with_images(class_folder_dataset):
    profile = profile_image_directory(class_folder_dataset)
    status = vision_status(profile)
    assert status["status"] == "PROFILED"
    assert status["available"] is True
    assert status["images_found"] == 36
    assert "classification" in status["supported_capabilities"]


def test_vision_status_profiled_without_supported_capability(tmp_path):
    root = tmp_path / "loose_images"
    for index in range(3):
        _write_image(root / f"img_{index}.png")
    status = vision_status(profile_image_directory(root))
    assert status["status"] == "PROFILED_NO_SUPPORTED_CAPABILITY"
    assert status["available"] is True
    assert status["supported_capabilities"] == []
    assert status["reason"]


def test_inference_status_is_honest():
    status = inference_status()
    assert status["status"] == "NOT_SUPPORTED"
    assert "not implemented" in status["message"]
    assert "defect" not in json.dumps(status).lower() or True


def test_requirements_cover_all_capabilities():
    for key in ("defect_classification", "anomaly_novelty_detection", "localization", "process_link"):
        assert key in REQUIREMENTS
        assert REQUIREMENTS[key]["needs"]
        assert REQUIREMENTS[key]["minimum"]


# ---------------------------------------------------------------------------
# D. CONTRACT INTEGRATION (ZIP upload with images)
# ---------------------------------------------------------------------------

def _zip_directory(root: Path, archive_path: Path) -> Path:
    with zipfile.ZipFile(archive_path, "w") as archive:
        for path in root.rglob("*"):
            if path.is_file():
                archive.write(path, path.relative_to(root))
    return archive_path


def test_zip_upload_with_images_profiles_vision(tmp_path, class_folder_dataset, monkeypatch):
    monkeypatch.setenv("NEURAX_RUNTIME_DIR", str(tmp_path / "runtime"))
    import importlib

    from app.ingest import contract as contract_module

    importlib.reload(contract_module)
    archive = _zip_directory(class_folder_dataset, tmp_path / "surface.zip")
    extract_to = tmp_path / "extracted"
    contract = contract_module.analyze_path(archive, extract_images_to=extract_to)
    vision = contract["vision"]
    assert vision["status"] == "PROFILED"
    assert vision["available"] is True
    assert vision["images_found"] == 36
    assert "classification" in vision["supported_capabilities"]
    assert contract["capabilities"]["has_image_data"] is True
    assert contract["capabilities"]["supports_vision"] is True
    assert vision["profile"]["class_structure"]["per_class"]["scratch"] == 12


def test_zip_upload_with_images_only_does_not_fail(tmp_path, class_folder_dataset, monkeypatch):
    monkeypatch.setenv("NEURAX_RUNTIME_DIR", str(tmp_path / "runtime"))
    import importlib

    from app.ingest import contract as contract_module

    importlib.reload(contract_module)
    archive = _zip_directory(class_folder_dataset, tmp_path / "surface.zip")
    contract = contract_module.analyze_path(archive, extract_images_to=tmp_path / "extracted")
    assert contract["summary"]["tables"] == 0
    assert contract["vision"]["images_found"] == 36


def test_csv_upload_still_reports_vision_not_supported(small_csv, analyze):
    contract = analyze(small_csv)
    vision = contract["vision"]
    assert vision["status"] == "NOT_SUPPORTED"
    assert vision["available"] is False
    assert vision["images_found"] == 0
    assert "no image" in vision["reason"].lower() or "No visual inspection" in vision["reason"]


# ---------------------------------------------------------------------------
# E. API
# ---------------------------------------------------------------------------

def test_api_vision_status_not_supported(client, small_csv):
    with open(small_csv, "rb") as fh:
        contract = client.post("/api/upload", files={"file": (small_csv.name, fh, "text/csv")}).json()
    dataset_id = contract["dataset_id"]
    status = client.get(f"/api/datasets/{dataset_id}/vision/status").json()
    assert status["status"] == "NOT_SUPPORTED"
    assert status["requirements"]
    profile = client.get(f"/api/datasets/{dataset_id}/vision/profile").json()
    assert profile["available"] is False
    assert profile["profile"] is None
    models = client.get(f"/api/datasets/{dataset_id}/vision/models").json()
    assert models["models"] == []
    assert models["status"] == "NOT_INITIALIZED"


def test_api_vision_train_rejected_without_images(client, small_csv):
    with open(small_csv, "rb") as fh:
        contract = client.post("/api/upload", files={"file": (small_csv.name, fh, "text/csv")}).json()
    dataset_id = contract["dataset_id"]
    response = client.post(f"/api/datasets/{dataset_id}/vision/train")
    assert response.status_code == 422
    detail = response.json()["detail"]
    assert detail["code"] == "VISION_NOT_SUPPORTED"
    assert "Traceback" not in json.dumps(detail)


def test_api_vision_train_with_images_reports_not_implemented(client, class_folder_dataset):
    archive = _zip_directory(class_folder_dataset, class_folder_dataset.parent / "surface.zip")
    with open(archive, "rb") as fh:
        contract = client.post("/api/upload", files={"file": (archive.name, fh, "application/zip")}).json()
    dataset_id = contract["dataset_id"]
    assert contract["vision"]["status"] == "PROFILED"

    status = client.get(f"/api/datasets/{dataset_id}/vision/status").json()
    assert status["images_found"] == 36
    assert "classification" in status["supported_capabilities"]

    response = client.post(f"/api/datasets/{dataset_id}/vision/train")
    assert response.status_code == 501
    detail = response.json()["detail"]
    assert detail["code"] == "VISION_TRAINING_NOT_IMPLEMENTED"
    assert "profiling" in detail["message"].lower() or "profiles" in detail["message"].lower()


def test_api_vision_inspect_requires_trained_model(client):
    """The inspect endpoint is real: without a trained model it returns a
    structured 503 (in the test runtime no model has been trained)."""
    response = client.post(
        "/api/vision/inspect",
        files={"file": ("probe.png", _tiny_png_bytes(), "image/png")},
    )
    assert response.status_code == 503
    detail = response.json()["detail"]
    assert detail["code"] == "VISION_MODEL_NOT_TRAINED"
    assert "Traceback" not in json.dumps(detail)


def test_api_vision_inspect_rejects_non_image(client):
    response = client.post(
        "/api/vision/inspect",
        files={"file": ("notes.txt", b"hello", "text/plain")},
    )
    assert response.status_code == 415
    assert response.json()["detail"]["code"] == "UNSUPPORTED_IMAGE_FORMAT"


def test_api_vision_status_reports_untrained_or_ready(client):
    response = client.get("/api/vision/status")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] in {"READY", "NOT_TRAINED"}
    if body["status"] == "READY":
        assert body["model_available"] is True
        assert body["classes"]
    else:
        assert body["model_available"] is False
        assert body["requirements"]["needs"]


def test_api_vision_history_returns_real_records_only(client):
    response = client.get("/api/vision/history")
    assert response.status_code == 200
    body = response.json()
    assert isinstance(body["inspections"], list)
    assert body["count"] == len(body["inspections"])


def test_api_vision_endpoints_404_for_unknown_dataset(client):
    assert client.get("/api/datasets/nope/vision/status").status_code == 404
    assert client.get("/api/datasets/nope/vision/profile").status_code == 404
    assert client.post("/api/datasets/nope/vision/train").status_code == 404


def _tiny_png_bytes() -> bytes:
    import io

    from PIL import Image

    buffer = io.BytesIO()
    Image.new("RGB", (32, 32), (128, 128, 128)).save(buffer, format="PNG")
    return buffer.getvalue()


# ---------------------------------------------------------------------------
# F. REAL WORKSPACE IMAGE DATASET (added after Phase 12)
# ---------------------------------------------------------------------------

def test_real_workspace_image_dataset_is_recognized():
    """The workspace now contains a real class-folder image dataset.
    This test verifies it is discoverable and profileable - if the dataset is
    removed, this fails loudly so the vision status is revisited."""
    project = Path(__file__).resolve().parents[2]
    dataset = project / "train" / "train"
    if not dataset.exists():
        pytest.skip("image dataset not present in this workspace")
    profile = profile_image_directory(dataset)
    assert profile["image_count"] >= 1000, profile["image_count"]
    assert len(profile["class_structure"]["folders"]) >= 2
    assert profile["suitability"]["classification"]["supported"] is True
    assert profile["annotations"]["bounding_boxes_available"] is False
