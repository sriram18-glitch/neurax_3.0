"""Image dataset discovery and profiling.

Scans a directory tree for image files and annotation formats, then reports
what actually exists: counts, formats, dimensions, class folders, annotation
availability, metadata files, and pre-existing splits.

Everything is measured from the files on disk. If nothing is found, the
profiler returns zero counts - it never estimates or invents image data.
"""

from __future__ import annotations

import json
import re
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path

from PIL import Image, UnidentifiedImageError

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff", ".webp", ".ppm", ".pgm"}
ANNOTATION_JSON_HINTS = re.compile(r"(coco|annotation|annotations|instances|labels|bbox)", re.I)
METADATA_FILE_NAMES = {
    "metadata.csv",
    "metadata.json",
    "labels.csv",
    "annotations.csv",
    "manifest.csv",
    "manifest.json",
    "info.json",
}
SPLIT_DIR_NAMES = {"train", "training", "val", "validation", "valid", "test", "testing"}
NORMAL_DIR_NAMES = {"good", "normal", "ok", "pass", "nominal", "healthy", "defect_free", "defectfree"}
DEFECT_DIR_HINTS = re.compile(r"defect|scratch|dent|crack|stain|contamination|discoloration|broken|fault|damage|hole|spot", re.I)
DIMENSION_SAMPLE_LIMIT = 50


def discover_images(root: Path, max_files: int = 50_000) -> list[Path]:
    root = Path(root)
    found: list[Path] = []
    for path in root.rglob("*"):
        if len(found) >= max_files:
            break
        if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS:
            found.append(path)
    return sorted(found)


def _relative_parts(image: Path, root: Path) -> list[str]:
    try:
        return list(image.relative_to(root).parts[:-1])
    except ValueError:
        return []


def _class_folder(parts: list[str]) -> str | None:
    for part in parts:
        low = part.lower()
        if low in SPLIT_DIR_NAMES:
            continue
        if low in NORMAL_DIR_NAMES or DEFECT_DIR_HINTS.search(part):
            return part
    return None


def _split_folder(parts: list[str]) -> str | None:
    for part in parts:
        low = part.lower()
        if low in {"train", "training"}:
            return "train"
        if low in {"val", "validation", "valid"}:
            return "validation"
        if low in {"test", "testing"}:
            return "test"
    return None


