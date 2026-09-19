"""Pipeline runner.

RAW -> VALIDATION -> CLEANING -> TYPED FRAMES -> FEATURE ENGINEERING ->
LEAKAGE-SAFE SPLIT -> STATION AGGREGATION -> ARTIFACTS.

The same dataset + same configuration (seed) produces reproducible results.
Every stage records timing and status; failures are contained and reported
without leaking internals to the UI.
"""

from __future__ import annotations

import platform
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import scipy
import sklearn

from ..core.settings import ARTIFACT_FULL_ROW_CAP, RANDOM_SEED
from .artifacts import sanitize_name, write_frame_gz, write_json
from .clean import clean_table
from .coverage import build_coverage
from .errors import PipelineError
from .features import build_features
from .model_inputs import ModelInput, build_model_inputs
from .split import UNSPLIT, compute_split
from .stations import build_station_metrics


def _versions() -> dict:
    return {
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "pandas": pd.__version__,
        "numpy": np.__version__,
        "scipy": scipy.__version__,
        "scikit_learn": sklearn.__version__,
    }


def _role_names(profile: dict, role: str) -> list[str]:
    return [c["name"] for c in profile["columns_detail"] if c["role"] == role]


def _roles_map(profile: dict) -> dict[str, dict]:
    return {c["name"]: c for c in profile.get("columns_detail", [])}


def _split_table(
    table_name: str,
    frame: pd.DataFrame,
    profile: dict,
    seed: int,
) -> tuple[dict[str, np.ndarray], dict]:
    time_candidates = [str(c) for c in frame.columns if _roles_map(profile).get(str(c), {}).get("role") == "timestamp"]
    group_candidates = [str(c) for c in frame.columns if _roles_map(profile).get(str(c), {}).get("role") == "input_factor"]
    assignments, meta = compute_split(frame, group_candidates, time_candidates, seed=seed, name=table_name)
    splits = {
        name: np.where(assignments == name)[0]
        for name in ("train", "validation", "test", UNSPLIT)
    }
    return splits, meta


