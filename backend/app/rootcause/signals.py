"""Factor analysis signals.

Each signal is computed only when its inputs actually exist. Unavailable
signals are recorded as {"available": false, "reason": ...} - never guessed.

Signals:
- correlation (Pearson + Spearman)
- mutual information (nonlinear dependence)
- group comparison (event vs non-event standardised mean difference)
- temporal evidence (change-point timing relative to the event, requires order)
- anomaly association (event enrichment among Phase 4 anomaly rows)
- model contribution (Phase 4 importance, when a model exists)
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats
from sklearn.feature_selection import mutual_info_regression

CORRELATION_SAMPLE_CAP = 50_000
MI_SAMPLE_CAP = 20_000
CHANGEPOINT_SAMPLE_CAP = 50_000
MAX_FACTORS = 60

EXCLUDE_COLUMNS = {
    "split",
    "row",
    "index",
}
EXCLUDE_PATTERN = ("_id",)


def select_factors(frame: pd.DataFrame, target: str, responses: list[str]) -> tuple[list[str], list[str]]:
    """Numeric factors excluding the target, other responses, ids and splits."""
    excluded = {target, *responses} | EXCLUDE_COLUMNS
    factors: list[str] = []
    excluded_names: list[str] = []
    for column in frame.columns:
        name = str(column)
        if name in excluded or any(token in name.lower() for token in EXCLUDE_PATTERN):
            excluded_names.append(name)
            continue
        if not pd.api.types.is_numeric_dtype(frame[column]):
            excluded_names.append(name)
            continue
        if frame[column].nunique(dropna=True) <= 1:
            excluded_names.append(name)
            continue
        factors.append(name)
    return factors[:MAX_FACTORS], excluded_names


def _sample_mask(n: int, cap: int, seed: int) -> tuple[np.ndarray, bool]:
    if n <= cap:
        return np.arange(n), False
    rng = np.random.default_rng(seed)
    return np.sort(rng.choice(n, size=cap, replace=False)), True


def correlation_signal(x: np.ndarray, y: np.ndarray, seed: int = 42) -> dict:
    mask = np.isfinite(x) & np.isfinite(y)
    x_clean, y_clean = x[mask], y[mask]
    n = int(x_clean.size)
    if n < 30 or np.ptp(x_clean) == 0 or np.ptp(y_clean) == 0:
        return {"available": False, "reason": "insufficient variation or samples for correlation"}
    idx, sampled = _sample_mask(n, CORRELATION_SAMPLE_CAP, seed)
    x_use, y_use = x_clean[idx], y_clean[idx]
    pearson_r, pearson_p = stats.pearsonr(x_use, y_use)
    spearman_r, spearman_p = stats.spearmanr(x_use, y_use)
    return {
        "available": True,
        "pearson_r": round(float(pearson_r), 6),
        "pearson_p": round(float(pearson_p), 8),
        "spearman_r": round(float(spearman_r), 6),
        "spearman_p": round(float(spearman_p), 8),
        "n": n,
        "sampled": sampled,
    }


def mutual_information_signal(x: np.ndarray, y: np.ndarray, seed: int = 42) -> dict:
    mask = np.isfinite(x) & np.isfinite(y)
    x_clean, y_clean = x[mask], y[mask]
    n = int(x_clean.size)
    if n < 30 or np.ptp(x_clean) == 0 or np.ptp(y_clean) == 0:
        return {"available": False, "reason": "insufficient variation or samples for mutual information"}
    idx, sampled = _sample_mask(n, MI_SAMPLE_CAP, seed)
    x_use = x_clean[idx].reshape(-1, 1)
    y_use = y_clean[idx]
    value = mutual_info_regression(x_use, y_use, random_state=seed)[0]
    baseline = mutual_info_regression(x_use, np.random.default_rng(seed).permutation(y_use), random_state=seed)[0]
    return {
        "available": True,
        "mi": round(float(value), 6),
        "mi_permutation_baseline": round(float(baseline), 6),
        "n": n,
        "sampled": sampled,
        "note": "Mutual information on a single feature; compare against the permutation baseline.",
    }


def group_comparison_signal(x: np.ndarray, mask: np.ndarray) -> dict:
    valid = np.isfinite(x)
    event_values = x[valid & mask]
    other_values = x[valid & ~mask]
    if event_values.size < 10 or other_values.size < 10:
        return {"available": False, "reason": "fewer than 10 samples in one of the groups"}
    event_mean = float(event_values.mean())
    other_mean = float(other_values.mean())
    pooled = float(np.sqrt((event_values.var(ddof=1) + other_values.var(ddof=1)) / 2)) or 0.0
    effect = (event_mean - other_mean) / pooled if pooled > 0 else 0.0
    try:
        u_stat, p_value = stats.mannwhitneyu(event_values, other_values, alternative="two-sided")
    except ValueError:
        p_value = float("nan")
    return {
        "available": True,
        "event_mean": round(event_mean, 6),
        "non_event_mean": round(other_mean, 6),
        "difference": round(event_mean - other_mean, 6),
        "standardized_effect": round(float(effect), 6),
        "mannwhitney_p": round(float(p_value), 8) if np.isfinite(p_value) else None,
        "event_n": int(event_values.size),
        "non_event_n": int(other_values.size),
    }


def temporal_signal(
    x: np.ndarray,
    y: np.ndarray,
    order: np.ndarray,
    target_event_mask: np.ndarray,
    seed: int = 42,
) -> dict:
    """Change-point evidence: when did the factor shift relative to the event?

    Requires a usable ordering column (passed in by the runner). Uses a
    two-sample split scan over ordered samples and compares the detected
    factor shift position with the first sustained event onset.
    """
    valid = np.isfinite(x) & np.isfinite(y) & np.isfinite(order)
    x_clean, y_clean, order_clean = x[valid], y[valid], order[valid]
    mask_clean = target_event_mask[valid]
    n = int(x_clean.size)
    if n < 200:
        return {"available": False, "reason": "fewer than 200 ordered samples for change-point analysis"}

    idx, sampled = _sample_mask(n, CHANGEPOINT_SAMPLE_CAP, seed)
    order_use = order_clean[idx]
    sort_idx = np.argsort(order_use, kind="stable")
    x_sorted = x_clean[idx][sort_idx]
    y_sorted = y_clean[idx][sort_idx]
    mask_sorted = mask_clean[idx][sort_idx]

    # cumulative-sum based change-point score on the factor (standardised)
    xz = (x_sorted - x_sorted.mean()) / (x_sorted.std() or 1.0)
    cusum = np.cumsum(xz - xz.mean())
    change_position = int(np.argmax(np.abs(cusum)))

    # first sustained event onset (run of >= 5 event samples)
    onset_position = None
    run = 0
    for position, flag in enumerate(mask_sorted):
        run = run + 1 if flag else 0
        if run >= 5:
            onset_position = position - 4
            break

    # persistence: factor-target relationship within event rows only
    event_x = x_sorted[mask_sorted]
    event_y = y_sorted[mask_sorted]
    persistence = None
    if event_x.size >= 30 and np.ptp(event_x) > 0 and np.ptp(event_y) > 0:
        persistence = float(np.corrcoef(event_x, event_y)[0, 1])

    precedes = None
    if onset_position is not None:
        precedes = bool(change_position <= onset_position)

    return {
        "available": True,
        "change_position": change_position,
        "event_onset_position": onset_position,
        "factor_shift_precedes_event_onset": precedes,
        "persistence_corr_within_events": round(persistence, 6) if persistence is not None else None,
        "n": n,
        "sampled": sampled,
        "note": "Ordering-based change-point scan; temporal ordering is not proof of causation.",
    }


def anomaly_association_signal(
    frame: pd.DataFrame,
    factor: str,
    event_mask: np.ndarray,
    anomaly_columns: list[str],
) -> dict:
    """Event enrichment among Phase 4 anomaly-flagged rows, when available."""
    if not anomaly_columns:
        return {"available": False, "reason": "no anomaly columns present in the source artifact"}
    usable = [c for c in anomaly_columns if c in frame.columns]
    if not usable:
        return {"available": False, "reason": "anomaly columns present but none usable"}
    states = frame[usable[0]].astype(str).to_numpy()
    anomaly_mask = states == "ANOMALOUS"
    if anomaly_mask.sum() < 5:
        return {
            "available": False,
            "reason": "fewer than 5 anomaly-flagged rows in this artifact",
            "anomaly_rows": int(anomaly_mask.sum()),
        }
    event_rate = float(event_mask.mean())
    rate_in_anomalies = float(event_mask[anomaly_mask].mean())
    return {
        "available": True,
        "source_column": usable[0],
        "anomaly_rows": int(anomaly_mask.sum()),
        "event_rate_overall": round(event_rate, 6),
        "event_rate_in_anomalies": round(rate_in_anomalies, 6),
        "enrichment": round(rate_in_anomalies / event_rate, 6) if event_rate > 0 else None,
        "note": "Anomaly rows are unusual in process feature space; enrichment is an association, not a cause.",
    }
