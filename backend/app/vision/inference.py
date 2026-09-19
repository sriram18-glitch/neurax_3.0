"""Single-image inspection inference.

Loads the trained artifacts and runs the real pipeline. The pipeline is
implemented as an EVENT STREAM: every stage emits the moment it completes,
including its real metrics and any intermediate artifact (preprocessed tensor,
anomaly heatmap). The frontend consumes these events to animate the inspection
live - the animation is driven by real backend events, not a replay.

Stages:
  validate -> preprocess -> feature extraction -> classification (calibrated)
  -> anomaly analysis -> localization (class-activation mapping) -> confidence
  -> PASS/DEFECT/REVIEW decision -> process link attempt

No chain-of-thought is exposed - only engineering steps and model outputs.
"""

from __future__ import annotations

import base64
import io
import json
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

import numpy as np
from PIL import Image

from .training import IMG_SIZE, softmax

INSPECTION_DIRNAME = "inspections"
HISTORY_LIMIT = 100

STAGE_LABELS = {
    "image_received": "Image received",
    "validation": "Validation",
    "preprocessing": "Preprocessing",
    "feature_extraction": "Feature extraction",
    "classification": "Classification",
    "anomaly_analysis": "Anomaly analysis",
    "localization": "Localization",
    "confidence": "Confidence",
    "decision": "Decision",
    "process_link": "Process link",
}


