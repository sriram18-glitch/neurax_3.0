"""What image data is required for each vision capability.

These are static requirement descriptions - they contain no measurements and
no predictions. They tell the operator exactly what to supply so the vision
layer can be implemented honestly.
"""

from __future__ import annotations

VISION_UNAVAILABLE_REASON = (
    "No visual inspection/image training data is available in the current dataset. "
    "Manufacturing simulation data does not itself provide visual inspection training data."
)

REQUIREMENTS: dict[str, dict] = {
    "defect_classification": {
        "label": "Defect classification (known classes)",
        "needs": "Labeled images organized in class folders (e.g. good/, scratch/, dent/, contamination/) with a reasonable number of images per class.",
        "minimum": "2+ classes with at least 10 images per class.",
    },
    "anomaly_novelty_detection": {
        "label": "Novel / unseen defect detection",
        "needs": "Defect-free (normal) images only, in a normal/ or good/ folder, to build a normal reference distribution.",
        "minimum": "At least 20 normal images.",
    },
    "localization": {
        "label": "Defect localization",
        "needs": "Ground-truth annotations alongside images: COCO JSON, YOLO label txt files, Pascal VOC XML, or segmentation masks.",
        "minimum": "Annotations covering a representative share of defective images. Without annotations only model-derived localization (heatmap) can be offered, labeled as such.",
    },
    "process_link": {
        "label": "Vision-to-process correlation",
        "needs": "Per-image metadata: batch, station, unit/product id, timestamp, or production run.",
        "minimum": "A join key shared with the process dataset.",
    },
    "split_metadata": {
        "label": "Leakage-safe evaluation",
        "needs": "Batch / production-run / condition identifiers per image, or a pre-existing train/validation/test structure.",
        "minimum": "Grouping identifiers so the same unit, batch or run cannot appear in both train and test.",
    },
}


def build_status(image_profile: dict | None, image_count: int, images_found: bool) -> dict:
    """Compose the vision status block for the dataset contract.

    If images were found, report the real profile. Otherwise report
    NOT_SUPPORTED with the exact reason and the requirements list.
    """
    if images_found and image_profile:
        assessment = image_profile.get("suitability", {})
        supported = [
            capability
            for capability, verdict in assessment.items()
            if verdict.get("supported") is True
        ]
        return {
            "status": "PROFILED" if supported else "PROFILED_NO_SUPPORTED_CAPABILITY",
            "available": True,
            "images_found": image_count,
            "profile": image_profile,
            "supported_capabilities": supported,
            "reason": None
            if supported
            else "Images were found but their structure does not yet support any vision capability.",
            "requirements": REQUIREMENTS,
        }
    return {
        "status": "NOT_SUPPORTED",
        "available": False,
        "images_found": 0,
        "profile": None,
        "supported_capabilities": [],
        "reason": VISION_UNAVAILABLE_REASON,
        "requirements": REQUIREMENTS,
    }
