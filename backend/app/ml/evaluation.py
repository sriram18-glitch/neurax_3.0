"""Metric computation. Only metrics that were actually calculated are emitted."""

from __future__ import annotations

import math

import numpy as np
from sklearn.metrics import (
    accuracy_score,
    confusion_matrix,
    f1_score,
    mean_absolute_error,
    mean_squared_error,
    precision_score,
    r2_score,
    recall_score,
)

from .targets import BINARY, MULTICLASS, REGRESSION


def _finite(value):
    if value is None:
        return None
    value = float(value)
    if math.isnan(value) or math.isinf(value):
        return None
    return round(value, 6)


def regression_metrics(y_true, y_pred) -> dict:
    y_true = np.asarray(y_true, dtype="float64")
    y_pred = np.asarray(y_pred, dtype="float64")
    n = int(y_true.size)
    metrics = {
        "kind": REGRESSION,
        "n": n,
        "mae": _finite(mean_absolute_error(y_true, y_pred)) if n else None,
        "rmse": _finite(math.sqrt(mean_squared_error(y_true, y_pred))) if n else None,
        "r2": _finite(r2_score(y_true, y_pred)) if n >= 2 and np.ptp(y_true) > 0 else None,
    }
    return metrics


def classification_metrics(y_true, y_pred, classes=None) -> dict:
    y_true = np.asarray(y_true)
    y_pred = np.asarray(y_pred)
    n = int(y_true.size)
    if n == 0:
        return {"kind": "classification", "n": 0}
    labels = list(classes) if classes is not None else sorted(set(y_true.tolist()) | set(y_pred.tolist()))
    matrix = confusion_matrix(y_true, y_pred, labels=labels).tolist()
    return {
        "kind": "classification",
        "n": n,
        "accuracy": _finite(accuracy_score(y_true, y_pred)),
        "precision_weighted": _finite(precision_score(y_true, y_pred, average="weighted", zero_division=0)),
        "recall_weighted": _finite(recall_score(y_true, y_pred, average="weighted", zero_division=0)),
        "f1_weighted": _finite(f1_score(y_true, y_pred, average="weighted", zero_division=0)),
        "confusion_matrix": matrix,
        "classes": [str(c) for c in labels],
    }


def primary_metric(metrics: dict) -> tuple[str, float | None, str]:
    if metrics.get("kind") == REGRESSION:
        return "rmse", metrics.get("rmse"), "lower"
    return "f1_weighted", metrics.get("f1_weighted"), "higher"


def is_better(candidate_value, current_value, direction: str) -> bool:
    if candidate_value is None:
        return False
    if current_value is None:
        return True
    return candidate_value < current_value if direction == "lower" else candidate_value > current_value
