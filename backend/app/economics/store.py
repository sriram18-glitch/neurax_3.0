"""Economics persistence: assumptions, baselines, scenario registry."""

from __future__ import annotations

import json
import platform
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from .assumptions import assumptions_fingerprint, load_assumptions, save_assumptions
from .model import baseline_economics

ECONOMICS_ENGINE_VERSION = "1.0.0"


def versions() -> dict:
    return {
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "pandas": pd.__version__,
        "numpy": np.__version__,
        "economics_engine": ECONOMICS_ENGINE_VERSION,
    }


def economics_dir(artifact_root: Path) -> Path:
    path = Path(artifact_root) / "economics"
    path.mkdir(parents=True, exist_ok=True)
    (path / "scenarios").mkdir(parents=True, exist_ok=True)
    return path


def get_assumptions(artifact_root: Path, dataset_id: str) -> dict:
    return load_assumptions(economics_dir(artifact_root) / "assumptions.json", dataset_id)


def put_assumptions(artifact_root: Path, dataset_id: str, payload: dict) -> None:
    save_assumptions(economics_dir(artifact_root) / "assumptions.json", payload)


def latest_bottleneck(artifact_root: Path) -> dict | None:
    registry_path = Path(artifact_root) / "bottleneck" / "analysis_registry.json"
    if not registry_path.exists():
        return None
    try:
        registry = json.loads(registry_path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return None
    if not registry:
        return None
    finding_path = Path(artifact_root) / "bottleneck" / "findings" / f"{registry[-1]['analysis_id']}.json"
    if not finding_path.exists():
        return None
    try:
        return json.loads(finding_path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return None


def compute_baseline(artifact_root: Path, dataset_id: str) -> dict:
    bottleneck = latest_bottleneck(artifact_root)
    assumptions = get_assumptions(artifact_root, dataset_id)
    what_if = (bottleneck or {}).get("what_if_inputs") or {}
    observed = ((what_if.get("observed_impact") or {}).get("observed") or {})
    throughput = None
    source = None
    if observed:
        column = next(iter(observed))
        throughput = observed[column].get("unconstrained_mean")
        source = f"Phase 7 observed comparison '{column}' (unconstrained group mean)"
    if throughput is None:
        throughput = what_if.get("throughput")
        source = "Phase 7 what_if_inputs.throughput" if throughput is not None else None

    baseline = baseline_economics(throughput, assumptions)
    payload = {
        "dataset_id": dataset_id,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "engine_version": ECONOMICS_ENGINE_VERSION,
        "bottleneck_analysis_id": (bottleneck or {}).get("analysis_id"),
        "bottleneck_station": ((bottleneck or {}).get("candidate_bottleneck") or {}).get("station"),
        "throughput_source": source,
        "assumptions_fingerprint": assumptions_fingerprint(assumptions),
        "currency": baseline["currency"],
        "baseline": baseline,
        "availability": {
            "bottleneck_available": bottleneck is not None,
            "throughput_available": throughput is not None,
            "assumptions_supplied": [
                field
                for field, entry in (assumptions.get("assumptions") or {}).items()
                if (entry or {}).get("value") is not None
            ],
        },
        "epistemic_status": "DATA_DERIVED throughput + USER_ASSUMPTION economics + CALCULATED results",
        "limitations": [
            "Baseline contribution is a calculation over observed throughput and user assumptions.",
            "No profit statement is made; only contribution-style arithmetic with supplied margin.",
        ],
        "versions": versions(),
    }
    _write_json(economics_dir(artifact_root) / "baseline.json", payload)
    return payload


def save_scenario(artifact_root: Path, payload: dict) -> dict:
    directory = economics_dir(artifact_root) / "scenarios"
    _write_json(directory / f"{payload['scenario_id']}.json", payload)
    registry_path = economics_dir(artifact_root) / "scenario_registry.json"
    registry: list[dict] = []
    if registry_path.exists():
        try:
            registry = json.loads(registry_path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            registry = []
    registry = [entry for entry in registry if entry.get("scenario_id") != payload["scenario_id"]]
    registry.append(
        {
            "scenario_id": payload["scenario_id"],
            "scenario_type": payload["scenario_type"],
            "station": payload["bottleneck"].get("station"),
            "generated_at": payload["generated_at"],
            "net_daily_impact": payload["economic_output"]["net_daily_impact"].get("value"),
            "epistemic_status": payload["epistemic_status"],
        }
    )
    _write_json(registry_path, registry)
    _write_json(
        economics_dir(artifact_root) / "metadata.json",
        {
            "dataset_id": payload["dataset_id"],
            "engine_version": ECONOMICS_ENGINE_VERSION,
            "last_scenario_id": payload["scenario_id"],
            "generated_at": payload["generated_at"],
            "versions": versions(),
        },
    )
    return {"scenario_id": payload["scenario_id"], "registry_entries": len(registry)}


def list_scenarios(artifact_root: Path) -> list[dict]:
    path = economics_dir(artifact_root) / "scenario_registry.json"
    if not path.exists():
        return []
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return []


def get_scenario(artifact_root: Path, scenario_id: str) -> dict | None:
    path = economics_dir(artifact_root) / "scenarios" / f"{scenario_id}.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return None


def _write_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, default=str)
