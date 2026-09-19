"""Transparent economic calculations.

Every number is produced by an explicit equation with named inputs. If a
required input is missing, the result is NOT_AVAILABLE with the exact list of
missing fields - never a default.

Epistemic labels used:
  DATA_DERIVED      baseline throughput taken from the dataset
  USER_ASSUMPTION   margin / costs / hours supplied by the user
  CALCULATED        arithmetic over observed + assumed inputs
  SIMULATED         scenario outcome from the scenario model
  ADVISORY          recommendation-level output
"""

from __future__ import annotations

from .assumptions import currency_of, get_value

NOT_AVAILABLE = "NOT_AVAILABLE"


def _block(value, *, label: str, missing: list[str], formula: str, inputs: dict) -> dict:
    if missing:
        return {
            "status": NOT_AVAILABLE,
            "value": None,
            "missing_inputs": missing,
            "formula": formula,
            "inputs": inputs,
            "epistemic_status": "NOT_AVAILABLE",
        }
    return {
        "status": "CALCULATED",
        "value": round(float(value), 6),
        "missing_inputs": [],
        "formula": formula,
        "inputs": inputs,
        "epistemic_status": label,
    }


def baseline_economics(
    throughput_per_hour: float | None,
    assumptions: dict,
) -> dict:
    """Daily / monthly contribution associated with observed throughput.

    Requires: throughput_per_hour (DATA_DERIVED), contribution_margin_per_unit
    (USER_ASSUMPTION), working_hours_per_day (USER_ASSUMPTION).
    """
    currency = currency_of(assumptions)
    margin = get_value(assumptions, "contribution_margin_per_unit")
    hours = get_value(assumptions, "working_hours_per_day")
    days = get_value(assumptions, "working_days_per_month")

    missing = [
        name
        for name, value in (
            ("throughput_per_hour", throughput_per_hour),
            ("contribution_margin_per_unit", margin),
            ("working_hours_per_day", hours),
            ("currency", currency),
        )
        if value is None
    ]
    inputs = {
        "throughput_per_hour": throughput_per_hour,
        "contribution_margin_per_unit": margin,
        "working_hours_per_day": hours,
        "working_days_per_month": days,
        "currency": currency,
    }

    daily_units = None
    if throughput_per_hour is not None and hours is not None:
        daily_units = throughput_per_hour * hours
    daily_contribution = None
    if daily_units is not None and margin is not None:
        daily_contribution = daily_units * margin
    monthly_contribution = None
    if daily_contribution is not None and days is not None:
        monthly_contribution = daily_contribution * days

    return {
        "currency": currency,
        "throughput_per_hour": {
            "value": throughput_per_hour,
            "epistemic_status": "DATA_DERIVED" if throughput_per_hour is not None else "NOT_AVAILABLE",
            "source": "Phase 3/7 artifacts (observed output column mean)",
        },
        "units_per_day": _block(
            daily_units,
            label="CALCULATED",
            missing=missing if daily_units is None else [],
            formula="throughput_per_hour * working_hours_per_day",
            inputs=inputs,
        ),
        "daily_contribution": _block(
            daily_contribution,
            label="CALCULATED",
            missing=missing if daily_contribution is None else [],
            formula="throughput_per_hour * working_hours_per_day * contribution_margin_per_unit",
            inputs=inputs,
        ),
        "monthly_contribution": _block(
            monthly_contribution,
            label="CALCULATED",
            missing=(missing + (["working_days_per_month"] if days is None else []))
            if monthly_contribution is None
            else [],
            formula="daily_contribution * working_days_per_month",
            inputs=inputs,
        ),
        "assumption_inputs": {
            field: (assumptions.get("assumptions", {}).get(field) or {})
            for field in ("contribution_margin_per_unit", "working_hours_per_day", "working_days_per_month")
        },
        "note": "Contribution figures are calculations over observed throughput and user assumptions; they are not profit statements.",
    }


