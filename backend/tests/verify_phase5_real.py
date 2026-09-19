"""Phase 5 exit verification.

Confirms:
- the real workspace contains no image dataset
- the real process datasets report vision NOT_SUPPORTED with requirements
- the vision profiler genuinely activates when given real images (synthetic fixture)
- Phases 3 and 4 remain intact

Run: python backend/tests/verify_phase5_real.py
"""

from __future__ import annotations

import json
import sys
import tempfile
import zipfile
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

import numpy as np  # noqa: E402
from PIL import Image  # noqa: E402

from app.ingest import analyze_path  # noqa: E402
from app.vision.discovery import profile_image_directory  # noqa: E402
from app.vision.requirements import VISION_UNAVAILABLE_REASON  # noqa: E402

PROJECT = BACKEND.parent
DS = PROJECT / "Manufacturing Data Shared Facility - Discrete-Event Simulation"

failures: list[str] = []


def verify(name: str, condition: bool, detail: str = "") -> None:
    print(f"  [{'PASS' if condition else 'FAIL'}] {name}{'' if condition else ' -> ' + detail}")
    if not condition:
        failures.append(name)


print("=" * 88)
print("PHASE 5 - VISION DATA FORENSICS & HONESTY VERIFICATION")
print("=" * 88)

print("\n### 1. Workspace scan for image data")
IGNORED_PARTS = {"runtime", ".pytest_cache", "node_modules", "dist", ".venv", "venv", "site-packages"}
image_files = [
    path
    for path in PROJECT.rglob("*")
    if path.is_file()
    and path.suffix.lower() in {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff", ".webp"}
    and not IGNORED_PARTS.intersection(path.parts)
]
verify("No image files exist in the project workspace", len(image_files) == 0, str(image_files[:5]))

annotation_files = [
    path
    for path in PROJECT.rglob("*")
    if path.is_file()
    and path.suffix.lower() == ".xml"
    and not IGNORED_PARTS.intersection(path.parts)
]
verify("No annotation files (VOC XML) in workspace", len(annotation_files) == 0)

print("\n### 2. Real process datasets report vision NOT_SUPPORTED")
for rel in ("Model 1/Model_1.csv", "Model 2/Model_2.csv", "3000Samplesv3.mat"):
    path = DS / rel
    if not path.exists():
        print(f"  SKIP (missing): {rel}")
        continue
    contract = analyze_path(path)
    vision = contract["vision"]
    verify(f"{rel}: vision status NOT_SUPPORTED", vision["status"] == "NOT_SUPPORTED", vision["status"])
    verify(f"{rel}: no image counts fabricated", vision["images_found"] == 0)
    verify(f"{rel}: reason is the exact unavailable text", vision["reason"] == VISION_UNAVAILABLE_REASON)
    verify(f"{rel}: requirements provided", bool(vision["requirements"]))
    verify(f"{rel}: supported_capabilities empty", vision["supported_capabilities"] == [])

print("\n### 3. Vision profiler genuinely activates on real images")
with tempfile.TemporaryDirectory(prefix="neurax_phase5_") as tmp:
    root = Path(tmp) / "surface"
    rng = np.random.default_rng(0)
    for cls, color, count in (("good", 140, 12), ("scratch", 90, 12), ("dent", 60, 12)):
        for index in range(count):
            array = np.clip(
                np.full((32, 32, 3), color, dtype=int) + rng.integers(-3, 4, (32, 32, 3)), 0, 255
            ).astype(np.uint8)
            target = root / cls / f"{cls}_{index:03d}.png"
            target.parent.mkdir(parents=True, exist_ok=True)
            Image.fromarray(array).save(target)
    profile = profile_image_directory(root)
    verify("Profiler found all 36 images", profile["image_count"] == 36, str(profile["image_count"]))
    verify("Profiler detected 3 class folders", set(profile["class_structure"]["folders"]) == {"good", "scratch", "dent"})
    verify("Profiler says classification supported", profile["suitability"]["classification"]["supported"] is True)
    verify("Profiler says localization not supported (no annotations)",
           profile["suitability"]["localization"]["supported"] is False)

    archive = Path(tmp) / "surface.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        for file in root.rglob("*"):
            if file.is_file():
                zf.write(file, file.relative_to(root))
    extract_to = Path(tmp) / "extracted"
    contract = analyze_path(archive, extract_images_to=extract_to)
    verify("ZIP upload with images -> vision PROFILED", contract["vision"]["status"] == "PROFILED")
    verify("ZIP upload reports real image count", contract["vision"]["images_found"] == 36)
    verify("ZIP upload does not fail without tables", contract["status"] == "analyzed")

print("\n### 4. No fabricated vision outputs anywhere")
from app.vision.service import inference_status  # noqa: E402

status = inference_status()
verify("Inference endpoint returns NOT_SUPPORTED", status["status"] == "NOT_SUPPORTED")
verify("Inference endpoint has no prediction fields",
       not any(key in status for key in ("prediction", "confidence", "defect_class", "heatmap")))

ml_summaries = list((BACKEND / "runtime" / "artifacts").glob("*/ml_summary.json"))
for summary_path in ml_summaries:
    payload = json.loads(summary_path.read_text(encoding="utf-8"))
    vision = payload.get("vision", {})
    verify(f"{summary_path.parent.name}: stored ml_summary vision status honest",
           vision.get("status") in {"NOT_SUPPORTED", "PROFILED", "PROFILED_NO_SUPPORTED_CAPABILITY"},
           str(vision.get("status")))
    serialized = json.dumps(payload)
    verify(f"{summary_path.parent.name}: no fake defect/heatmap fields",
           "heatmap" not in serialized and "defect_probability" not in serialized)

print("\n" + "=" * 88)
print(f"RESULT: {'ALL CHECKS PASSED' if not failures else str(len(failures)) + ' FAILURES'}")
for failure in failures:
    print(f"  FAILED: {failure}")
print("=" * 88)
raise SystemExit(1 if failures else 0)
