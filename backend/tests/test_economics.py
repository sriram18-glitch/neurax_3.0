"""Phase 8 test suite: economic impact & what-if simulation.

Unit tests use SYNTHETIC values (explicitly labelled) to validate formulas.
Real-data verification lives in verify_phase8_real.py.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from app.economics import (
    EconomicsError,
    baseline_economics,
    break_even,
    cost_blocks,
    empty_assumptions,
    net_impact,
    run_scenario,
    scenario_economics,
    sensitivity,
    validate_and_merge,
)
from app.economics import store as econ_store


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _assumptions_with(dataset_id: str = "d1", **values) -> dict:
    base = empty_assumptions(dataset_id)
    updates = dict(values)
    return validate_and_merge(base, updates)


def _bottleneck_fixture() -> dict:
    return {
        "analysis_id": "abc123def456",
        "candidate_bottleneck": {
            "station": "StationB",
            "evidence_score": 88.0,
            "evidence_quality": {"label": "MODERATE_EVIDENCE"},
            "status": "CANDIDATE_BOTTLENECK",
        },
        "what_if_inputs": {
            "station": "StationB",
            "current_utilization": {"available": True, "mean": 0.92, "max": 0.99, "samples": 600},
            "current_queue": {"available": True, "mean": 60.0, "max": 80.0, "samples": 600},
            "current_cycle_time": {"available": False, "reason": "NOT AVAILABLE FROM DATASET"},
            "observed_impact": {
                "status": "OBSERVED_COMPARISON",
                "observed": {
                    "Units": {
                        "output_column": "Units",
                        "constrained_mean": 950.0,
                        "unconstrained_mean": 1000.0,
                        "difference": -50.0,
                    }
                },
            },
            "throughput": None,
        },
    }


# ---------------------------------------------------------------------------
# A. ASSUMPTIONS
# ---------------------------------------------------------------------------

def test_empty_assumptions_all_not_provided():
    payload = empty_assumptions("d1")
    assert payload["currency"]["value"] is None
    for entry in payload["assumptions"].values():
        assert entry["value"] is None
        assert entry["source"] == "NOT_PROVIDED"


def test_validate_merge_accepts_valid_values():
    payload = _assumptions_with(
        currency="inr",
        contribution_margin_per_unit=25.5,
        working_hours_per_day=8,
        working_days_per_month=22,
    )
    assert payload["currency"]["value"] == "INR"
    assert payload["currency"]["source"] == "USER_ASSUMPTION"
    entry = payload["assumptions"]["contribution_margin_per_unit"]
    assert entry["value"] == 25.5
    assert entry["source"] == "USER_ASSUMPTION"
    assert entry["unit"] == "currency/unit"
    assert entry["provided_at"]


def test_validate_merge_rejects_unknown_field():
    with pytest.raises(EconomicsError) as excinfo:
        validate_and_merge(empty_assumptions("d1"), {"selling_price": 10})
    assert excinfo.value.code == "UNKNOWN_ASSUMPTION"


def test_validate_merge_rejects_negative_and_invalid():
    with pytest.raises(EconomicsError):
        validate_and_merge(empty_assumptions("d1"), {"contribution_margin_per_unit": -5})
    with pytest.raises(EconomicsError):
        validate_and_merge(empty_assumptions("d1"), {"working_hours_per_day": 30})
    with pytest.raises(EconomicsError):
        validate_and_merge(empty_assumptions("d1"), {"contribution_margin_per_unit": "abc"})
    with pytest.raises(EconomicsError):
        validate_and_merge(empty_assumptions("d1"), {"expected_defect_rate": 1.5})


def test_validate_merge_can_clear_value():
    payload = _assumptions_with(contribution_margin_per_unit=10)
    cleared = validate_and_merge(payload, {"contribution_margin_per_unit": None})
    assert cleared["assumptions"]["contribution_margin_per_unit"]["value"] is None
    assert cleared["assumptions"]["contribution_margin_per_unit"]["source"] == "NOT_PROVIDED"


# ---------------------------------------------------------------------------
# B. BASELINE ECONOMICS (synthetic formula validation)
# ---------------------------------------------------------------------------

def test_baseline_not_available_without_assumptions():
    baseline = baseline_economics(100.0, empty_assumptions("d1"))
    assert baseline["units_per_day"]["status"] == "NOT_AVAILABLE"
    assert "contribution_margin_per_unit" in baseline["units_per_day"]["missing_inputs"]
    assert baseline["daily_contribution"]["status"] == "NOT_AVAILABLE"


def test_baseline_calculates_exact_values():
    # SYNTHETIC: 100 units/hour * 8 h * 25 = 20000/day; * 22 days = 440000/month
    assumptions = _assumptions_with(
        currency="INR",
        contribution_margin_per_unit=25,
        working_hours_per_day=8,
        working_days_per_month=22,
    )
    baseline = baseline_economics(100.0, assumptions)
    assert baseline["units_per_day"]["value"] == 800.0
    assert baseline["daily_contribution"]["value"] == 20000.0
    assert baseline["monthly_contribution"]["value"] == 440000.0
    assert baseline["throughput_per_hour"]["epistemic_status"] == "DATA_DERIVED"
    assert baseline["daily_contribution"]["epistemic_status"] == "CALCULATED"


def test_baseline_missing_throughput_is_not_available():
    assumptions = _assumptions_with(currency="USD", contribution_margin_per_unit=5, working_hours_per_day=8)
    baseline = baseline_economics(None, assumptions)
    assert baseline["units_per_day"]["status"] == "NOT_AVAILABLE"


# ---------------------------------------------------------------------------
# C. SCENARIO ECONOMICS
# ---------------------------------------------------------------------------

def test_scenario_economics_delta_formula():
    # SYNTHETIC: (900-800) units * 25 = 2500/day; * 22 = 55000/month
    assumptions = _assumptions_with(
        currency="INR", contribution_margin_per_unit=25, working_days_per_month=22
    )
    result = scenario_economics(800.0, 900.0, assumptions)
    assert result["units_per_day_delta"]["value"] == 100.0
    assert result["daily_contribution_delta"]["value"] == 2500.0
    assert result["monthly_contribution_delta"]["value"] == 55000.0
    assert "SIMULATED" in result["daily_contribution_delta"]["epistemic_status"]


def test_cost_blocks_gated_on_inputs():
    assumptions = _assumptions_with(
        currency="INR",
        expected_defect_rate=0.02,
        scrap_cost_per_unit=50,
    )
    blocks = cost_blocks(assumptions, units_delta=100.0)
    assert blocks["scrap"]["status"] == "CALCULATED"
    assert blocks["scrap"]["value"] == pytest.approx(100.0)
    assert blocks["rework"]["status"] == "NOT_AVAILABLE"
    assert blocks["downtime"]["status"] == "NOT_AVAILABLE"
    assert blocks["operating"]["status"] == "NOT_AVAILABLE"


def test_net_impact_subtracts_only_calculated_costs():
    assumptions = _assumptions_with(
        currency="INR",
        expected_defect_rate=0.02,
        scrap_cost_per_unit=50,
        expected_rework_rate=0.01,
        rework_cost_per_unit=100,
    )
    blocks = cost_blocks(assumptions, units_delta=100.0)
    result = net_impact(5000.0, blocks)
    assert result["status"] == "CALCULATED"
    # scrap 100*0.02*50=100; rework 100*0.01*100=100; net = 5000-200=4800
    assert result["value"] == pytest.approx(4800.0)
    assert "downtime" in result["cost_blocks_missing"]


def test_break_even_requires_intervention_cost():
    assumptions = _assumptions_with(currency="INR", contribution_margin_per_unit=25)
    result = break_even(assumptions)
    assert result["status"] == "NOT_AVAILABLE"


def test_break_even_calculation():
    # SYNTHETIC: cost 55000, margin 25, 22 days -> 100 units/day needed
    assumptions = _assumptions_with(
        currency="INR", contribution_margin_per_unit=25, working_days_per_month=22, intervention_cost=55000
    )
    result = break_even(assumptions)
    assert result["status"] == "CALCULATED"
    assert result["required_daily_units_improvement"] == pytest.approx(100.0)


# ---------------------------------------------------------------------------
# D. SCENARIO ENGINE
# ---------------------------------------------------------------------------

def test_utilization_scenario_runs_and_does_not_extrapolate_throughput():
    assumptions = _assumptions_with(currency="INR", contribution_margin_per_unit=25, working_hours_per_day=8)
    result = run_scenario("d1", _bottleneck_fixture(), assumptions, "utilization_reduction", {"utilization_reduction": 0.10})
    assert result["scenario_type"] == "utilization_reduction"
    metric = result["scenario"]["metrics"]["utilization"]
    assert metric["baseline"] == 0.92
    assert metric["scenario"] == pytest.approx(0.92 * 0.9)
    assert any("NOT extrapolated" in warning for warning in result["warnings"])
    assert result["economic_output"]["units_per_day_delta"]["value"] == pytest.approx(0.0)


def test_throughput_scaling_requires_user_assumption_basis():
    assumptions = _assumptions_with(currency="INR", contribution_margin_per_unit=25, working_hours_per_day=8)
    with pytest.raises(EconomicsError) as excinfo:
        run_scenario("d1", _bottleneck_fixture(), assumptions, "throughput_scaling", {"throughput_change": 0.1})
    assert excinfo.value.code == "SCENARIO_NOT_SUPPORTED"


def test_throughput_scaling_with_basis_calculates_economics():
    # SYNTHETIC: baseline 1000/h, +10% -> 1100/h; 8h -> +800 units/day; *25 = +20000/day
    assumptions = _assumptions_with(currency="INR", contribution_margin_per_unit=25, working_hours_per_day=8)
    result = run_scenario(
        "d1",
        _bottleneck_fixture(),
        assumptions,
        "throughput_scaling",
        {"throughput_change": 0.10, "scaling_basis": "user_assumption"},
    )
    assert result["baseline"]["throughput_per_hour"] == 1000.0
    assert result["scenario"]["metrics"]["throughput_per_hour"]["scenario"] == pytest.approx(1100.0)
    assert result["economic_output"]["units_per_day_delta"]["value"] == pytest.approx(800.0)
    assert result["economic_output"]["daily_contribution_delta"]["value"] == pytest.approx(20000.0)
    assert "user assumption" in result["warnings"][0].lower()


def test_scenario_rejects_unsupported_type_and_bad_change():
    assumptions = _assumptions_with(currency="INR", contribution_margin_per_unit=25)
    with pytest.raises(EconomicsError):
        run_scenario("d1", _bottleneck_fixture(), assumptions, "time_travel", {})
    with pytest.raises(EconomicsError):
        run_scenario("d1", _bottleneck_fixture(), assumptions, "utilization_reduction", {"utilization_reduction": 1.5})
    with pytest.raises(EconomicsError):
        run_scenario("d1", _bottleneck_fixture(), assumptions, "utilization_reduction", {"utilization_reduction": -0.1})


def test_scenario_without_utilization_is_not_supported():
    bottleneck = _bottleneck_fixture()
    bottleneck["what_if_inputs"]["current_utilization"] = {"available": False, "reason": "NOT AVAILABLE FROM DATASET"}
    assumptions = _assumptions_with(currency="INR", contribution_margin_per_unit=25)
    with pytest.raises(EconomicsError) as excinfo:
        run_scenario("d1", bottleneck, assumptions, "utilization_reduction", {"utilization_reduction": 0.1})
    assert excinfo.value.code == "SCENARIO_NOT_SUPPORTED"


def test_scenario_missing_margin_stays_not_available():
    assumptions = empty_assumptions("d1")
    result = run_scenario(
        "d1", _bottleneck_fixture(), assumptions, "throughput_scaling",
        {"throughput_change": 0.10, "scaling_basis": "user_assumption"},
    )
    assert result["economic_output"]["daily_contribution_delta"]["status"] == "NOT_AVAILABLE"
    assert "contribution_margin_per_unit" in result["economic_output"]["daily_contribution_delta"]["missing_inputs"]


def test_scenario_epistemic_labels():
    assumptions = _assumptions_with(currency="INR", contribution_margin_per_unit=25, working_hours_per_day=8)
    result = run_scenario(
        "d1", _bottleneck_fixture(), assumptions, "throughput_scaling",
        {"throughput_change": 0.10, "scaling_basis": "user_assumption"},
    )
    assert result["epistemic_status"].startswith("SIMULATED SCENARIO")
    assert result["baseline"]["epistemic_status"].startswith("DATA_DERIVED")
    assert result["scenario"]["epistemic_status"] == "SIMULATED"
    serialized = json.dumps(result).lower()
    for forbidden in ("guaranteed", "will increase", "actual profit", "confirmed saving"):
        assert forbidden not in serialized, forbidden


def test_scenario_reproducible_id():
    assumptions = _assumptions_with(currency="INR", contribution_margin_per_unit=25, working_hours_per_day=8)
    first = run_scenario(
        "d1", _bottleneck_fixture(), assumptions, "throughput_scaling",
        {"throughput_change": 0.10, "scaling_basis": "user_assumption"},
    )
    second = run_scenario(
        "d1", _bottleneck_fixture(), assumptions, "throughput_scaling",
        {"throughput_change": 0.10, "scaling_basis": "user_assumption"},
    )
    assert first["scenario_id"] == second["scenario_id"]


def test_sensitivity_sweep_uses_model():
    assumptions = _assumptions_with(currency="INR", contribution_margin_per_unit=25, working_hours_per_day=8)
    result = sensitivity(
        "d1", _bottleneck_fixture(), assumptions, "throughput_scaling", "throughput_change", [0.05, 0.10, 0.20]
    )
    values = [point["daily_contribution_delta"] for point in result["points"]]
    assert values == [pytest.approx(10000.0), pytest.approx(20000.0), pytest.approx(40000.0)]
    assert all(point["status"] == "SIMULATED" for point in result["points"])


# ---------------------------------------------------------------------------
# E. PERSISTENCE
# ---------------------------------------------------------------------------

def test_store_roundtrip(tmp_path):
    artifact_root = tmp_path / "artifacts" / "ds1"
    assumptions = _assumptions_with("ds1", currency="INR", contribution_margin_per_unit=25, working_hours_per_day=8)
    econ_store.put_assumptions(artifact_root, "ds1", assumptions)
    loaded = econ_store.get_assumptions(artifact_root, "ds1")
    assert loaded["assumptions"]["contribution_margin_per_unit"]["value"] == 25

    scenario = run_scenario(
        "ds1", _bottleneck_fixture(), assumptions, "throughput_scaling",
        {"throughput_change": 0.10, "scaling_basis": "user_assumption"},
    )
    econ_store.save_scenario(artifact_root, scenario)
    reloaded = econ_store.get_scenario(artifact_root, scenario["scenario_id"])
    assert reloaded is not None
    assert reloaded["scenario_id"] == scenario["scenario_id"]
    registry = econ_store.list_scenarios(artifact_root)
    assert any(entry["scenario_id"] == scenario["scenario_id"] for entry in registry)
    for name in ("assumptions.json", "scenario_registry.json", "metadata.json"):
        assert (artifact_root / "economics" / name).exists(), name


def test_store_isolated_per_dataset(tmp_path):
    root_a = tmp_path / "a" / "ds1"
    root_b = tmp_path / "b" / "ds2"
    econ_store.put_assumptions(root_a, "ds1", _assumptions_with("ds1", currency="INR", contribution_margin_per_unit=25))
    econ_store.put_assumptions(root_b, "ds2", _assumptions_with("ds2", currency="USD", contribution_margin_per_unit=99))
    assert econ_store.get_assumptions(root_a, "ds1")["assumptions"]["contribution_margin_per_unit"]["value"] == 25
    assert econ_store.get_assumptions(root_b, "ds2")["assumptions"]["contribution_margin_per_unit"]["value"] == 99
    assert econ_store.get_assumptions(root_a, "ds1")["currency"]["value"] == "INR"


# ---------------------------------------------------------------------------
# F. API
# ---------------------------------------------------------------------------

def _upload_and_analyze(client, tmp_path, name="econ_api.csv") -> str:
    rng = np.random.default_rng(9)
    rows = 500
    frame = pd.DataFrame(
        {
            "Time_Now": np.arange(rows),
            "StationA_Util": rng.uniform(0.3, 0.5, rows),
            "StationB_Util": rng.uniform(0.85, 0.99, rows),
            "StationA_Queue": rng.uniform(0, 2, rows),
            "StationB_Queue": rng.uniform(40, 80, rows),
            "Total parts": 900 + rng.normal(0, 10, rows),
        }
    )
    path = tmp_path / name
    frame.to_csv(path, index=False)
    with open(path, "rb") as fh:
        contract = client.post("/api/upload", files={"file": (path.name, fh, "text/csv")}).json()
    dataset_id = contract["dataset_id"]
    response = client.post(f"/api/datasets/{dataset_id}/bottleneck/analyze", json={})
    assert response.status_code == 200, response.text
    return dataset_id


def test_api_economics_flow(client, tmp_path):
    dataset_id = _upload_and_analyze(client, tmp_path)

    status = client.get(f"/api/datasets/{dataset_id}/economics/status").json()
    assert status["status"] == "READY"
    assert status["assumptions_supplied"] == []
    assert status["currency"] is None

    # assumptions before supply: everything NOT_PROVIDED
    assumptions = client.get(f"/api/datasets/{dataset_id}/economics/assumptions").json()
    assert assumptions["assumptions"]["contribution_margin_per_unit"]["value"] is None

    # baseline before assumptions: NOT_AVAILABLE
    baseline = client.get(f"/api/datasets/{dataset_id}/economics/baseline").json()
    assert baseline["baseline"]["daily_contribution"]["status"] == "NOT_AVAILABLE"

    # supply assumptions
    response = client.put(
        f"/api/datasets/{dataset_id}/economics/assumptions",
        json={
            "currency": "INR",
            "contribution_margin_per_unit": 25,
            "working_hours_per_day": 8,
            "working_days_per_month": 22,
        },
    )
    assert response.status_code == 200, response.text
    assert response.json()["currency"]["value"] == "INR"

    # invalid assumption
    bad = client.put(f"/api/datasets/{dataset_id}/economics/assumptions", json={"contribution_margin_per_unit": -1})
    assert bad.status_code == 422

    # baseline now calculated
    baseline = client.get(f"/api/datasets/{dataset_id}/economics/baseline").json()
    assert baseline["baseline"]["daily_contribution"]["status"] == "CALCULATED"
    assert baseline["currency"] == "INR"

    # scenario
    response = client.post(
        f"/api/datasets/{dataset_id}/economics/scenario",
        json={
            "scenario_type": "throughput_scaling",
            "changes": {"throughput_change": 0.10, "scaling_basis": "user_assumption"},
            "sensitivity": {"parameter": "throughput_change", "values": [0.05, 0.10]},
        },
    )
    assert response.status_code == 200, response.text
    scenario = response.json()
    assert scenario["epistemic_status"].startswith("SIMULATED")
    assert "sensitivity" in scenario
    scenario_id = scenario["scenario_id"]

    listing = client.get(f"/api/datasets/{dataset_id}/economics/scenarios").json()
    assert any(entry["scenario_id"] == scenario_id for entry in listing["scenarios"])

    fetched = client.get(f"/api/datasets/{dataset_id}/economics/{scenario_id}").json()
    assert fetched["scenario_id"] == scenario_id

    # what-if alias
    alias = client.post(
        f"/api/datasets/{dataset_id}/what-if",
        json={"scenario_type": "utilization_reduction", "changes": {"utilization_reduction": 0.1}},
    )
    assert alias.status_code == 200

    assert client.get(f"/api/datasets/{dataset_id}/economics/nonexistent").status_code == 404


def test_api_scenario_requires_bottleneck(client, tmp_path):
    frame = pd.DataFrame({"Demand": np.arange(300, dtype=float), "Total parts": np.arange(300, dtype=float)})
    path = tmp_path / "no_bottleneck.csv"
    frame.to_csv(path, index=False)
    with open(path, "rb") as fh:
        contract = client.post("/api/upload", files={"file": (path.name, fh, "text/csv")}).json()
    dataset_id = contract["dataset_id"]
    response = client.post(f"/api/datasets/{dataset_id}/economics/scenario", json={"scenario_type": "utilization_reduction", "changes": {}})
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "BOTTLENECK_NOT_ANALYZED"


def test_api_economics_unknown_dataset_404(client):
    assert client.get("/api/datasets/nope/economics/status").status_code == 404
    assert client.get("/api/datasets/nope/economics/assumptions").status_code == 404