def scenario_economics(
    baseline_daily_units: float | None,
    scenario_daily_units: float | None,
    assumptions: dict,
) -> dict:
    """Economic delta between baseline and scenario daily units.

    Requires: both unit figures (CALCULATED), contribution margin (USER_ASSUMPTION).
    """
    currency = currency_of(assumptions)
    margin = get_value(assumptions, "contribution_margin_per_unit")
    missing = [
        name
        for name, value in (
            ("baseline_daily_units", baseline_daily_units),
            ("scenario_daily_units", scenario_daily_units),
            ("contribution_margin_per_unit", margin),
            ("currency", currency),
        )
        if value is None
    ]
    delta_units = None
    if baseline_daily_units is not None and scenario_daily_units is not None:
        delta_units = scenario_daily_units - baseline_daily_units
    delta_contribution = None
    if delta_units is not None and margin is not None:
        delta_contribution = delta_units * margin

    inputs = {
        "baseline_daily_units": baseline_daily_units,
        "scenario_daily_units": scenario_daily_units,
        "contribution_margin_per_unit": margin,
        "currency": currency,
    }
    return {
        "currency": currency,
        "units_per_day_delta": _block(
            delta_units,
            label="CALCULATED",
            missing=missing if delta_units is None else [],
            formula="scenario_daily_units - baseline_daily_units",
            inputs=inputs,
        ),
        "daily_contribution_delta": _block(
            delta_contribution,
            label="SIMULATED",
            missing=missing if delta_contribution is None else [],
            formula="(scenario_daily_units - baseline_daily_units) * contribution_margin_per_unit",
            inputs=inputs,
        ),
        "monthly_contribution_delta": (
            _block(
                delta_contribution * get_value(assumptions, "working_days_per_month"),
                label="SIMULATED",
                missing=(["working_days_per_month"] if get_value(assumptions, "working_days_per_month") is None else []),
                formula="daily_contribution_delta * working_days_per_month",
                inputs=inputs,
            )
            if delta_contribution is not None and get_value(assumptions, "working_days_per_month") is not None
            else _block(
                None,
                label="SIMULATED",
                missing=missing + (["working_days_per_month"] if get_value(assumptions, "working_days_per_month") is None else []),
                formula="daily_contribution_delta * working_days_per_month",
                inputs=inputs,
            )
        ),
        "epistemic_status": "SIMULATED - assumption-dependent, not a guaranteed outcome",
        "note": "The delta depends entirely on the scenario model and user-supplied margin.",
    }


def cost_blocks(assumptions: dict, units_delta: float | None) -> dict:
    """Additional cost lines, each independently gated on its own inputs."""
    currency = currency_of(assumptions)
    scrap_rate = get_value(assumptions, "expected_defect_rate")
    rework_rate = get_value(assumptions, "expected_rework_rate")
    scrap_cost = get_value(assumptions, "scrap_cost_per_unit")
    rework_cost = get_value(assumptions, "rework_cost_per_unit")
    downtime_hours = get_value(assumptions, "downtime_hours_per_day")
    downtime_cost = get_value(assumptions, "downtime_cost_per_hour")
    operating_hours = get_value(assumptions, "working_hours_per_day")
    operating_cost = get_value(assumptions, "operating_cost_per_hour")

    blocks: dict[str, dict] = {}
    blocks["scrap"] = _block(
        (units_delta * scrap_rate * scrap_cost) if (units_delta is not None and scrap_rate is not None and scrap_cost is not None) else None,
        label="CALCULATED",
        missing=[name for name, value in (("units_delta", units_delta), ("expected_defect_rate", scrap_rate), ("scrap_cost_per_unit", scrap_cost)) if value is None],
        formula="units_delta * expected_defect_rate * scrap_cost_per_unit",
        inputs={"currency": currency},
    )
    blocks["rework"] = _block(
        (units_delta * rework_rate * rework_cost) if (units_delta is not None and rework_rate is not None and rework_cost is not None) else None,
        label="CALCULATED",
        missing=[name for name, value in (("units_delta", units_delta), ("expected_rework_rate", rework_rate), ("rework_cost_per_unit", rework_cost)) if value is None],
        formula="units_delta * expected_rework_rate * rework_cost_per_unit",
        inputs={"currency": currency},
    )
    blocks["downtime"] = _block(
        (downtime_hours * downtime_cost) if (downtime_hours is not None and downtime_cost is not None) else None,
        label="CALCULATED",
        missing=[name for name, value in (("downtime_hours_per_day", downtime_hours), ("downtime_cost_per_hour", downtime_cost)) if value is None],
        formula="downtime_hours_per_day * downtime_cost_per_hour",
        inputs={"currency": currency},
    )
    blocks["operating"] = _block(
        (operating_hours * operating_cost) if (operating_hours is not None and operating_cost is not None) else None,
        label="CALCULATED",
        missing=[name for name, value in (("working_hours_per_day", operating_hours), ("operating_cost_per_hour", operating_cost)) if value is None],
        formula="working_hours_per_day * operating_cost_per_hour",
        inputs={"currency": currency},
    )
    return blocks


