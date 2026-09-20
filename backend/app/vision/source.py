"""Inspection sources.

The production workflow NEVER depends on a hardcoded dataset path. Users select
images (single), image sets (multi) or a folder from ANY accessible location;
the browser uploads the files and NEURAX ingests them into a session source
under generated IDs. The stream runs over the ACTIVE source only.

Source types:
  SINGLE_IMAGE    one user-selected image
  IMAGE_SET       multiple user-selected images
  FOLDER_DATASET  a user-selected folder (class structure from relative paths)
  BUILT_IN_DEMO   optional bundled sample dataset (config-driven, demo only)
"""

from __future__ import annotations

import json
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from .batch import BatchError, create_batch, get_batch, inspect_batch, save_batch_raw

SOURCES_DIRNAME = "sources"
RAW_DIRNAME = "raw"
DEMO_SOURCE_LIMIT = 3000

SOURCE_TYPES = {"SINGLE_IMAGE", "IMAGE_SET", "FOLDER_DATASET", "BUILT_IN_DEMO"}

TYPE_LABELS = {
    "SINGLE_IMAGE": "USER IMAGE",
    "IMAGE_SET": "USER IMAGE SET",
    "FOLDER_DATASET": "USER DATASET",
    "BUILT_IN_DEMO": "BUILT-IN DEMO",
}


