"""Feature importance / association.

Terminology is deliberate: a high importance is a MODEL CONTRIBUTION or an
ASSOCIATED PREDICTOR, never a root cause. Methods: linear coefficients,
tree impurity importance, permutation importance (fallback for pipelines).
"""

from __future__ import annotations

import numpy as np
from sklearn.inspection import permutation_importance

MAX_IMPORTANCE_ROWS = 20_000
TOP_N = 10


def _direction(coefficient: float) -> str:
    if coefficient > 0:
        return "positive_association"
    if coefficient < 0:
        return "negative_association"
    return "neutral"


def compute_importance(model, features: list[str], X, y, seed: int = 42) -> dict:
    result = {
        "method": None,
        "label": "MODEL CONTRIBUTION",
        "note": "Feature importance describes model association within this dataset; it is not evidence of causation.",
        "top_features": [],
    }
    estimator = model
    pipeline = None
    if hasattr(model, "named_steps"):
        pipeline = model
        estimator = list(model.named_steps.values())[-1]

    if hasattr(estimator, "coef_"):
        coefficients = np.asarray(estimator.coef_, dtype="float64")
        values = coefficients if coefficients.ndim == 1 else np.abs(coefficients).mean(axis=0)
        if values.size == len(features):
            result["method"] = "linear_coefficients"
            ranked = np.argsort(-np.abs(values))
            result["top_features"] = [
                {
                    "feature": features[i],
                    "importance": round(float(abs(values[i])), 6),
                    "direction": _direction(float(values[i])),
                }
                for i in ranked[:TOP_N]
            ]
            return result

    if hasattr(estimator, "feature_importances_"):
        values = np.asarray(estimator.feature_importances_, dtype="float64")
        if values.size == len(features):
            result["method"] = "tree_impurity_importance"
            ranked = np.argsort(-values)
            result["top_features"] = [
                {"feature": features[i], "importance": round(float(values[i]), 6), "direction": None}
                for i in ranked[:TOP_N]
            ]
            return result

    try:
        n = min(len(X), MAX_IMPORTANCE_ROWS)
        X_sample = X.iloc[:n] if hasattr(X, "iloc") else X[:n]
        y_sample = y[:n]
        importance = permutation_importance(
            model, X_sample, y_sample, n_repeats=5, random_state=seed, n_jobs=1
        )
        values = importance.importances_mean
        if values.size == len(features):
            result["method"] = "permutation_importance"
            ranked = np.argsort(-values)
            result["top_features"] = [
                {"feature": features[i], "importance": round(float(max(values[i], 0.0)), 6), "direction": None}
                for i in ranked[:TOP_N]
            ]
            return result
    except Exception as exc:  # noqa: BLE001 - importance must never fail a pipeline
        result["note"] += f" Permutation importance unavailable: {exc}"
    return result


def coefficient_table(model, features: list[str]) -> dict | None:
    estimator = model
    if hasattr(model, "named_steps"):
        estimator = list(model.named_steps.values())[-1]
    if not hasattr(estimator, "coef_"):
        return None
    coefficients = np.asarray(estimator.coef_, dtype="float64")
    if coefficients.ndim != 1 or coefficients.size != len(features):
        return None
    return {
        "intercept": round(float(np.asarray(estimator.intercept_).ravel()[0]), 6),
        "coefficients": {features[i]: round(float(coefficients[i]), 6) for i in range(len(features))},
        "note": "Linear model coefficients on standardized features; association only, not causation.",
    }
