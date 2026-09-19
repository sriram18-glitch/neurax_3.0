"""Phase 6 exit verification: root-cause analysis on the REAL datasets.

Runs against datasets already processed by Phases 3/4 in runtime/artifacts.
Verifies findings are computed from real data, epistemically labeled, persisted
and reloadable, and that unsupported cases are explicit.

Run: python backend/tests/verify_phase6_real.py
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from app.core.settings import ARTIFACTS_DIR, MODELS_DIR  # noqa: E402
from app.ingest import analyze_path, ingest_path  # noqa: E402
from app.ml.runner import run_ml_pipeline  # noqa: E402
from app.pipeline import run_pipeline  # noqa: E402
from app.rootcause.runner import get_analysis, list_analyses, run_root_cause  # noqa: E402
from app.rootcause.targets import discover_targets  # noqa: E402

PROJECT = BACKEND.parent
DS = PROJECT / "Manufacturing Data Shared Facility - Discrete-Event Simulation"

failures: list[str] = []


def verify(name: str, condition: bool, detail: str = "") -> None:
    print(f"  [{'PASS' if condition else 'FAIL'}] {name}{'' if condition else ' -> ' + detail}")
    if not condition:
        failures.append(name)


def prepare(path: Path) -> tuple[str, dict, Path]:
    contract = analyze_path(path)
    result = ingest_path(path)
    dataset_id = contract["dataset_id"]
    analysis = run_pipeline(dataset_id, path.name, contract, result, ARTIFACTS_DIR)
    run_ml_pipeline(dataset_id, analysis, ARTIFACTS_DIR / dataset_id, MODELS_DIR)
    return dataset_id, analysis, ARTIFACTS_DIR / dataset_id


print("=" * 92)
print("PHASE 6 - REAL DATA ROOT-CAUSE VERIFICATION")
print("=" * 92)

# ---------------------------------------------------------------------------
# Model_1.csv - real process data with station columns
# ---------------------------------------------------------------------------
print("\n### Model_1.csv (3000 rows, Drilling/Milling/Assembly)")
t0 = time.time()
dataset_id, analysis, artifact_root = prepare(DS / "Model 1" / "Model_1.csv")
targets = discover_targets(dataset_id, analysis, artifact_root)
print(f"    targets discovered: {[t['target'] for t in targets]}")

for target_name, direction in (("Parts per hour", "low"), ("Total parts", "high")):
    result = run_root_cause(dataset_id, target_name, direction, 0.10, analysis, artifact_root, MODELS_DIR)
    verify(f"Model_1/{target_name}/{direction}: analysis complete", result["status"] == "complete", str(result.get("error")))
    if result["status"] != "complete":
        continue
    ranked = result["ranked_findings"]
    print(f"    {target_name} ({direction} 10%): {result['factors_analyzed']} factors analyzed in {result['total_duration_s']}s")
    for finding in ranked[:4]:
        print(
            f"      #{finding['rank']} {finding['factor']:>22} score={finding['evidence_score']} "
            f"status={finding['association_status']} station={finding['station']}"
        )
    verify(f"Model_1/{target_name}: findings ranked by data-driven score",
           all(ranked[i]["evidence_score"] is None or ranked[i]["evidence_score"] >= (ranked[i + 1]["evidence_score"] or 0)
               for i in range(len(ranked) - 1)))
    verify(f"Model_1/{target_name}: every finding has epistemic labels",
           all("not causation" in f["epistemic_status"].lower() or "hypothesis" in f["epistemic_status"].lower() for f in ranked))
    verify(f"Model_1/{target_name}: station attribution present for station columns",
           any(f["station"] for f in ranked), str([f["station"] for f in ranked[:5]]))
    verify(f"Model_1/{target_name}: model contribution integrated",
           any(f["evidence"]["model_contribution"]["available"] for f in ranked))
    verify(f"Model_1/{target_name}: drift analysis ran or explicitly unsupported",
           result["drift"]["status"] in {"DRIFT_DETECTED", "NO_SIGNIFICANT_DRIFT_DETECTED", "DRIFT_ANALYSIS_NOT_SUPPORTED"})
    verify(f"Model_1/{target_name}: artifact persisted", (artifact_root / "root_cause" / "findings" / f"{result['analysis_id']}.json").exists())
    reloaded = get_analysis(artifact_root / "root_cause", result["analysis_id"])
    verify(f"Model_1/{target_name}: artifact reloads with identical ranking",
           reloaded is not None and [f["factor"] for f in reloaded["ranked_findings"]] == [f["factor"] for f in ranked])
    # real correlation numbers must be present and finite
    top = ranked[0]
    corr = top["evidence"]["correlation"]
    verify(f"Model_1/{target_name}: top factor has real correlation value",
           corr.get("available") and corr.get("spearman_r") is not None)

print(f"    duration: {time.time() - t0:.1f}s")

# ---------------------------------------------------------------------------
# Model_3.csv - 605k station data (process-mode targets)
# ---------------------------------------------------------------------------
print("\n### Model_3.csv (605,620 rows, 17 stations)")
t0 = time.time()
dataset_id3, analysis3, artifact_root3 = prepare(DS / "Model 3" / "Model_3.csv")
targets3 = discover_targets(dataset_id3, analysis3, artifact_root3)
print(f"    targets discovered: {[(t['target'], t['mode']) for t in targets3][:6]}")
verify("Model_3: process-mode targets discovered", any(t["mode"] == "process_table" for t in targets3))

if targets3:
    target = targets3[0]
    result3 = run_root_cause(dataset_id3, target["target"], "high", 0.10, analysis3, artifact_root3, MODELS_DIR)
    verify("Model_3: analysis complete", result3["status"] == "complete", str(result3.get("error")))
    if result3["status"] == "complete":
        print(f"    target '{target['target']}' (high 10%): {result3['factors_analyzed']} factors in {result3['total_duration_s']}s")
        for finding in result3["ranked_findings"][:5]:
            print(
                f"      #{finding['rank']} {finding['factor']:>26} score={finding['evidence_score']} "
                f"station={finding['station']}"
            )
        verify("Model_3: ordering detected (Time_Now present)", result3["ordering"]["column"] is not None, str(result3["ordering"]))
        verify("Model_3: drift analysis ran", result3["drift"]["status"] in {"DRIFT_DETECTED", "NO_SIGNIFICANT_DRIFT_DETECTED"}, str(result3["drift"].get("status")))
        verify("Model_3: sampling recorded when applied",
               all(not (c.get("sampled") and c.get("n") is None) for f in result3["ranked_findings"] for c in f["evidence"].values() if isinstance(c, dict)))
        verify("Model_3: runtime under 120s", result3["total_duration_s"] < 120, f"{result3['total_duration_s']}s")
print(f"    duration: {time.time() - t0:.1f}s")

# ---------------------------------------------------------------------------
# MAT dataset - fused model inputs
# ---------------------------------------------------------------------------
print("\n### 3000Samplesv3.mat (fused model inputs)")
t0 = time.time()
dataset_idm, analysism, artifact_rootm = prepare(DS / "3000Samplesv3.mat")
targetsm = discover_targets(dataset_idm, analysism, artifact_rootm)
model_targets = [t for t in targetsm if t["mode"] == "model_input"]
verify("MAT: model-input targets discovered", len(model_targets) > 0, str(len(model_targets)))
if model_targets:
    target = next((t for t in model_targets if t["target"].startswith("Model1Response")), model_targets[0])
    resultm = run_root_cause(dataset_idm, target["target"], "low", 0.10, analysism, artifact_rootm, MODELS_DIR)
    verify("MAT: analysis complete", resultm["status"] == "complete", str(resultm.get("error")))
    if resultm["status"] == "complete":
        print(f"    target '{target['target']}': {resultm['factors_analyzed']} factors in {resultm['total_duration_s']}s")
        for finding in resultm["ranked_findings"][:4]:
            print(f"      #{finding['rank']} {finding['factor']:>28} score={finding['evidence_score']}")
        verify("MAT: model contribution available (Phase 4 model exists)",
               any(f["evidence"]["model_contribution"]["available"] for f in resultm["ranked_findings"]))
print(f"    duration: {time.time() - t0:.1f}s")

# ---------------------------------------------------------------------------
# Registry and honesty checks
# ---------------------------------------------------------------------------
print("\n### Registry and honesty")
registry = list_analyses(artifact_root / "root_cause")
verify("Model_1: analyses registered", len(registry) >= 2, str(len(registry)))
serialized = json.dumps(result).lower()
for forbidden in ("confirmed root cause", "is the root cause", "caused by"):
    verify(f"No forbidden causal phrase '{forbidden}'", forbidden not in serialized)
verify("Causal claim explicitly NOT SUPPORTED", result["epistemic_summary"]["causal_claim"].startswith("NOT SUPPORTED"))
verify("Limitations recorded", len(result["limitations"]) >= 3)

# unsupported case: dataset without usable targets
print("\n### Unsupported case handling")
from app.rootcause.targets import resolve_target  # noqa: E402
from app.rootcause.errors import RootCauseError  # noqa: E402

try:
    resolve_target(targets, "Definitely Not A Column")
    verify("Unknown target raises structured error", False, "no exception")
except RootCauseError as exc:
    verify("Unknown target raises structured error", exc.code == "TARGET_NOT_FOUND")

print("\n" + "=" * 92)
print(f"RESULT: {'ALL CHECKS PASSED' if not failures else str(len(failures)) + ' FAILURES'}")
for failure in failures:
    print(f"  FAILED: {failure}")
print("=" * 92)
raise SystemExit(1 if failures else 0)
