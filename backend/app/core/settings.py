from __future__ import annotations

import os
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[2]
RUNTIME_DIR = Path(os.environ.get("NEURAX_RUNTIME_DIR", str(BACKEND_DIR / "runtime")))
UPLOAD_DIR = RUNTIME_DIR / "uploads"
ARTIFACTS_DIR = RUNTIME_DIR / "artifacts"
MODELS_DIR = RUNTIME_DIR / "models"
IMAGES_DIR = RUNTIME_DIR / "images"
VISION_MODEL_DIR = RUNTIME_DIR / "vision_model"
# Configuration-driven demo/training dataset. Used ONLY for BUILT-IN DEMO
# sources and model training defaults - never for the production stream.
# The normal workflow ingests user-selected files into the session instead.
DEMO_DATASET_DIR = Path(
    os.environ.get("NEURAX_DEMO_DATASET", str(BACKEND_DIR.parent / "train" / "train"))
)
VISION_DATASET_DIR = DEMO_DATASET_DIR  # legacy alias (training endpoint default)
RANDOM_SEED = int(os.environ.get("NEURAX_SEED", "42"))
ARTIFACT_FULL_ROW_CAP = int(os.environ.get("NEURAX_ARTIFACT_ROW_CAP", "250000"))
