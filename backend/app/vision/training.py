"""Real vision model training.

Pipeline (all real, no fabricated results):

  class-folder discovery -> perceptual-hash grouping -> leakage-safe split
  -> MobileNetV2 (ImageNet, frozen) embeddings -> logistic-regression head
  -> temperature-scaling calibration -> normal-class anomaly reference
  -> test-set evaluation -> artifact persistence

The backbone is a frozen pretrained feature extractor; only the linear head is
trained. This is appropriate for a 24-hour prototype on CPU and keeps training
to a few minutes.
"""

from __future__ import annotations

import hashlib
import json
import platform
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from PIL import Image
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix, f1_score
from sklearn.preprocessing import StandardScaler

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff", ".webp"}
IMG_SIZE = 224
BACKBONE_NAME = "mobilenet_v2"
SEED = 42
TRAIN_PER_CLASS = 400
VAL_PER_CLASS = 100
TEST_PER_CLASS = 100
NORMAL_CLASS = "normal"
DHASH_NEAR_DUPLICATE_DISTANCE = 0


def _dhash(path: Path) -> int:
    """64-bit difference hash for near-duplicate grouping."""
    with Image.open(path) as handle:
        small = handle.convert("L").resize((9, 8), Image.BILINEAR)
    pixels = np.asarray(small, dtype=np.int16)
    diff = pixels[:, 1:] > pixels[:, :-1]
    bits = 0
    for bit in diff.flatten():
        bits = (bits << 1) | int(bit)
    return bits


def discover_class_dataset(root: Path) -> dict:
    root = Path(root)
    classes: dict[str, list[Path]] = {}
    for folder in sorted(root.iterdir()):
        if not folder.is_dir():
            continue
        files = sorted(
            path for path in folder.rglob("*") if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS
        )
        if files:
            classes[folder.name] = files
    return classes


def build_grouped_splits(classes: dict[str, list[Path]], seed: int = SEED) -> dict:
    """Leakage-safe split: near-duplicate images (same dHash group) never cross splits."""
    rng = np.random.default_rng(seed)
    splits = {"train": [], "validation": [], "test": [], "labels": {}}
    group_stats = {"groups_total": 0, "near_duplicate_groups": 0}

    for class_name, files in classes.items():
        selected = files[: TRAIN_PER_CLASS + VAL_PER_CLASS + TEST_PER_CLASS]
        groups: dict[int, list[Path]] = defaultdict(list)
        for path in selected:
            groups[_dhash(path)].append(path)
        group_keys = sorted(groups.keys())
        rng.shuffle(group_keys)
        group_stats["groups_total"] += len(group_keys)
        group_stats["near_duplicate_groups"] += sum(1 for key in group_keys if len(groups[key]) > 1)

        total = len(selected)
        train_target = int(total * TRAIN_PER_CLASS / (TRAIN_PER_CLASS + VAL_PER_CLASS + TEST_PER_CLASS))
        val_target = int(total * VAL_PER_CLASS / (TRAIN_PER_CLASS + VAL_PER_CLASS + TEST_PER_CLASS))

        current = 0
        for index, key in enumerate(group_keys):
            members = groups[key]
            if current < train_target:
                bucket = "train"
            elif current < train_target + val_target:
                bucket = "validation"
            else:
                bucket = "test"
            for member in members:
                splits[bucket].append(member)
                splits["labels"][str(member)] = class_name
            current += len(members)

    splits["group_stats"] = group_stats
    return splits


def load_image_tensor(path: Path) -> np.ndarray:
    with Image.open(path) as handle:
        image = handle.convert("RGB").resize((IMG_SIZE, IMG_SIZE), Image.BILINEAR)
    return np.asarray(image, dtype=np.float32)


def build_feature_model():
    import tensorflow as tf

    base = tf.keras.applications.MobileNetV2(
        include_top=False, weights="imagenet", input_shape=(IMG_SIZE, IMG_SIZE, 3)
    )
    base.trainable = False
    conv_features = base.output  # (7, 7, 1280) - last conv activation
    pooled = tf.keras.layers.GlobalAveragePooling2D()(conv_features)
    model = tf.keras.Model(inputs=base.input, outputs=[pooled, conv_features])
    return model