def net_impact(delta_contribution: float | None, costs: dict) -> dict:
    cost_values = [
        block["value"] for block in costs.values() if block.get("status") == "CALCULATED" and block.get("value") is not None
    ]
    if delta_contribution is None and not cost_values:
        return {
            "status": NOT_AVAILABLE,
            "value": None,
            "formula": "daily_contribution_delta - sum(calculated_cost_blocks)",
            "missing_inputs": ["daily_contribution_delta", "at least one cost block"],
            "epistemic_status": NOT_AVAILABLE,
        }
    total_costs = sum(cost_values) if cost_values else 0.0
    value = (delta_contribution or 0.0) - total_costs
    return {
        "status": "CALCULATED",
        "value": round(float(value), 6),
        "cost_total": round(float(total_costs), 6),
        "formula": "daily_contribution_delta - sum(calculated_cost_blocks)",
        "cost_blocks_included": [name for name, block in costs.items() if block.get("status") == "CALCULATED"],
        "cost_blocks_missing": [name for name, block in costs.items() if block.get("status") != "CALCULATED"],
        "epistemic_status": "CALCULATED (assumption-dependent)",
        "note": "Net impact is only as reliable as the supplied assumptions; blocks marked missing were excluded.",
    }


def break_even(assumptions: dict) -> dict:
    """Minimum daily improvement needed to cover a supplied intervention cost."""
    currency = currency_of(assumptions)
    intervention_cost = get_value(assumptions, "intervention_cost")
    margin = get_value(assumptions, "contribution_margin_per_unit")
    if intervention_cost is None or margin is None or margin <= 0:
        return {
            "status": "NOT_AVAILABLE",
            "reason": "intervention_cost and contribution_margin_per_unit must both be supplied (margin > 0).",
            "required_daily_units_improvement": None,
            "epistemic_status": "NOT_AVAILABLE",
        }
    # simplest defensible break-even: units needed per day to recover the cost
    # over one month of working days, or per-day recovery if no month defined
    days = get_value(assumptions, "working_days_per_month")
    if days and days > 0:
        required_daily_units = intervention_cost / (margin * days)
        horizon = f"{days:g} working days"
    else:
        required_daily_units = intervention_cost / margin
        horizon = "1 day (no working_days_per_month supplied)"
    return {
        "status": "CALCULATED",
        "currency": currency,
        "intervention_cost": intervention_cost,
        "required_daily_units_improvement": round(float(required_daily_units), 6),
        "horizon": horizon,
        "formula": "intervention_cost / (contribution_margin_per_unit * working_days_per_month)",
        "epistemic_status": "CALCULATED (assumption-dependent)",
        "note": "Break-even is an arithmetic requirement, not a forecast.",
    }