def _sample_dimensions(images: list[Path]) -> dict:
    sizes: Counter = Counter()
    modes: Counter = Counter()
    unreadable = 0
    step = max(1, len(images) // DIMENSION_SAMPLE_LIMIT)
    sampled = images[::step][:DIMENSION_SAMPLE_LIMIT]
    for image in sampled:
        try:
            with Image.open(image) as handle:
                sizes[f"{handle.width}x{handle.height}"] += 1
                modes[handle.mode] += 1
        except (UnidentifiedImageError, OSError):
            unreadable += 1
    return {
        "sampled": len(sampled),
        "unreadable": unreadable,
        "common_sizes": [{"size": size, "count": count} for size, count in sizes.most_common(8)],
        "color_modes": [{"mode": mode, "count": count} for mode, count in modes.most_common(5)],
    }


def _annotation_scan(root: Path) -> dict:
    coco_json: list[str] = []
    yolo_dirs: set[str] = set()
    voc_xml: list[str] = []
    mask_candidates: list[str] = []
    metadata_files: list[str] = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        name_low = path.name.lower()
        if path.suffix.lower() == ".json" and ANNOTATION_JSON_HINTS.search(path.name):
            try:
                payload = json.loads(path.read_text(encoding="utf-8", errors="ignore"))
                if isinstance(payload, dict) and {"images", "annotations"} <= set(payload.keys()):
                    coco_json.append(str(path.relative_to(root)))
                    continue
            except Exception:  # noqa: BLE001 - non-JSON or unreadable: not an annotation file
                pass
        if path.suffix.lower() == ".xml":
            try:
                tree = ET.parse(path)
                if tree.getroot().tag.lower() == "annotation":
                    voc_xml.append(str(path.relative_to(root)))
            except Exception:  # noqa: BLE001
                pass
        if path.suffix.lower() == ".txt" and path.parent.name.lower() in {"labels", "annotations", "yolo"}:
            yolo_dirs.add(str(path.parent.relative_to(root)))
        if path.suffix.lower() in IMAGE_EXTENSIONS and re.search(r"mask|seg", name_low):
            mask_candidates.append(str(path.relative_to(root)))
        if name_low in METADATA_FILE_NAMES:
            metadata_files.append(str(path.relative_to(root)))
    return {
        "coco_json": coco_json[:20],
        "yolo_label_dirs": sorted(yolo_dirs)[:20],
        "voc_xml": voc_xml[:20],
        "mask_candidates": mask_candidates[:20],
        "metadata_files": metadata_files[:20],
    }


def profile_image_directory(root: Path) -> dict:
    root = Path(root)
    images = discover_images(root)
    if not images:
        return {
            "root": str(root),
            "image_count": 0,
            "formats": {},
            "dimensions": None,
            "class_structure": {"folders": [], "per_class": {}, "normal_count": 0, "defect_count": 0},
            "annotations": None,
            "splits_present": None,
            "suitability": {
                "classification": {"supported": False, "reason": "no images found"},
                "anomaly_detection": {"supported": False, "reason": "no images found"},
                "localization": {"supported": False, "reason": "no images found"},
            },
            "notes": ["No image files were found in this dataset."],
        }

    formats = Counter(image.suffix.lower().lstrip(".") for image in images)
    per_class: Counter = Counter()
    per_split: Counter = Counter()
    normal_count = 0
    defect_count = 0
    for image in images:
        parts = _relative_parts(image, root)
        class_name = _class_folder(parts)
        if class_name:
            per_class[class_name] += 1
            if class_name.lower() in NORMAL_DIR_NAMES:
                normal_count += 1
            elif DEFECT_DIR_HINTS.search(class_name):
                defect_count += 1
        split_name = _split_folder(parts)
        if split_name:
            per_split[split_name] += 1

    annotations = _annotation_scan(root)
    has_boxes = bool(annotations["coco_json"] or annotations["voc_xml"] or annotations["yolo_label_dirs"])
    has_masks = bool(annotations["mask_candidates"])
    has_metadata = bool(annotations["metadata_files"])
    class_folders = sorted(per_class.keys())

    suitability = {
        "classification": {
            "supported": len(class_folders) >= 2 and min(per_class.values()) >= 10,
            "reason": (
                f"{len(class_folders)} class folder(s) detected with per-class counts "
                f"{dict(per_class)}; need 2+ classes with >= 10 images each."
            ),
        },
        "anomaly_detection": {
            "supported": normal_count >= 20,
            "reason": (
                f"{normal_count} normal image(s) detected; need >= 20 defect-free images "
                "to build a normal reference."
            ),
        },
        "localization": {
            "supported": has_boxes or has_masks,
            "reason": (
                "Annotation sources detected: "
                + ", ".join(
                    filter(
                        None,
                        [
                            "COCO JSON" if annotations["coco_json"] else None,
                            "Pascal VOC XML" if annotations["voc_xml"] else None,
                            "YOLO label directories" if annotations["yolo_label_dirs"] else None,
                            "segmentation mask candidates" if annotations["mask_candidates"] else None,
                        ],
                    )
                )
            )
            if (has_boxes or has_masks)
            else "No bounding-box or mask annotations detected; only model-derived localization could be offered.",
        },
    }

    notes: list[str] = []
    if per_split:
        notes.append(f"Pre-existing split folders detected: {dict(per_split)}. These will be respected.")
    else:
        notes.append("No pre-existing train/validation/test folders; a leakage-safe split must be derived from metadata.")
    if not has_metadata:
        notes.append("No per-image metadata files detected; process linkage may be unavailable.")
    if defect_count and normal_count:
        notes.append(f"Supervised structure present: {normal_count} normal, {defect_count} defect image(s).")

    return {
        "root": str(root),
        "image_count": len(images),
        "formats": dict(formats.most_common()),
        "dimensions": _sample_dimensions(images),
        "class_structure": {
            "folders": class_folders,
            "per_class": dict(per_class),
            "normal_count": normal_count,
            "defect_count": defect_count,
        },
        "annotations": {
            **annotations,
            "bounding_boxes_available": has_boxes,
            "segmentation_masks_available": has_masks,
            "per_image_metadata_available": has_metadata,
        },
        "splits_present": dict(per_split) if per_split else None,
        "suitability": suitability,
        "notes": notes,
    }