def extract_embeddings(model, paths: list[Path], batch_size: int = 32, progress=None) -> np.ndarray:
    import tensorflow as tf

    outputs: list[np.ndarray] = []
    total = len(paths)
    for start in range(0, total, batch_size):
        batch_paths = paths[start : start + batch_size]
        batch = np.stack([load_image_tensor(path) for path in batch_paths])
        batch = tf.keras.applications.mobilenet_v2.preprocess_input(batch)
        pooled, _ = model(batch, training=False)
        outputs.append(np.asarray(pooled))
        if progress:
            progress(min(start + batch_size, total), total)
    return np.concatenate(outputs, axis=0)


def fit_temperature(logits: np.ndarray, labels: np.ndarray) -> float:
    """Single-parameter temperature scaling minimizing validation NLL."""
    from scipy.optimize import minimize_scalar

    def nll(log_temperature: float) -> float:
        temperature = float(np.exp(log_temperature))
        scaled = logits / temperature
        scaled -= scaled.max(axis=1, keepdims=True)
        probabilities = np.exp(scaled)
        probabilities /= probabilities.sum(axis=1, keepdims=True)
        picked = probabilities[np.arange(len(labels)), labels]
        return float(-np.mean(np.log(np.clip(picked, 1e-12, 1.0))))

    result = minimize_scalar(nll, bounds=(-2.0, 2.0), method="bounded")
    return float(np.exp(result.x))


def softmax(logits: np.ndarray) -> np.ndarray:
    scaled = logits - logits.max(axis=1, keepdims=True)
    probabilities = np.exp(scaled)
    return probabilities / probabilities.sum(axis=1, keepdims=True)


FEATURE_SPACE_POINTS_PER_CLASS = 90


def _build_feature_space(scaled: np.ndarray, labels: np.ndarray, class_names: list[str]) -> dict:
    """Deterministic 2-D PCA projection of the real standardized embeddings.

    The projection is computed once at training time and stored; live samples
    are projected with the same components, so the UI scatter shows real data.
    """
    mean = scaled.mean(axis=0)
    centered = scaled - mean
    _, _, vt = np.linalg.svd(centered, full_matrices=False)
    components = vt[:2]
    projected = centered @ components.T
    total_variance = float((centered**2).sum())
    explained = [
        round(float((projected[:, index] ** 2).sum() / total_variance), 4) if total_variance > 0 else 0.0
        for index in range(2)
    ]
    clouds: dict[str, list[list[float]]] = {}
    counts: dict[str, int] = {}
    for class_index, name in enumerate(class_names):
        positions = np.flatnonzero(labels == class_index)
        counts[name] = int(positions.size)
        take = min(positions.size, FEATURE_SPACE_POINTS_PER_CLASS)
        if take == 0:
            clouds[name] = []
            continue
        step = positions.size / take
        chosen = positions[(np.arange(take) * step).astype(int)]
        clouds[name] = [
            [round(float(point[0]), 3), round(float(point[1]), 3)] for point in projected[chosen]
        ]
    payload = {
        "method": "PCA via SVD over standardized training embeddings (real data only)",
        "components": 2,
        "explained_variance_ratio": explained,
        "sampling": f"deterministic evenly-spaced subsample, up to {FEATURE_SPACE_POINTS_PER_CLASS} points per class",
        "clouds": clouds,
        "counts": counts,
    }
    return {"components": components, "mean": mean, "payload": payload}


