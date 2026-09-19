"""Recommendation engine runner.

Reads Phase 6/7/8 artifacts, activates deterministic rules, validates language
safety, deduplicates, ranks with a transparent priority formula, and persists
recommendations plus a machine-readable decision summary.

No LLM. No fabricated evidence. Deterministic for identical inputs.
"""

from __future__ import annotations

import hashlib
import json
import platform
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from ..pipeline.artifacts import write_json
from .language import validate_recommendation
from .rules import (
    ENGINE_VERSION,
    build_recommendation,
    compute_priority,
    rule_anomaly_review,
    rule_cycle_time,
    rule_data_gap_economics,
    rule_data_gap_vision,
    rule_drift,
    rule_high_utilization,
    rule_queue_bottleneck,
    rule_scenario,
)


def _versions() -> dict:
    return {
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "pandas": pd.__version__,
        "numpy": np.__version__,
        "recommendation_engine": ENGINE_VERSION,
    }


def _load_json(path: Path) -> dict | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return None


def _load_latest(artifact_root: Path, folder: str) -> dict | None:
    registry = _load_json(Path(artifact_root) / folder / "analysis_registry.json") or []
    if not registry:
        return None
    return _load_json(Path(artifact_root) / folder / "findings" / f"{registry[-1]['analysis_id']}.json")


def _load_latest_scenario(artifact_root: Path) -> dict | None:
    registry = _load_json(Path(artifact_root) / "economics" / "scenario_registry.json") or []
    if not registry:
        return None
    return _load_json(Path(artifact_root) / "economics" / "scenarios" / f"{registry[-1]['scenario_id']}.json")


def generate_recommendations(
    dataset_id: str,
    contract: dict,
    artifact_root: Path,
    seed: int = 42,
) -> dict:
    started = time.time()
    artifact_root = Path(artifact_root)
    output_dir = artifact_root / "recommendations"
    output_dir.mkdir(parents=True, exist_ok=True)

    bottleneck = _load_latest(artifact_root, "bottleneck")
    root_cause = _load_latest(artifact_root, "root_cause")
    scenario = _load_latest_scenario(artifact_root)
    assumptions = _load_json(artifact_root / "economics" / "assumptions.json")
    vision = (contract or {}).get("vision") or {}

    station = ((bottleneck or {}).get("candidate_bottleneck") or {}).get("station") if bottleneck else None
    has_scenario = bool(scenario)
    has_economics = bool(
        scenario
        and ((scenario.get("economic_output") or {}).get("daily_contribution_delta") or {}).get("status") == "CALCULATED"
    )

    candidates: list[dict] = []
    rule_trace: list[dict] = []

    def attempt(rule_name: str, produced: dict | None) -> None:
        if produced is None:
            rule_trace.append({"rule": rule_name, "activated": False})
            return
        errors = validate_recommendation(produced)
        if errors:
            rule_trace.append({"rule": rule_name, "activated": True, "rejected": errors})
            return
        priority = compute_priority(
            produced["evidence_quality"],
            bottleneck_relevant=produced.get("station") is not None and produced.get("station") == station,
            has_scenario=has_scenario and produced["action_type"] == "EVALUATE_CAPACITY_IMPROVEMENT",
            has_economics=has_economics and produced["action_type"] == "EVALUATE_CAPACITY_IMPROVEMENT",
        )
        produced["priority"] = priority["score"]
        produced["priority_components"] = priority
        candidates.append(produced)
        rule_trace.append({"rule": rule_name, "activated": True, "recommendation_id": produced["recommendation_id"]})

    attempt("high_utilization", rule_high_utilization(dataset_id, bottleneck, root_cause) if bottleneck else None)
    attempt("queue_bottleneck", rule_queue_bottleneck(dataset_id, bottleneck) if bottleneck else None)
    attempt("cycle_time", rule_cycle_time(dataset_id, bottleneck) if bottleneck else None)
    attempt("process_drift", rule_drift(dataset_id, root_cause))
    attempt("anomaly_review", rule_anomaly_review(dataset_id, bottleneck, root_cause) if bottleneck else None)
    attempt("scenario", rule_scenario(dataset_id, scenario))
    attempt("data_gap_economics", rule_data_gap_economics(dataset_id, assumptions, scenario))
    attempt("data_gap_vision", rule_data_gap_vision(dataset_id, vision))

    # deduplicate by (action_type, target)
    deduped: dict[tuple[str, str], dict] = {}
    duplicates: list[str] = []
    for recommendation in candidates:
        key = (recommendation["action_type"], recommendation["target"])
        if key in deduped:
            duplicates.append(recommendation["recommendation_id"])
            continue
        deduped[key] = recommendation

    final = sorted(
        deduped.values(),
        key=lambda r: (-(r["priority"] or 0), r["action_type"], r["target"]),
    )
    for index, recommendation in enumerate(final, start=1):
        recommendation["rank"] = index

    decision_summary = {
        "dataset_id": dataset_id,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "engine_version": ENGINE_VERSION,
        "situation": {
            "bottleneck_analysis_id": (bottleneck or {}).get("analysis_id"),
            "candidate_bottleneck": station,
            "candidate_evidence_quality": (((bottleneck or {}).get("candidate_bottleneck") or {}).get("evidence_quality") or {}).get("label"),
            "root_cause_analysis_id": (root_cause or {}).get("analysis_id"),
            "root_cause_target": ((root_cause or {}).get("target") or {}).get("target"),
            "drift_status": ((root_cause or {}).get("drift") or {}).get("status"),
            "scenario_id": (scenario or {}).get("scenario_id"),
            "vision_status": vision.get("status", "NOT_SUPPORTED"),
        },
        "quality_status": ((root_cause or {}).get("coverage") or {}).get("modules", {}).get("vision_inspection", {}).get("status", "NOT_SUPPORTED"),
        "process_status": {
            "stations_analyzed": (bottleneck or {}).get("stations_analyzed"),
            "flow_graph_status": ((bottleneck or {}).get("flow") or {}).get("graph", {}).get("status"),
        },
        "bottleneck_status": {
            "station": station,
            "status": ((bottleneck or {}).get("candidate_bottleneck") or {}).get("status"),
            "evidence_quality": (((bottleneck or {}).get("candidate_bottleneck") or {}).get("evidence_quality") or {}).get("label"),
        },
        "throughput_status": {
            "observed_comparison_available": bool(
                ((((bottleneck or {}).get("what_if_inputs") or {}).get("observed_impact") or {}).get("observed"))
            ),
            "epistemic_status": "OBSERVED COMPARISON",
        },
        "economic_status": {
            "scenario_available": has_scenario,
            "economics_calculated": has_economics,
            "currency": (scenario or {}).get("baseline", {}).get("economics", {}).get("currency") if scenario else None,
        },
        "recommendations": [r["recommendation_id"] for r in final],
        "data_gaps": [
            {
                "gap": r["target"],
                "action_type": r["action_type"],
                "why": r["why"],
            }
            for r in final
            if r.get("data_requirement")
        ],
        "assumptions": [
            {
                "field": field,
                "value": (entry or {}).get("value"),
                "unit": (entry or {}).get("unit"),
                "source": (entry or {}).get("source"),
            }
            for field, entry in ((assumptions or {}).get("assumptions") or {}).items()
            if (entry or {}).get("value") is not None
        ],
        "limitations": [
            "All recommendations are advisory decision support, not machine-control commands.",
            "Evidence reflects statistical association and model contribution, not proven causation.",
            "Simulated effects are assumption-dependent and are not forecasts.",
        ],
        "epistemic_status": "ADVISORY",
    }

    payload = {
        "dataset_id": dataset_id,
        "status": "complete",
        "generated_at": decision_summary["generated_at"],
        "engine_version": ENGINE_VERSION,
        "seed": seed,
        "rule_trace": rule_trace,
        "duplicates_removed": duplicates,
        "recommendation_count": len(final),
        "recommendations": final,
        "decision_summary": decision_summary,
        "source_artifacts": [
            "bottleneck/analysis_registry.json",
            "root_cause/analysis_registry.json",
            "economics/scenario_registry.json",
            "economics/assumptions.json",
            "profile.json",
        ],
        "versions": _versions(),
        "total_duration_s": round(time.time() - started, 3),
    }

    # persist
    _persist(output_dir, payload)
    return payload


