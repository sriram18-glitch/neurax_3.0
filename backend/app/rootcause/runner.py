"""Root-cause analysis runner.

Flow:
  resolve target -> load source artifact -> define event from the data ->
  analyse every available factor (correlation, MI, group difference, temporal,
  anomaly association, Phase 4 model contribution) -> transparent evidence
  score -> ranking -> station attribution -> drift scan -> persisted artifacts.

Every field is either computed from the data or explicitly marked unavailable.
Nothing is invented; association is never presented as causation.
"""

from __future__ import annotations

import hashlib
import json
import platform
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import scipy
import sklearn

from ..pipeline.artifacts import sanitize_name, write_json
from .drift import detect_drift
from .errors import RootCauseError
from .scoring import build_explanation, score_factor, status_for_score
from .signals import (
    anomaly_association_signal,
    correlation_signal,
    group_comparison_signal,
    mutual_information_signal,
    select_factors,
    temporal_signal,
)
from .targets import define_event, discover_targets, load_target_frame, resolve_target

ROOT_CAUSE_VERSION = "1.0.0"
DEFAULT_QUANTILE = 0.10
RANKED_FINDING_LIMIT = 25


def _versions() -> dict:
    return {
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "pandas": pd.__version__,
        "numpy": np.__version__,
        "scipy": scipy.__version__,
        "scikit_learn": sklearn.__version__,
        "root_cause_engine": ROOT_CAUSE_VERSION,
    }


def _analysis_id(dataset_id: str, target: str, direction: str, quantile: float, seed: int) -> str:
    digest = hashlib.sha256(
        f"{dataset_id}|{target}|{direction}|{quantile}|{seed}".encode("utf-8")
    ).hexdigest()
    return digest[:12]


def _order_column(frame: pd.DataFrame, profile_columns: list[dict]) -> tuple[str | None, str]:
    """Find a usable ordering column: monotonic timestamp, else a row-order proxy."""
    roles = {c["name"]: c.get("role") for c in profile_columns}
    for column in frame.columns:
        name = str(column)
        if roles.get(name) == "timestamp":
            series = pd.to_numeric(frame[name], errors="coerce")
            if series.notna().sum() >= 500:
                if series.is_monotonic_increasing:
                    return name, "monotonic_timestamp"
                return name, "timestamp_present_not_monotonic"
    return None, "no_timestamp_column"


def _station_lookup(profile: dict) -> tuple[dict[str, str], dict[str, dict]]:
    """column -> station, and station -> sources, from the profiled columns."""
    roles = {c["name"]: c for c in profile.get("columns_detail", [])}
    column_to_station: dict[str, str] = {}
    for column, info in roles.items():
        if info.get("station") and info.get("metric"):
            column_to_station[column] = info["station"]
    return column_to_station, roles


def _model_importance(dataset_id: str, model_id: str | None, models_dir: Path) -> tuple[dict[str, float], dict | None]:
    if not model_id:
        return {}, None
    path = Path(models_dir) / dataset_id / model_id / "feature_importance.json"
    if not path.exists():
        return {}, None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {}, None
    values = {entry["feature"]: float(entry["importance"]) for entry in payload.get("top_features", [])}
    return values, {
        "method": payload.get("method"),
        "label": payload.get("label"),
        "note": payload.get("note"),
        "source": str(path),
    }


