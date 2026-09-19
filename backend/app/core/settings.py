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
VISION_DATASET_DIR = Path(
    os.environ.get("NEURAX_VISION_DATASET", str(BACKEND_DIR.parent / "train" / "train"))
)
RANDOM_SEED = int(os.environ.get("NEURAX_SEED", "42"))
ARTIFACT_FULL_ROW_CAP = int(os.environ.get("NEURAX_ARTIFACT_ROW_CAP", "250000"))
