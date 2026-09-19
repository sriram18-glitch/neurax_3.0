"""Bottleneck / flow analysis runner.

Reuses: station_metrics.json (Phase 3), root_cause findings (Phase 6),
anomaly states (Phase 4), drift (Phase 6). Produces a transparent,
evidence-quality-labelled station ranking and a flow graph. No economic
calculations are performed here.
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
import scipy
import sklearn

from ..pipeline.artifacts import sanitize_name, write_json
from .errors import FlowError
from .graph import blocking_starvation_status, build_flow_graph
from .impact import throughput_impact
from .scoring import evidence_quality, percentile_rank, score_station, station_status

FLOW_ENGINE_VERSION = "1.0.0"
OUTPUT_NAME_HINTS = ("parts per hour", "total parts", "entities out", "totalproducts", "throughput", "c_cycle")
MAX_IMPACT_OUTPUTS = 3


def _versions() -> dict:
    return {
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "pandas": pd.__version__,
        "numpy": np.__version__,
        "scipy": scipy.__version__,
        "scikit_learn": sklearn.__version__,
        "flow_engine": FLOW_ENGINE_VERSION,
    }


def _analysis_id(dataset_id: str, input_name: str | None, seed: int) -> str:
    digest = hashlib.sha256(f"{dataset_id}|{input_name or 'primary'}|{seed}".encode("utf-8")).hexdigest()
    return digest[:12]


def _load_json(path: Path) -> dict | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return None


def _station_metrics_for(artifact_root: Path, input_name: str | None) -> tuple[dict | None, str | None]:
    payload = _load_json(artifact_root / "station_metrics.json")
    if not payload:
        return None, None
    tables = payload.get("tables", [])
    if input_name:
        for table in tables:
            if table.get("table") == input_name:
                return table, input_name
    for table in tables:
        if table.get("station_count", 0) > 0:
            return table, table.get("table")
    return None, None


def _root_cause_context(artifact_root: Path) -> dict:
    rca_dir = artifact_root / "root_cause"
    registry = _load_json(rca_dir / "analysis_registry.json") or []
    latest = None
    if registry:
        latest = _load_json(rca_dir / "findings" / f"{registry[-1]['analysis_id']}.json")
    station_scores: dict[str, dict] = {}
    drift_by_column: dict[str, dict] = {}
    if latest:
        for finding in latest.get("ranked_findings", []):
            station = finding.get("station")
            if not station:
                continue
            entry = station_scores.setdefault(station, {"best_score": None, "best_factor": None, "factors": []})
            score = finding.get("evidence_score")
            if score is not None and (entry["best_score"] is None or score > entry["best_score"]):
                entry["best_score"] = score
                entry["best_factor"] = finding["factor"]
            if len(entry["factors"]) < 5:
                entry["factors"].append({"factor": finding["factor"], "score": score})
            anomaly = (finding.get("evidence") or {}).get("anomaly") or {}
            if anomaly.get("available") and anomaly.get("enrichment") is not None:
                current = entry.get("anomaly_enrichment")
                entry["anomaly_enrichment"] = max(current or 0.0, anomaly["enrichment"])
        drift = latest.get("drift") or {}
        for column in drift.get("columns", []):
            drift_by_column[column["column"]] = column
    return {
        "analysis_id": registry[-1]["analysis_id"] if registry else None,
        "target": (latest or {}).get("target", {}).get("target"),
        "station_scores": station_scores,
        "drift_by_column": drift_by_column,
        "drift_status": (latest or {}).get("drift", {}).get("status"),
    }


def _anomaly_rates(artifact_root: Path, input_name: str | None) -> dict[str, dict]:
    """Anomaly state rates per station column from Phase 4 prediction previews.

    Uses the preview files (test-split rows) because they are the only artifact
    carrying per-row anomaly states. Reported as rates over the preview sample.
    """
    preview_dir = artifact_root / "predictions"
    if not preview_dir.exists():
        return {}
    rates: dict[str, dict] = {}
    for path in sorted(preview_dir.glob("*.csv.gz")):
        try:
            frame = pd.read_csv(path)
        except Exception:  # noqa: BLE001
            continue
        if "anomaly_state" not in frame.columns:
            continue
        total = int(frame["anomaly_state"].notna().sum())
        if total == 0:
            continue
        anomalous = int((frame["anomaly_state"] == "ANOMALOUS").sum())
        rates[path.stem] = {
            "file": path.name,
            "rows": total,
            "anomalous_rows": anomalous,
            "anomaly_rate": round(anomalous / total, 6),
        }
    return rates


def _metric_summary(entry: dict | None) -> dict:
    if not entry or not entry.get("available"):
        return {"available": False, "reason": "NOT AVAILABLE FROM DATASET"}
    return {
        "available": True,
        "mean": entry.get("mean"),
        "max": entry.get("max"),
        "samples": entry.get("samples"),
    }


def run_bottleneck_analysis(
    dataset_id: str,
    analysis: dict,
    artifact_root: Path,
    input_name: str | None = None,
    seed: int = 42,
) -> dict:
    started = time.time()
    artifact_root = Path(artifact_root)
    flow_dir = artifact_root / "bottleneck"
    flow_dir.mkdir(parents=True, exist_ok=True)

    try:
        station_table, resolved_input = _station_metrics_for(artifact_root, input_name)
        if not station_table or station_table.get("station_count", 0) == 0:
            raise FlowError(
                "NO_STATION_DATA",
                "No station or cell identifiers were detected for this dataset; bottleneck analysis is not supported.",
                "Provide a dataset with per-station utilization/queue/cycle-time columns.",
            )

        stations = station_table["stations"]
        station_ids = [s["station_id"] for s in stations]
        single_station = len(station_ids) == 1

        # cross-station percentile inputs --------------------------------------
        utilization_means = {
            s["station_id"]: s["utilization"]["mean"] for s in stations if s["utilization"].get("available")
        }
        queue_means = {
            s["station_id"]: s["queue_wait"]["mean"] for s in stations if s["queue_wait"].get("available")
        }
        cycle_means = {
            s["station_id"]: s["cycle_time"]["mean"] for s in stations if s["cycle_time"].get("available")
        }
        throughput_means = {
            s["station_id"]: s["throughput"]["mean"] for s in stations if s["throughput"].get("available")
        }

        rca = _root_cause_context(artifact_root)
        anomaly_rates = _anomaly_rates(artifact_root, resolved_input)

        # load source frame once for impact analysis ---------------------------
        frame = None
        for folder, target_file in (
            ("processed_data", artifact_root / "processed_data" / f"{sanitize_name(resolved_input or '')}.csv.gz"),
            ("model_inputs", artifact_root / "model_inputs" / f"{sanitize_name(resolved_input or '')}.csv.gz"),
        ):
            if target_file.exists():
                try:
                    frame = pd.read_csv(target_file)
                except Exception:  # noqa: BLE001
                    frame = None
                break

        findings: list[dict] = []
        for station in stations:
            station_id = station["station_id"]
            components = {
                "utilization_pressure": percentile_rank(utilization_means, station_id),
                "queue_pressure": percentile_rank(queue_means, station_id),
                "cycle_time_pressure": percentile_rank(cycle_means, station_id),
                "throughput_constraint": (
                    1.0 - percentile_rank(throughput_means, station_id)
                    if station_id in throughput_means
                    else None
                ),
                "root_cause_evidence": None,
                "anomaly_evidence": None,
            }
            rca_entry = rca["station_scores"].get(station_id)
            if rca_entry and rca_entry.get("best_score") is not None:
                components["root_cause_evidence"] = min(rca_entry["best_score"] / 100.0, 1.0)
            if rca_entry and rca_entry.get("anomaly_enrichment") is not None:
                components["anomaly_evidence"] = min(rca_entry["anomaly_enrichment"] / 3.0, 1.0)

            score = score_station(components)
            samples = max(
                [entry.get("samples", 0) for key in ("utilization", "queue_wait", "cycle_time", "throughput") if (entry := station.get(key, {})).get("available")] or [0]
            )
            quality = evidence_quality(score, samples, single_station)

            drift_evidence = []
            for metric_name, columns in (station.get("sources") or {}).items():
                for column in columns:
                    drift = rca["drift_by_column"].get(column)
                    if drift and drift.get("drift_detected"):
                        drift_evidence.append(
                            {
                                "column": column,
                                "metric": metric_name,
                                "peak_ewma_z": drift["peak_ewma_z"],
                                "direction": drift["direction"],
                                "change_position": drift["change_position"],
                            }
                        )

            unavailable = [
                label
                for label, key in (
                    ("utilization", "utilization"),
                    ("queue", "queue_wait"),
                    ("cycle_time", "cycle_time"),
                    ("throughput", "throughput"),
                    ("capacity", "capacity"),
                )
                if not station.get(key, {}).get("available")
            ]

            impact = None
            if frame is not None:
                utilization_column = (station.get("sources") or {}).get("utilization", [None])[0]
                output_columns = [
                    c for c in frame.columns if any(hint in str(c).lower() for hint in OUTPUT_NAME_HINTS)
                ][:MAX_IMPACT_OUTPUTS]
                impact = throughput_impact(frame, station_id, utilization_column, output_columns)

            findings.append(
                {
                    "station": station_id,
                    "evidence_score": score["score"],
                    "score_status": score["status"],
                    "score_components": score["components"],
                    "score_weights": score["weights"],
                    "score_formula": score["formula"],
                    "available_components": score["available_components"],
                    "consistency": score["consistency"],
                    "evidence_quality": quality,
                    "utilization": _metric_summary(station.get("utilization")),
                    "queue": _metric_summary(station.get("queue_wait")),
                    "cycle_time": _metric_summary(station.get("cycle_time")),
                    "throughput": _metric_summary(station.get("throughput")),
                    "capacity": {"available": False, "reason": "NOT AVAILABLE FROM DATASET"},
                    "anomaly_evidence": {
                        "available": bool(anomaly_rates),
                        "rates": anomaly_rates,
                        "note": "Anomaly rates come from Phase 4 test-split prediction previews; association only.",
                    },
                    "drift_evidence": drift_evidence,
                    "root_cause_evidence": rca_entry,
                    "unavailable_metrics": unavailable,
                    "impact": impact,
                    "assumptions": [
                        "Station metrics are aggregates of the uploaded dataset.",
                        "Percentile pressure is relative to the stations present in this dataset.",
                    ],
                    "limitations": [
                        "Bottleneck identification is an evidence-based hypothesis, not a proven constraint.",
                        "High utilization alone is not treated as a bottleneck.",
                        "Blocking/starvation cannot be measured from aggregate counters.",
                    ],
                    "epistemic_status": "EVIDENCE-BASED HYPOTHESIS (not proven causation)",
                }
            )

        findings.sort(
            key=lambda f: (
                f["evidence_score"] is None,
                -(
                    f["evidence_score"]
                    if f["evidence_score"] is not None
                    else 100.0 * (
                        sum(value for value in f["score_components"].values() if value is not None)
                        / max(sum(1 for value in f["score_components"].values() if value is not None), 1)
                    )
                ),
            )
        )
        for rank, finding in enumerate(findings, start=1):
            finding["rank"] = rank
            finding["status"] = station_status(rank, {
                "status": finding["score_status"],
                "score": finding["evidence_score"],
            }, finding["evidence_quality"])

        flow_station_evidence = {
            f["station"]: {
                "rank": f["rank"],
                "score": f["evidence_score"],
                "status": f["status"],
                "evidence_quality": f["evidence_quality"]["label"],
            }
            for f in findings
        }
        flow_graph = build_flow_graph(station_ids, flow_station_evidence, analysis.get("filename"))
        bs_status = blocking_starvation_status(flow_graph["status"] == "SUPPORTED", bool(queue_means))

        candidate = next(
            (f for f in findings if f["status"] in {"CANDIDATE_BOTTLENECK", "POSSIBLE_CONTRIBUTOR"}),
            None,
        )
        analysis_id = _analysis_id(dataset_id, resolved_input, seed)
        payload = {
            "dataset_id": dataset_id,
            "analysis_id": analysis_id,
            "status": "complete",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "engine_version": FLOW_ENGINE_VERSION,
            "seed": seed,
            "source": {
                "station_metrics_table": resolved_input,
                "station_metrics_artifact": "station_metrics.json",
                "root_cause_analysis_id": rca["analysis_id"],
                "root_cause_target": rca["target"],
                "frame_rows": int(frame.shape[0]) if frame is not None else None,
                "artifact_truncated": False,
            },
            "configuration": {
                "scoring_weights": findings[0]["score_weights"] if findings else None,
                "scoring_formula": findings[0]["score_formula"] if findings else None,
                "confidence_thresholds": {"consistent_component": 0.5, "candidate_min_score": 40},
                "utilization_constrained_quantile": 0.75,
            },
            "stations_analyzed": len(findings),
            "station_rankings": findings,
            "candidate_bottleneck": {
                "station": candidate["station"] if candidate else None,
                "evidence_score": candidate["evidence_score"] if candidate else None,
                "evidence_quality": candidate["evidence_quality"] if candidate else None,
                "status": candidate["status"] if candidate else "NO_CANDIDATE_WITH_SUFFICIENT_EVIDENCE",
                "why": (
                    [
                        f"{label}: {value}"
                        for label, value in (candidate["score_components"] if candidate else {}).items()
                        if value is not None
                    ]
                    if candidate
                    else []
                ),
                "unavailable_metrics": candidate["unavailable_metrics"] if candidate else [],
            },
            "flow": {
                "graph": flow_graph,
                "blocking_starvation": bs_status,
            },
            "what_if_inputs": {
                "station": candidate["station"] if candidate else None,
                "current_utilization": candidate["utilization"] if candidate else None,
                "current_queue": candidate["queue"] if candidate else None,
                "current_cycle_time": candidate["cycle_time"] if candidate else None,
                "observed_impact": candidate["impact"] if candidate else None,
                "potential_interventions": [
                    "reduce cycle time at the constrained station",
                    "reduce queue accumulation",
                    "shift load to less constrained stations",
                ]
                if candidate
                else [],
                "expected_effect": "NOT YET SIMULATED",
                "note": "Inputs prepared for the simulation/economics phase; no economic values are computed here.",
            },
            "epistemic_summary": {
                "observed_data": "Station metrics computed from the uploaded dataset.",
                "statistical_association": "Root-cause and anomaly evidence from Phases 4/6.",
                "hypothesis": "Candidate bottleneck ranking is an evidence-based hypothesis.",
                "simulated_effect": "NOT YET SIMULATED (future phase).",
                "causal_claim": "NOT SUPPORTED: no interventional or simulation-based proof was applied.",
            },
            "limitations": [
                "Bottleneck ranking depends on the metrics present in this dataset.",
                "Percentile pressure is dataset-relative and not comparable across datasets.",
                "Observed throughput comparisons are associations, not predicted gains.",
                "Blocking and starvation are NOT_SUPPORTED for aggregate-counter datasets.",
            ],
            "versions": _versions(),
            "total_duration_s": round(time.time() - started, 3),
        }

        write_json(flow_dir / "findings" / f"{analysis_id}.json", payload)
        write_json(flow_dir / "station_scores.json", {
            "dataset_id": dataset_id,
            "analysis_id": analysis_id,
            "formula": payload["configuration"]["scoring_formula"],
            "weights": payload["configuration"]["scoring_weights"],
            "stations": [
                {
                    "station": f["station"],
                    "rank": f["rank"],
                    "score": f["evidence_score"],
                    "status": f["status"],
                    "components": f["score_components"],
                    "quality": f["evidence_quality"]["label"],
                }
                for f in findings
            ],
        })
        write_json(flow_dir / "flow.json", {
            "dataset_id": dataset_id,
            "analysis_id": analysis_id,
            **payload["flow"],
        })
        write_json(flow_dir / "metadata.json", {
            "dataset_id": dataset_id,
            "engine_version": FLOW_ENGINE_VERSION,
            "last_analysis_id": analysis_id,
            "generated_at": payload["generated_at"],
            "versions": payload["versions"],
        })
        _update_registry(flow_dir, payload)
        return payload

    except FlowError as exc:
        return {
            "dataset_id": dataset_id,
            "status": "failed",
            "error": exc.to_dict(),
            "total_duration_s": round(time.time() - started, 3),
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "dataset_id": dataset_id,
            "status": "failed",
            "error": {
                "error": True,
                "code": "FLOW_ANALYSIS_FAILURE",
                "message": "Bottleneck analysis failed unexpectedly.",
                "detail": str(exc),
            },
            "total_duration_s": round(time.time() - started, 3),
        }


def _update_registry(flow_dir: Path, payload: dict) -> None:
    registry_path = flow_dir / "analysis_registry.json"
    registry: list[dict] = []
    if registry_path.exists():
        try:
            registry = json.loads(registry_path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            registry = []
    registry = [entry for entry in registry if entry.get("analysis_id") != payload["analysis_id"]]
    candidate = payload["candidate_bottleneck"]
    registry.append(
        {
            "analysis_id": payload["analysis_id"],
            "station_metrics_table": payload["source"]["station_metrics_table"],
            "generated_at": payload["generated_at"],
            "stations_analyzed": payload["stations_analyzed"],
            "candidate_station": candidate["station"],
            "candidate_score": candidate["evidence_score"],
            "candidate_quality": (candidate["evidence_quality"] or {}).get("label") if candidate["evidence_quality"] else None,
            "candidate_status": candidate["status"],
        }
    )
    write_json(registry_path, registry)


def list_analyses(flow_dir: Path) -> list[dict]:
    path = Path(flow_dir) / "analysis_registry.json"
    if not path.exists():
        return []
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return []


def get_analysis(flow_dir: Path, analysis_id: str) -> dict | None:
    path = Path(flow_dir) / "findings" / f"{analysis_id}.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return None
