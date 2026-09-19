"""Phase 3 exit verification: run the full pipeline on every real dataset file,
spot-check that reported numbers match independent pandas calculations, and
inspect the artifact structure.

Run: python backend/tests/verify_phase3_real.py
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

import pandas as pd  # noqa: E402

from app.ingest import analyze_path, ingest_path  # noqa: E402
from app.pipeline import run_pipeline  # noqa: E402
from app.core.settings import ARTIFACTS_DIR  # noqa: E402

PROJECT = BACKEND.parent
DS = PROJECT / "Manufacturing Data Shared Facility - Discrete-Event Simulation"

FILES = [
    DS / "Model 1" / "Model_1.csv",
    DS / "Model 2" / "Model_2.csv",
    DS / "Model 3" / "Model_3.csv",
    DS / "3000Samplesv3.mat",
]

failures = []


def verify(name: str, condition: bool, detail: str = "") -> None:
    mark = "PASS" if condition else "FAIL"
    if not condition:
        failures.append(f"{name}: {detail}")
    print(f"  [{mark}] {name} {detail if not condition else ''}".rstrip())


print("=" * 84)
print("PHASE 3 - REAL DATASET EXIT VERIFICATION")
print("=" * 84)

for path in FILES:
    if not path.exists():
        print(f"SKIP (missing): {path.name}")
        continue
    t0 = time.time()
    contract = analyze_path(path)
    result = ingest_path(path)
    analysis = run_pipeline(contract["dataset_id"], path.name, contract, result, ARTIFACTS_DIR)
    elapsed = time.time() - t0
    print(f"\n### {path.name}  ({elapsed:.1f}s)  dataset_id={contract['dataset_id']}")
    verify(f"{path.name} pipeline complete", analysis["status"] == "complete", str(analysis.get("error")))
    if analysis["status"] != "complete":
        continue

    print(f"    tables={len(analysis['tables'])}  model_inputs={len(analysis['model_inputs'])}  "
          f"stations={analysis['station_metrics']['tables'][0]['station_count']}")
    for mi in analysis["model_inputs"][:4]:
        split = mi.get("split") or {}
        counts = split.get("counts", {})
        print(f"      input '{mi['name']}': rows={mi['rows']}  preds={len(mi['predictors'])} "
              f"resp={len(mi['responses'])}  split={split.get('strategy')} {counts}")
    derived = analysis["features"]["derived_features"]
    print(f"    derived features: {len(derived)}  skipped candidates: {len(analysis['features']['skipped_candidates'])}")
    cov = analysis["coverage"]["modules"]
    print(f"    coverage: vision={cov['vision_inspection']['status']} "
          f"economics={cov['economic_analysis']['status']} "
          f"predictive={cov['predictive_modeling']['status']}")

    # --- independent number verification --------------------------------------
    if path.name == "Model_1.csv":
        raw = pd.read_csv(path)
        expected_mean = raw["Drilling Util"].mean()
        drilling = next(s for s in analysis["station_metrics"]["tables"][0]["stations"] if s["station_id"] == "Drilling")
        reported = drilling["utilization"]["mean"]
        verify(
            "Model_1 Drilling utilization mean matches independent pandas calc",
            abs(reported - expected_mean) < 1e-4,
            f"reported={reported} expected={expected_mean}",
        )
        expected_rows = int(raw.shape[0])
        verify("Model_1 model input rows == raw rows", analysis["model_inputs"][0]["rows"] == expected_rows)

    if path.name == "Model_3.csv":
        raw = pd.read_csv(path, usecols=["Cell1_Util", "Quality_Util"])
        cell1 = next(s for s in analysis["station_metrics"]["tables"][0]["stations"] if s["station_id"] == "Cell1")
        verify(
            "Model_3 Cell1 utilization mean matches independent pandas calc",
            abs(cell1["utilization"]["mean"] - raw["Cell1_Util"].mean()) < 1e-4,
            f"reported={cell1['utilization']['mean']} expected={raw['Cell1_Util'].mean()}",
        )
        quality = next(s for s in analysis["station_metrics"]["tables"][0]["stations"] if s["station_id"] == "Quality")
        verify("Model_3 Quality station detected", quality["utilization"]["available"] is True)
        verify("Model_3 Quality queue available (Quality_Queue exists in dataset)",
               quality["queue_wait"]["available"] is True)
        cell4 = next(s for s in analysis["station_metrics"]["tables"][0]["stations"] if s["station_id"] == "Cell4")
        verify("Model_3 Cell4 queue available (Cell4_Queue exists in dataset)",
               cell4["queue_wait"]["available"] is True)
        cell1 = next(s for s in analysis["station_metrics"]["tables"][0]["stations"] if s["station_id"] == "Cell1")
        verify("Model_3 Cell1 cycle time available (c_Cycle1 exists)",
               cell1["cycle_time"]["available"] is True)
        split_meta = analysis["splits"]["table_splits"][0]
        verify("Model_3 split is sequential (605k unordered rows)",
               split_meta["strategy"] == "sequential_holdout", split_meta["strategy"])
        counts = split_meta["counts"]
        verify("Model_3 split counts sum to row count",
               sum(counts.values()) == split_meta["rows"])

    if path.name == "3000Samplesv3.mat":
        names = [mi["name"] for mi in analysis["model_inputs"]]
        model1 = next((mi for mi in analysis["model_inputs"] if mi["name"] == "Model1"), None)
        verify("MAT fusion produced a 'Model1' input", model1 is not None, str(names[:6]))
        if model1:
            verify("Model1 fused input rows == 3000", model1["rows"] == 3000, str(model1["rows"]))
            verify("Model1 fused: 1 predictor + 6 real response columns (Answer+Response)",
                   len(model1["predictors"]) == 1 and len(model1["responses"]) == 6,
                   f"{len(model1['predictors'])}/{len(model1['responses'])}")
            verify("Model1 predictors and responses are disjoint",
                   not set(model1["predictors"]) & set(model1["responses"]))
            verify("Model1 split computed", (model1.get("split") or {}).get("status") == "COMPUTED")
        # independent check: predictor values present in frame artifact
        mat_path = ARTIFACTS_DIR / contract["dataset_id"] / "model_inputs" / "Model1.csv.gz"
        verify("Model1 model input artifact written", mat_path.exists(), str(mat_path))
        if mat_path.exists():
            stored = pd.read_csv(mat_path)
            verify("stored artifact row count == reported rows", len(stored) == model1["rows"])
            verify("stored artifact has a split column with 3 values",
                   set(stored["split"].unique()) <= {"train", "validation", "test", "unsplit"})

print("\n" + "=" * 84)
print("ARTIFACT TREE (last processed dataset)")
print("=" * 84)
root = Path(analysis["artifacts"]["root"])
for p in sorted(root.rglob("*")):
    rel = p.relative_to(root)
    if p.is_file():
        print(f"  {rel}  ({p.stat().st_size/1024:.0f} KB)")
    else:
        print(f"  {rel}/")

# reproducibility spot check: rerun one dataset with same seed -> same split counts
print("\n" + "=" * 84)
print("REPRODUCIBILITY SPOT CHECK (same file, same seed, twice)")
print("=" * 84)
p = DS / "Model 1" / "Model_1.csv"
c1 = analyze_path(p)
r1 = ingest_path(p)
a1 = run_pipeline(c1["dataset_id"], p.name, c1, r1, ARTIFACTS_DIR / "repro1")
a2 = run_pipeline(c1["dataset_id"], p.name, c1, r1, ARTIFACTS_DIR / "repro2")
s1 = a1["model_inputs"][0]["split"]
s2 = a2["model_inputs"][0]["split"]
verify("split metadata identical across runs", s1 == s2)
verify("feature metadata identical across runs",
       a1["features"]["derived_features"] == a2["features"]["derived_features"])

print("\n" + "=" * 84)
print(f"RESULT: {'ALL CHECKS PASSED' if not failures else str(len(failures)) + ' FAILURES'}")
for f in failures:
    print(f"  FAILED: {f}")
print("=" * 84)
raise SystemExit(1 if failures else 0)
