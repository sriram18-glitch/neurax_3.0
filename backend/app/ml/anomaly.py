"""Process anomaly detection.

Feature-space anomaly detection on numeric process data. This is NOT visual
OOD detection and is labeled as PROCESS / FEATURE-SPACE ANOMALY DETECTION
everywhere it appears. Target columns, split columns and identifiers are
excluded from the feature set.
"""

from __future__ import annotations

import numpy as np
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler

MAX_ANOMALY_ROWS = 50_000
CONTAMINATION = 0.02
SEED = 42
STATE_NORMAL = "NORMAL"
STATE_ANOMALOUS = "ANOMALOUS"
STATE_REVIEW = "REVIEW"
EXCLUDE_NAME = ("split", "index", "id", "time")


def select_anomaly_features(frame, target_columns: list[str]) -> list[str]:
    numeric = frame.select_dtypes(include=[np.number])
    excluded = set(target_columns)
    features = [
        column
        for column in numeric.columns
        if column not in excluded and not any(token in str(column).lower() for token in EXCLUDE_NAME)
    ]
    usable = [column for column in features if frame[column].nunique(dropna=True) > 1]
    return usable


def fit_anomaly_detector(frame, target_columns: list[str], seed: int = SEED) -> dict:
    features = select_anomaly_features(frame, target_columns)
    if len(features) < 2:
        return {
            "status": "NOT_SUPPORTED",
            "reason": "fewer than 2 usable numeric process features after excluding targets/identifiers",
            "features": features,
        }

    data = frame[features].apply(np.asarray, axis=1, result_type="expand")
    matrix = np.asarray(frame[features].to_numpy(), dtype="float64")
    matrix = np.nan_to_num(matrix, nan=0.0, posinf=0.0, neginf=0.0)

    if matrix.shape[0] < 50:
        return {
            "status": "NOT_SUPPORTED",
            "reason": f"only {matrix.shape[0]} rows; at least 50 are required for a stable normal reference",
            "features": features,
        }

    rng = np.random.default_rng(seed)
    reference_rows = min(matrix.shape[0], MAX_ANOMALY_ROWS)
    if reference_rows < matrix.shape[0]:
        reference_idx = np.sort(rng.choice(matrix.shape[0], size=reference_rows, replace=False))
    else:
        reference_idx = np.arange(matrix.shape[0])

    scaler = StandardScaler().fit(matrix[reference_idx])
    scaled = scaler.transform(matrix)
    detector = IsolationForest(
        n_estimators=200,
        contamination=CONTAMINATION,
        random_state=seed,
        n_jobs=-1,
    )
    detector.fit(scaled[reference_idx])

    raw_scores = detector.decision_function(scaled)
    labels = detector.predict(scaled)
    percentiles = (raw_scores.argsort().argsort() / max(len(raw_scores) - 1, 1) * 100.0)

    states = np.where(labels == -1, STATE_ANOMALOUS, STATE_NORMAL)
    review_cut = np.percentile(raw_scores, 5.0)
    states[(labels == 1) & (raw_scores <= review_cut)] = STATE_REVIEW

    # top contributing unusual features per anomalous sample (z-deviation)
    anomalies = np.where(states == STATE_ANOMALOUS)[0]
    top_examples: list[dict] = []
    if anomalies.size:
        z = np.abs(scaled[anomalies])
        for row_position, sample_index in enumerate(anomalies[:25]):
            order = np.argsort(-z[row_position])[:3]
            top_examples.append(
                {
                    "row": int(sample_index),
                    "score": round(float(raw_scores[sample_index]), 6),
                    "percentile": round(float(percentiles[sample_index]), 2),
                    "top_deviating_features": [
                        {
                            "feature": features[i],
                            "abs_z": round(float(z[row_position][i]), 3),
                            "value": round(float(matrix[sample_index][i]), 6),
                        }
                        for i in order
                    ],
                }
            )

    return {
        "status": "READY",
        "method": "isolation_forest",
        "detector_kind": "PROCESS / FEATURE-SPACE ANOMALY DETECTION",
        "note": "Anomaly means unusual in process feature space; it is not a validated defect label.",
        "features": features,
        "contamination": CONTAMINATION,
        "scaler": scaler,
        "detector": detector,
        "scores": raw_scores,
        "percentiles": percentiles,
        "states": states,
        "summary": {
            "n": int(matrix.shape[0]),
            "normal": int((states == STATE_NORMAL).sum()),
            "review": int((states == STATE_REVIEW).sum()),
            "anomalous": int((states == STATE_ANOMALOUS).sum()),
            "score_min": round(float(raw_scores.min()), 6),
            "score_max": round(float(raw_scores.max()), 6),
        },
        "top_anomaly_examples": top_examples,
    }
