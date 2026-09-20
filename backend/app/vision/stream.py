"""Simulated production inspection stream.

Deterministic round-robin over the REAL image dataset: a defect frame followed
by two normal frames, rotating through the defect classes. No randomness, no
fake camera feed - the stream is labelled SIMULATED PRODUCTION STREAM in every
response and in the UI. Each frame is processed by the real trained vision
pipeline and persisted like any other inspection.
"""

from __future__ import annotations

import threading
from datetime import datetime, timezone
from pathlib import Path

from .inference import VisionModel, VisionModelError
from .training import discover_class_dataset

STATION_ID = "Camera 01"
STREAM_LABEL = "SIMULATED PRODUCTION STREAM"
STREAM_NOTE = (
    "Frames are served from the real image dataset in a deterministic order "
    "(one defect frame, two normal frames, rotating defect classes). No randomness."
)
SPEEDS = [0.5, 1.0, 2.0, 5.0]
NORMAL_FRAMES_PER_DEFECT = 2
MAX_HISTORY = 60


class InspectionStream:
    """Single-process stream state. Frames are processed on demand so the
    frontend controls cadence; nothing is pre-generated or faked."""

    def __init__(self, dataset_root: Path):
        self.dataset_root = Path(dataset_root)
        self._lock = threading.Lock()
        self.sequence: list[tuple[str, Path]] = []
        self.class_plan: dict[str, int] = {}
        self.cursor = 0
        self.running = False
        self.speed = 1.0
        self.processed = 0
        self.session_started_at: str | None = None
        self.history: list[dict] = []
        self.last_inspection_id: str | None = None
        self.last_summary: dict | None = None
        self.dataset_available = False
        self.dataset_error: str | None = None
        self._build_sequence()

    # ------------------------------------------------------------------
    # sequence construction
    # ------------------------------------------------------------------

    def _build_sequence(self) -> None:
        try:
            classes = discover_class_dataset(self.dataset_root)
        except Exception as exc:  # noqa: BLE001 - stream must report, not crash
            self.dataset_available = False
            self.dataset_error = str(exc)
            return
        if not classes:
            self.dataset_available = False
            self.dataset_error = "No class-folder image dataset was found for the stream."
            return
        self.dataset_available = True
        self.dataset_error = None

        names = sorted(classes.keys())
        normal_name = "normal" if "normal" in classes else names[0]
        normal_paths = sorted(classes.get(normal_name, []))
        defect_names = [name for name in names if name != normal_name]
        defect_paths = {name: sorted(classes[name]) for name in defect_names}
        defect_total = sum(len(paths) for paths in defect_paths.values())

        sequence: list[tuple[str, Path]] = []
        normal_index = 0
        defect_index = 0
        while normal_index < len(normal_paths) or defect_index < defect_total:
            if defect_index < defect_total and defect_names:
                name = defect_names[defect_index % len(defect_names)]
                slot = defect_index // len(defect_names)
                paths = defect_paths[name]
                if slot < len(paths):
                    sequence.append((name, paths[slot]))
                defect_index += 1
            for _ in range(NORMAL_FRAMES_PER_DEFECT):
                if normal_index < len(normal_paths):
                    sequence.append((normal_name, normal_paths[normal_index]))
                    normal_index += 1
        self.sequence = sequence
        self.class_plan = {
            "order": "one defect frame, then two normal frames, rotating defect classes",
            "counts": {name: len(paths) for name, paths in defect_paths.items()} | {normal_name: len(normal_paths)},
            "normal_class": normal_name,
            "total_frames": len(sequence),
        }

    # ------------------------------------------------------------------
    # controls
    # ------------------------------------------------------------------

    def _require_dataset(self) -> None:
        if not self.dataset_available:
            raise VisionModelError(
                "STREAM_DATASET_UNAVAILABLE",
                "No image dataset is available for the production stream.",
                self.dataset_error,
            )

    def start(self) -> dict:
        with self._lock:
            if not self.dataset_available:
                self._build_sequence()
            self._require_dataset()
            if self.cursor >= len(self.sequence):
                self.cursor = 0
                self.processed = 0
                self.history = []
            self.running = True
            if self.session_started_at is None:
                self.session_started_at = datetime.now(timezone.utc).isoformat()
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
            self.last_inspection_id = None
            self.last_summary = None
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

    # ------------------------------------------------------------------
    # frame processing
    # ------------------------------------------------------------------

    def next_frame(self, model: VisionModel) -> dict:
        """Process the next real frame. Returns {"inspection": ..., "status": ...}
        or {"inspection": None, "exhausted": True} when the sequence is complete."""
        with self._lock:
            self._require_dataset()
            if not model.available:
                raise VisionModelError(
                    "VISION_MODEL_NOT_TRAINED",
                    "No vision model has been trained yet.",
                    "Train the model before starting the production stream (POST /api/vision/train).",
                )
            if self.cursor >= len(self.sequence):
                self.running = False
                return {"inspection": None, "exhausted": True, "status": self._status_locked()}
            class_name, path = self.sequence[self.cursor]
            self.cursor += 1

        inspection = model.inspect(path.read_bytes(), path.name)
        with self._lock:
            self.processed += 1
            self.last_inspection_id = inspection["inspection_id"]
            self.last_summary = {
                "inspection_id": inspection["inspection_id"],
                "filename": inspection.get("filename"),
                "class_folder": class_name,
                "decision": inspection["decision"],
                "predicted_class": inspection["prediction"]["predicted_class"],
                "confidence": inspection["confidence"]["value"],
                "novelty_status": inspection["anomaly_score"]["novelty_status"],
                "at": inspection["generated_at"],
            }
            self.history.append(self.last_summary)
            self.history = self.history[-MAX_HISTORY:]
            return {"inspection": inspection, "exhausted": False, "status": self._status_locked()}

    # ------------------------------------------------------------------
    # status
    # ------------------------------------------------------------------

    def _status_locked(self) -> dict:
        total = len(self.sequence)
        next_frame = None
        if self.cursor < total:
            class_name, path = self.sequence[self.cursor]
            next_frame = {"class_folder": class_name, "filename": path.name}
        decision_counts: dict[str, int] = {}
        for entry in self.history:
            decision_counts[entry["decision"]] = decision_counts.get(entry["decision"], 0) + 1
        return {
            "label": STREAM_LABEL,
            "note": STREAM_NOTE,
            "station_id": STATION_ID,
            "dataset_available": self.dataset_available,
            "dataset_error": self.dataset_error,
            "running": self.running,
            "speed": self.speed,
            "speeds": SPEEDS,
            "cursor": self.cursor,
            "frame_number": self.cursor,
            "total_frames": total,
            "processed": self.processed,
            "remaining": max(0, total - self.cursor),
            "session_started_at": self.session_started_at,
            "next_frame": next_frame,
            "class_plan": self.class_plan,
            "last_summary": self.last_summary,
            "history": list(reversed(self.history[-20:])),
            "decision_counts": decision_counts,
        }

    def status(self) -> dict:
        with self._lock:
            return self._status_locked()
