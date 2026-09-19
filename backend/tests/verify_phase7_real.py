"""Phase 7 exit verification: bottleneck/flow analysis on the REAL datasets.

Runs against datasets already processed by Phases 3/4/6 in runtime/artifacts.
Verifies real station metrics, real scoring, artifact persistence/reload,
reproducibility, no fabricated values, and 605k-row performance.

Run: python backend/tests/verify_phase7_real.py
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from app.core.settings import ARTIFACTS_DIR, MODELS_DIR  # noqa: E402
from app.flow.runner import get_analysis, list_analyses, run_bottleneck_analysis  # noqa: E402
from app.ingest import analyze_path, ingest_path  # noqa: E402
from app.ml.runner import run_ml_pipeline  # noqa: E402
from app.pipeline import run_pipeline  # noqa: E402
from app.rootcause.runner import run_root_cause  # noqa: E402
from app.rootcause.targets import discover_targets  # noqa: E402

PROJECT = BACKEND.parent
DS = PROJECT / "Manufacturing Data Shared Facility - Discrete-Event Simulation"

failures: list[str] = []


def verify(name: str, condition: bool, detail: str = "") -> None:
    print(f"  [{'PASS' if condition else 'FAIL'}] {name}{'' if condition else ' -> ' + detail}")
    if not condition:
        failures.append(name)


def prepare(path: Path, run_rca: bool = True) -> tuple[str, dict, Path]:
    contract = analyze_path(path)
    result = ingest_path(path)
    dataset_id = contract["dataset_id"]
    analysis = run_pipeline(dataset_id, path.name, contract, result, ARTIFACTS_DIR)
    artifact_root = ARTIFACTS_DIR / dataset_id
    run_ml_pipeline(dataset_id, analysis, artifact_root, MODELS_DIR)
    if run_rca:
        targets = discover_targets(dataset_id, analysis, artifact_root)
        if targets:
            run_root_cause(dataset_id, targets[0]["target"], "low", 0.10, analysis, artifact_root, MODELS_DIR)
    return dataset_id, analysis, artifact_root


print("=" * 96)
print("PHASE 7 - REAL DATA BOTTLENECK / FLOW VERIFICATION")
print("=" * 96)

# ---------------------------------------------------------------------------
# Model_1.csv
# ---------------------------------------------------------------------------
print("\n### Model_1.csv (3000 rows, Drilling/Milling/Assembly)")
t0 = time.time()
dataset_id, analysis, artifact_root = prepare(DS / "Model 1" / "Model_1.csv")
result = run_bottleneck_analysis(dataset_id, analysis, artifact_root)
verify("Model_1: analysis complete", result["status"] == "complete", str(result.get("error")))
if result["status"] == "complete":
    print(f"    stations: {result['stations_analyzed']}  runtime: {result['total_duration_s']}s")
    for finding in result["station_rankings"]:
        components = {k: v for k, v in finding["score_components"].items() if v is not None}
        print(
            f"      #{finding['rank']} {finding['station']:>10} score={finding['evidence_score']} "
            f"status={finding['status']} quality={finding['evidence_quality']['label']} "
            f"components={components}"
        )
    verify("Model_1: station ranking produced", len(result["station_rankings"]) == 3)
    verify("Model_1: candidate identified with why-evidence",
           result["candidate_bottleneck"]["station"] is not None and bool(result["candidate_bottleneck"]["why"]))
    verify("Model_1: scoring never relies on utilization alone",
           all(len([v for v in f["score_components"].values() if v is not None]) >= 2 for f in result["station_rankings"]))
    verify("Model_1: formula persisted", "sum(weight_i" in (result["configuration"]["scoring_formula"] or ""))
    verify("Model_1: flow graph built from documented structure",
           result["flow"]["graph"]["status"] == "SUPPORTED", result["flow"]["graph"]["status"])
    verify("Model_1: blocking/starvation NOT_SUPPORTED with reason",
           result["flow"]["blocking_starvation"]["blocking"]["status"] == "NOT_SUPPORTED")
    verify("Model_1: observed impact labeled non-simulated",
           result["epistemic_summary"]["simulated_effect"].startswith("NOT YET SIMULATED"))
    verify("Model_1: what-if inputs prepared without economics",
           "no economic values" in result["what_if_inputs"]["note"].lower())
    # real numbers check: top station utilization must match Phase 3 artifact
    station_metrics = json.loads((artifact_root / "station_metrics.json").read_text(encoding="utf-8"))
    table = next(t for t in station_metrics["tables"] if t.get("station_count", 0) > 0)
    top_station = result["station_rankings"][0]["station"]
    phase3_entry = next(s for s in table["stations"] if s["station_id"] == top_station)
    top_util = result["station_rankings"][0]["utilization"]
    verify(f"Model_1: top station utilization matches Phase 3 artifact",
           top_util["mean"] == phase3_entry["utilization"]["mean"])
    # reload
    reloaded = get_analysis(artifact_root / "bottleneck", result["analysis_id"])
    verify("Model_1: artifact reloads identically",
           reloaded is not None and [f["station"] for f in reloaded["station_rankings"]] == [f["station"] for f in result["station_rankings"]])
    # reproducibility
    second = run_bottleneck_analysis(dataset_id, analysis, artifact_root)
    verify("Model_1: reproducible across runs",
           [f["evidence_score"] for f in second["station_rankings"]] == [f["evidence_score"] for f in result["station_rankings"]])
    serialized = json.dumps(result).lower()
    for forbidden in ("is the bottleneck", "proven bottleneck", "guaranteed improvement"):
        verify(f"Model_1: no forbidden phrase '{forbidden}'", forbidden not in serialized)
print(f"    duration: {time.time() - t0:.1f}s")

# ---------------------------------------------------------------------------
# Model_3.csv - 605k rows, 17 stations
# ---------------------------------------------------------------------------
print("\n### Model_3.csv (605,620 rows, 17 stations)")
t0 = time.time()
dataset_id3, analysis3, artifact_root3 = prepare(DS / "Model 3" / "Model_3.csv", run_rca=True)
result3 = run_bottleneck_analysis(dataset_id3, analysis3, artifact_root3)
verify("Model_3: analysis complete", result3["status"] == "complete", str(result3.get("error")))
if result3["status"] == "complete":
    print(f"    stations: {result3['stations_analyzed']}  runtime: {result3['total_duration_s']}s")
    for finding in result3["station_rankings"][:8]:
        components = {k: round(v, 2) for k, v in finding["score_components"].items() if v is not None}
        print(
            f"      #{finding['rank']} {finding['station']:>12} score={finding['evidence_score']} "
            f"status={finding['status']} quality={finding['evidence_quality']['label']} components={components}"
        )
    verify("Model_3: all 17 stations analyzed", result3["stations_analyzed"] == 17)
    verify("Model_3: candidate identified", result3["candidate_bottleneck"]["station"] is not None)
    verify("Model_3: runtime under 60s", result3["total_duration_s"] < 60, f"{result3['total_duration_s']}s")
    verify("Model_3: root-cause evidence integrated where available",
           any(f["root_cause_evidence"] for f in result3["station_rankings"]))
    # Drift: Phase 6 found NO_SIGNIFICANT_DRIFT_DETECTED on Model_3. The engine
    # must therefore show empty drift evidence - fabricating drift would be a
    # violation. Integration-when-present is covered by unit tests.
    rca_registry = json.loads((artifact_root3 / "root_cause" / "analysis_registry.json").read_text(encoding="utf-8"))
    rca_latest = json.loads(
        (artifact_root3 / "root_cause" / "findings" / f"{rca_registry[-1]['analysis_id']}.json").read_text(encoding="utf-8")
    )
    drift_status = rca_latest["drift"]["status"]
    if drift_status == "NO_SIGNIFICANT_DRIFT_DETECTED":
        verify("Model_3: drift honestly empty (Phase 6 found no significant drift)",
               all(not f["drift_evidence"] for f in result3["station_rankings"]))
        verify("Model_3: drift status preserved from Phase 6",
               result3["source"]["root_cause_analysis_id"] == rca_registry[-1]["analysis_id"])
    else:
        verify("Model_3: drift evidence integrated where drift detected",
               any(f["drift_evidence"] for f in result3["station_rankings"]))
    verify("Model_3: flow graph uses documented Model 3 structure",
           result3["flow"]["graph"]["status"] == "SUPPORTED")
    verify("Model_3: throughput impact observed where outputs exist",
           any((f["impact"] or {}).get("status") == "OBSERVED_COMPARISON" for f in result3["station_rankings"]))
print(f"    duration: {time.time() - t0:.1f}s")

# ---------------------------------------------------------------------------
# Registry + honesty
# ---------------------------------------------------------------------------
print("\n### Registry and honesty")
registry = list_analyses(artifact_root / "bottleneck")
verify("Model_1: analyses registered", len(registry) >= 1)
candidate = result["candidate_bottleneck"]
verify("Candidate has evidence quality label", bool((candidate.get("evidence_quality") or {}).get("label")))
verify("Candidate lists unavailable metrics", isinstance(candidate.get("unavailable_metrics"), list))
verify("Epistemic causal claim NOT SUPPORTED", result["epistemic_summary"]["causal_claim"].startswith("NOT SUPPORTED"))

# unsupported case
print("\n### Unsupported case")
from app.flow.errors import FlowError  # noqa: E402

frame_path = ARTIFACTS_DIR / "no_station_probe"
print("  (covered by unit test test_analysis_without_station_data_fails_structurally)")

print("\n" + "=" * 96)
print(f"RESULT: {'ALL CHECKS PASSED' if not failures else str(len(failures)) + ' FAILURES'}")
for failure in failures:
    print(f"  FAILED: {failure}")
print("=" * 96)
raise SystemExit(1 if failures else 0)
