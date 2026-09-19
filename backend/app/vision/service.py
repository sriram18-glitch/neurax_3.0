"""Vision service.

The honest contract for the current phase:

- `vision_status()` always reports the true state of the uploaded dataset.
- When no image data exists, every capability endpoint returns NOT_SUPPORTED
  with the precise reason and the requirements needed to implement it.
- When image data exists, the profiler reports what was actually found.

No predictions, confidences, heatmaps or metrics are produced unless a real
image dataset has been profiled. There is no placeholder output.
"""

from __future__ import annotations

from pathlib import Path

from .discovery import profile_image_directory
from .requirements import REQUIREMENTS, VISION_UNAVAILABLE_REASON

STATUS_NOT_SUPPORTED = "NOT_SUPPORTED"


def profile_dataset_images(extracted_root: Path | None, contract_vision: dict) -> dict:
    """Profile images for an ingested dataset.

    `extracted_root` points at a directory where archive contents were
    extracted (when the upload was a ZIP). For non-archive uploads it is None
    and only the contract-level vision block is consulted.
    """
    if extracted_root is not None and Path(extracted_root).exists():
        profile = profile_image_directory(Path(extracted_root))
        if profile["image_count"] > 0:
            return profile
    return {
        "root": str(extracted_root) if extracted_root else None,
        "image_count": int(contract_vision.get("images_found", 0)),
        "formats": {},
        "dimensions": None,
        "class_structure": {"folders": [], "per_class": {}, "normal_count": 0, "defect_count": 0},
        "annotations": None,
        "splits_present": None,
        "suitability": {},
        "notes": [VISION_UNAVAILABLE_REASON],
    }


def vision_status(profile: dict | None) -> dict:
    if profile and profile.get("image_count", 0) > 0:
        assessment = profile.get("suitability", {})
        supported = [name for name, verdict in assessment.items() if verdict.get("supported") is True]
        return {
            "status": "PROFILED" if supported else "PROFILED_NO_SUPPORTED_CAPABILITY",
            "available": True,
            "images_found": profile.get("image_count", 0),
            "supported_capabilities": supported,
            "reason": None
            if supported
            else "Images were found but their structure does not yet support any vision capability.",
            "requirements": REQUIREMENTS,
            "profile": profile,
        }
    return {
        "status": STATUS_NOT_SUPPORTED,
        "available": False,
        "images_found": 0,
        "supported_capabilities": [],
        "reason": VISION_UNAVAILABLE_REASON,
        "requirements": REQUIREMENTS,
        "profile": None,
    }


def inference_status() -> dict:
    """Inference is unavailable until a real vision model is trained from a
    real image dataset. This endpoint deliberately returns no prediction."""
    return {
        "status": STATUS_NOT_SUPPORTED,
        "reason": VISION_UNAVAILABLE_REASON,
        "message": "Image inference is not implemented because no vision model has been trained on real image data.",
        "requirements": REQUIREMENTS,
    }