def _persist(output_dir: Path, payload: dict) -> None:
    recommendations_dir = output_dir / "recommendations"
    recommendations_dir.mkdir(parents=True, exist_ok=True)
    for recommendation in payload["recommendations"]:
        write_json(recommendations_dir / f"{recommendation['recommendation_id']}.json", recommendation)
    write_json(
        output_dir / "recommendation_registry.json",
        [
            {
                "recommendation_id": r["recommendation_id"],
                "action_type": r["action_type"],
                "title": r["title"],
                "target": r["target"],
                "station": r["station"],
                "priority": r["priority"],
                "evidence_quality": r["evidence_quality"],
                "rank": r["rank"],
                "generated_at": r["generated_at"],
            }
            for r in payload["recommendations"]
        ],
    )
    write_json(output_dir / "decision_summary.json", payload["decision_summary"])
    write_json(
        output_dir / "metadata.json",
        {
            "dataset_id": payload["dataset_id"],
            "engine_version": payload["engine_version"],
            "generated_at": payload["generated_at"],
            "recommendation_count": payload["recommendation_count"],
            "versions": payload["versions"],
        },
    )
    write_json(output_dir / "latest_run.json", payload)


def list_recommendations(artifact_root: Path) -> list[dict]:
    registry = _load_json(Path(artifact_root) / "recommendations" / "recommendation_registry.json")
    return registry or []


def get_recommendation(artifact_root: Path, recommendation_id: str) -> dict | None:
    return _load_json(Path(artifact_root) / "recommendations" / "recommendations" / f"{recommendation_id}.json")


def get_decision_summary(artifact_root: Path) -> dict | None:
    return _load_json(Path(artifact_root) / "recommendations" / "decision_summary.json")


def latest_run(artifact_root: Path) -> dict | None:
    return _load_json(Path(artifact_root) / "recommendations" / "latest_run.json")