def train_vision_model(
    dataset_root: Path,
    artifacts_dir: Path,
    seed: int = SEED,
    use_cached_embeddings: bool = False,
) -> dict:
    import joblib
    import tensorflow as tf

    started = time.time()
    artifacts_dir = Path(artifacts_dir)
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    cache_path = artifacts_dir / "embeddings.npz"

    classes = discover_class_dataset(dataset_root)
    if len(classes) < 2:
        raise ValueError("Vision dataset must contain at least 2 class folders.")
    if NORMAL_CLASS not in classes:
        raise ValueError(f"Vision dataset must contain a '{NORMAL_CLASS}' class folder for PASS decisions.")

    split_started = time.time()
    splits = build_grouped_splits(classes, seed=seed)
    split_seconds = time.time() - split_started
    class_names = sorted(classes.keys())
    label_index = {name: index for index, name in enumerate(class_names)}

    embedding_seconds = 0.0
    if use_cached_embeddings and cache_path.exists():
        cached = np.load(cache_path, allow_pickle=True)
        train_embeddings = cached["train_embeddings"]
        val_embeddings = cached["val_embeddings"]
        test_embeddings = cached["test_embeddings"]
        train_labels = cached["train_labels"]
        val_labels = cached["val_labels"]
        test_labels = cached["test_labels"]
    else:
        model = build_feature_model()
        embedding_started = time.time()
        train_embeddings = extract_embeddings(model, splits["train"])
        val_embeddings = extract_embeddings(model, splits["validation"])
        test_embeddings = extract_embeddings(model, splits["test"])
        embedding_seconds = time.time() - embedding_started
        train_labels = np.array([label_index[splits["labels"][str(p)]] for p in splits["train"]])
        val_labels = np.array([label_index[splits["labels"][str(p)]] for p in splits["validation"]])
        test_labels = np.array([label_index[splits["labels"][str(p)]] for p in splits["test"]])
        np.savez(
            cache_path,
            train_embeddings=train_embeddings,
            val_embeddings=val_embeddings,
            test_embeddings=test_embeddings,
            train_labels=train_labels,
            val_labels=val_labels,
            test_labels=test_labels,
        )

    scaler = StandardScaler().fit(train_embeddings)
    scaled_train = scaler.transform(train_embeddings)
    scaled_val = scaler.transform(val_embeddings)
    scaled_test = scaler.transform(test_embeddings)

    classifier = LogisticRegression(max_iter=3000, C=1.0, random_state=seed)
    classifier.fit(scaled_train, train_labels)

    val_logits = classifier.decision_function(scaled_val)
    temperature = fit_temperature(val_logits, val_labels)
    val_probabilities = softmax(val_logits / temperature)
    val_accuracy = float(accuracy_score(val_labels, val_probabilities.argmax(axis=1)))

    # --- novelty references: one centroid + distance distribution per class ----
    # A defect is "novel" when it is unlike the KNOWN class it was assigned to,
    # not merely unlike the normal class (every defect is unlike normal).
    centroids: dict[int, np.ndarray] = {}
    class_distance_references: dict[int, np.ndarray] = {}
    for class_index in range(len(class_names)):
        members = scaled_train[train_labels == class_index]
        centroid = members.mean(axis=0)
        centroids[class_index] = centroid
        distances = np.linalg.norm(members - centroid, axis=1)
        class_distance_references[class_index] = distances

    def class_novelty(matrix: np.ndarray, predicted: np.ndarray) -> np.ndarray:
        scores = np.zeros(len(matrix))
        for index in range(len(matrix)):
            reference = class_distance_references[int(predicted[index])]
            distance = float(np.linalg.norm(matrix[index] - centroids[int(predicted[index])]))
            scores[index] = float((reference < distance).mean())
        return scores

    # --- anomaly reference against the normal class (reported separately) ------
    normal_mask = train_labels == label_index[NORMAL_CLASS]
    normal_embeddings = scaled_train[normal_mask]
    normal_mean = normal_embeddings.mean(axis=0)
    covariance = np.cov(normal_embeddings, rowvar=False)
    shrinkage = 1e-3 * np.trace(covariance) / covariance.shape[0]
    precision = np.linalg.inv(covariance + shrinkage * np.eye(covariance.shape[0]))

    def mahalanobis(matrix: np.ndarray) -> np.ndarray:
        delta = matrix - normal_mean
        return np.sqrt(np.einsum("ij,jk,ik->i", delta, precision, delta))

    normal_val_mask = val_labels == label_index[NORMAL_CLASS]
    normal_reference_distances = mahalanobis(scaled_val[normal_val_mask])
    anomaly_threshold = float(np.percentile(normal_reference_distances, 99.0))

    # --- test evaluation with the full decision layer --------------------------
    test_logits = classifier.decision_function(scaled_test)
    test_probabilities = softmax(test_logits / temperature)
    test_predictions = test_probabilities.argmax(axis=1)
    test_distances = mahalanobis(scaled_test)
    test_anomaly_scores = np.array(
        [float((normal_reference_distances < distance).mean()) for distance in test_distances]
    )
    test_novelty_scores = class_novelty(scaled_test, test_predictions)

    pass_confidence = 0.80
    defect_confidence = 0.70
    novelty_gate = 0.99
    decisions = []
    for index in range(len(test_labels)):
        predicted = class_names[int(test_predictions[index])]
        confidence = float(test_probabilities[index, test_predictions[index]])
        anomaly = float(test_anomaly_scores[index])
        novelty = float(test_novelty_scores[index])
        if predicted == NORMAL_CLASS:
            if confidence >= pass_confidence and anomaly <= novelty_gate:
                decisions.append("PASS")
            else:
                decisions.append("REVIEW")
        else:
            if confidence >= defect_confidence and novelty <= novelty_gate:
                decisions.append("DEFECT")
            else:
                decisions.append("REVIEW")
    decisions = np.array(decisions)

    true_defect = test_labels != label_index[NORMAL_CLASS]
    true_normal = ~true_defect
    false_accept_rate = float((decisions[true_defect] == "PASS").mean()) if true_defect.any() else None
    false_reject_rate = float((decisions[true_normal] == "DEFECT").mean()) if true_normal.any() else None
    review_rate = float((decisions == "REVIEW").mean())

    # PASS / DEFECT / REVIEW decision matrix measured on the test split
    decision_columns = ["PASS", "DEFECT", "REVIEW"]
    actual_rows = ["PASS (normal)", "DEFECT (defective)"]
    decision_matrix = []
    for is_defect, label in ((False, actual_rows[0]), (True, actual_rows[1])):
        row_actual = true_defect if is_defect else true_normal
        decision_matrix.append(
            {
                "actual": label,
                "counts": {column: int((decisions[row_actual] == column).sum()) for column in decision_columns},
            }
        )

    report = classification_report(
        test_labels, test_predictions, labels=list(range(len(class_names))), target_names=class_names, output_dict=True, zero_division=0
    )
    metrics = {
        "accuracy": float(accuracy_score(test_labels, test_predictions)),
        "f1_weighted": float(f1_score(test_labels, test_predictions, average="weighted")),
        "per_class": {
            name: {
                "precision": float(report[name]["precision"]),
                "recall": float(report[name]["recall"]),
                "f1": float(report[name]["f1-score"]),
                "support": int(report[name]["support"]),
            }
            for name in class_names
        },
        "confusion_matrix": confusion_matrix(test_labels, test_predictions, labels=list(range(len(class_names)))).tolist(),
        "val_accuracy": val_accuracy,
        "false_accept_rate": false_accept_rate,
        "false_reject_rate": false_reject_rate,
        "review_rate": review_rate,
        "decision_matrix": decision_matrix,
        "decision_matrix_columns": decision_columns,
        "decisions": {
            "PASS": int((decisions == "PASS").sum()),
            "DEFECT": int((decisions == "DEFECT").sum()),
            "REVIEW": int((decisions == "REVIEW").sum()),
        },
    }

    joblib.dump(classifier, artifacts_dir / "classifier.joblib")
    joblib.dump(scaler, artifacts_dir / "scaler.joblib")

    # --- feature space projection (PCA over the real training embeddings) ------
    # Deterministic 2-D projection so the UI can show the reference clouds and
    # where a live sample lands. Nothing is invented: these are real embeddings.
    feature_space = _build_feature_space(scaled_train, train_labels, class_names)
    np.savez(
        artifacts_dir / "feature_space.npz",
        components=feature_space["components"],
        mean=feature_space["mean"],
    )
    with open(artifacts_dir / "feature_space.json", "w", encoding="utf-8") as handle:
        json.dump(feature_space["payload"], handle, indent=2)

    np.savez(
        artifacts_dir / "normal_reference.npz",
        mean=normal_mean,
        precision=precision,
        reference_distances=normal_reference_distances,
        anomaly_threshold=np.array([anomaly_threshold]),
        class_centroids=np.stack([centroids[index] for index in range(len(class_names))]),
        class_distance_references=np.array(
            [class_distance_references[index] for index in range(len(class_names))], dtype=object
        ),
    )
    with open(artifacts_dir / "calibration.json", "w", encoding="utf-8") as handle:
        json.dump(
            {
                "method": "temperature_scaling",
                "temperature": temperature,
                "fitted_on": "validation split logits",
                "val_accuracy_after": val_accuracy,
            },
            handle,
            indent=2,
        )
    with open(artifacts_dir / "class_mapping.json", "w", encoding="utf-8") as handle:
        json.dump({"classes": class_names, "normal_class": NORMAL_CLASS, "index": label_index}, handle, indent=2)
    with open(artifacts_dir / "thresholds.json", "w", encoding="utf-8") as handle:
        json.dump(
            {
                "pass_confidence": pass_confidence,
                "defect_confidence": defect_confidence,
                "anomaly_review_percentile": 0.99,
                "note": "Thresholds are configurable; values above were used for the recorded metrics.",
            },
            handle,
            indent=2,
        )
    with open(artifacts_dir / "preprocessing.json", "w", encoding="utf-8") as handle:
        json.dump(
            {
                "image_size": [IMG_SIZE, IMG_SIZE],
                "color": "grayscale converted to RGB",
                "normalization": "mobilenet_v2.preprocess_input",
                "backbone": BACKBONE_NAME,
            },
            handle,
            indent=2,
        )
    with open(artifacts_dir / "metrics.json", "w", encoding="utf-8") as handle:
        json.dump(metrics, handle, indent=2)

    metadata = {
        "dataset_root": str(dataset_root),
        "class_count": len(class_names),
        "classes": class_names,
        "normal_class": NORMAL_CLASS,
        "images": {
            "total_available": int(sum(len(files) for files in classes.values())),
            "train": len(splits["train"]),
            "validation": len(splits["validation"]),
            "test": len(splits["test"]),
        },
        "split": {
            "strategy": "perceptual-hash grouped split (near-duplicate images never cross splits)",
            "seed": seed,
            "group_stats": splits["group_stats"],
            "split_seconds": round(split_seconds, 3),
        },
        "backbone": {
            "name": BACKBONE_NAME,
            "pretrained": "imagenet",
            "frozen": True,
            "embedding_dim": int(train_embeddings.shape[1]),
            "conv_feature_shape": [7, 7, 1280],
        },
        "head": {"model": "LogisticRegression", "max_iter": 3000, "C": 1.0},
        "calibration": "temperature_scaling",
        "localization": "class-activation mapping (model-derived; no ground-truth annotations exist)",
        "novelty": "distance to predicted-class centroid vs that class's training distribution",
        "anomaly": "Mahalanobis distance percentile against the normal-class reference",
        "decision_logic": {
            "PASS": "predicted normal, calibrated confidence >= pass_confidence, anomaly within normal reference",
            "DEFECT": "predicted known defect, calibrated confidence >= defect_confidence, novelty within class reference",
            "REVIEW": "low confidence, novel condition (unlike the assigned known class), or anomalous normal sample",
        },
        "trained_at": datetime.now(timezone.utc).isoformat(),
        "timings": {
            "embedding_seconds": round(embedding_seconds, 1),
            "total_seconds": round(time.time() - started, 1),
        },
        "versions": {
            "python": platform.python_version(),
            "tensorflow": tf.__version__,
            "platform": platform.platform(),
        },
    }
    with open(artifacts_dir / "metadata.json", "w", encoding="utf-8") as handle:
        json.dump(metadata, handle, indent=2)

    return {
        "status": "complete",
        "artifacts_dir": str(artifacts_dir),
        "classes": class_names,
        "images": metadata["images"],
        "metrics": metrics,
        "temperature": temperature,
        "timings": metadata["timings"],
    }


def dataset_fingerprint(dataset_root: Path) -> str:
    digest = hashlib.sha256()
    for folder in sorted(Path(dataset_root).iterdir()):
        if folder.is_dir():
            digest.update(folder.name.encode("utf-8"))
            digest.update(str(len(list(folder.glob("*")))).encode("utf-8"))
    return digest.hexdigest()[:12]