class VisionModelError(Exception):
    def __init__(self, code: str, message: str, detail: str | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.detail = detail

    def to_dict(self) -> dict:
        return {"error": True, "code": self.code, "message": self.message, "detail": self.detail}


class VisionModel:
    """Loaded once per process; reload() after retraining."""

    def __init__(self, artifacts_dir: Path):
        self.artifacts_dir = Path(artifacts_dir)
        self._feature_model = None
        self.classifier = None
        self.scaler = None
        self.class_names: list[str] = []
        self.normal_index = 0
        self.temperature = 1.0
        self.thresholds: dict = {}
        self.normal_mean = None
        self.normal_precision = None
        self.reference_distances = None
        self.anomaly_threshold = 1.0
        self.class_centroids = None
        self.class_distance_references = None
        self.metadata: dict = {}
        self.metrics: dict = {}
        self._load()

    @property
    def available(self) -> bool:
        return self.classifier is not None

    def warm_up(self) -> None:
        """Load the TensorFlow backbone so the first inspection is instant."""
        if self.available:
            self._ensure_feature_model()

    def _load(self) -> None:
        import joblib

        base = self.artifacts_dir
        classifier_path = base / "classifier.joblib"
        if not classifier_path.exists():
            return
        self.classifier = joblib.load(classifier_path)
        self.scaler = joblib.load(base / "scaler.joblib")
        with open(base / "class_mapping.json", "r", encoding="utf-8") as handle:
            mapping = json.load(handle)
        self.class_names = mapping["classes"]
        self.normal_index = self.class_names.index(mapping["normal_class"])
        with open(base / "calibration.json", "r", encoding="utf-8") as handle:
            self.temperature = float(json.load(handle)["temperature"])
        with open(base / "thresholds.json", "r", encoding="utf-8") as handle:
            self.thresholds = json.load(handle)
        reference = np.load(base / "normal_reference.npz", allow_pickle=True)
        self.normal_mean = reference["mean"]
        self.normal_precision = reference["precision"]
        self.reference_distances = reference["reference_distances"]
        self.anomaly_threshold = float(reference["anomaly_threshold"][0])
        self.class_centroids = reference["class_centroids"]
        self.class_distance_references = reference["class_distance_references"]
        with open(base / "metadata.json", "r", encoding="utf-8") as handle:
            self.metadata = json.load(handle)
        with open(base / "metrics.json", "r", encoding="utf-8") as handle:
            self.metrics = json.load(handle)

    def _ensure_feature_model(self):
        if self._feature_model is None:
            from .training import build_feature_model

            self._feature_model = build_feature_model()
        return self._feature_model

    def _mahalanobis(self, matrix: np.ndarray) -> np.ndarray:
        delta = matrix - self.normal_mean
        return np.sqrt(np.einsum("ij,jk,ik->i", delta, self.normal_precision, delta))

    # ------------------------------------------------------------------
    # Event-stream pipeline
    # ------------------------------------------------------------------

    def inspect_events(self, image_bytes: bytes, filename: str | None = None) -> Iterator[dict]:
        """Yield {"event": "stage", "stage": ...} as each real stage completes,
        then {"event": "result", "result": ...}. Errors yield an error event."""
        import tensorflow as tf

        if not self.available:
            yield {
                "event": "error",
                "error": VisionModelError(
                    "VISION_MODEL_NOT_TRAINED",
                    "No vision model has been trained yet.",
                    "Train the model on the class-folder image dataset first (POST /api/vision/train).",
                ).to_dict(),
            }
            return

        inspection_id = uuid.uuid4().hex[:12]
        trace: list[dict] = []

        def stage(stage_id: str, summary: str, metrics: dict | None = None) -> dict:
            return {
                "id": stage_id,
                "label": STAGE_LABELS.get(stage_id, stage_id),
                "started_at": datetime.now(timezone.utc).isoformat(),
                "started": time.time(),
                "summary": summary,
                "metrics": metrics or {},
            }

        def finish(entry: dict, status: str = "complete", summary: str | None = None, metrics: dict | None = None) -> dict:
            entry["status"] = status
            entry["duration_ms"] = round((time.time() - entry.pop("started")) * 1000, 1)
            if summary:
                entry["summary"] = summary
            if metrics:
                entry["metrics"].update(metrics)
            snapshot = {key: value for key, value in entry.items()}
            trace.append(snapshot)
            return snapshot

        # 1) image received
        received = finish(stage("image_received", "Image received by the inspection endpoint.", {"bytes": len(image_bytes)}))
        yield {"event": "stage", "stage": received}

        # 2) validation
        validation = stage("validation", "Checking that the file is a readable image.")
        try:
            with Image.open(io.BytesIO(image_bytes)) as handle:
                handle.load()
                width, height = handle.size
                mode = handle.mode
                image_format = handle.format or "unknown"
        except Exception as exc:  # noqa: BLE001
            failed = finish(validation, "failed", f"Unreadable image: {exc}")
            yield {"event": "stage", "stage": failed}
            yield {
                "event": "error",
                "error": VisionModelError("INVALID_IMAGE", "The uploaded file is not a readable image.", str(exc)).to_dict(),
            }
            return
        validated = finish(
            validation,
            "complete",
            f"Valid {image_format} image {width}x{height} ({mode}).",
            {"width": width, "height": height, "mode": mode, "format": image_format},
        )
        yield {"event": "stage", "stage": validated}

        # 3) preprocessing
        preprocessing = stage("preprocessing", "Resizing and normalizing for the backbone.")
        tensor = load_image_tensor_from_bytes(image_bytes)
        preprocessed_png = encode_preprocessed_png(tensor)
        normalized = tf.keras.applications.mobilenet_v2.preprocess_input(tensor[np.newaxis, ...].copy())
        preprocessed = finish(
            preprocessing,
            metrics={
                "resize": f"{IMG_SIZE}x{IMG_SIZE}",
                "color": "grayscale/RGB converted to RGB",
                "normalization": "mobilenet_v2.preprocess_input",
                "preprocessed_png_base64": preprocessed_png,
                "note": "The preprocessed image is the real 224x224 tensor input the backbone consumed.",
            },
        )
        yield {"event": "stage", "stage": preprocessed}

        # 4) feature extraction
        feature_stage = stage("feature_extraction", "Running the frozen pretrained visual backbone.")
        model = self._ensure_feature_model()
        pooled, conv_features = model(normalized, training=False)
        pooled = np.asarray(pooled)[0]
        conv_map = np.asarray(conv_features)[0]
        features = finish(
            feature_stage,
            metrics={
                "backbone": self.metadata.get("backbone", {}).get("name", "mobilenet_v2"),
                "embedding_dim": int(pooled.shape[0]),
                "conv_feature_shape": list(conv_map.shape),
            },
        )
        yield {"event": "stage", "stage": features}

        # 5) classification
        classification = stage("classification", "Scoring calibrated class probabilities.")
        standardized = self.scaler.transform(pooled[np.newaxis, :])
        logits = self.classifier.decision_function(standardized)[0]
        probabilities = softmax(logits[np.newaxis, :] / self.temperature)[0]
        predicted_index = int(probabilities.argmax())
        predicted_class = self.class_names[predicted_index]
        confidence = float(probabilities[predicted_index])
        classified = finish(
            classification,
            metrics={
                "predicted_class": predicted_class,
                "calibrated_probability": round(confidence, 4),
                "class_probabilities": {name: round(float(probabilities[i]), 4) for i, name in enumerate(self.class_names)},
                "temperature": self.temperature,
            },
        )
        yield {"event": "stage", "stage": classified}

        # 6) anomaly analysis
        anomaly_stage = stage("anomaly_analysis", "Comparing the embedding against the normal reference and the assigned class.")
        distance = float(self._mahalanobis(standardized)[0])
        anomaly_score = float((self.reference_distances < distance).mean())
        centroid = self.class_centroids[predicted_index]
        class_distance = float(np.linalg.norm(standardized[0] - centroid))
        class_reference = self.class_distance_references[predicted_index]
        novelty_score = float((class_reference < class_distance).mean())
        novelty_status = "HIGH" if novelty_score > self.thresholds.get("anomaly_review_percentile", 0.99) else "NORMAL"
        anomaly = finish(
            anomaly_stage,
            metrics={
                "mahalanobis_distance": round(distance, 4),
                "anomaly_score": round(anomaly_score, 4),
                "anomaly_reference": "normal-class training embeddings",
                "class_distance": round(class_distance, 4),
                "novelty_score": round(novelty_score, 4),
                "novelty_reference": f"distance distribution of the '{predicted_class}' training class",
                "note": "Anomaly score is a percentile against the normal reference - not a probability. Novelty compares against the assigned known class.",
                "novelty_status": novelty_status,
            },
        )
        yield {"event": "stage", "stage": anomaly}

        # 7) localization (class-activation mapping, model-derived)
        localization = stage("localization", "Computing model-derived class activation map.")
        weights = self._effective_weights(predicted_index)
        cam = np.tensordot(conv_map, weights, axes=([2], [0]))
        cam = np.maximum(cam, 0)
        if cam.max() > 0:
            cam = cam / cam.max()
        heatmap_png, box = render_heatmap(cam, width, height)
        localized = finish(
            localization,
            metrics={
                "method": "class-activation mapping",
                "type": "MODEL-DERIVED LOCALIZATION",
                "ground_truth_annotations": False,
                "note": "No ground-truth defect annotations exist in the dataset; this is model-derived attention.",
                "bounding_box": box,
                "heatmap_png_base64": heatmap_png,
            },
        )
        yield {"event": "stage", "stage": localized}

        # 8) confidence
        confidence_stage = stage("confidence", "Summarizing confidence from calibrated probability and anomaly.")
        if confidence >= 0.9:
            confidence_level = "HIGH"
        elif confidence >= 0.7:
            confidence_level = "MODERATE"
        else:
            confidence_level = "LOW"
        confident = finish(
            confidence_stage,
            metrics={
                "calibrated_probability": round(confidence, 4),
                "confidence_level": confidence_level,
                "calibration": "temperature scaling on validation logits",
            },
        )
        yield {"event": "stage", "stage": confident}

        # 9) decision
        decision_stage = stage("decision", "Applying the PASS / DEFECT / REVIEW thresholds.")
        pass_confidence = float(self.thresholds.get("pass_confidence", 0.8))
        defect_confidence = float(self.thresholds.get("defect_confidence", 0.7))
        anomaly_gate = float(self.thresholds.get("anomaly_review_percentile", 0.99))
        review_reason = None
        if predicted_class == self.class_names[self.normal_index]:
            if confidence >= pass_confidence and anomaly_score <= anomaly_gate:
                decision = "PASS"
            else:
                decision = "REVIEW"
                review_reason = (
                    "Anomalous condition detected in a nominally normal sample."
                    if anomaly_score > anomaly_gate
                    else f"Normal-class confidence {confidence:.2f} below pass threshold {pass_confidence:.2f}."
                )
        else:
            if confidence >= defect_confidence and novelty_score <= anomaly_gate:
                decision = "DEFECT"
            else:
                decision = "REVIEW"
                if novelty_score > anomaly_gate:
                    review_reason = (
                        "Unfamiliar condition: the sample does not resemble the known class it was assigned to; "
                        "not forced into a known defect class."
                    )
                else:
                    review_reason = (
                        f"Defect-class confidence {confidence:.2f} below defect threshold {defect_confidence:.2f}."
                    )
        decided = finish(
            decision_stage,
            metrics={
                "decision": decision,
                "review_reason": review_reason,
                "thresholds": {
                    "pass_confidence": pass_confidence,
                    "defect_confidence": defect_confidence,
                    "anomaly_review_percentile": anomaly_gate,
                },
            },
        )
        yield {"event": "stage", "stage": decided}

        # 10) process link
        link_stage = stage("process_link", "Attempting to link the image to process metadata.")
        process_link = attempt_process_link()
        linked = finish(
            link_stage,
            "complete" if process_link["status"] == "LINKED" else "not_supported",
            process_link["reason"],
            {"status": process_link["status"]},
        )
        yield {"event": "stage", "stage": linked}

        result = {
            "inspection_id": inspection_id,
            "filename": filename,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "image_metadata": {
                "width": width,
                "height": height,
                "mode": mode,
                "format": image_format,
                "bytes": len(image_bytes),
            },
            "preprocessing": {
                "resize": f"{IMG_SIZE}x{IMG_SIZE}",
                "normalization": "mobilenet_v2.preprocess_input",
                "preprocessed_png_base64": preprocessed_png,
                "note": "The preprocessed image is the real 224x224 tensor input the backbone consumed.",
            },
            "prediction": {
                "predicted_class": predicted_class,
                "is_normal": predicted_class == self.class_names[self.normal_index],
            },
            "class_probabilities": {name: round(float(probabilities[i]), 4) for i, name in enumerate(self.class_names)},
            "confidence": {
                "value": round(confidence, 4),
                "level": confidence_level,
                "method": "temperature_scaled softmax on validation-calibrated logits",
                "limitations": "Confidence reflects model uncertainty, not physical certainty.",
            },
            "anomaly_score": {
                "value": round(anomaly_score, 4),
                "novelty_score": round(novelty_score, 4),
                "novelty_status": novelty_status,
                "method": "Mahalanobis distance percentile against normal reference; novelty vs assigned class centroid",
                "note": "Anomaly score is not a probability.",
            },
            "localization": {
                "type": "MODEL-DERIVED LOCALIZATION",
                "method": "class-activation mapping",
                "ground_truth": False,
                "bounding_box": box,
                "heatmap_png_base64": heatmap_png,
                "note": "Model attention map - not a ground-truth defect boundary.",
            },
            "decision": decision,
            "review_reason": review_reason,
            "evidence": [
                {
                    "statement": f"Calibrated probability for '{predicted_class}' is {confidence:.2%}.",
                    "source": "classification",
                    "epistemic_status": "MODEL_OUTPUT",
                },
                {
                    "statement": f"Anomaly score {anomaly_score:.3f} (novelty: {novelty_status}).",
                    "source": "anomaly_analysis",
                    "epistemic_status": "MODEL_OUTPUT",
                },
                {
                    "statement": "Localization is model-derived (CAM); the dataset has no ground-truth annotations.",
                    "source": "localization",
                    "epistemic_status": "MODEL_DERIVED",
                },
            ],
            "process_link": process_link,
            "model": {
                "backbone": self.metadata.get("backbone", {}).get("name"),
                "trained_at": self.metadata.get("trained_at"),
                "classes": self.class_names,
            },
            "limitations": [
                "Decision support only - not an automated accept/reject control.",
                "Localization is model-derived (no ground-truth annotations in the dataset).",
                "Confidence reflects model uncertainty, not physical certainty.",
                "Anomaly score is a percentile against a normal reference, not a probability.",
            ],
            "trace": trace,
        }
        persist_inspection(self.artifacts_dir, result, image_bytes)
        yield {"event": "result", "result": result}

    def inspect(self, image_bytes: bytes, filename: str | None = None) -> dict:
        """Consume the event stream and return the final result (non-streaming use)."""
        result = None
        for event in self.inspect_events(image_bytes, filename):
            if event["event"] == "result":
                result = event["result"]
            elif event["event"] == "error":
                error = event["error"]
                raise VisionModelError(error["code"], error["message"], error.get("detail"))
        if result is None:
            raise VisionModelError("INSPECTION_FAILED", "The inspection produced no result.")
        return result

    def _effective_weights(self, class_index: int) -> np.ndarray:
        """Linear weights from embedding space mapped back through the scaler."""
        coefficients = self.classifier.coef_
        if coefficients.ndim == 1:
            weights = coefficients
        else:
            weights = coefficients[class_index]
        return weights / self.scaler.scale_


def load_image_tensor_from_bytes(image_bytes: bytes) -> np.ndarray:
    with Image.open(io.BytesIO(image_bytes)) as handle:
        image = handle.convert("RGB").resize((IMG_SIZE, IMG_SIZE), Image.BILINEAR)
    return np.asarray(image, dtype=np.float32)


def encode_preprocessed_png(tensor: np.ndarray) -> str:
    """Encode the exact 224x224 RGB tensor the backbone consumed."""
    image = Image.fromarray(np.clip(tensor, 0, 255).astype(np.uint8), mode="RGB")
    buffer = io.BytesIO()
    image.save(buffer, format="PNG", optimize=True)
    return base64.b64encode(buffer.getvalue()).decode("ascii")


def render_heatmap(cam: np.ndarray, original_width: int, original_height: int) -> tuple[str, dict]:
    """Turn a small CAM into a base64 PNG heatmap and a bounding box."""
    cam_image = Image.fromarray((cam * 255).astype(np.uint8), mode="L")
    upscaled = cam_image.resize((256, 256), Image.BILINEAR)
    colored = np.zeros((256, 256, 4), dtype=np.uint8)
    values = np.asarray(upscaled, dtype=np.float32) / 255.0
    colored[..., 0] = np.clip(255 * values, 0, 255)
    colored[..., 1] = np.clip(160 * values**2, 0, 255)
    colored[..., 3] = np.clip(210 * values, 0, 255)
    buffer = io.BytesIO()
    Image.fromarray(colored, mode="RGBA").save(buffer, format="PNG")
    heatmap_b64 = base64.b64encode(buffer.getvalue()).decode("ascii")

    threshold = cam >= max(0.4, float(cam.max()) * 0.5)
    if threshold.any():
        rows = np.where(threshold.any(axis=1))[0]
        cols = np.where(threshold.any(axis=0))[0]
        grid_height, grid_width = cam.shape
        box = {
            "x": round(float(cols[0]) / grid_width * original_width, 1),
            "y": round(float(rows[0]) / grid_height * original_height, 1),
            "width": round(float(cols[-1] - cols[0] + 1) / grid_width * original_width, 1),
            "height": round(float(rows[-1] - rows[0] + 1) / grid_height * original_height, 1),
            "coordinates": "original image pixels",
            "type": "MODEL-DERIVED",
        }
    else:
        box = None
    return heatmap_b64, box


def attempt_process_link() -> dict:
    """The image dataset carries no batch/station/unit metadata."""
    return {
        "status": "NOT_AVAILABLE",
        "reason": "PROCESS LINK NOT AVAILABLE: the image dataset contains no per-image batch, station, unit or timestamp metadata.",
        "available_metadata": [],
    }


def persist_inspection(artifacts_dir: Path, result: dict, image_bytes: bytes | None = None) -> None:
    directory = Path(artifacts_dir) / INSPECTION_DIRNAME
    directory.mkdir(parents=True, exist_ok=True)
    with open(directory / f"{result['inspection_id']}.json", "w", encoding="utf-8") as handle:
        json.dump(result, handle, indent=2)
    if image_bytes:
        (directory / f"{result['inspection_id']}.img").write_bytes(image_bytes)
    index_path = directory / "index.json"
    index: list[dict] = []
    if index_path.exists():
        try:
            index = json.loads(index_path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            index = []
    index = [entry for entry in index if entry.get("inspection_id") != result["inspection_id"]]
    index.insert(
        0,
        {
            "inspection_id": result["inspection_id"],
            "filename": result.get("filename"),
            "decision": result["decision"],
            "predicted_class": result["prediction"]["predicted_class"],
            "confidence": result["confidence"]["value"],
            "anomaly_score": result["anomaly_score"]["value"],
            "novelty_status": result["anomaly_score"]["novelty_status"],
            "generated_at": result["generated_at"],
        },
    )
    with open(index_path, "w", encoding="utf-8") as handle:
        json.dump(index[:HISTORY_LIMIT], handle, indent=2)


def list_inspections(artifacts_dir: Path) -> list[dict]:
    index_path = Path(artifacts_dir) / INSPECTION_DIRNAME / "index.json"
    if not index_path.exists():
        return []
    try:
        return json.loads(index_path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return []


def get_inspection(artifacts_dir: Path, inspection_id: str) -> dict | None:
    path = Path(artifacts_dir) / INSPECTION_DIRNAME / f"{inspection_id}.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return None


def get_inspection_image(artifacts_dir: Path, inspection_id: str) -> Path | None:
    path = Path(artifacts_dir) / INSPECTION_DIRNAME / f"{inspection_id}.img"
    return path if path.exists() else None
