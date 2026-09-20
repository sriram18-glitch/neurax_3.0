"""Batch / dataset inspection.

Users add many images (or a ZIP); NEURAX validates every file, then runs the
real inspection pipeline over the valid ones. Every image receives its own
inspection record with confidence, novelty, localization and decision — nothing
is silently dropped. When the images come from class folders, those folders are
real ground-truth labels, so the batch summary includes measured decision
quality (TP/TN/FP/FN, FAR/FRR, precision/recall/F1) against them.
"""

from __future__ import annotations

import io
import json
import threading
import time
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image

SUPPORTED_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff"}
MIN_DIMENSION = 8
MAX_IMAGE_BYTES = 30 * 1024 * 1024


class BatchError(Exception):
    def __init__(self, code: str, message: str, detail: str | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.detail = detail

    def to_dict(self) -> dict:
        return {"error": True, "code": self.code, "message": self.message, "detail": self.detail}


def _batches_dir(base: Path | None = None) -> Path:
    from app.core.settings import RUNTIME_DIR

    directory = Path(base) if base else (RUNTIME_DIR / "batches")
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _scan_zip(zip_path: Path) -> list[tuple[str, bytes]]:
    entries: list[tuple[str, bytes]] = []
    with zipfile.ZipFile(zip_path) as archive:
        for info in archive.infolist():
            if info.is_dir():
                continue
            suffix = Path(info.filename).suffix.lower()
            if suffix not in SUPPORTED_IMAGE_SUFFIXES:
                continue
            if info.file_size > MAX_IMAGE_BYTES:
                continue
            entries.append((info.filename, archive.read(info)))
    if not entries:
        raise BatchError(
            "BATCH_NO_IMAGES",
            "No supported image files found in the uploaded data.",
            "Supported formats: " + ", ".join(sorted(SUPPORTED_IMAGE_SUFFIXES)),
        )
    return entries


def validate_image(name: str, data: bytes) -> dict:
    """Validate a single image file. Returns a per-image validation record."""
    suffix = Path(name).suffix.lower()
    base = {
        "original_name": name,
        "size_bytes": len(data),
        "class_folder": None,
        "sha256": None,
        "status": "valid",
        "reason": None,
        "width": None,
        "height": None,
        "format": None,
    }
    if suffix not in SUPPORTED_IMAGE_SUFFIXES:
        return {**base, "status": "unsupported", "reason": f"unsupported format '{suffix or 'none'}'"}
    if len(data) > MAX_IMAGE_BYTES:
        return {**base, "status": "invalid", "reason": f"file exceeds {MAX_IMAGE_BYTES // (1024 * 1024)} MB"}
    import hashlib

    base["sha256"] = hashlib.sha256(data).hexdigest()
    try:
        with Image.open(io.BytesIO(data)) as handle:
            handle.load()
            width, height = handle.size
            image_format = handle.format or "unknown"
    except Exception as exc:  # noqa: BLE001 - readability is the validation result
        return {**base, "status": "invalid", "reason": f"unreadable image: {exc}"}
    if width < MIN_DIMENSION or height < MIN_DIMENSION:
        return {**base, "status": "invalid", "reason": f"image too small ({width}x{height})"}
    return {**base, "status": "valid", "width": width, "height": height, "format": image_format}


def create_batch(
    uploaded: list[tuple[str, bytes]] | None = None,
    zip_path: Path | None = None,
    *,
    batches_base: Path | None = None,
) -> dict:
    """Create a validated batch record. Every file gets a validation result."""
    entries: list[tuple[str, bytes]] = []
    if zip_path is not None:
        entries = _scan_zip(zip_path)
    for name, data in uploaded or []:
        entries.append((name, data))
    if not entries:
        raise BatchError("BATCH_NO_IMAGES", "No images were provided.", None)

    images = [validate_image(name, data) for name, data in entries]
    # duplicate detection by content hash within the batch
    seen: dict[str, str] = {}
    for image in images:
        if image["status"] != "valid":
            continue
        digest = image["sha256"]
        if digest in seen:
            image["status"] = "duplicate"
            image["reason"] = f"duplicate of {seen[digest]}"
        else:
            seen[digest] = image["original_name"]

    # class structure: valid images inside class folders carry real labels
    class_counts: dict[str, int] = {}
    for image in images:
        parts = Path(image["original_name"]).parts
        if len(parts) >= 2:
            folder = parts[-2]
            if folder:
                image["class_folder"] = folder
                class_counts[folder] = class_counts.get(folder, 0) + 1
    labels_available = bool(class_counts)
    balanced = True
    if class_counts and len(class_counts) > 1:
        counts = list(class_counts.values())
        largest = max(counts)
        smallest = min(counts)
        balanced = largest <= smallest * 4

    summary = {
        "total": len(images),
        "valid": sum(1 for image in images if image["status"] == "valid"),
        "invalid": sum(1 for image in images if image["status"] == "invalid"),
        "unsupported": sum(1 for image in images if image["status"] == "unsupported"),
        "duplicates": sum(1 for image in images if image["status"] == "duplicate"),
        "classes": sorted(class_counts.keys()),
        "class_counts": class_counts,
        "labels_available": labels_available,
        "labels_note": "class folders present; used as ground truth for decision quality"
        if labels_available
        else "no class folders found; decision quality requires labels and stays NOT AVAILABLE",
        "class_balance": "BALANCED" if (labels_available and balanced) else ("IMBALANCED" if labels_available else "NOT_APPLICABLE"),
        "localization_annotations": "NOT AVAILABLE",
        "localization_note": "the image dataset ships no bounding-box or mask annotations; localization is model-derived (CAM)",
        "process_join": "NOT AVAILABLE",
        "process_join_note": "no per-image batch/station/unit metadata; process correlation cannot be linked per unit",
    }

    batch_id = f"batch_{uuid.uuid4().hex[:12]}"
    record = {
        "batch_id": batch_id,
        "created_at": _now(),
        "status": "validated",
        "source": "zip" if zip_path is not None else "uploaded files",
        "summary": summary,
        "images": images,
        "progress": {"inspected": 0, "total": summary["valid"]},
        "decisions": {"PASS": 0, "DEFECT": 0, "REVIEW": 0},
        "review_queue": 0,
        "quality": None,
        "results": [],
        "note": "Every image receives its own inspection result; nothing is silently discarded.",
    }
    _save(record, batches_base)
    return record


def _save(record: dict, batches_base: Path | None = None) -> None:
    path = _batches_dir(batches_base) / f"{record['batch_id']}.json"
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(record, handle, indent=2, default=str)


def _load(batch_id: str, batches_base: Path | None = None) -> dict | None:
    path = _batches_dir(batches_base) / f"{batch_id}.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return None


def get_batch(batch_id: str, batches_base: Path | None = None) -> dict | None:
    return _load(batch_id, batches_base)


def list_batches(limit: int = 20, batches_base: Path | None = None) -> list[dict]:
    directory = _batches_dir(batches_base)
    records = []
    for path in sorted(directory.glob("batch_*.json"), key=lambda entry: entry.stat().st_mtime, reverse=True):
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            continue
        records.append(
            {
                "batch_id": record["batch_id"],
                "created_at": record.get("created_at"),
                "status": record.get("status"),
                "summary": record.get("summary"),
                "progress": record.get("progress"),
                "decisions": record.get("decisions"),
                "review_queue": record.get("review_queue"),
            }
        )
        if len(records) >= limit:
            break
    return records


def _decision_quality(record: dict) -> dict:
    """Measured decision quality vs class-folder ground truth (PASS = normal)."""
    tp = tn = fp = fn = 0
    for result in record.get("results", []):
        actual = "PASS" if result.get("ground_truth") == "normal" else "DEFECT"
        predicted = result.get("decision")
        if actual == "DEFECT" and predicted == "DEFECT":
            tp += 1
        elif actual == "PASS" and predicted == "PASS":
            tn += 1
        elif actual == "PASS" and predicted == "DEFECT":
            fp += 1
        elif actual == "DEFECT" and predicted == "PASS":
            fn += 1
        # REVIEW is not counted as an accept/reject error; it is an escalation
    total = tp + tn + fp + fn
    far = fn / (fn + tn) if (fn + tn) else None
    frr = fp / (fp + tp) if (fp + tp) else None
    precision = tp / (tp + fp) if (tp + fp) else None
    recall = tp / (tp + fn) if (tp + fn) else None
    f1 = 2 * precision * recall / (precision + recall) if (precision is not None and recall is not None and (precision + recall) > 0) else None
    return {
        "basis": "measured against class-folder ground truth (DEFECT = positive; normal = PASS)",
        "tp": tp,
        "tn": tn,
        "fp": fp,
        "fn": fn,
        "false_accept_rate": round(far, 4) if far is not None else None,
        "false_reject_rate": round(frr, 4) if frr is not None else None,
        "precision": round(precision, 4) if precision is not None else None,
        "recall": round(recall, 4) if recall is not None else None,
        "f1": round(f1, 4) if f1 is not None else None,
        "review_rate": round((record["review_queue"] / record["progress"]["total"]) if record["progress"]["total"] else None, 4),
        "note": "REVIEW decisions are escalations, not accept/reject errors. Ground truth comes from class folders.",
    }


def mark_inspecting(batch_id: str, batches_base: Path | None = None) -> dict:
    """Flip a validated batch to 'inspecting' synchronously (pollable progress)."""
    record = _load(batch_id, batches_base)
    if record is None:
        raise BatchError("BATCH_NOT_FOUND", f"Batch '{batch_id}' does not exist.", None)
    if record["status"] not in {"validated", "inspecting"}:
        return record
    record["status"] = "inspecting"
    record["started_at"] = _now()
    _save(record, batches_base)
    return record


def inspect_batch(batch_id: str, model, *, batches_base: Path | None = None) -> dict:
    """Run the real inspection pipeline over every valid image (background-safe).

    Updates the persisted record image-by-image so the UI can poll real progress.
    """
    from .inference import VisionModel

    record = _load(batch_id, batches_base)
    if record is None:
        raise BatchError("BATCH_NOT_FOUND", f"Batch '{batch_id}' does not exist.", None)
    if record["status"] == "complete":
        return record

    model: VisionModel = model
    if not model.available:
        raise BatchError("VISION_MODEL_NOT_TRAINED", "No vision model has been trained yet.", None)

    record["status"] = "inspecting"
    record["started_at"] = _now()
    _save(record, batches_base)

    start = time.time()
    for index, image in enumerate(record["images"]):
        if image["status"] != "valid":
            continue
        data_path = None  # bytes are not retained in the record; reload from upload cache if available
        # Images were validated from memory; re-inspect requires the bytes.
        # The upload handler stores raw files under batches/<id>/raw/<n>.
        raw = _batches_dir(batches_base) / "raw" / batch_id / str(index)
        data = raw.read_bytes() if raw.exists() else None
        if data is None:
            image["status"] = "invalid"
            image["reason"] = "raw upload not retained; re-upload the batch"
            _save(record, batches_base)
            continue
        inspection = model.inspect(data, image["original_name"])
        record["results"].append(
            {
                "index": index,
                "inspection_id": inspection["inspection_id"],
                "filename": inspection.get("filename"),
                "class_folder": image.get("class_folder"),
                "ground_truth": image.get("class_folder"),
                "decision": inspection["decision"],
                "confidence": inspection["confidence"]["value"],
                "raw_probability": inspection["confidence"].get("raw_probability"),
                "anomaly_score": inspection["anomaly_score"]["value"],
                "novelty_score": inspection["anomaly_score"]["novelty_score"],
                "novelty_status": inspection["anomaly_score"]["novelty_status"],
                "localization": bool(inspection["localization"].get("bounding_box")),
                "review_reason": inspection.get("review_reason"),
                "review_reasons": inspection.get("review_reasons", []),
            }
        )
        image["inspection_id"] = inspection["inspection_id"]
        record["decisions"][inspection["decision"]] = record["decisions"].get(inspection["decision"], 0) + 1
        record["progress"]["inspected"] = sum(1 for entry in record["images"] if entry.get("inspection_id"))
        _save(record, batches_base)

    record["progress"]["inspected"] = record["progress"]["total"]
    record["review_queue"] = record["decisions"].get("REVIEW", 0)
    record["quality"] = _decision_quality(record) if record["summary"]["labels_available"] else None
    record["status"] = "complete"
    record["completed_at"] = _now()
    record["duration_s"] = round(time.time() - start, 3)
    record["avg_confidence"] = (
        round(sum(entry["confidence"] for entry in record["results"] if entry.get("confidence") is not None) / len(record["results"]), 4)
        if record["results"]
        else None
    )
    _save(record, batches_base)
    return record


def save_batch_raw(batch_id: str, uploaded: list[tuple[str, bytes]] | None, zip_path: Path | None, *, batches_base: Path | None = None) -> dict:
    """Persist raw bytes for later inspection, indexed by the validated image order."""
    entries: list[tuple[str, bytes]] = []
    if zip_path is not None:
        entries = _scan_zip(zip_path)
    for name, data in uploaded or []:
        entries.append((name, data))
    raw_dir = _batches_dir(batches_base) / "raw" / batch_id
    raw_dir.mkdir(parents=True, exist_ok=True)
    for index, (_, data) in enumerate(entries):
        (raw_dir / str(index)).write_bytes(data)
    return {"saved": len(entries)}