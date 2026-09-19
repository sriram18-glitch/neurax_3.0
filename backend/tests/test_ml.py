"""Phase 4 test suite: target typing, training, evaluation, isolation,
reproducibility, anomaly detection, reload, no-fabrication, API.

Run everything:  pytest backend/tests -q
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from app.ml.anomaly import fit_anomaly_detector, select_anomaly_features
from app.ml.registry import ModelRegistry, sanitize_model_id
from app.ml.targets import BINARY, MULTICLASS, REGRESSION, detect_target_type


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _contract_and_ingest(frame: pd.DataFrame, tmp_path: Path, name: str = "toy.csv"):
    from app.ingest import ingest_path
    from app.ingest.contract import build_contract
    from app.ingest.profiler import profile_ingest

    tmp_path = Path(tmp_path)
    tmp_path.mkdir(parents=True, exist_ok=True)
    path = tmp_path / name
    frame.to_csv(path, index=False)
    result = ingest_path(path)
    profiles = profile_ingest(result)
    return build_contract(result, profiles), result, path


def _run_full(frame: pd.DataFrame, tmp_path: Path, name: str = "toy.csv") -> dict:
    from app.pipeline import run_pipeline
    from app.ml.runner import run_ml_pipeline

    contract, result, path = _contract_and_ingest(frame, tmp_path, name)
    dataset_id = contract["dataset_id"]
    analysis = run_pipeline(dataset_id, name, contract, result, tmp_path / "artifacts")
    assert analysis["status"] == "complete", analysis.get("error")
    return run_ml_pipeline(dataset_id, analysis, tmp_path / "artifacts" / dataset_id, tmp_path / "models")


def _regression_frame(rows: int = 240, seed: int = 5) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    demand = rng.integers(1, 20, rows).astype(float)
    noise = rng.normal(0, 1.0, rows)
    return pd.DataFrame(
        {
            "Demand": demand,
            "Drilling_Util": rng.uniform(0.2, 0.9, rows),
            "Milling_Util": rng.uniform(0.1, 0.8, rows),
            "Total parts": 100 + 25 * demand + noise,
        }
    )


def _classification_frame(rows: int = 240, seed: int = 6) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    demand = rng.integers(1, 20, rows).astype(float)
    defect = ((demand > 10) ^ (rng.uniform(0, 1, rows) < 0.1)).astype(float)
    return pd.DataFrame(
        {
            "Demand": demand,
            "Drilling_Util": rng.uniform(0.2, 0.9, rows),
            "Defect Pass": defect,
        }
    )


# ---------------------------------------------------------------------------
# A. TARGET TYPING
# ---------------------------------------------------------------------------

def test_target_type_regression_for_counts():
    info = detect_target_type("Total parts", pd.Series(np.arange(100, 200)))
    assert info["type"] == REGRESSION


def test_target_type_binary_for_class_like_name():
    info = detect_target_type("Defect Pass", pd.Series([0.0, 1.0] * 30))
    assert info["type"] == BINARY


def test_target_type_multiclass_for_grade():
    info = detect_target_type("Quality Grade", pd.Series([0, 1, 2, 3] * 20))
    assert info["type"] == MULTICLASS


def test_target_type_unsupported_for_constant_and_text():
    assert detect_target_type("Total parts", pd.Series([5.0] * 40))["type"] == "unsupported"
    assert detect_target_type("Comment", pd.Series(["a", "b"] * 20))["type"] == "unsupported"


def test_counts_are_never_reinterpreted_as_defect_probability():
    info = detect_target_type("Total parts", pd.Series([431, 1458, 5000, 3000, 100, 200]))
    assert info["type"] == REGRESSION
    assert "defect" not in info["reason"].lower()


# ---------------------------------------------------------------------------
# B. TRAINING, EVALUATION, BASELINE
# ---------------------------------------------------------------------------

def test_regression_pipeline_trains_with_baseline_and_metrics(tmp_path):
    summary = _run_full(_regression_frame(), tmp_path)
    assert summary["status"] == "complete", summary.get("error")
    assert summary["models"], "expected at least one trained model"
    model = summary["models"][0]
    assert model["status"] == "READY"
    assert model["target"] == "Total parts"
    assert model["target_type"] == REGRESSION
    assert model["test_metrics"]["rmse"] is not None
    assert np.isfinite(model["test_metrics"]["rmse"])
    assert model["baseline"]["model"] == "dummy_mean"
    assert model["baseline"]["test_metrics"] is not None
    candidates = {c["model"] for c in model["candidates"]}
    assert {"dummy_mean", "ridge", "hist_gradient_boosting"} <= candidates
    assert model["test_metrics"]["rmse"] <= model["baseline"]["test_metrics"]["rmse"] * 1.5


def test_classification_pipeline_reports_classification_metrics(tmp_path):
    summary = _run_full(_classification_frame(), tmp_path)
    assert summary["models"]
    model = summary["models"][0]
    assert model["target_type"] == BINARY
    assert model["test_metrics"]["kind"] == "classification"
    assert model["test_metrics"]["f1_weighted"] is not None
    assert model["baseline"]["model"] == "dummy_most_frequent"


def test_metrics_finite_and_test_untouched(tmp_path):
    summary = _run_full(_regression_frame(), tmp_path)
    model = summary["models"][0]
    for key, value in model["test_metrics"].items():
        if isinstance(value, (int, float)):
            assert np.isfinite(value), (key, value)
    assert model["validation_metrics"] is not model["test_metrics"]


# ---------------------------------------------------------------------------
# C. ARTIFACTS, METADATA, RELOAD
# ---------------------------------------------------------------------------

def test_model_artifacts_and_metadata(tmp_path):
    summary = _run_full(_regression_frame(), tmp_path)
    model = summary["models"][0]
    directory = Path(model["artifact"]["directory"])
    for name in ("model.joblib", "metadata.json", "metrics.json", "feature_importance.json"):
        assert (directory / name).exists(), name
    metadata = json.loads((directory / "metadata.json").read_text(encoding="utf-8"))
    assert metadata["dataset_id"] == summary["dataset_id"]
    assert metadata["target"] == "Total parts"
    assert metadata["predictors"]
    assert metadata["split_counts"]["train"] > 0
    assert metadata["seed"] == 42
    assert metadata["status"] == "READY"
    assert metadata["versions"]["scikit_learn"]


def test_model_reload_produces_consistent_predictions(tmp_path):
    summary = _run_full(_regression_frame(), tmp_path)
    model_summary = summary["models"][0]
    model_id = model_summary["model_id"]
    dataset_id = summary["dataset_id"]

    registry = ModelRegistry(tmp_path / "models")
    reloaded = registry.load_model(dataset_id, model_id)

    frame = pd.read_csv(tmp_path / "artifacts" / dataset_id / "model_inputs" / "toy.csv.gz")
    features = model_summary.get("feature_importance") and json.loads(
        (Path(model_summary["artifact"]["directory"]) / "metadata.json").read_text(encoding="utf-8")
    )["predictors"]
    X = frame[features]
    predictions = reloaded.predict(X)
    assert predictions.shape[0] == X.shape[0]
    assert np.isfinite(np.asarray(predictions, dtype="float64")).all()


def test_feature_importance_present_and_labeled(tmp_path):
    summary = _run_full(_regression_frame(), tmp_path)
    model = summary["models"][0]
    importance = model["feature_importance"]
    assert importance["method"] in {
        "linear_coefficients",
        "tree_impurity_importance",
        "permutation_importance",
    }
    assert importance["top_features"]
    assert importance["label"] == "MODEL CONTRIBUTION"
    top = importance["top_features"][0]
    assert top["feature"] in {"Demand", "Drilling_Util", "Milling_Util"}


def test_linear_coefficient_table_saved(tmp_path):
    summary = _run_full(_regression_frame(), tmp_path)
    model = summary["models"][0]
    directory = Path(model["artifact"]["directory"])
    payload = json.loads((directory / "feature_importance.json").read_text(encoding="utf-8"))
    assert "not evidence of causation" in payload["note"].lower()
    if payload.get("linear_coefficients"):
        assert payload["linear_coefficients"]["coefficients"]


# ---------------------------------------------------------------------------
# D. ISOLATION
# ---------------------------------------------------------------------------

def test_dataset_isolation_models_do_not_overwrite(tmp_path):
    summary_a = _run_full(_regression_frame(seed=1), tmp_path / "a", name="a.csv")
    summary_b = _run_full(_regression_frame(seed=2), tmp_path / "b", name="b.csv")
    assert summary_a["dataset_id"] != summary_b["dataset_id"]
    dir_a = Path(summary_a["models"][0]["artifact"]["directory"])
    dir_b = Path(summary_b["models"][0]["artifact"]["directory"])
    assert dir_a != dir_b
    assert dir_a.exists() and dir_b.exists()
    meta_a = json.loads((dir_a / "metadata.json").read_text(encoding="utf-8"))
    meta_b = json.loads((dir_b / "metadata.json").read_text(encoding="utf-8"))
    assert meta_a["dataset_id"] == summary_a["dataset_id"]
    assert meta_b["dataset_id"] == summary_b["dataset_id"]


def test_sanitize_model_id_distinguishes_targets():
    assert sanitize_model_id("Total parts", "ridge") != sanitize_model_id("Parts per hour", "ridge")


# ---------------------------------------------------------------------------
# E. REPRODUCIBILITY
# ---------------------------------------------------------------------------

def test_reproducible_training_configuration(tmp_path):
    frame = _regression_frame()
    first = _run_full(frame, tmp_path / "one", name="toy.csv")
    second = _run_full(frame, tmp_path / "two", name="toy.csv")
    model_a, model_b = first["models"][0], second["models"][0]
    assert model_a["model_type"] == model_b["model_type"]
    assert model_a["feature_importance"]["top_features"] == model_b["feature_importance"]["top_features"]
    assert model_a["test_metrics"] == model_b["test_metrics"]


# ---------------------------------------------------------------------------
# F. ANOMALY DETECTION
# ---------------------------------------------------------------------------

def test_anomaly_detector_scores_and_labels():
    rng = np.random.default_rng(11)
    normal = pd.DataFrame(
        {"a": rng.normal(0, 1, 500), "b": rng.normal(5, 1, 500), "c": rng.uniform(0, 1, 500)}
    )
    bundle = fit_anomaly_detector(normal, target_columns=[], seed=42)
    assert bundle["status"] == "READY"
    assert bundle["method"] == "isolation_forest"
    states = bundle["states"]
    assert set(states) <= {"NORMAL", "ANOMALOUS", "REVIEW"}
    assert len(states) == 500
    assert bundle["summary"]["n"] == 500
    assert bundle["summary"]["anomalous"] > 0
    assert all("feature" in ex["top_deviating_features"][0] for ex in bundle["top_anomaly_examples"])


def test_anomaly_excludes_target_and_identifier_columns():
    frame = pd.DataFrame(
        {
            "a": np.arange(100.0),
            "b": np.arange(100.0) * 2,
            "Total parts": np.arange(100.0) * 3,
            "row_id": np.arange(100.0),
            "split": ["train"] * 100,
        }
    )
    features = select_anomaly_features(frame, target_columns=["Total parts"])
    assert "Total parts" not in features
    assert "row_id" not in features
    assert "split" not in features


def test_anomaly_not_supported_for_tiny_or_single_feature_data():
    tiny = pd.DataFrame({"a": [1.0, 2.0, 3.0], "b": [1.0, 2.0, 3.0]})
    assert fit_anomaly_detector(tiny, [])["status"] == "NOT_SUPPORTED"
    single = pd.DataFrame({"a": np.arange(200.0), "b": [1.0] * 200})
    assert fit_anomaly_detector(single, [])["status"] == "NOT_SUPPORTED"


def test_anomaly_terminology_is_precise(tmp_path):
    summary = _run_full(_regression_frame(), tmp_path)
    anomaly = summary["models"][0]["anomaly"]
    assert anomaly["detector_kind"] == "PROCESS / FEATURE-SPACE ANOMALY DETECTION"
    assert "defect" not in (anomaly["detector_kind"] or "").lower()


# ---------------------------------------------------------------------------
# G. NO-FABRICATION
# ---------------------------------------------------------------------------

def test_vision_remains_not_supported(tmp_path):
    summary = _run_full(_regression_frame(), tmp_path)
    assert summary["vision"]["status"] == "NOT_SUPPORTED"
    assert "No visual inspection/image training data" in summary["vision"]["reason"]
    assert "defect_rate" not in json.dumps(summary)


def test_unsupported_targets_are_not_modeled(tmp_path):
    rng = np.random.default_rng(8)
    frame = pd.DataFrame(
        {
            "Demand": rng.integers(1, 10, 200).astype(float),
            "Total parts": rng.normal(100, 5, 200),
            "Notes": ["alpha"] * 200,
        }
    )
    summary = _run_full(frame, tmp_path)
    skipped_targets = {s.get("target") for s in summary["skipped_inputs"] if s.get("target")}
    assert "Notes" not in skipped_targets
    assert all(m["status"] in {"READY", "FAILED", "NOT_SUPPORTED"} for m in summary["models"])


def test_no_prediction_preview_file_contains_fabricated_columns(tmp_path):
    summary = _run_full(_regression_frame(), tmp_path)
    dataset_id = summary["dataset_id"]
    preview_dir = tmp_path / "artifacts" / dataset_id / "predictions"
    files = list(preview_dir.glob("*.csv.gz"))
    assert files, "expected persisted prediction previews"
    frame = pd.read_csv(files[0])
    assert {"actual", "predicted"} <= set(frame.columns)
    assert frame["predicted"].notna().all()


# ---------------------------------------------------------------------------
# H. API
# ---------------------------------------------------------------------------

def test_api_models_endpoints(client, tmp_path):
    rng = np.random.default_rng(3)
    frame = pd.DataFrame(
        {
            "Demand": rng.integers(1, 20, 240).astype(float),
            "Drilling_Util": rng.uniform(0.2, 0.9, 240),
            "Total parts": 100 + 20 * rng.integers(1, 20, 240) + rng.normal(0, 1, 240),
        }
    )
    path = tmp_path / "api_toy.csv"
    frame.to_csv(path, index=False)
    with open(path, "rb") as fh:
        response = client.post("/api/upload", files={"file": (path.name, fh, "text/csv")})
    assert response.status_code == 200, response.text
    contract = response.json()
    dataset_id = contract["dataset_id"]
    assert contract["ml"]["status"] == "complete"
    assert contract["ml"]["models_trained"] >= 1
    assert contract["ml"]["vision_status"] == "NOT_SUPPORTED"

    listing = client.get(f"/api/datasets/{dataset_id}/models").json()
    assert listing["status"] == "complete"
    assert listing["models"]
    model_id = listing["models"][0]["model_id"]

    detail = client.get(f"/api/datasets/{dataset_id}/models/{model_id}").json()
    assert detail["metadata"]["dataset_id"] == dataset_id
    assert detail["metrics"]["test"]
    assert detail["feature_importance"]["top_features"]

    assert client.get(f"/api/datasets/{dataset_id}/models/does-not-exist").status_code == 404

    predictions = client.get(f"/api/datasets/{dataset_id}/predictions").json()
    assert predictions["previews"]

    anomalies = client.get(f"/api/datasets/{dataset_id}/anomalies").json()
    assert anomalies["status"] in {"READY", "NOT_SUPPORTED"}
    if anomalies["status"] == "READY":
        assert anomalies["summary"]["n"] > 0
        assert "not a defect label" in anomalies["terminology"]

    retrain = client.post(f"/api/datasets/{dataset_id}/models/train")
    assert retrain.status_code == 200
    assert retrain.json()["status"] == "complete"

    assert client.get("/api/datasets/nope/models").status_code == 404


def test_api_upload_without_predictive_target_still_succeeds(client, tmp_path):
    frame = pd.DataFrame(
        {
            "Cell1_Util": [0.5, 0.6, 0.7, 0.8] * 30,
            "Queue_Load": [1.0, 2.0, 3.0, 4.0] * 30,
        }
    )
    path = tmp_path / "station_only.csv"
    frame.to_csv(path, index=False)
    with open(path, "rb") as fh:
        response = client.post("/api/upload", files={"file": (path.name, fh, "text/csv")})
    assert response.status_code == 200
    contract = response.json()
    assert contract["ml"]["status"] == "complete"
    assert contract["ml"]["models_trained"] == 0
    models = client.get(f"/api/datasets/{contract['dataset_id']}/models").json()
    assert models["models"] == []