class SourceError(Exception):
    def __init__(self, code: str, message: str, detail: str | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.detail = detail

    def to_dict(self) -> dict:
        return {"error": True, "code": self.code, "message": self.message, "detail": self.detail}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sources_dir(base: Path | None = None) -> Path:
    from app.core.settings import RUNTIME_DIR

    directory = Path(base) if base else (RUNTIME_DIR / SOURCES_DIRNAME)
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def _save(record: dict, base: Path | None = None) -> None:
    path = _sources_dir(base) / f"{record['source_id']}.json"
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(record, handle, indent=2, default=str)


def _load(source_id: str, base: Path | None = None) -> dict | None:
    path = _sources_dir(base) / f"{source_id}.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return None


def safe_display_name(name: str | None, source_type: str) -> str:
    """A display-safe name - never a full filesystem path."""
    if not name:
        return TYPE_LABELS.get(source_type, "User data")
    # last path component only, sanitized
    clean = str(name).replace("\\", "/").rstrip("/").split("/")[-1]
    clean = clean[:48]
    return clean or TYPE_LABELS.get(source_type, "User data")


def create_source(
    uploaded: list[tuple[str, bytes]],
    source_type: str,
    *,
    display_name: str | None = None,
    sources_base: Path | None = None,
) -> dict:
    """Ingest user-selected files into a session source (generated ID)."""
    if source_type not in SOURCE_TYPES:
        raise SourceError("INVALID_SOURCE_TYPE", f"Unknown source type '{source_type}'.", None)
    if not uploaded:
        raise SourceError("SOURCE_NO_FILES", "No files were provided.", None)
    if source_type == "SINGLE_IMAGE" and len(uploaded) != 1:
        raise SourceError("SOURCE_SINGLE_ONLY", "A single-image source accepts exactly one file.", None)

    source_id = f"src_{uuid.uuid4().hex[:10]}"
    base = _sources_dir(sources_base)
    record = create_batch(uploaded, None, batches_base=base)
    # unify identity: raw files and the record live under the source id
    orphan_batch_id = record["batch_id"]
    record["batch_id"] = source_id
    record["source_id"] = source_id
    save_batch_raw(source_id, uploaded, None, batches_base=base)
    orphan_path = base / f"{orphan_batch_id}.json"
    if orphan_path.exists():
        orphan_path.unlink()
    record["source_type"] = source_type
    record["type_label"] = TYPE_LABELS[source_type]
    record["display_name"] = safe_display_name(display_name, source_type)
    record["created_at"] = _now()
    record["stream"] = {"cursor": 0, "processed": 0, "running": False, "history": []}
    _save(record, sources_base)
    return record


def create_demo_source(*, demo_dir: Path, sources_base: Path | None = None, limit: int = DEMO_SOURCE_LIMIT) -> dict:
    """Build a BUILT_IN_DEMO source from the config-driven demo dataset.

    The demo dataset path lives in configuration only and is never required by
    the normal workflow.
    """
    from .training import discover_class_dataset

    demo_dir = Path(demo_dir)
    try:
        classes = discover_class_dataset(demo_dir)
    except Exception as exc:  # noqa: BLE001
        raise SourceError("DEMO_DATASET_UNAVAILABLE", "The bundled demo dataset is not available.", str(exc)) from exc
    if not classes:
        raise SourceError("DEMO_DATASET_UNAVAILABLE", "The bundled demo dataset contains no images.", None)

    uploaded: list[tuple[str, bytes]] = []
    total = 0
    for class_name in sorted(classes.keys()):
        paths = sorted(classes[class_name])
        take = min(len(paths), max(1, limit // max(1, len(classes))))
        for path in paths[:take]:
            uploaded.append((f"{class_name}/{path.name}", path.read_bytes()))
        total += take
    if not uploaded:
        raise SourceError("DEMO_DATASET_UNAVAILABLE", "No images could be read from the demo dataset.", None)

    record = create_source(uploaded, "BUILT_IN_DEMO", display_name="Bundled demo dataset", sources_base=sources_base)
    record["demo_note"] = f"BUILT-IN DEMO - {total} images from the configured demo dataset (configuration-driven, not required by normal use)."
    _save(record, sources_base)
    return record


# ---------------------------------------------------------------------------
# Curated bundled demo sources (for presentations)
# ---------------------------------------------------------------------------

DEMO_SOURCE_LABELS = {
    "surface_scratch": "Surface defects — scratch + normal",
    "hole_normal": "Hole defects — hole + normal",
    "mixed_review": "Mixed defects + human-review set",
}


def list_bundled_sources(demo_sources_dir: Path) -> list[dict]:
    """Discover the curated demo datasets configured under DEMO_SOURCES_DIR."""
    demo_sources_dir = Path(demo_sources_dir)
    if not demo_sources_dir.exists():
        return []
    entries = []
    for folder in sorted(demo_sources_dir.iterdir()):
        if not folder.is_dir():
            continue
        files = sorted(p for p in folder.rglob("*") if p.is_file() and p.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff"})
        if not files:
            continue
        class_counts: dict[str, int] = {}
        for path in files:
            parent = path.parent
            if parent != folder:
                class_counts[parent.name] = class_counts.get(parent.name, 0) + 1
        top_level = sum(1 for path in files if path.parent == folder)
        entries.append(
            {
                "name": folder.name,
                "label": DEMO_SOURCE_LABELS.get(folder.name, folder.name.replace("_", " ")),
                "image_count": len(files),
                "classes": sorted(class_counts.keys()),
                "class_counts": class_counts,
                "review_images": top_level,
                "review_note": f"{top_level} top-level image(s) with no class label — unseen-condition samples that trigger human review"
                if top_level
                else None,
            }
        )
    return entries


def create_bundled_source(name: str, *, demo_sources_dir: Path, sources_base: Path | None = None) -> dict:
    """Ingest a curated demo dataset by name (path-traversal safe)."""
    demo_sources_dir = Path(demo_sources_dir)
    name = str(name)
    if name in {"", ".", ".."} or "/" in name or "\\" in name or ":" in name:
        raise SourceError("INVALID_DEMO_SOURCE", f"Invalid demo source name '{name}'.", None)
    folder = demo_sources_dir / name
    if not folder.is_dir():
        raise SourceError("DEMO_SOURCE_NOT_FOUND", f"Bundled demo source '{name}' is not available.", None)
    uploaded: list[tuple[str, bytes]] = []
    for path in sorted(folder.rglob("*")):
        if path.is_file() and path.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff"}:
            relative = str(path.relative_to(folder)).replace("\\", "/")
            uploaded.append((relative, path.read_bytes()))
    if not uploaded:
        raise SourceError("DEMO_SOURCE_EMPTY", f"Bundled demo source '{name}' contains no images.", None)
    record = create_source(uploaded, "BUILT_IN_DEMO", display_name=DEMO_SOURCE_LABELS.get(name, name), sources_base=sources_base)
    record["demo_source"] = name
    record["demo_note"] = "BUILT-IN DEMO - curated presentation dataset from the configured demo sources (config-driven, not required by normal use)."
    _save(record, sources_base)
    return record


def get_source(source_id: str, sources_base: Path | None = None) -> dict | None:
    return _load(source_id, sources_base)


def list_sources(limit: int = 20, sources_base: Path | None = None) -> list[dict]:
    directory = _sources_dir(sources_base)
    records = []
    for path in sorted(directory.glob("src_*.json"), key=lambda entry: entry.stat().st_mtime, reverse=True):
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            continue
        records.append(
            {
                "source_id": record["source_id"],
                "source_type": record["source_type"],
                "type_label": record.get("type_label"),
                "display_name": record.get("display_name"),
                "created_at": record.get("created_at"),
                "status": record.get("status"),
                "summary": record.get("summary"),
                "progress": record.get("progress"),
                "decisions": record.get("decisions"),
                "review_queue": record.get("review_queue"),
                "stream": record.get("stream"),
            }
        )
        if len(records) >= limit:
            break
    return records


def delete_source(source_id: str, sources_base: Path | None = None) -> None:
    directory = _sources_dir(sources_base)
    record_path = directory / f"{source_id}.json"
    if record_path.exists():
        record_path.unlink()
    raw_dir = directory / RAW_DIRNAME / source_id
    if raw_dir.exists():
        import shutil

        shutil.rmtree(raw_dir, ignore_errors=True)


def raw_dir_for(source_id: str, sources_base: Path | None = None) -> Path:
    return _sources_dir(sources_base) / RAW_DIRNAME / source_id


def add_files(source_id: str, uploaded: list[tuple[str, bytes]], *, sources_base: Path | None = None) -> dict:
    """Append files to an existing source (revalidates; stream resets)."""
    record = _load(source_id, sources_base)
    if record is None:
        raise SourceError("SOURCE_NOT_FOUND", f"Source '{source_id}' does not exist.", None)
    start_index = len(record["images"])
    new_images = []
    for name, data in uploaded:
        from .batch import validate_image

        new_images.append(validate_image(name, data))
    # duplicate detection across the whole source
    seen = {image["sha256"]: image["original_name"] for image in record["images"] if image.get("sha256")}
    for image in new_images:
        if image["status"] != "valid":
            continue
        digest = image["sha256"]
        if digest in seen:
            image["status"] = "duplicate"
            image["reason"] = f"duplicate of {seen[digest]}"
        else:
            seen[digest] = image["original_name"]
    record["images"].extend(new_images)
    summary = record["summary"]
    summary["total"] = len(record["images"])
    summary["valid"] = sum(1 for image in record["images"] if image["status"] == "valid")
    summary["invalid"] = sum(1 for image in record["images"] if image["status"] == "invalid")
    summary["unsupported"] = sum(1 for image in record["images"] if image["status"] == "unsupported")
    summary["duplicates"] = sum(1 for image in record["images"] if image["status"] == "duplicate")
    class_counts: dict[str, int] = {}
    for image in record["images"]:
        folder = image.get("class_folder")
        if folder:
            class_counts[folder] = class_counts.get(folder, 0) + 1
    summary["classes"] = sorted(class_counts.keys())
    summary["class_counts"] = class_counts
    summary["labels_available"] = bool(class_counts)
    record["status"] = "validated"
    record["results"] = []
    record["decisions"] = {"PASS": 0, "DEFECT": 0, "REVIEW": 0}
    record["review_queue"] = 0
    record["quality"] = None
    record["progress"] = {"inspected": 0, "total": summary["valid"]}
    record["stream"] = {"cursor": 0, "processed": 0, "running": False, "history": []}
    raw_dir = raw_dir_for(source_id, sources_base)
    raw_dir.mkdir(parents=True, exist_ok=True)
    for index, (_, data) in enumerate(uploaded):
        (raw_dir / str(start_index + index)).write_bytes(data)
    _save(record, sources_base)
    return record


def inspect_source(source_id: str, model, *, sources_base: Path | None = None) -> dict:
    """Run the real pipeline over the source's valid images (batch-style results)."""
    base = _sources_dir(sources_base)
    record = _load(source_id, sources_base)
    if record is None:
        raise SourceError("SOURCE_NOT_FOUND", f"Source '{source_id}' does not exist.", None)
    from .batch import mark_inspecting

    mark_inspecting(source_id, batches_base=base)
    return inspect_batch(source_id, model, batches_base=base)


def mark_source_inspecting(source_id: str, sources_base: Path | None = None) -> dict:
    """Flip a validated source to 'inspecting' synchronously (pollable progress)."""
    from .batch import mark_inspecting

    return mark_inspecting(source_id, batches_base=_sources_dir(sources_base))


def source_quality(record: dict) -> dict | None:
    return record.get("quality")


# ---------------------------------------------------------------------------
# Source-backed stream
# ---------------------------------------------------------------------------

STREAM_LABEL = "SIMULATED PRODUCTION STREAM"
STREAM_NOTE = (
    "Frames come from the currently selected inspection source in deterministic order. "
    "When class folders are present: one defect frame, then two normal frames, rotating classes."
)
SPEEDS = [0.5, 1.0, 2.0, 5.0]
MAX_HISTORY = 60


def build_sequence(record: dict) -> list[dict]:
    """Deterministic frame order over the source's valid ingested images."""
    summary = record.get("summary") or {}
    class_counts = summary.get("class_counts") or {}
    class_names = summary.get("classes") or []
    valid = [image for image in record["images"] if image["status"] == "valid"]

    if class_names and len(class_names) > 1 and "normal" in class_names:
        normal = sorted(image["original_name"] for image in valid if image.get("class_folder") == "normal")
        defect_classes = [name for name in class_names if name != "normal"]
        defect_by_class = {
            name: sorted(image["original_name"] for image in valid if image.get("class_folder") == name)
            for name in defect_classes
        }
        defect_total = sum(len(paths) for paths in defect_by_class.values())
        sequence: list[dict] = []
        normal_index = 0
        defect_index = 0
        while normal_index < len(normal) or defect_index < defect_total:
            if defect_index < defect_total and defect_classes:
                name = defect_classes[defect_index % len(defect_classes)]
                paths = defect_by_class[name]
                slot = defect_index // len(defect_classes)
                if slot < len(paths):
                    sequence.append({"class_folder": name, "original_name": paths[slot]})
                defect_index += 1
            for _ in range(2):
                if normal_index < len(normal):
                    sequence.append({"class_folder": "normal", "original_name": normal[normal_index]})
                    normal_index += 1
        return sequence

    # no class structure: plain deterministic order (sorted by name)
    ordered = sorted(valid, key=lambda image: image["original_name"].lower())
    return [{"class_folder": image.get("class_folder"), "original_name": image["original_name"]} for image in ordered]


class SourceStream:
    """Stream state over the ACTIVE inspection source. No filesystem paths
    are used for identity - frames are the ingested raw files by index."""

    def __init__(self, sources_base: Path | None = None):
        self.sources_base = Path(sources_base) if sources_base else _sources_dir()
        self._lock = threading.Lock()
        self.active_source_id: str | None = None
        self.sequence: list[dict] = []
        self.cursor = 0
        self.running = False
        self.speed = 1.0
        self.processed = 0
        self.session_started_at: str | None = None
        self.history: list[dict] = []

    # -- source management -------------------------------------------------

    def set_source(self, source_id: str) -> dict:
        record = _load(source_id, self.sources_base)
        if record is None:
            raise SourceError("SOURCE_NOT_FOUND", f"Source '{source_id}' does not exist.", None)
        with self._lock:
            self.active_source_id = source_id
            self.sequence = build_sequence(record)
            self.cursor = 0
            self.processed = 0
            self.history = []
            self.running = False
            self.session_started_at = None
            record["stream"] = {"cursor": 0, "processed": 0, "running": False, "history": []}
            _save(record, self.sources_base)
            return self._status_locked()

    def clear_source(self) -> dict:
        with self._lock:
            self.active_source_id = None
            self.sequence = []
            self.cursor = 0
            self.processed = 0
            self.history = []
            self.running = False
            return self.status()

    def active_source(self) -> dict | None:
        if not self.active_source_id:
            return None
        return _load(self.active_source_id, self.sources_base)

    def _require_source(self) -> dict:
        record = self.active_source()
        if record is None:
            raise SourceError(
                "NO_INSPECTION_SOURCE",
                "No inspection source selected.",
                "Add an image, image set, or dataset to begin (ADD INSPECTION DATA).",
            )
        if record["summary"]["valid"] == 0:
            raise SourceError("SOURCE_NO_VALID_IMAGES", "The selected source contains no valid images.", None)
        return record

    # -- controls -----------------------------------------------------------

    def start(self) -> dict:
        with self._lock:
            record = self._require_source()
            if self.cursor >= len(self.sequence):
                self.cursor = 0
                self.processed = 0
                self.history = []
            self.running = True
            if self.session_started_at is None:
                self.session_started_at = _now()
            return self._status_locked()

    def pause(self) -> dict:
        with self._lock:
            self.running = False
            return self._status_locked()

    def resume(self) -> dict:
        return self.start()

    def reset(self) -> dict:
        with self._lock:
            self.cursor = 0
            self.processed = 0
            self.history = []
            self.running = False
            self.session_started_at = None
            return self._status_locked()

    def set_speed(self, speed: float) -> dict:
        with self._lock:
            try:
                value = float(speed)
            except (TypeError, ValueError):
                value = 1.0
            self.speed = value if value in SPEEDS else min(SPEEDS, key=lambda candidate: abs(candidate - value))
            return self._status_locked()

    # -- frame processing ---------------------------------------------------

    def next_frame(self, model) -> dict:
        """Process the next real frame from the ACTIVE source's ingested files."""
        from .inference import VisionModelError

        with self._lock:
            record = self._require_source()
            if not model.available:
                raise VisionModelError(
                    "VISION_MODEL_NOT_TRAINED",
                    "No vision model has been trained yet.",
                    "Train the model before starting the production stream (POST /api/vision/train).",
                )
            if self.cursor >= len(self.sequence):
                self.running = False
                return {"inspection": None, "exhausted": True, "status": self._status_locked()}
            frame = self.sequence[self.cursor]
            index = next(
                (i for i, image in enumerate(record["images"]) if image["status"] == "valid" and image["original_name"] == frame["original_name"]),
                0,
            )
            self.cursor += 1

        raw = raw_dir_for(self.active_source_id, self.sources_base) / str(index)
        if not raw.exists():
            raise SourceError("SOURCE_RAW_MISSING", "The ingested file for this frame is missing.", None)
        data = raw.read_bytes()
        inspection = model.inspect(data, frame["original_name"], extra={"source_id": self.active_source_id})

        with self._lock:
            self.processed += 1
            summary_entry = {
                "inspection_id": inspection["inspection_id"],
                "filename": inspection.get("filename"),
                "class_folder": frame.get("class_folder"),
                "decision": inspection["decision"],
                "predicted_class": inspection["prediction"]["predicted_class"],
                "confidence": inspection["confidence"]["value"],
                "novelty_status": inspection["anomaly_score"]["novelty_status"],
                "at": inspection["generated_at"],
            }
            self.history.append(summary_entry)
            self.history = self.history[-MAX_HISTORY:]
            return {"inspection": inspection, "exhausted": False, "status": self._status_locked()}

    # -- status -------------------------------------------------------------

    def _status_locked(self) -> dict:
        active = self.active_source()
        decisions: dict[str, int] = {}
        for entry in self.history:
            decisions[entry["decision"]] = decisions.get(entry["decision"], 0) + 1
        source = None
        if active:
            source = {
                "source_id": active["source_id"],
                "source_type": active["source_type"],
                "type_label": active.get("type_label"),
                "display_name": active.get("display_name"),
                "image_count": active["summary"]["valid"],
                "total": active["summary"]["total"],
                "labels_available": active["summary"]["labels_available"],
            }
        next_frame = self.sequence[self.cursor] if self.cursor < len(self.sequence) else None
        return {
            "label": STREAM_LABEL,
            "note": STREAM_NOTE,
            "station_id": "Camera 01",
            "source": source,
            "running": self.running,
            "speed": self.speed,
            "speeds": SPEEDS,
            "cursor": self.cursor,
            "frame_number": self.cursor,
            "total_frames": len(self.sequence),
            "processed": self.processed,
            "remaining": max(0, len(self.sequence) - self.cursor),
            "session_started_at": self.session_started_at,
            "next_frame": next_frame,
            "last_summary": self.history[-1] if self.history else None,
            "history": list(reversed(self.history[-20:])),
            "decision_counts": decisions,
        }

    def status(self) -> dict:
        with self._lock:
            return self._status_locked()