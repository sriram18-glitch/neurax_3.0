"""What-if scenario engine.

Scenario parameters act on the OBSERVED Phase 7 baseline through explicit,
documented transforms. Every transform is gated on data availability and
labelled SIMULATED. Nothing claims to predict the future.

Supported scenario types (only exposed when the underlying data exists):

A. utilization_reduction   : utilization *= (1 - change)  -> effective capacity uplift
B. throughput_scaling      : throughput  *= (1 + change)  -> ONLY when the user
                             explicitly opts in via `scaling_basis: "user_assumption"`,
                             because the observed relationship is demand-confounded.
C. demand_uplift           : units/day *= (1 + change)    -> demand-side what-if

The Phase 7 observed comparison is deliberately NOT auto-extrapolated into a
throughput prediction: the real Model_1 data shows high utilization co-occurring
with HIGHER throughput (demand confound). Auto-multiplying would fabricate a
relationship the data contradicts.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone

from .errors import EconomicsError
from .model import baseline_economics, cost_blocks, net_impact, scenario_economics

SCENARIO_TYPES = ("utilization_reduction", "throughput_scaling", "demand_uplift")
MAX_CHANGE = 0.95


def _scenario_id(dataset_id: str, bottleneck_id: str | None, scenario_type: str, changes: dict, seed: int) -> str:
    digest = hashlib.sha256(
        json.dumps(
            {"d": dataset_id, "b": bottleneck_id, "t": scenario_type, "c": changes, "s": seed},
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()
    return digest[:12]


def _validate_change(value, name: str) -> float:
    try:
        change = float(value)
    except (TypeError, ValueError):
        raise EconomicsError("INVALID_SCENARIO", f"'{name}' must be numeric.")
    if change != change or change in (float("inf"), float("-inf")):
        raise EconomicsError("INVALID_SCENARIO", f"'{name}' must be finite.")
    if abs(change) > MAX_CHANGE:
        raise EconomicsError("INVALID_SCENARIO", f"'{name}' magnitude must be <= {MAX_CHANGE} (95%).")
    return change


def run_scenario(
    dataset_id: str,
    bottleneck: dict | None,
    assumptions: dict,
    scenario_type: str,
    changes: dict,
    seed: int = 42,
) -> dict:
    if scenario_type not in SCENARIO_TYPES:
        raise EconomicsError(
            "UNSUPPORTED_SCENARIO",
            f"Scenario type '{scenario_type}' is not supported.",
            f"Supported types: {', '.join(SCENARIO_TYPES)}.",
        )

    what_if = (bottleneck or {}).get("what_if_inputs") or {}
    station = what_if.get("station")
    current_utilization = (what_if.get("current_utilization") or {}).get("mean") if what_if else None
    current_queue = (what_if.get("current_queue") or {}).get("mean") if what_if else None
    current_cycle = (what_if.get("current_cycle_time") or {}).get("mean") if what_if else None
    observed_impact = (what_if.get("observed_impact") or {}) if what_if else {}
    observed_block = (observed_impact.get("observed") or {}) if observed_impact else {}

    # baseline throughput: prefer the observed unconstrained group mean from Phase 7
    baseline_throughput = None
    baseline_source = None
    if observed_block:
        column = next(iter(observed_block))
        baseline_throughput = observed_block[column].get("unconstrained_mean")
        baseline_source = f"Phase 7 observed comparison, '{column}' unconstrained group mean"
    if baseline_throughput is None:
        baseline_throughput = what_if.get("throughput") if what_if else None
        baseline_source = "Phase 7 what_if_inputs.throughput" if baseline_throughput is not None else None

    baseline_econ = baseline_economics(baseline_throughput, assumptions)
    baseline_daily_units = baseline_econ["units_per_day"]["value"]

    scenario_metrics: dict = {}
    applied_changes: dict = {}
    simulation_method = None
    warnings: list[str] = []

    if scenario_type == "utilization_reduction":
        change = _validate_change(changes.get("utilization_reduction", 0.0), "utilization_reduction")
        if current_utilization is None:
            raise EconomicsError(
                "SCENARIO_NOT_SUPPORTED",
                "This dataset provides no utilization for the candidate bottleneck; utilization scenarios cannot be run.",
            )
        if change <= 0:
            raise EconomicsError("INVALID_SCENARIO", "utilization_reduction must be > 0.")
        scenario_utilization = current_utilization * (1.0 - change)
        applied_changes = {"utilization_reduction": change}
        scenario_metrics = {
            "utilization": {
                "baseline": round(current_utilization, 6),
                "scenario": round(scenario_utilization, 6),
                "epistemic_status": "SIMULATED",
            }
        }
        simulation_method = "analytical utilization transform (no throughput extrapolation)"
        warnings.append(
            "Throughput was NOT extrapolated from the utilization change: the observed comparison in this dataset is "
            "demand-confounded, so a utilization->throughput relationship is not established. The scenario reports the "
            "utilization shift only; supply 'throughput_scaling' if you want a user-assumption-based throughput scenario."
        )

    elif scenario_type == "throughput_scaling":
        change = _validate_change(changes.get("throughput_change", 0.0), "throughput_change")
        basis = changes.get("scaling_basis")
        if basis != "user_assumption":
            raise EconomicsError(
                "SCENARIO_NOT_SUPPORTED",
                "throughput_scaling requires 'scaling_basis': 'user_assumption' because the dataset does not establish "
                "a causal utilization->throughput relationship.",
                "This guard exists to prevent fabricated extrapolation from the demand-confounded observed comparison.",
            )
        if baseline_throughput is None:
            raise EconomicsError("SCENARIO_NOT_SUPPORTED", "No baseline throughput is available for this bottleneck.")
        scenario_throughput = baseline_throughput * (1.0 + change)
        applied_changes = {"throughput_change": change, "scaling_basis": basis}
        scenario_metrics = {
            "throughput_per_hour": {
                "baseline": round(baseline_throughput, 6),
                "scenario": round(scenario_throughput, 6),
                "epistemic_status": "SIMULATED (user-assumption scaling)",
            }
        }
        simulation_method = "user-assumption scaling of observed baseline throughput"
        warnings.append("This scaling is a user assumption, not a data-derived relationship.")

    elif scenario_type == "demand_uplift":
        change = _validate_change(changes.get("demand_change", 0.0), "demand_change")
        if baseline_daily_units is None:
            raise EconomicsError(
                "SCENARIO_NOT_SUPPORTED",
                "Daily units cannot be computed (missing throughput, margin or working hours); demand scenarios are unavailable.",
            )
        scenario_units = baseline_daily_units * (1.0 + change)
        applied_changes = {"demand_change": change}
        scenario_metrics = {
            "units_per_day": {
                "baseline": round(baseline_daily_units, 6),
                "scenario": round(scenario_units, 6),
                "epistemic_status": "SIMULATED",
            }
        }
        simulation_method = "demand-side scaling of calculated daily units"

    scenario_daily_units = None
    if "units_per_day" in scenario_metrics:
        scenario_daily_units = scenario_metrics["units_per_day"]["scenario"]
    elif "throughput_per_hour" in scenario_metrics:
        hours = baseline_econ["assumption_inputs"]["working_hours_per_day"].get("value")
        if hours is not None:
            scenario_daily_units = scenario_metrics["throughput_per_hour"]["scenario"] * hours
    elif baseline_daily_units is not None and scenario_type == "utilization_reduction":
        scenario_daily_units = baseline_daily_units  # utilization-only scenario: units unchanged

    economic = scenario_economics(baseline_daily_units, scenario_daily_units, assumptions)
    units_delta = economic["units_per_day_delta"]["value"]
    costs = cost_blocks(assumptions, units_delta)
    net = net_impact(economic["daily_contribution_delta"]["value"], costs)

    scenario_id = _scenario_id(dataset_id, (bottleneck or {}).get("analysis_id"), scenario_type, applied_changes, seed)
    return {
        "dataset_id": dataset_id,
        "scenario_id": scenario_id,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "bottleneck": {
            "analysis_id": (bottleneck or {}).get("analysis_id"),
            "station": station,
            "evidence_quality": ((bottleneck or {}).get("candidate_bottleneck") or {}).get("evidence_quality"),
            "status": ((bottleneck or {}).get("candidate_bottleneck") or {}).get("status"),
        },
        "scenario_type": scenario_type,
        "parameter_changes": applied_changes,
        "baseline": {
            "throughput_per_hour": baseline_throughput,
            "throughput_source": baseline_source,
            "units_per_day": baseline_daily_units,
            "utilization": current_utilization,
            "queue": current_queue,
            "cycle_time": current_cycle,
            "epistemic_status": "DATA_DERIVED (observed)",
            "economics": baseline_econ,
        },
        "scenario": {
            "metrics": scenario_metrics,
            "units_per_day": scenario_daily_units,
            "epistemic_status": "SIMULATED",
        },
        "economic_output": {
            "units_per_day_delta": economic["units_per_day_delta"],
            "daily_contribution_delta": economic["daily_contribution_delta"],
            "monthly_contribution_delta": economic["monthly_contribution_delta"],
            "cost_blocks": costs,
            "net_daily_impact": net,
            "epistemic_status": "SIMULATED + ASSUMPTION-DEPENDENT",
        },
        "simulation_method": simulation_method,
        "assumptions_snapshot": assumptions,
        "warnings": warnings,
        "limitations": [
            "Scenario outputs are simulations under stated assumptions, not forecasts or guarantees.",
            "The observed utilization/throughput comparison in this dataset is demand-confounded.",
            "No discrete-event simulation was performed; only transparent transforms were applied.",
            "Economic values depend entirely on user-supplied assumptions.",
        ],
        "epistemic_status": "SIMULATED SCENARIO - advisory decision support only",
        "seed": seed,
    }


def sensitivity(
    dataset_id: str,
    bottleneck: dict | None,
    assumptions: dict,
    scenario_type: str,
    parameter: str,
    values: list[float],
    seed: int = 42,
) -> dict:
    """Run the scenario model across a parameter sweep - no hardcoded curves."""
    if len(values) > 21:
        raise EconomicsError("INVALID_SCENARIO", "Sensitivity sweep is limited to 21 values.")
    points: list[dict] = []
    for value in values:
        changes = {parameter: float(value)}
        if scenario_type == "throughput_scaling":
            changes["scaling_basis"] = "user_assumption"
        try:
            result = run_scenario(dataset_id, bottleneck, assumptions, scenario_type, changes, seed=seed)
            points.append(
                {
                    "parameter_value": float(value),
                    "units_per_day_delta": result["economic_output"]["units_per_day_delta"]["value"],
                    "daily_contribution_delta": result["economic_output"]["daily_contribution_delta"]["value"],
                    "net_daily_impact": result["economic_output"]["net_daily_impact"]["value"],
                    "status": "SIMULATED",
                }
            )
        except EconomicsError as exc:
            points.append({"parameter_value": float(value), "status": "NOT_SUPPORTED", "reason": exc.message})
    return {
        "dataset_id": dataset_id,
        "scenario_type": scenario_type,
        "parameter": parameter,
        "points": points,
        "epistemic_status": "SIMULATED (sweep of the scenario model; curve shape comes from the model, not from a hardcoded relationship)",
    }
