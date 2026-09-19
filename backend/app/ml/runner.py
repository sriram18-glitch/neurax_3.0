"""ML pipeline runner.

For each supported Phase 3 model input:
  target typing -> candidate models -> train/validate selection on the
  leakage-safe split -> final untouched-test evaluation -> importance ->
  anomaly detection on the train split -> persisted artifacts -> prediction
  previews.

Respects the Phase 3 split exactly (no new splits are created).
"""

from __future__ import annotations

import json
import platform
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import sklearn

from ..pipeline.artifacts import sanitize_name, write_json
from ..pipeline.split import TEST, TRAIN, VALIDATION
from .anomaly import fit_anomaly_detector
from .candidates import build_candidates, params_summary
from .evaluation import classification_metrics, is_better, primary_metric, regression_metrics
from .errors import ModelError
from .importance import coefficient_table, compute_importance
from .registry import ModelRegistry, sanitize_model_id
from .targets import BINARY, MULTICLASS, REGRESSION, detect_target_type

PREDICTION_PREVIEW_ROWS = 200
MODEL_ID_TARGET_CAP = 60


def _versions() -> dict:
    return {
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "scikit_learn": sklearn.__version__,
        "numpy": np.__version__,
        "pandas": pd.__version__,
    }


ANOMALY_SUMMARY_KEYS = (
    "status",
    "method",
    "detector_kind",
    "note",
    "features",
    "contamination",
    "summary",
    "reason",
)


def _anomaly_payload(anomaly: dict, examples_limit: int = 5) -> dict:
    payload = {key: anomaly.get(key) for key in ANOMALY_SUMMARY_KEYS}
    payload["top_examples"] = (anomaly.get("top_anomaly_examples") or [])[:examples_limit]
    return payload


def _load_model_input(artifact_root: Path, name: str) -> pd.DataFrame | None:
    path = artifact_root / "model_inputs" / f"{sanitize_name(name)}.csv.gz"
    if not path.exists():
        return None
    return pd.read_csv(path)


def _split_frames(frame: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, dict]:
    split_column = frame["split"]
    train = frame[split_column == TRAIN]
    validation = frame[split_column == VALIDATION]
    test = frame[split_column == TEST]
    meta = {
        "train": int(train.shape[0]),
        "validation": int(validation.shape[0]),
        "test": int(test.shape[0]),
    }
    return train, validation, test, meta


def _predict(model, X: pd.DataFrame) -> np.ndarray:
    return np.asarray(model.predict(X))