def run_root_cause(
    dataset_id: str,
    target_name: str,
    direction: str,
    quantile: float,
    analysis: dict,
    artifact_root: Path,
    models_dir: Path,
    input_name: str | None = None,
    seed: int = 42,
) -> dict:
    started = time.time()
    artifact_root = Path(artifact_root)
    rca_dir = artifact_root / "root_cause"
    rca_dir.mkdir(parents=True, exist_ok=True)

    try:
        targets = discover_targets(dataset_id, analysis, artifact_root)
        target = resolve_target(targets, target_name, input_name)
        frame, truncated, artifact_used = load_target_frame(target, artifact_root)
        if target["target"] not in frame.columns:
            raise RootCauseError("TARGET_COLUMN_MISSING", f"Target column '{target['target']}' is missing from the source artifact.")

        event = define_event(frame, target["target"], direction, quantile)
        event_mask = event.pop("mask")

        responses = [t["target"] for t in targets if t["input"] == target["input"]]
        factors, excluded = select_factors(frame, target["target"], responses)

        profile_path = artifact_root / "profile.json"
        profile_columns: list[dict] = []
        if profile_path.exists():
            try:
                profile = json.loads(profile_path.read_text(encoding="utf-8"))
                for table in profile.get("tables", []):
                    if table.get("name") == target["input"] or table.get("source_file", "").endswith(target["input"] + ".csv"):
                        profile_columns = table.get("columns_detail", [])
                        break
                if not profile_columns and profile.get("tables"):
                    profile_columns = profile["tables"][0].get("columns_detail", [])
            except Exception:  # noqa: BLE001
                profile_columns = []
        column_to_station, _ = _station_lookup({"columns_detail": profile_columns})

        order_column, ordering_note = _order_column(frame, profile_columns)

        importance_values, importance_meta = _model_importance(dataset_id, target.get("model_id"), models_dir)
        max_importance = max(importance_values.values()) if importance_values else None

        anomaly_columns = [
            column
            for column in frame.columns
            if str(column).startswith("anomaly_") or str(column) in {"anomaly_state", "anomaly_score"}
        ]

        y = pd.to_numeric(frame[target["target"]], errors="coerce").to_numpy(dtype="float64")
        order_values = (
            pd.to_numeric(frame[order_column], errors="coerce").to_numpy(dtype="float64")
            if order_column
            else np.arange(len(frame), dtype="float64")
        )

        findings: list[dict] = []
        for factor in factors:
            x = pd.to_numeric(frame[factor], errors="coerce").to_numpy(dtype="float64")
            correlation = correlation_signal(x, y, seed)
            mutual_info = mutual_information_signal(x, y, seed)
            group = group_comparison_signal(x, event_mask)
            temporal = (
                temporal_signal(x, y, order_values, event_mask, seed)
                if order_column
                else {
                    "available": False,
                    "reason": "TEMPORAL_CAUSAL_ORDERING = NOT_AVAILABLE_FROM_DATASET (no ordering column)",
                }
            )
            anomaly = anomaly_association_signal(frame, factor, event_mask, anomaly_columns)
            importance_value = importance_values.get(factor)
            score = score_factor(correlation, mutual_info, group, temporal, anomaly, importance_value, max_importance)
            station = column_to_station.get(factor)
            explanation = build_explanation(factor, target["target"], event, {
                "correlation": correlation,
                "group_difference": group,
                "temporal": temporal,
                "anomaly": anomaly,
            }, score, station)

            findings.append(
                {
                    "factor": factor,
                    "station": station,
                    "evidence": {
                        "correlation": correlation,
                        "mutual_information": mutual_info,
                        "group_difference": group,
                        "temporal": temporal,
                        "anomaly": anomaly,
                        "model_contribution": {
                            "available": importance_value is not None,
                            "importance": importance_value,
                            "max_importance": max_importance,
                            "method": (importance_meta or {}).get("method"),
                            "label": "MODEL CONTRIBUTION",
                            "reason": None
                            if importance_value is not None
                            else "feature is not among the saved top features for this model",
                        },
                    },
                    "evidence_score": score["score"],
                    "score_status": score["status"],
                    "score_components": score["components"],
                    "score_weights": score["weights"],
                    "score_formula": score["formula"],
                    "association_status": status_for_score(score["score"]),
                    "epistemic_status": "STATISTICAL ASSOCIATION + MODEL CONTRIBUTION (hypothesis, not causation)",
                    "explanation": explanation,
                    "source_columns": [factor, target["target"]],
                    "limitations": [
                        "Association does not establish causation.",
                        "No interventional or counterfactual methodology was applied.",
                    ],
                }
            )

        findings.sort(key=lambda f: (f["evidence_score"] is None, -(f["evidence_score"] or 0.0)))
        for rank, finding in enumerate(findings, start=1):
            finding["rank"] = rank
        ranked = findings[:RANKED_FINDING_LIMIT]
        insufficient = [f for f in findings if f["evidence_score"] is None]

        # station-level summary for factors that map to stations
        station_summary: dict[str, dict] = {}
        for finding in findings:
            station = finding.get("station")
            if not station:
                continue
            entry = station_summary.setdefault(
                station,
                {"station": station, "factors": 0, "best_score": None, "best_factor": None, "ranked_factors": []},
            )
            entry["factors"] += 1
            score_value = finding["evidence_score"]
            if score_value is not None and (entry["best_score"] is None or score_value > entry["best_score"]):
                entry["best_score"] = score_value
                entry["best_factor"] = finding["factor"]
            if len(entry["ranked_factors"]) < 5:
                entry["ranked_factors"].append(
                    {"factor": finding["factor"], "score": score_value, "rank": finding["rank"]}
                )
        station_ranking = sorted(
            station_summary.values(),
            key=lambda entry: (entry["best_score"] is None, -(entry["best_score"] or 0.0)),
        )

        drift_columns = factors[:25]
        drift = detect_drift(frame, order_column, drift_columns)

        # station metrics reuse from Phase 3 artifacts when the source table matches
        station_metrics = None
        station_metrics_path = artifact_root / "station_metrics.json"
        if station_metrics_path.exists():
            try:
                payload = json.loads(station_metrics_path.read_text(encoding="utf-8"))
                for table in payload.get("tables", []):
                    if table.get("table") == target["input"]:
                        station_metrics = table
                        break
            except Exception:  # noqa: BLE001
                station_metrics = None

        analysis_id = _analysis_id(dataset_id, target["target"], direction, quantile, seed)
        payload = {
            "dataset_id": dataset_id,
            "analysis_id": analysis_id,
            "target": target,
            "event": event,
            "status": "complete",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "engine_version": ROOT_CAUSE_VERSION,
            "seed": seed,
            "configuration": {
                "direction": direction,
                "quantile": quantile,
                "ranked_finding_limit": RANKED_FINDING_LIMIT,
                "scoring_weights": findings[0]["score_weights"] if findings else None,
                "scoring_formula": findings[0]["score_formula"] if findings else None,
            },
            "source": {
                "artifact": target["source"],
                "artifact_used": artifact_used,
                "rows": int(frame.shape[0]),
                "rows_with_target": target["rows_with_target"],
                "artifact_truncated": truncated,
                "sampling_note": "Signals use capped sampling where recorded per component (see sampled flags).",
            },
            "ordering": {"column": order_column, "note": ordering_note},
            "factors_analyzed": len(findings),
            "factors_excluded": excluded[:30],
            "ranked_findings": ranked,
            "insufficient_evidence_factors": [f["factor"] for f in insufficient][:30],
            "station_ranking": station_ranking,
            "station_metrics": station_metrics,
            "drift": drift,
            "model_contribution_source": importance_meta,
            "epistemic_summary": {
                "observed_data": "Source columns and event definition computed directly from the artifact.",
                "model_contribution": "Phase 4 model feature importance, reused unchanged.",
                "statistical_association": "Correlation, mutual information, group comparison, anomaly enrichment.",
                "hypothesis": "Ranked candidate contributing factors - not confirmed causes.",
                "causal_claim": "NOT SUPPORTED: no interventional methodology was applied.",
            },
            "limitations": [
                "All findings are associations within this dataset, not proven causes.",
                "Temporal ordering, when present, is record order - not guaranteed wall-clock causality.",
                "Anomaly enrichment reuses Phase 4 IsolationForest states and inherits its limitations.",
                "Drift detection requires an ordering column and sufficient rows.",
            ],
            "versions": _versions(),
            "total_duration_s": round(time.time() - started, 3),
        }

        write_json(rca_dir / "findings" / f"{analysis_id}.json", payload)
        write_json(rca_dir / "metadata.json", {
            "dataset_id": dataset_id,
            "engine_version": ROOT_CAUSE_VERSION,
            "last_analysis_id": analysis_id,
            "last_target": target["target"],
            "generated_at": payload["generated_at"],
            "versions": payload["versions"],
        })
        _update_registry(rca_dir, payload)
        return payload

    except RootCauseError as exc:
        return {
            "dataset_id": dataset_id,
            "status": "failed",
            "error": exc.to_dict(),
            "total_duration_s": round(time.time() - started, 3),
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "dataset_id": dataset_id,
            "status": "failed",
            "error": {
                "error": True,
                "code": "ROOT_CAUSE_FAILURE",
                "message": "Root-cause analysis failed unexpectedly.",
                "detail": str(exc),
            },
            "total_duration_s": round(time.time() - started, 3),
        }