def run_pipeline(dataset_id: str, filename: str, contract: dict, ingest, artifacts_root: Path, seed: int = RANDOM_SEED) -> dict:
    """Execute the full Phase 3 pipeline and persist artifacts.

    Returns a JSON-safe analysis payload. Never raises for data problems:
    returns status="failed" with a structured error instead.
    """
    started = time.time()
    artifact_dir = Path(artifacts_root) / dataset_id
    artifact_dir.mkdir(parents=True, exist_ok=True)

    stages: list[dict] = []

    def stage(name: str, label: str):
        class _Stage:
            def __enter__(self_inner):
                self_inner.t0 = time.time()
                return self_inner

            def __exit__(self_inner, exc_type, exc, tb):
                duration = time.time() - self_inner.t0
                stages.append(
                    {
                        "id": name,
                        "label": label,
                        "status": "failed" if exc_type else "complete",
                        "duration_s": round(duration, 3),
                        "detail": None if exc_type is None else str(exc),
                    }
                )
                return False

        return _Stage()

    try:
        profiles_by_name = {p["name"]: p for p in contract["tables"]}

        with stage("validation", "Dataset validation"):
            if ingest is None:
                raise PipelineError("NO_INGEST", "No ingestion result is available for this dataset session.")
            if contract.get("status") != "analyzed":
                raise PipelineError("NOT_ANALYZED", "Dataset contract is not in 'analyzed' state.")
            if not getattr(ingest, "tables", None):
                analysis = {
                    "dataset_id": dataset_id,
                    "filename": filename,
                    "status": "complete",
                    "error": None,
                    "generated_at": datetime.now(timezone.utc).isoformat(),
                    "processing": {"seed": seed, "configuration": {}, "versions": _versions()},
                    "stages": stages,
                    "total_duration_s": round(time.time() - started, 3),
                    "coverage": {
                        "modules": {
                            "data_ingestion": {"status": "SUPPORTED", "reason": "File ingested and validated."},
                            "process_analysis": {
                                "status": "NOT_SUPPORTED",
                                "reason": "This dataset contains no tabular data; process analysis is not applicable.",
                            },
                        }
                    },
                    "tables": [],
                    "cleaning": {"dataset_id": dataset_id, "tables": []},
                    "features": {"derived_features": [], "skipped_candidates": []},
                    "model_inputs": [],
                    "rejected_model_inputs": [],
                    "splits": {"model_input_splits": [], "table_splits": []},
                    "station_metrics": {"tables": []},
                    "note": "No tabular data in this dataset. Process pipeline skipped; see the vision profile for image data.",
                }
                artifact_dir.mkdir(parents=True, exist_ok=True)
                write_json(artifact_dir / "analysis.json", analysis)
                return analysis

        with stage("cleaning", "Cleaning & validation"):
            clean_frames: dict[str, pd.DataFrame] = {}
            clean_reports: list[dict] = []
            for table in ingest.tables:
                profile = profiles_by_name.get(table.name)
                if profile is None:
                    continue
                cleaned, report = clean_table(table.name, table.frame, profile)
                clean_frames[table.name] = cleaned
                clean_reports.append(report)

        with stage("feature_engineering", "Feature engineering"):
            feature_frames: dict[str, pd.DataFrame] = {}
            derived_features: list[dict] = []
            skipped_features: list[dict] = []
            for name, frame in clean_frames.items():
                featured, derived, skipped = build_features(name, frame, profiles_by_name[name])
                feature_frames[name] = featured
                derived_features.extend(derived)
                skipped_features.extend(skipped)

        with stage("model_inputs", "Model input preparation"):
            model_inputs, rejected_inputs = build_model_inputs(feature_frames, profiles_by_name)
            for model_input in model_inputs:
                time_candidates = [
                    str(c)
                    for c in model_input.frame.columns
                    if _roles_map(profiles_by_name.get(model_input.name, {})).get(str(c), {}).get("role") == "timestamp"
                ]
                group_candidates = model_input.input_factors or model_input.predictors
                assignments, split_meta = compute_split(
                    model_input.frame,
                    group_candidates,
                    time_candidates,
                    seed=seed,
                    name=model_input.name,
                )
                model_input.split_meta = split_meta

        with stage("splitting", "Leakage-safe splitting"):
            table_splits: dict[str, dict] = {}
            split_metadata: list[dict] = []
            for name, frame in feature_frames.items():
                splits, meta = _split_table(name, frame, profiles_by_name[name], seed)
                table_splits[name] = splits
                split_metadata.append(meta)

        with stage("station_aggregation", "Station aggregation"):
            station_metrics: list[dict] = []
            primary_name = contract["summary"].get("primary_table")
            if primary_name in feature_frames:
                station_metrics.append(
                    build_station_metrics(primary_name, feature_frames[primary_name], profiles_by_name[primary_name])
                )
            for name, frame in feature_frames.items():
                if name == primary_name:
                    continue
                metrics = build_station_metrics(name, frame, profiles_by_name[name])
                if metrics["station_count"] > 0:
                    station_metrics.append(metrics)
            if not station_metrics:
                station_metrics.append(build_station_metrics(None, None, None))
            primary_station_metrics = station_metrics[0]

        with stage("artifacts", "Artifact generation"):
            schema = {
                "dataset_id": dataset_id,
                "tables": [
                    {
                        "name": p["name"],
                        "source_file": p["source_file"],
                        "rows": p["rows"],
                        "columns": p["columns"],
                        "role_counts": p["role_counts"],
                        "stations": sorted(p["stations"].keys()),
                    }
                    for p in contract["tables"]
                ],
            }
            feature_metadata = {
                "dataset_id": dataset_id,
                "derived_features": derived_features,
                "skipped_candidates": skipped_features,
                "note": "Derived features exist only where their source columns were detected.",
            }
            split_payload = {
                "dataset_id": dataset_id,
                "seed": seed,
                "model_input_splits": [mi.summary() for mi in model_inputs],
                "table_splits": split_metadata,
            }
            cleaning_report = {"dataset_id": dataset_id, "tables": clean_reports}
            station_payload = {"dataset_id": dataset_id, "tables": station_metrics}
            coverage = build_coverage(contract, primary_station_metrics, model_inputs, rejected_inputs)

            analysis = {
                "dataset_id": dataset_id,
                "filename": filename,
                "status": "complete",
                "error": None,
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "processing": {
                    "seed": seed,
                    "configuration": {
                        "artifact_row_cap": ARTIFACT_FULL_ROW_CAP,
                        "utilization_normalization": "percent-to-ratio when median>1 and max<=100",
                        "split": "chronological > sequential > grouped > seeded random",
                        "imputation": "median (predictors only, after response-complete row filtering)",
                    },
                    "versions": _versions(),
                },
                "stages": stages,
                "total_duration_s": round(time.time() - started, 3),
                "coverage": coverage,
                "tables": [
                    {
                        "name": p["name"],
                        "rows": p["rows"],
                        "columns": p["columns"],
                        "role_counts": p["role_counts"],
                        "stations": sorted(p["stations"].keys()),
                        "warnings": p["warnings"],
                    }
                    for p in contract["tables"]
                ],
                "cleaning": cleaning_report,
                "features": feature_metadata,
                "model_inputs": [mi.summary() for mi in model_inputs],
                "rejected_model_inputs": rejected_inputs,
                "splits": split_payload,
                "station_metrics": station_payload,
            }

            write_json(artifact_dir / "profile.json", contract)
            write_json(artifact_dir / "schema.json", schema)
            write_json(artifact_dir / "cleaning_report.json", cleaning_report)
            write_json(artifact_dir / "feature_metadata.json", feature_metadata)
            write_json(artifact_dir / "split_metadata.json", split_payload)
            write_json(artifact_dir / "station_metrics.json", station_payload)
            write_json(artifact_dir / "coverage.json", coverage)
            write_json(artifact_dir / "analysis.json", analysis)
            write_json(
                artifact_dir / "reproducibility.json",
                {
                    "dataset_id": dataset_id,
                    "filename": filename,
                    "sha256": contract.get("sha256"),
                    "ingested_at": contract.get("ingested_at"),
                    "processed_at": analysis["generated_at"],
                    "seed": seed,
                    "versions": analysis["processing"]["versions"],
                },
            )

            processed_artifacts = {}
            for name, frame in feature_frames.items():
                processed_artifacts[name] = write_frame_gz(
                    artifact_dir / "processed_data" / f"{sanitize_name(name)}.csv.gz", frame, ARTIFACT_FULL_ROW_CAP
                )
            model_artifacts = []
            for model_input in model_inputs:
                frame = model_input.frame.copy()
                assignments = np.full(len(frame), UNSPLIT, dtype=object)
                if model_input.split_meta and model_input.split_meta.get("status") == "COMPUTED":
                    time_candidates = []
                    group_candidates = model_input.input_factors or model_input.predictors
                    assignments, _ = compute_split(
                        frame, group_candidates, time_candidates, seed=seed, name=model_input.name
                    )
                frame.insert(0, "split", assignments)
                meta = write_frame_gz(
                    artifact_dir / "model_inputs" / f"{sanitize_name(model_input.name)}.csv.gz",
                    frame,
                    None,
                )
                model_artifacts.append(meta)
            write_json(artifact_dir / "processed_data" / "manifest.json", processed_artifacts)
            write_json(artifact_dir / "model_inputs" / "manifest.json", model_artifacts)

            analysis["artifacts"] = {
                "root": str(artifact_dir),
                "files": sorted(p.name for p in artifact_dir.iterdir() if p.is_file()),
                "processed_tables": processed_artifacts,
                "model_input_files": model_artifacts,
                "note": "model_inputs artifacts are stored in full (no row cap) because Phase 4 trains on them; processed_data artifacts may be capped.",
            }

        return analysis

    except PipelineError as exc:
        return {
            "dataset_id": dataset_id,
            "filename": filename,
            "status": "failed",
            "error": exc.to_dict(),
            "stages": stages,
            "total_duration_s": round(time.time() - started, 3),
        }
    except Exception as exc:  # noqa: BLE001 - contain everything, report safely
        return {
            "dataset_id": dataset_id,
            "filename": filename,
            "status": "failed",
            "error": {
                "error": True,
                "code": "PROCESSING_FAILURE",
                "message": "Pipeline processing failed unexpectedly.",
                "detail": str(exc),
            },
            "stages": stages,
            "total_duration_s": round(time.time() - started, 3),
        }