def _train_one_target(
    dataset_id: str,
    input_name: str,
    target: str,
    target_info: dict,
    train: pd.DataFrame,
    validation: pd.DataFrame,
    test: pd.DataFrame,
    features: list[str],
    seed: int,
    registry: ModelRegistry,
    anomaly: dict,
) -> tuple[dict, dict | None]:
    target_type = target_info["type"]
    y_train = train[target].to_numpy(dtype="float64")
    y_validation = validation[target].to_numpy(dtype="float64")
    y_test = test[target].to_numpy(dtype="float64")
    X_train, X_validation, X_test = train[features], validation[features], test[features]

    candidates = build_candidates(target_type, len(train), len(features), seed)
    if not candidates:
        return (
            {
                "input": input_name,
                "target": target,
                "status": "NOT_SUPPORTED",
                "reason": f"target type '{target_type}' has no configured candidates",
                "target_info": target_info,
            },
            None,
        )

    start = time.time()
    results: list[dict] = []
    best_name, best_model, best_metrics, best_value, direction = None, None, None, None, "lower"
    for candidate_name, model in candidates:
        try:
            model.fit(X_train, y_train)
        except Exception as exc:  # noqa: BLE001 - a failed candidate is recorded, not fatal
            results.append({"model": candidate_name, "status": "fit_failed", "error": str(exc)})
            continue
        predictions = _predict(model, X_validation)
        if target_type == REGRESSION:
            metrics = regression_metrics(y_validation, predictions)
        else:
            metrics = classification_metrics(y_validation, predictions)
        metric_name, value, direction = primary_metric(metrics)
        results.append(
            {"model": candidate_name, "status": "fitted", "validation_metrics": metrics, "primary": {metric_name: value}}
        )
        if best_model is None or is_better(value, best_value, direction):
            best_name, best_model, best_metrics, best_value = candidate_name, model, metrics, value

    if best_model is None:
        return (
            {
                "input": input_name,
                "target": target,
                "status": "FAILED",
                "reason": "all candidate models failed to fit",
                "candidates": results,
                "target_info": target_info,
            },
            None,
        )

    test_predictions = _predict(best_model, X_test)
    if target_type == REGRESSION:
        test_metrics = regression_metrics(y_test, test_predictions)
    else:
        test_metrics = classification_metrics(y_test, test_predictions)

    baseline_name = results[0]["model"]
    baseline_metrics = results[0].get("validation_metrics")
    baseline_test_metrics = None
    if baseline_name != best_name:
        baseline_model = candidates[0][1]
        try:
            baseline_test_metrics = (
                regression_metrics(y_test, _predict(baseline_model, X_test))
                if target_type == REGRESSION
                else classification_metrics(y_test, _predict(baseline_model, X_test))
            )
        except Exception:  # noqa: BLE001
            baseline_test_metrics = None

    importance = compute_importance(best_model, features, X_train, y_train, seed)
    coefficients = coefficient_table(best_model, features)

    anomaly_bundle = None
    if anomaly.get("status") == "READY":
        anomaly_bundle = {
            "scaler": anomaly["scaler"],
            "detector": anomaly["detector"],
            "features": anomaly["features"],
            "contamination": anomaly["contamination"],
        }
    anomaly_payload = _anomaly_payload(anomaly)

    training_seconds = time.time() - start

    # prediction preview on test rows -------------------------------------------------
    preview_rows = min(PREDICTION_PREVIEW_ROWS, len(test))
    preview = pd.DataFrame({"row": np.arange(preview_rows)})
    preview["actual"] = y_test[:preview_rows]
    preview["predicted"] = test_predictions[:preview_rows]
    if target_type == REGRESSION:
        preview["residual"] = preview["actual"] - preview["predicted"]
    if anomaly.get("status") == "READY":
        anomaly_features = anomaly.get("features", [])
        if anomaly_features and all(column in test.columns for column in anomaly_features):
            test_matrix = np.nan_to_num(test[anomaly_features].to_numpy(dtype="float64"))
            test_scaled = anomaly["scaler"].transform(test_matrix)
            test_scores = anomaly["detector"].decision_function(test_scaled)
            test_labels = anomaly["detector"].predict(test_scaled)
            test_states = np.where(test_labels == -1, "ANOMALOUS", "NORMAL")
            preview["anomaly_state"] = test_states[:preview_rows]
            preview["anomaly_score"] = test_scores[:preview_rows]

    model_id = sanitize_model_id(input_name[:MODEL_ID_TARGET_CAP], target)
    metadata = {
        "dataset_id": dataset_id,
        "model_id": model_id,
        "input": input_name,
        "target": target,
        "target_type": target_type,
        "target_info": target_info,
        "model_type": best_name,
        "hyperparameters": params_summary(best_model),
        "predictors": features,
        "split_strategy": "phase3_leakage_safe_split",
        "split_counts": {"train": len(train), "validation": len(validation), "test": len(test)},
        "seed": seed,
        "trained_at": datetime.now(timezone.utc).isoformat(),
        "training_seconds": round(training_seconds, 3),
        "versions": _versions(),
        "status": "READY",
        "note": "Trained on the Phase 3 leakage-safe train split; final metrics use the untouched test split.",
    }

    metrics_payload = {
        "validation": {"selected": best_metrics, "all_candidates": results},
        "test": test_metrics,
        "baseline": {
            "model": baseline_name,
            "test_metrics": baseline_test_metrics,
            "note": "Baseline is the first configured candidate; comparison only, never used for selection claims beyond validation.",
        },
        "selection_metric": primary_metric(best_metrics)[0],
        "test_untouched_during_selection": True,
    }

    importance_payload = {
        **importance,
        "linear_coefficients": coefficients,
        "terminology": "MODEL CONTRIBUTION / ASSOCIATED PREDICTOR - not root cause",
    }

    saved = registry.save(
        dataset_id, model_id, best_model, metadata, metrics_payload, importance_payload, anomaly_bundle
    )

    summary = {
        "input": input_name,
        "target": target,
        "target_type": target_type,
        "target_info": target_info,
        "model_id": model_id,
        "model_type": best_name,
        "status": "READY",
        "candidates": [
            {
                "model": r["model"],
                "status": r["status"],
                "validation_primary": r.get("primary"),
                **({"error": r["error"]} if "error" in r else {}),
            }
            for r in results
        ],
        "validation_metrics": best_metrics,
        "test_metrics": test_metrics,
        "baseline": {"model": baseline_name, "test_metrics": baseline_test_metrics},
        "feature_importance": {
            "method": importance.get("method"),
            "top_features": importance.get("top_features", []),
            "label": importance.get("label"),
        },
        "anomaly": anomaly_payload,
        "training_seconds": round(training_seconds, 3),
        "artifact": saved,
    }

    return summary, {
        "preview": preview,
        "model_id": model_id,
        "input": input_name,
        "target": target,
    }


