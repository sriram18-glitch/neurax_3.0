"""Phase 8 exit verification: economics & what-if on REAL Phase 7 outputs.

Key honesty checks:
- dataset contains NO economic columns -> economics must be NOT_AVAILABLE
  until the user supplies assumptions
- once supplied, baseline/scenario calculations are exact and labelled
- simulated output is never presented as observed
- artifacts persist, reload, and reproduce

Run: python backend/tests/verify_phase8_real.py
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from app.core.settings import ARTIFACTS_DIR  # noqa: E402
from app.economics import EconomicsError, run_scenario  # noqa: E402
from app.economics import store as econ_store  # noqa: E402
from app.flow.runner import run_bottleneck_analysis  # noqa: E402

failures: list[str] = []


def verify(name: str, condition: bool, detail: str = "") -> None:
    print(f"  [{'PASS' if condition else 'FAIL'}] {name}{'' if condition else ' -> ' + detail}")
    if not condition:
        failures.append(name)


print("=" * 96)
print("PHASE 8 - REAL DATA ECONOMICS / WHAT-IF VERIFICATION")
print("=" * 96)

# ---------------------------------------------------------------------------
# Model_1.csv - real Phase 7 bottleneck artifacts already exist
# ---------------------------------------------------------------------------
dataset_id = "66f2977648d1"
artifact_root = ARTIFACTS_DIR / dataset_id

print("\n### Model_1.csv (real Phase 7 outputs)")
bottleneck = econ_store.latest_bottleneck(artifact_root)
verify("Phase 7 bottleneck artifact loaded", bottleneck is not None)
if bottleneck is None:
    print("  cannot continue without Phase 7 artifact")
    raise SystemExit(1)

station = bottleneck["candidate_bottleneck"]["station"]
quality = bottleneck["candidate_bottleneck"]["evidence_quality"]["label"]
print(f"    candidate bottleneck: {station} ({quality})")

# 1) economics status before assumptions --------------------------------------
# NOTE: assumptions are user data and persist across runs. To verify the
# NOT_PROVIDED behaviour without destroying real user assumptions, we check the
# empty-state logic against a fresh empty payload (what a first-time dataset sees).
t0 = time.time()
from app.economics.assumptions import empty_assumptions  # noqa: E402

fresh_empty = empty_assumptions(dataset_id)
verify("Empty state: assumptions NOT_PROVIDED", fresh_empty["assumptions"]["contribution_margin_per_unit"]["value"] is None)
verify("Empty state: currency NOT_PROVIDED", fresh_empty["currency"]["value"] is None)

from app.economics import baseline_economics  # noqa: E402

baseline_before = baseline_economics(
    (econ_store.latest_bottleneck(artifact_root)["what_if_inputs"]["observed_impact"]["observed"] or {}).get("Total parts", {}).get("unconstrained_mean")
    or (econ_store.latest_bottleneck(artifact_root)["what_if_inputs"]["observed_impact"]["observed"] or {}).get("Parts per hour", {}).get("unconstrained_mean"),
    fresh_empty,
)
verify("Empty state: baseline economics NOT_AVAILABLE",
       baseline_before["daily_contribution"]["status"] == "NOT_AVAILABLE")
verify("Empty state: missing inputs listed explicitly",
       "contribution_margin_per_unit" in baseline_before["daily_contribution"]["missing_inputs"])

existing_assumptions = econ_store.get_assumptions(artifact_root, dataset_id)
real_throughput = None
observed = ((econ_store.latest_bottleneck(artifact_root)["what_if_inputs"].get("observed_impact") or {}).get("observed") or {})
if observed:
    column = next(iter(observed))
    real_throughput = observed[column].get("unconstrained_mean")
verify("Real throughput detected from Phase 7", real_throughput is not None, str(real_throughput))
print(f"    observed throughput: {real_throughput} (DATA_DERIVED)")

# 2) verify the dataset really has no economic columns ------------------------
profile = json.loads((artifact_root / "profile.json").read_text(encoding="utf-8"))
all_columns = [c["name"].lower() for table in profile["tables"] for c in table["columns_detail"]]
economic_hits = [c for c in all_columns if any(token in c for token in ("price", "cost", "margin", "profit", "revenue", "currency"))]
verify("Dataset contains no economic columns (so assumptions are required)",
       economic_hits == [], str(economic_hits[:5]))

# 3) supply assumptions and recompute baseline --------------------------------
from app.economics import validate_and_merge  # noqa: E402

merged = validate_and_merge(
    existing_assumptions,
    {
        "currency": "INR",
        "contribution_margin_per_unit": 25.0,
        "working_hours_per_day": 8.0,
        "working_days_per_month": 22.0,
        "intervention_cost": 55000.0,
    },
)
econ_store.put_assumptions(artifact_root, dataset_id, merged)

baseline_after = econ_store.compute_baseline(artifact_root, dataset_id)
verify("Baseline CALCULATED after assumptions",
       baseline_after["baseline"]["daily_contribution"]["status"] == "CALCULATED")
throughput = baseline_after["baseline"]["throughput_per_hour"]["value"]
expected_daily = throughput * 8.0 * 25.0
verify("Baseline arithmetic exact (throughput * hours * margin)",
       abs(baseline_after["baseline"]["daily_contribution"]["value"] - expected_daily) < 1e-3,
       f"{baseline_after['baseline']['daily_contribution']['value']} vs {expected_daily}")
print(f"    baseline daily contribution: {baseline_after['baseline']['daily_contribution']['value']} INR "
      f"(from observed {throughput} units/h)")

# 4) scenario engine -----------------------------------------------------------
scenario = run_scenario(
    dataset_id,
    bottleneck,
    merged,
    "throughput_scaling",
    {"throughput_change": 0.10, "scaling_basis": "user_assumption"},
)
verify("Scenario runs with user-assumption basis", scenario["scenario_type"] == "throughput_scaling")
verify("Scenario labelled SIMULATED", scenario["epistemic_status"].startswith("SIMULATED SCENARIO"))
delta_units = scenario["economic_output"]["units_per_day_delta"]["value"]
delta_contrib = scenario["economic_output"]["daily_contribution_delta"]["value"]
verify("Scenario units delta exact (+10% of throughput * 8h)",
       abs(delta_units - throughput * 0.10 * 8.0) < 1e-3,
       f"{delta_units} vs {throughput * 0.10 * 8.0}")
verify("Scenario contribution delta exact (units * margin)",
       abs(delta_contrib - delta_units * 25.0) < 1e-3)
verify("Baseline marked DATA_DERIVED", scenario["baseline"]["epistemic_status"].startswith("DATA_DERIVED"))
verify("Scenario metrics marked SIMULATED", scenario["scenario"]["epistemic_status"] == "SIMULATED")
print(f"    simulated +10%: +{delta_units} units/day, +{delta_contrib} INR/day (SIMULATED)")

# utilization scenario must not extrapolate throughput -------------------------
util_scenario = run_scenario(
    dataset_id, bottleneck, merged, "utilization_reduction", {"utilization_reduction": 0.10}
)
verify("Utilization scenario does NOT extrapolate throughput",
       any("NOT extrapolated" in warning for warning in util_scenario["warnings"]))
verify("Utilization scenario units delta is zero (no fabricated throughput gain)",
       util_scenario["economic_output"]["units_per_day_delta"]["value"] == 0.0)

# guard: throughput scaling without user-assumption basis is refused -----------
try:
    run_scenario(dataset_id, bottleneck, merged, "throughput_scaling", {"throughput_change": 0.10})
    verify("Throughput scaling refused without user_assumption basis", False, "no exception")
except EconomicsError as exc:
    verify("Throughput scaling refused without user_assumption basis", exc.code == "SCENARIO_NOT_SUPPORTED")

# 5) persistence, reload, reproducibility --------------------------------------
saved = econ_store.save_scenario(artifact_root, scenario)
reloaded = econ_store.get_scenario(artifact_root, scenario["scenario_id"])
verify("Scenario artifact persists and reloads",
       reloaded is not None and reloaded["scenario_id"] == scenario["scenario_id"])
registry = econ_store.list_scenarios(artifact_root)
verify("Scenario registry updated", any(e["scenario_id"] == scenario["scenario_id"] for e in registry))
for name in ("assumptions.json", "baseline.json", "scenario_registry.json", "metadata.json"):
    verify(f"Artifact exists: {name}", (artifact_root / "economics" / name).exists())

repeat = run_scenario(
    dataset_id, bottleneck, merged, "throughput_scaling",
    {"throughput_change": 0.10, "scaling_basis": "user_assumption"},
)
verify("Scenario reproducible (same id and values)",
       repeat["scenario_id"] == scenario["scenario_id"]
       and repeat["economic_output"]["daily_contribution_delta"]["value"] == delta_contrib)

# 6) no-fabrication language check ---------------------------------------------
serialized = json.dumps(scenario).lower()
for forbidden in ("guaranteed", "will increase", "confirmed saving", "actual profit"):
    verify(f"No forbidden phrase '{forbidden}'", forbidden not in serialized)
verify("Limitations recorded", len(scenario["limitations"]) >= 3)

# 7) isolate: a fresh dataset id must not inherit these assumptions -------------
fresh = econ_store.get_assumptions(artifact_root, "different_dataset_id")
verify("Assumptions isolated per dataset id", fresh["assumptions"]["contribution_margin_per_unit"]["value"] is None)

print(f"\n    duration: {time.time() - t0:.1f}s")

print("\n" + "=" * 96)
print(f"RESULT: {'ALL CHECKS PASSED' if not failures else str(len(failures)) + ' FAILURES'}")
for failure in failures:
    print(f"  FAILED: {failure}")
print("=" * 96)
raise SystemExit(1 if failures else 0)
