"""Phase 9 exit verification: recommendations from REAL Phase 6-8 artifacts.

Verifies:
- recommendations are generated only from real evidence present in artifacts
- every recommendation is traceable to source artifacts
- language safety holds on real output
- no fabricated economics / interventions / causes
- deterministic output across runs
- artifacts persist and reload
- data gaps reported honestly (economics missing, vision unsupported)

Run: python backend/tests/verify_phase9_real.py
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from app.core.settings import ARTIFACTS_DIR  # noqa: E402
from app.recommend import (  # noqa: E402
    find_violations,
    generate_recommendations,
    get_decision_summary,
    get_recommendation,
    list_recommendations,
    validate_recommendation,
)

failures: list[str] = []


def verify(name: str, condition: bool, detail: str = "") -> None:
    print(f"  [{'PASS' if condition else 'FAIL'}] {name}{'' if condition else ' -> ' + detail}")
    if not condition:
        failures.append(name)


def run_for(dataset_id: str, label: str) -> dict:
    artifact_root = ARTIFACTS_DIR / dataset_id
    profile = json.loads((artifact_root / "profile.json").read_text(encoding="utf-8"))
    t0 = time.time()
    payload = generate_recommendations(dataset_id, profile, artifact_root)
    elapsed = time.time() - t0

    print(f"\n### {label} (dataset {dataset_id}) - {elapsed:.2f}s")
    print(f"    candidate bottleneck: {payload['decision_summary']['bottleneck_status']['station']}")
    print(f"    recommendations: {payload['recommendation_count']}")
    for recommendation in payload["recommendations"]:
        print(
            f"      #{recommendation['rank']} [{recommendation['action_type']}] {recommendation['title']} "
            f"(priority={recommendation['priority']}, quality={recommendation['evidence_quality']})"
        )

    verify(f"{label}: generation complete", payload["status"] == "complete")
    verify(f"{label}: at least one recommendation", payload["recommendation_count"] >= 1)
    verify(f"{label}: all recommendations pass validation",
           all(validate_recommendation(r) == [] for r in payload["recommendations"]))
    verify(f"{label}: no forbidden language in whole payload",
           find_violations(json.dumps(payload)) == [], str(find_violations(json.dumps(payload))[:3]))
    verify(f"{label}: every recommendation has evidence + limitations + ADVISORY status",
           all(r["evidence"] and r["limitations"] and r["epistemic_status"] == "ADVISORY" for r in payload["recommendations"]))
    verify(f"{label}: every recommendation traces to source artifacts",
           all(r["source_artifacts"] for r in payload["recommendations"]))
    verify(f"{label}: priorities sorted descending",
           [r["priority"] for r in payload["recommendations"]] == sorted([r["priority"] for r in payload["recommendations"]], reverse=True))

    # determinism
    second = generate_recommendations(dataset_id, profile, artifact_root)
    verify(f"{label}: deterministic across runs",
           [r["recommendation_id"] for r in second["recommendations"]] == [r["recommendation_id"] for r in payload["recommendations"]]
           and [r["priority"] for r in second["recommendations"]] == [r["priority"] for r in payload["recommendations"]])

    # persistence
    registry = list_recommendations(artifact_root)
    verify(f"{label}: registry persisted", len(registry) == payload["recommendation_count"])
    first_id = registry[0]["recommendation_id"]
    reloaded = get_recommendation(artifact_root, first_id)
    verify(f"{label}: recommendation reloads", reloaded is not None and reloaded["recommendation_id"] == first_id)
    summary = get_decision_summary(artifact_root)
    verify(f"{label}: decision summary persisted", summary is not None and summary["dataset_id"] == dataset_id)
    for name in ("recommendation_registry.json", "decision_summary.json", "metadata.json", "latest_run.json"):
        verify(f"{label}: artifact {name}", (artifact_root / "recommendations" / name).exists())

    # evidence really exists in source artifacts
    bottleneck_registry = json.loads((artifact_root / "bottleneck" / "analysis_registry.json").read_text(encoding="utf-8"))
    latest_bottleneck = json.loads(
        (artifact_root / "bottleneck" / "findings" / f"{bottleneck_registry[-1]['analysis_id']}.json").read_text(encoding="utf-8")
    )
    real_station = latest_bottleneck["candidate_bottleneck"]["station"]
    station_recommendations = [r for r in payload["recommendations"] if r.get("station")]
    verify(f"{label}: station-based recommendations match the real candidate bottleneck",
           all(r["station"] == real_station for r in station_recommendations),
           f"{[r['station'] for r in station_recommendations]} vs {real_station}")

    # real utilization value in evidence must equal the artifact value
    util_recommendations = [r for r in payload["recommendations"] if r["action_type"] == "INVESTIGATE_HIGH_UTILIZATION"]
    if util_recommendations:
        ranking = next(s for s in latest_bottleneck["station_rankings"] if s["station"] == real_station)
        real_mean = ranking["utilization"]["mean"]
        evidence_value = util_recommendations[0]["evidence"][0]["value"]
        verify(f"{label}: utilization evidence matches Phase 7 artifact exactly",
               evidence_value == real_mean, f"{evidence_value} vs {real_mean}")

    # economics honesty
    scenario_recs = [r for r in payload["recommendations"] if r["action_type"] == "EVALUATE_CAPACITY_IMPROVEMENT"]
    assumptions_path = artifact_root / "economics" / "assumptions.json"
    supplied = False
    if assumptions_path.exists():
        assumptions = json.loads(assumptions_path.read_text(encoding="utf-8"))
        supplied = (assumptions.get("assumptions", {}).get("contribution_margin_per_unit", {}) or {}).get("value") is not None
    if not supplied:
        verify(f"{label}: no scenario recommendation without economic assumptions", scenario_recs == [])
        verify(f"{label}: economics data-gap recommendation present",
               any(r["target"] == "economic_assumptions" for r in payload["recommendations"]))
    else:
        if scenario_recs:
            rec = scenario_recs[0]
            verify(f"{label}: scenario recommendation labelled SIMULATED",
                   rec["simulated_effect"]["epistemic_status"] == "SIMULATED")
            verify(f"{label}: scenario recommendation includes assumptions",
                   len(rec["assumptions"]) > 0)

    # vision honesty
    verify(f"{label}: vision data gap reported (vision NOT_SUPPORTED)",
           any(r["target"] == "vision_dataset" for r in payload["recommendations"])
           if not (profile.get("vision") or {}).get("available")
           else True)

    return payload


print("=" * 96)
print("PHASE 9 - REAL DATA RECOMMENDATION VERIFICATION")
print("=" * 96)

# Model_1: full pipeline exists (bottleneck + root cause + economics scenario from Phase 8)
run_for("66f2977648d1", "Model_1.csv")

# Model_3: bottleneck + root cause, no economics scenario (assumptions never supplied for it)
run_for("f5b2df4fb4f9", "Model_3.csv")

print("\n### Cross-dataset isolation")
a = list_recommendations(ARTIFACTS_DIR / "66f2977648d1")
b = list_recommendations(ARTIFACTS_DIR / "f5b2df4fb4f9")
ids_a = {entry["recommendation_id"] for entry in a}
ids_b = {entry["recommendation_id"] for entry in b}
verify("Recommendations are dataset-scoped (ids differ)", ids_a.isdisjoint(ids_b))

print("\n" + "=" * 96)
print(f"RESULT: {'ALL CHECKS PASSED' if not failures else str(len(failures)) + ' FAILURES'}")
for failure in failures:
    print(f"  FAILED: {failure}")
print("=" * 96)
raise SystemExit(1 if failures else 0)