def run_ml_pipeline(
    dataset_id: str,
    analysis: dict,
    artifact_root: Path,
    models_dir: Path,
    seed: int = 42,
) -> dict:
    """Train models for every supported Phase 3 model input of this dataset."""
    started = time.time()
    registry = ModelRegistry(models_dir)
    artifact_root = Path(artifact_root)
    summary: dict = {
        "dataset_id": dataset_id,
        "status": "complete",
        "error": None,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "seed": seed,
        "models": [],
        "skipped_inputs": [],
        "anomaly": {"status": "NOT_SUPPORTED", "reason": "no model input with >= 2 usable process features"},
        "vision": {
            "status": "NOT_SUPPORTED",
            "reason": "No visual inspection/image training data is available in the current manufacturing dataset.",
        },
        "prediction_previews": [],
        "versions": _versions(),
    }

    if analysis.get("status") != "complete":
        summary["status"] = "failed"
        summary["error"] = {
            "error": True,
            "code": "ANALYSIS_NOT_COMPLETE",
            "message": "Phase 3 analysis is not complete for this dataset; models cannot be trained.",
            "detail": analysis.get("error"),
        }
        return summary

    try:
        for model_input in analysis.get("model_inputs", []):
            name = model_input["name"]
            frame = _load_model_input(artifact_root, name)
            if frame is None:
                summary["skipped_inputs"].append({"input": name, "reason": "model input artifact not found"})
                continue

            split_meta = model_input.get("split") or {}
            if split_meta.get("status") != "COMPUTED":
                summary["skipped_inputs"].append(
                    {
                        "input": name,
                        "reason": split_meta.get("reason", "split not available for this input"),
                    }
                )
                continue

            train, validation, test, counts = _split_frames(frame)
            if min(counts.values()) == 0:
                summary["skipped_inputs"].append({"input": name, "reason": f"empty split partition: {counts}"})
                continue

            features = [c for c in model_input["predictors"] if c in frame.columns]
            targets = [c for c in model_input["responses"] if c in frame.columns]
            if not features or not targets:
                summary["skipped_inputs"].append({"input": name, "reason": "no usable predictor/response columns"})
                continue

            anomaly = fit_anomaly_detector(train, targets, seed=seed)
            if anomaly.get("status") == "READY" and summary["anomaly"]["status"] != "READY":
                summary["anomaly"] = _anomaly_payload(anomaly, examples_limit=5)

            for target in targets:
                target_info = detect_target_type(target, frame[target])
                if target_info["type"] == "unsupported":
                    summary["skipped_inputs"].append(
                        {"input": name, "target": target, "reason": target_info["reason"]}
                    )
                    continue
                model_summary, preview = _train_one_target(
                    dataset_id,
                    name,
                    target,
                    target_info,
                    train,
                    validation,
                    test,
                    features,
                    seed,
                    registry,
                    anomaly,
                )
                summary["models"].append(model_summary)
                if preview is not None:
                    summary["prediction_previews"].append(preview)

        # persist prediction previews as artifacts
        preview_dir = artifact_root / "predictions"
        preview_files = []
        for preview in summary["prediction_previews"]:
            file_name = sanitize_name(f"{preview['input']}__{preview['target']}.csv.gz")
            target_path = preview_dir / file_name
            target_path.parent.mkdir(parents=True, exist_ok=True)
            preview["preview"].to_csv(target_path, index=False, compression="gzip")
            preview_files.append(file_name)
        summary["prediction_previews"] = [
            {k: v for k, v in preview.items() if k != "preview"} for preview in summary["prediction_previews"]
        ]
        summary["prediction_preview_files"] = preview_files

        summary["total_training_seconds"] = round(time.time() - started, 3)
        write_json(artifact_root / "ml_summary.json", summary)
        write_json(
            artifact_root / "model_registry.json",
            {"dataset_id": dataset_id, "models": registry.list_models(dataset_id)},
        )
        return summary

    except ModelError as exc:
        summary["status"] = "failed"
        summary["error"] = exc.to_dict()
        return summary
    except Exception as exc:  # noqa: BLE001 - contained failure, reported honestly
        summary["status"] = "failed"
        summary["error"] = {
            "error": True,
            "code": "ML_PROCESSING_FAILURE",
            "message": "Model training failed unexpectedly.",
            "detail": str(exc),
        }
        return summary
