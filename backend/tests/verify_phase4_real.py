"""Phase 4 exit verification: run Phase 3 + Phase 4 on the real dataset files,
verify metrics/artifacts/reload, and confirm vision stays NOT_SUPPORTED.

Run: python backend/tests/verify_phase4_real.py
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from app.core.settings import ARTIFACTS_DIR, MODELS_DIR  # noqa: E402
from app.ingest import analyze_path, ingest_path  # noqa: E402
from app.ml.registry import ModelRegistry  # noqa: E402
from app.ml.runner import run_ml_pipeline  # noqa: E402
from app.pipeline import run_pipeline  # noqa: E402

PROJECT = BACKEND.parent
DS = PROJECT / "Manufacturing Data Shared Facility - Discrete-Event Simulation"

FILES = [
    DS / "Model 1" / "Model_1.csv",
    DS / "Model 2" / "Model_2.csv",
    DS / "3000Samplesv3.mat",
]

failures: list[str] = []


def verify(name: str, condition: bool, detail: str = "") -> None:
    print(f"  [{'PASS' if condition else 'FAIL'}] {name}{'' if condition else ' -> ' + detail}")
    if not condition:
        failures.append(f"{name}: {detail}")


print("=" * 88)
print("PHASE 4 - REAL DATASET ML VERIFICATION")
print("=" * 88)

for path in FILES:
    if not path.exists():
        print(f"SKIP (missing): {path.name}")
        continue
    t0 = time.time()
    contract = analyze_path(path)
    result = ingest_path(path)
    dataset_id = contract["dataset_id"]
    analysis = run_pipeline(dataset_id, path.name, contract, result, ARTIFACTS_DIR)
    ml = run_ml_pipeline(dataset_id, analysis, ARTIFACTS_DIR / dataset_id, MODELS_DIR)
    elapsed = time.time() - t0

    print(f"\n### {path.name}  dataset_id={dataset_id}  ({elapsed:.1f}s total)")
    verify(f"{path.name} ML run complete", ml["status"] == "complete", str(ml.get("error")))
    verify(f"{path.name} vision NOT_SUPPORTED", ml["vision"]["status"] == "NOT_SUPPORTED", ml["vision"]["status"])

    ready = [m for m in ml["models"] if m.get("status") == "READY"]
    print(f"    models READY: {len(ready)} / attempted: {len(ml['models'])}  "
          f"skipped inputs: {len(ml['skipped_inputs'])}  training: {ml.get('total_training_seconds')}s")
    for m in ml["models"][:12]:
        status = m.get("status")
        if status != "READY":
            print(f"      [{status}] {m.get('input')} -> {m.get('target')}: {m.get('reason', '')[:70]}")
            continue
        test = m["test_metrics"]
        baseline = (m.get("baseline") or {}).get("test_metrics") or {}
        if test.get("kind") == "regression":
            print(f"      [READY] {m['input']} -> {m['target']} ({m['model_type']}): "
                  f"test RMSE={test.get('rmse')} R2={test.get('r2')} | baseline {m['baseline']['model']} RMSE={baseline.get('rmse')}")
        else:
            print(f"      [READY] {m['input']} -> {m['target']} ({m['model_type']}): "
                  f"test F1={test.get('f1_weighted')} acc={test.get('accuracy')} | baseline {m['baseline']['model']}")

    for m in ready[:4]:
        target = m["target"]
        model_id = m["model_id"]
        directory = Path(m["artifact"]["directory"])
        # artifact files
        verify(f"{path.name}/{target}: artifact files exist",
               all((directory / f).exists() for f in ("model.joblib", "metadata.json", "metrics.json", "feature_importance.json")))
        # metrics finite
        test = m["test_metrics"]
        numeric_metrics = [v for v in test.values() if isinstance(v, (int, float))]
        verify(f"{path.name}/{target}: all metrics finite", all(np.isfinite(numeric_metrics)))
        # baseline exists
        verify(f"{path.name}/{target}: baseline present", bool(m.get("baseline", {}).get("model")))
        # feature importance present
        top = (m.get("feature_importance") or {}).get("top_features") or []
        verify(f"{path.name}/{target}: feature importance present", bool(top), str(top))
        # anomaly
        anomaly = m.get("anomaly") or {}
        if anomaly.get("status") == "READY":
            verify(f"{path.name}/{target}: anomaly detector READY with summary",
                   anomaly["summary"]["n"] > 0)
            verify(f"{path.name}/{target}: anomaly terminology precise",
                   anomaly["detector_kind"] == "PROCESS / FEATURE-SPACE ANOMALY DETECTION")
        # reload test
        registry = ModelRegistry(MODELS_DIR)
        reloaded = registry.load_model(dataset_id, model_id)
        frame = pd.read_csv(ARTIFACTS_DIR / dataset_id / "model_inputs" / f"{m['input']}.csv.gz")
        metadata = json.loads((directory / "metadata.json").read_text(encoding="utf-8"))
        X = frame[metadata["predictors"]]
        predictions = np.asarray(reloaded.predict(X.head(50)), dtype="float64")
        verify(f"{path.name}/{target}: reloaded model predicts finite values",
               predictions.shape[0] == 50 and np.isfinite(predictions).all())

print("\n" + "=" * 88)
print(f"RESULT: {'ALL CHECKS PASSED' if not failures else str(len(failures)) + ' FAILURES'}")
for f in failures:
    print(f"  FAILED: {f}")
print("=" * 88)
raise SystemExit(1 if failures else 0)