def _update_registry(rca_dir: Path, payload: dict) -> None:
    registry_path = rca_dir / "analysis_registry.json"
    registry: list[dict] = []
    if registry_path.exists():
        try:
            registry = json.loads(registry_path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            registry = []
    registry = [entry for entry in registry if entry.get("analysis_id") != payload["analysis_id"]]
    registry.append(
        {
            "analysis_id": payload["analysis_id"],
            "target": payload["target"]["target"],
            "direction": payload["event"]["direction"],
            "quantile": payload["event"]["quantile"],
            "generated_at": payload["generated_at"],
            "factors_analyzed": payload["factors_analyzed"],
            "top_factor": (payload["ranked_findings"][0]["factor"] if payload["ranked_findings"] else None),
            "top_score": (payload["ranked_findings"][0]["evidence_score"] if payload["ranked_findings"] else None),
        }
    )
    write_json(registry_path, registry)


def list_analyses(rca_dir: Path) -> list[dict]:
    registry_path = Path(rca_dir) / "analysis_registry.json"
    if not registry_path.exists():
        return []
    try:
        return json.loads(registry_path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return []


def get_analysis(rca_dir: Path, analysis_id: str) -> dict | None:
    path = Path(rca_dir) / "findings" / f"{analysis_id}.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return None
