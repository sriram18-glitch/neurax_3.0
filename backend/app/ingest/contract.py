"""Dataset contract builder.

Combines ingestion + profiling into a single JSON-safe contract that tells the
rest of the system (and the UI) exactly what this dataset can and cannot
support. No capability is claimed unless evidence was detected.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path

from ..vision.discovery import profile_image_directory
from ..vision.service import vision_status
from .profiler import profile_ingest
from .readers import IngestResult, ingest_path

VISION_UNAVAILABLE_REASON = (
    "Uploaded dataset contains no image files or image-path columns. "
    "Vision inspection capability is unavailable for this dataset. "
    "Manufacturing simulation data does not itself provide visual inspection training data."
)


def _all_columns(profiles: list[dict]) -> list[dict]:
    out: list[dict] = []
    for profile in profiles:
        out.extend(profile["columns_detail"])
    return out


def build_contract(result: IngestResult, profiles: list[dict]) -> dict:
    columns = _all_columns(profiles)
    roles = {c["role"] for c in columns}
    quality_hits = [c["name"] for c in columns if re.search(r"defect|quality|pass|fail|reject|scrap|rework", c["name"], re.I)]
    label_like = [c["name"] for c in columns if re.search(r"defect|label|class|quality|pass|fail|reject", c["name"], re.I)]

    stations: dict[str, dict[str, list[str]]] = {}
    for profile in profiles:
        for station, metrics in profile["stations"].items():
            merged = stations.setdefault(station, {})
            for metric, cols in metrics.items():
                merged.setdefault(metric, [])
                for col in cols:
                    if col not in merged[metric]:
                        merged[metric].append(col)

    has_images = bool(result.image_files) or "image_reference" in roles
    has_process = "process_metric" in roles or bool(stations)
    has_inputs = "input_factor" in roles
    has_responses = bool({"response_candidate", "ml_variable"} & roles)
    has_time = "timestamp" in roles
    total_rows = sum(p["rows"] for p in profiles)
    max_numeric = max((p["numeric_columns"] for p in profiles), default=0)
    has_labels = bool(label_like) and any(
        c["unique"] <= 30 for c in columns if c["name"] in set(label_like)
    )

    capabilities = {
        "has_image_data": has_images,
        "has_defect_labels": has_labels,
        "has_quality_columns": bool(quality_hits),
        "has_process_data": has_process,
        "has_station_structure": bool(stations),
        "has_process_inputs": has_inputs,
        "has_response_variables": has_responses,
        "has_time_series": has_time,
        "supports_process_regression": bool(has_inputs and has_responses and total_rows >= 100),
        "supports_anomaly_detection": bool(max_numeric >= 2 and total_rows >= 100),
        "supports_vision": has_images,
    }

    primary = max(profiles, key=lambda p: p["rows"]) if profiles else None

    image_profile = None
    if result.extracted_root and Path(result.extracted_root).exists():
        candidate = profile_image_directory(Path(result.extracted_root))
        if candidate["image_count"] > 0:
            image_profile = candidate

    vision_block = vision_status(image_profile)
    vision_block["image_samples"] = result.image_files[:10]

    contract = {
        "dataset_id": result.sha256[:12],
        "filename": result.filename,
        "format": result.container,
        "size_bytes": result.size_bytes,
        "sha256": result.sha256,
        "status": "analyzed",
        "ingested_at": datetime.now(timezone.utc).isoformat(),
        "summary": {
            "tables": len(profiles),
            "total_rows": int(total_rows),
            "primary_table": primary["name"] if primary else None,
            "primary_rows": primary["rows"] if primary else 0,
            "primary_columns": primary["columns"] if primary else 0,
            "stations": sorted(stations.keys()),
            "station_metrics": {
                s: sorted(m.keys()) for s, m in sorted(stations.items())
            },
        },
        "capabilities": capabilities,
        "vision": {
            **vision_block,
        },
        "provenance": {
            "data_origin": "uploaded_dataset",
            "labels": ["REAL DATA"],
            "note": (
                "All figures derived from this dataset will be tagged as derived/model output. "
                "Simulations and recommendations are labeled separately in the UI."
            ),
        },
        "tables": profiles,
        "warnings": list(result.warnings),
        "skipped_files": result.skipped[:50],
    }
    return contract


def analyze_path(path: Path, extract_images_to: Path | None = None) -> dict:
    result = ingest_path(path, extract_images_to=extract_images_to)
    profiles = profile_ingest(result)
    has_rows = profiles and any(p["rows"] > 0 for p in profiles)
    if not has_rows:
        if result.image_files:
            return build_contract(result, profiles)
        from .errors import IngestError

        raise IngestError(
            "EMPTY_DATASET",
            f"'{path.name}' contains no data rows to analyze.",
            "The file has a header or structure but zero records. Upload a dataset with at least one data row.",
        )
    return build_contract(result, profiles)
