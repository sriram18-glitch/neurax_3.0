"""Target and event discovery.

Targets come only from artifacts that actually exist:

1. Responses of Phase 3 model inputs (with Phase 4 models attached when present).
2. Response-candidate / throughput columns in processed_data for tables that
   produced no model input (e.g. Model_3.csv station data).

Events are defined as distribution tails of the target (low / high quantile),
so the "event to explain" is always derived from the data, never configured.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pandas as pd

from ..pipeline.artifacts import sanitize_name
from .errors import RootCauseError

MIN_TARGET_ROWS = 100
MAX_TARGETS = 40
MAX_PROCESS_TARGETS = 6

TARGET_EXCLUDE = re.compile(r"^split$|_id$|^row$|^index$", re.I)


def _load_model_input(artifact_root: Path, name: str) -> pd.DataFrame | None:
    path = artifact_root / "model_inputs" / f"{sanitize_name(name)}.csv.gz"
    if not path.exists():
        return None
    return pd.read_csv(path)


def _load_processed(artifact_root: Path, name: str) -> pd.DataFrame | None:
    path = artifact_root / "processed_data" / f"{sanitize_name(name)}.csv.gz"
    if not path.exists():
        return None
    return pd.read_csv(path)


def _phase4_models(artifact_root: Path) -> list[dict]:
    path = artifact_root / "ml_summary.json"
    if not path.exists():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return [m for m in payload.get("models", []) if m.get("status") == "READY"]
    except Exception:  # noqa: BLE001 - absent/corrupt summary simply means no model contribution
        return []


def discover_targets(dataset_id: str, analysis: dict, artifact_root: Path) -> list[dict]:
    artifact_root = Path(artifact_root)
    targets: list[dict] = []
    seen: set[tuple[str, str]] = set()

    models = _phase4_models(artifact_root)
    models_by_key = {(m.get("input"), m.get("target")): m for m in models}

    for model_input in analysis.get("model_inputs", []):
        name = model_input.get("name")
        split = model_input.get("split") or {}
        if split.get("status") != "COMPUTED":
            continue
        frame = _load_model_input(artifact_root, name)
        if frame is None:
            continue
        for response in model_input.get("responses", []):
            if response not in frame.columns or TARGET_EXCLUDE.search(response):
                continue
            series = pd.to_numeric(frame[response], errors="coerce").dropna()
            if series.size < MIN_TARGET_ROWS or series.nunique() <= 1:
                continue
            key = (name, response)
            if key in seen:
                continue
            seen.add(key)
            model = models_by_key.get(key)
            targets.append(
                {
                    "target": response,
                    "input": name,
                    "mode": "model_input",
                    "rows": int(frame.shape[0]),
                    "rows_with_target": int(series.size),
                    "target_min": round(float(series.min()), 6),
                    "target_max": round(float(series.max()), 6),
                    "target_mean": round(float(series.mean()), 6),
                    "has_phase4_model": model is not None,
                    "model_id": (model or {}).get("model_id"),
                    "split_strategy": split.get("strategy"),
                    "source": f"model_inputs/{name}",
                }
            )

    # process-mode targets: response candidates in processed tables without model inputs
    model_input_names = {m.get("name") for m in analysis.get("model_inputs", [])}
    process_added = 0
    for table in analysis.get("tables", []):
        if process_added >= MAX_PROCESS_TARGETS:
            break
        name = table.get("name")
        if name in model_input_names:
            continue
        role_counts = table.get("role_counts", {})
        if role_counts.get("response_candidate", 0) == 0:
            continue
        frame = _load_processed(artifact_root, name)
        if frame is None:
            continue
        candidates = [c for c in frame.columns if c not in {m.get("target") for m in targets}]
        for candidate in candidates:
            if process_added >= MAX_PROCESS_TARGETS:
                break
            column = str(candidate)
            if TARGET_EXCLUDE.search(column) or not pd.api.types.is_numeric_dtype(frame[column]):
                continue
            series = pd.to_numeric(frame[column], errors="coerce").dropna()
            if series.size < MIN_TARGET_ROWS or series.nunique() <= 1:
                continue
            key = (name, column)
            if key in seen:
                continue
            seen.add(key)
            process_added += 1
            targets.append(
                {
                    "target": column,
                    "input": name,
                    "mode": "process_table",
                    "rows": int(frame.shape[0]),
                    "rows_with_target": int(series.size),
                    "target_min": round(float(series.min()), 6),
                    "target_max": round(float(series.max()), 6),
                    "target_mean": round(float(series.mean()), 6),
                    "has_phase4_model": False,
                    "model_id": None,
                    "split_strategy": None,
                    "source": f"processed_data/{name}",
                    "note": "No Phase 3/4 model exists for this table; model contribution will be unavailable.",
                }
            )

    targets.sort(key=lambda t: (t["mode"] != "model_input", t["input"] or "", t["target"]))
    return targets[:MAX_TARGETS]


def resolve_target(targets: list[dict], target: str, input_name: str | None = None) -> dict:
    matches = [t for t in targets if t["target"] == target]
    if input_name:
        matches = [t for t in matches if t["input"] == input_name]
    if not matches:
        raise RootCauseError(
            "TARGET_NOT_FOUND",
            f"Target '{target}' is not available for root-cause analysis in this dataset.",
            "Use GET /root-cause/targets to list available targets.",
        )
    model_matches = [t for t in matches if t["mode"] == "model_input"]
    return (model_matches or matches)[0]


def _truncated_flag(artifact_root: Path, folder: str, name: str) -> bool:
    manifest_file = artifact_root / folder / "manifest.json"
    if not manifest_file.exists():
        return False
    try:
        manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
        entry = manifest.get(name)
        return bool(entry and entry.get("truncated"))
    except Exception:  # noqa: BLE001
        return False


def load_target_frame(target: dict, artifact_root: Path) -> tuple[pd.DataFrame, bool, str]:
    """Load the richest available source frame for a target.

    For model-input targets the FULL cleaned process table (processed_data) is
    preferred over the narrower model_inputs artifact, because root-cause
    analysis must consider every process column - not only model predictors.
    Falls back to model_inputs when no matching processed table exists
    (e.g. fused MAT inputs). Returns (frame, truncated, artifact_used).
    """
    artifact_root = Path(artifact_root)
    if target["mode"] == "model_input":
        processed = _load_processed(artifact_root, target["input"])
        if processed is not None and target["target"] in processed.columns:
            return processed, _truncated_flag(artifact_root, "processed_data", target["input"]), "processed_data"
        frame = _load_model_input(artifact_root, target["input"])
        if frame is not None:
            return frame, _truncated_flag(artifact_root, "model_inputs", target["input"]), "model_inputs"
    else:
        frame = _load_processed(artifact_root, target["input"])
        if frame is not None:
            return frame, _truncated_flag(artifact_root, "processed_data", target["input"]), "processed_data"
    raise RootCauseError(
        "SOURCE_ARTIFACT_MISSING",
        f"Source data for target '{target['target']}' is no longer available.",
        f"Expected model_inputs or processed_data artifact for '{target['input']}'.",
    )


def define_event(frame: pd.DataFrame, target: str, direction: str, quantile: float) -> dict:
    if direction not in {"low", "high"}:
        raise RootCauseError("INVALID_DIRECTION", "Event direction must be 'low' or 'high'.")
    if not 0.01 <= quantile <= 0.4:
        raise RootCauseError("INVALID_QUANTILE", "Event quantile must be between 0.01 and 0.4.")

    series = pd.to_numeric(frame[target], errors="coerce")
    valid = series.dropna()
    if valid.size < MIN_TARGET_ROWS:
        raise RootCauseError(
            "INSUFFICIENT_DATA",
            f"Target '{target}' has only {valid.size} usable values; at least {MIN_TARGET_ROWS} are required.",
        )
    if direction == "low":
        threshold = float(valid.quantile(quantile))
        mask = (series <= threshold).to_numpy()
        definition = f"target <= {quantile:.0%} percentile ({threshold:.6g})"
    else:
        threshold = float(valid.quantile(1 - quantile))
        mask = (series >= threshold).to_numpy()
        definition = f"target >= {1 - quantile:.0%} percentile ({threshold:.6g})"

    return {
        "target": target,
        "direction": direction,
        "quantile": quantile,
        "threshold": round(threshold, 6),
        "definition": definition,
        "event_rows": int(mask.sum()),
        "non_event_rows": int((~mask).sum()),
        "mask": mask,
    }
