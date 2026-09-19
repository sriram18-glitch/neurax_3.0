"""Candidate model selection.

Simple, strong, deterministic baselines first. Heavy candidates are only added
when the data size justifies them. No hyperparameter search is performed.
"""

from __future__ import annotations

from sklearn.dummy import DummyClassifier, DummyRegressor
from sklearn.ensemble import (
    HistGradientBoostingClassifier,
    HistGradientBoostingRegressor,
    RandomForestClassifier,
    RandomForestRegressor,
)
from sklearn.linear_model import LogisticRegression, Ridge
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from .targets import BINARY, MULTICLASS, REGRESSION

RF_MAX_TRAIN_ROWS = 100_000


def _hgb_iterations(n_train: int) -> int:
    return 150 if n_train <= 200_000 else 80


def build_candidates(target_type: str, n_train: int, n_features: int, seed: int) -> list[tuple[str, object]]:
    if target_type == REGRESSION:
        candidates: list[tuple[str, object]] = [
            ("dummy_mean", DummyRegressor(strategy="mean")),
            ("ridge", make_pipeline(StandardScaler(), Ridge(alpha=1.0))),
        ]
        if n_train <= RF_MAX_TRAIN_ROWS:
            candidates.append(
                ("random_forest", RandomForestRegressor(n_estimators=200, n_jobs=-1, random_state=seed))
            )
        candidates.append(
            (
                "hist_gradient_boosting",
                HistGradientBoostingRegressor(
                    max_iter=_hgb_iterations(n_train), learning_rate=0.1, random_state=seed
                ),
            )
        )
        return candidates

    if target_type in (BINARY, MULTICLASS):
        candidates = [
            ("dummy_most_frequent", DummyClassifier(strategy="most_frequent")),
            ("logistic_regression", make_pipeline(StandardScaler(), LogisticRegression(max_iter=1000))),
        ]
        if n_train <= RF_MAX_TRAIN_ROWS:
            candidates.append(
                ("random_forest", RandomForestClassifier(n_estimators=200, n_jobs=-1, random_state=seed))
            )
        candidates.append(
            (
                "hist_gradient_boosting",
                HistGradientBoostingClassifier(
                    max_iter=_hgb_iterations(n_train), learning_rate=0.1, random_state=seed
                ),
            )
        )
        return candidates

    return []


def params_summary(model) -> dict:
    estimator = model
    if hasattr(model, "named_steps"):
        estimator = list(model.named_steps.values())[-1]
        summary = {"pipeline": [type(step).__name__ for step in model.named_steps.values()]}
    else:
        summary = {}
    name = type(estimator).__name__
    for key in (
        "alpha",
        "n_estimators",
        "max_depth",
        "max_iter",
        "learning_rate",
        "max_samples",
        "contamination",
        "random_state",
    ):
        if hasattr(estimator, key):
            summary[key] = getattr(estimator, key)
    summary["estimator"] = name
    return summary
