"""Model registry: persistence, loading, isolation.

Artifacts live under runtime/models/<dataset_id>/<model_id>/ and are keyed by
dataset ID, so two datasets or two targets can never overwrite each other.
"""

from __future__ import annotations

import json
import re
import threading
from pathlib import Path

import joblib

from .errors import ModelError


def sanitize_model_id(target: str, model_type: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "_", f"{target}__{model_type}").strip("_")
    return cleaned or "model"


class ModelRegistry:
    def __init__(self, models_dir: Path):
        self.models_dir = Path(models_dir)
        self.models_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def dataset_dir(self, dataset_id: str) -> Path:
        path = self.models_dir / dataset_id
        path.mkdir(parents=True, exist_ok=True)
        return path

    def save(
        self,
        dataset_id: str,
        model_id: str,
        model,
        metadata: dict,
        metrics: dict,
        importance: dict,
        anomaly_bundle: dict | None = None,
    ) -> dict:
        directory = self.dataset_dir(dataset_id) / model_id
        with self._lock:
            directory.mkdir(parents=True, exist_ok=True)
            joblib.dump(model, directory / "model.joblib")
            if anomaly_bundle:
                joblib.dump(anomaly_bundle, directory / "anomaly.joblib")
            _write_json(directory / "metadata.json", metadata)
            _write_json(directory / "metrics.json", metrics)
            _write_json(directory / "feature_importance.json", importance)
        return {
            "model_id": model_id,
            "directory": str(directory),
            "files": sorted(p.name for p in directory.iterdir() if p.is_file()),
        }

    def list_models(self, dataset_id: str) -> list[dict]:
        directory = self.dataset_dir(dataset_id)
        entries: list[dict] = []
        for model_dir in sorted(p for p in directory.iterdir() if p.is_dir()):
            metadata_file = model_dir / "metadata.json"
            if not metadata_file.exists():
                continue
            metadata = json.loads(metadata_file.read_text(encoding="utf-8"))
            entries.append(
                {
                    "model_id": model_dir.name,
                    "target": metadata.get("target"),
                    "model_type": metadata.get("model_type"),
                    "status": metadata.get("status"),
                    "trained_at": metadata.get("trained_at"),
                }
            )
        return entries

    def get_metadata(self, dataset_id: str, model_id: str) -> dict | None:
        directory = self.models_dir / dataset_id / model_id
        if not directory.exists():
            return None
        return {
            "metadata": _read_json(directory / "metadata.json"),
            "metrics": _read_json(directory / "metrics.json"),
            "feature_importance": _read_json(directory / "feature_importance.json"),
            "has_anomaly_bundle": (directory / "anomaly.joblib").exists(),
        }

    def load_model(self, dataset_id: str, model_id: str):
        path = self.models_dir / dataset_id / model_id / "model.joblib"
        if not path.exists():
            raise ModelError("MODEL_NOT_FOUND", f"Model '{model_id}' for dataset '{dataset_id}' does not exist.")
        return joblib.load(path)


def load_model(dataset_id: str, model_id: str, models_dir: Path):
    return ModelRegistry(models_dir).load_model(dataset_id, model_id)


def _write_json(path: Path, payload) -> None:
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, default=str)


def _read_json(path: Path) -> dict | None:
    if not path.exists():
        return None
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)
