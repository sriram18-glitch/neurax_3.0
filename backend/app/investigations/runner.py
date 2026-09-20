"""Investigation orchestration and persistence.

The investigation record is deliberately compact: summaries and identifiers,
never raw frames or base64 images. Replay reads the stored inspection by id.
"""

from __future__ import annotations

import json
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from app.core.settings import ARTIFACTS_DIR, MODELS_DIR, RUNTIME_DIR
from app.core.store import SessionStore

INVESTIGATION_DIRNAME = "investigations"
INDEX_LIMIT = 200


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _investigations_dir(base: Path | None = None) -> Path:
    path = Path(base) if base else (RUNTIME_DIR / INVESTIGATION_DIRNAME)
    path.mkdir(parents=True, exist_ok=True)
    return path


def _stage(
    stage_id: str,
    label: str,
    status: str,
    summary: str,
    *,
    epistemic: str,
    detail: str | None = None,
    payload: dict | None = None,
    duration_ms: float | None = None,
    required_inputs: list[str] | None = None,
    available_inputs: list[str] | None = None,
) -> dict:
    return {
        "id": stage_id,
        "label": label,
        "status": status,
        "summary": summary,
        "detail": detail,
        "epistemic": epistemic,
        "payload": payload,
        "duration_ms": round(duration_ms, 2) if duration_ms is not None else None,
        "required_inputs": required_inputs or [],
        "available_inputs": available_inputs or [],
    }


def _from_inspection(inspection: dict) -> list[dict]:
    """Stages that are already recorded on the inspection result (no re-run)."""
    prediction = inspection.get("prediction") or {}
    confidence = inspection.get("confidence") or {}
    anomaly = inspection.get("anomaly_score") or {}
    localization = inspection.get("localization") or {}
    metadata = inspection.get("image_metadata") or {}
    return [
        _stage(
            "received",
            "Inspection received",
            "COMPLETE",
            f"{metadata.get('width', '?')}x{metadata.get('height', '?')} {metadata.get('format', 'image')}",
            epistemic="OBSERVED",
            detail=f"source: {inspection.get('filename') or inspection.get('inspection_id')}",
            available_inputs=["inspection image"],
        ),
        _stage(
            "classifying",
            "Classification",
            "COMPLETE",
            f"{prediction.get('predicted_class', 'unknown')} · calibrated probability {confidence.get('value', 0):.1%}",
            epistemic="MODEL OUTPUT",
            detail=confidence.get("method"),
            payload={
                "predicted_class": prediction.get("predicted_class"),
                "class_probabilities": inspection.get("class_probabilities"),
                "confidence": confidence.get("value"),
                "confidence_level": confidence.get("level"),
            },
            available_inputs=["inspection image", "trained vision model"],
        ),
        _stage(
            "localizing",
            "Localization",
            "COMPLETE" if localization.get("bounding_box") else "DATA_GAP",
            "attention region derived" if localization.get("bounding_box") else "no attention region produced",
            epistemic="MODEL-DERIVED",
            detail=localization.get("note"),
            payload={"bounding_box": localization.get("bounding_box"), "method": localization.get("method")},
            required_inputs=[] if localization.get("bounding_box") else ["backbone activation map"],
            available_inputs=["inspection image", "class-activation map"],
        ),
        _stage(
            "checking_robustness",
            "Robustness check",
            "REVIEW"
            if (anomaly.get("novelty_status") == "HIGH" or inspection.get("decision") == "REVIEW")
            else "COMPLETE",
            f"anomaly percentile {anomaly.get('value', 0):.3f} · novelty {anomaly.get('novelty_score', 0):.3f} ({anomaly.get('novelty_status', 'NORMAL')})",
            epistemic="MODEL OUTPUT",
            detail=inspection.get("review_reason") or anomaly.get("note"),
            payload={
                "anomaly_score": anomaly.get("value"),
                "novelty_score": anomaly.get("novelty_score"),
                "novelty_status": anomaly.get("novelty_status"),
                "review_reason": inspection.get("review_reason"),
            },
            available_inputs=["embedding", "normal reference", "class reference distributions"],
        ),
    ]


def _process_correlation_stage(inspection: dict, dataset_id: str | None, store: SessionStore | None, artifact_root: Path | None) -> dict:
    started = time.time()
    link = inspection.get("process_link") or {}
    if not dataset_id or store is None or store.get(dataset_id) is None:
        return _stage(
            "process_correlation",
            "Process correlation",
            "DATA_GAP",
            "No process dataset selected",
            epistemic="DATA GAP",
            detail="Select a processed dataset to attach dataset-level process context. Per-inspection joins require image metadata (batch/station/unit), which this dataset does not contain.",
            payload={"join_status": link.get("status"), "join_reason": link.get("reason")},
            duration_ms=(time.time() - started) * 1000,
            required_inputs=["process dataset", "valid inspection→process join key (unit/batch/station/timestamp)"],
            available_inputs=["inspection result"],
        )
    session = store.get(dataset_id) or {}
    contract = session.get("contract") or {}
    summary = contract.get("summary") or {}
    return _stage(
        "process_correlation",
        "Process correlation",
        "PARTIAL",
        f"dataset-level context: {contract.get('filename')} · {summary.get('total_rows')} rows · {len(summary.get('stations') or [])} station(s)",
        epistemic="OBSERVED",
        detail=link.get("reason")
        or "No per-inspection join key exists, so process context is reported at dataset level only.",
        payload={
            "join_status": link.get("status"),
            "join_reason": link.get("reason"),
            "dataset_id": dataset_id,
            "filename": contract.get("filename"),
            "rows": summary.get("total_rows"),
            "stations": summary.get("stations"),
            "note": "No valid inspection -> process join key. Context is dataset-level, not per-unit.",
        },
        duration_ms=(time.time() - started) * 1000,
        required_inputs=["per-unit join key (batch/station/unit/timestamp) for inspection→process linking"],
        available_inputs=["inspection result", "process dataset (dataset-level)"],
    )


def _root_cause_stage(dataset_id: str | None, store: SessionStore | None, artifact_root: Path | None, models_dir: Path | None) -> dict:
    from app.rootcause import discover_targets, get_analysis as get_rca, list_analyses as list_rca, run_root_cause

    started = time.time()
    if not dataset_id or store is None or artifact_root is None:
        return _stage(
            "root_cause",
            "Root-cause hypotheses",
            "DATA_GAP",
            "No process dataset selected",
            epistemic="DATA GAP",
            detail="Root-cause analysis runs over the process dataset; none is loaded.",
            duration_ms=(time.time() - started) * 1000,
            required_inputs=["process dataset with a numeric response column"],
            available_inputs=["inspection result"],
        )
    analysis = store.get_analysis(dataset_id)
    if not analysis or analysis.get("status") != "complete":
        return _stage(
            "root_cause",
            "Root-cause hypotheses",
            "DATA_GAP",
            "Process analysis for the dataset is not complete",
            epistemic="DATA GAP",
            detail="Upload or re-process the dataset before root-cause analysis can run.",
            duration_ms=(time.time() - started) * 1000,
        )
    rca_dir = artifact_root / "root_cause"
    registry = list_rca(rca_dir)
    payload = get_rca(rca_dir, registry[-1]["analysis_id"]) if registry else None
    error_detail = None
    if payload is None:
        try:
            targets = discover_targets(dataset_id, analysis, artifact_root)
            target = next((entry for entry in targets if entry.get("mode") != "model_input"), targets[0] if targets else None)
            if target is None:
                return _stage(
                    "root_cause",
                    "Root-cause hypotheses",
                    "DATA_GAP",
                    "No valid response/target column was found",
                    epistemic="DATA GAP",
                    detail="The dataset has no numeric target with enough rows for association analysis.",
                    duration_ms=(time.time() - started) * 1000,
                )
            result = run_root_cause(
                dataset_id,
                str(target["target"]),
                "low",
                0.10,
                analysis,
                artifact_root,
                models_dir or MODELS_DIR,
                input_name=target.get("input"),
            )
            if result.get("status") == "failed":
                error_detail = (result.get("error") or {}).get("message")
                payload = None
            else:
                payload = result
        except Exception as exc:  # noqa: BLE001 - a failed stage must be reported, not hidden
            error_detail = str(exc)
            payload = None
    if payload is None:
        return _stage(
            "root_cause",
            "Root-cause hypotheses",
            "FAILED",
            "Root-cause analysis could not be completed",
            epistemic="DATA GAP",
            detail=error_detail or "The engine returned no analysis.",
            duration_ms=(time.time() - started) * 1000,
        )
    top = (payload.get("ranked_findings") or [])[:3]
    return _stage(
        "root_cause",
        "Root-cause hypotheses",
        "COMPLETE",
        f"{payload.get('factors_analyzed', 0)} factors analyzed · {len(payload.get('ranked_findings') or [])} ranked findings",
        epistemic="STATISTICAL ASSOCIATION",
        detail=f"target: {payload.get('event', {}).get('target')} {payload.get('event', {}).get('direction')} tail · association is not causation",
        payload={
            "analysis_id": payload.get("analysis_id"),
            "target": payload.get("event", {}).get("target"),
            "direction": payload.get("event", {}).get("direction"),
            "quantile": payload.get("event", {}).get("quantile"),
            "factors_analyzed": payload.get("factors_analyzed"),
            "top_findings": [
                {
                    "factor": finding.get("factor"),
                    "station": finding.get("station"),
                    "score": finding.get("evidence_score"),
                    "association_status": finding.get("association_status"),
                }
                for finding in top
            ],
            "drift": {
                "status": (payload.get("drift") or {}).get("status"),
                "columns_drifted": (payload.get("drift") or {}).get("columns_drifted"),
            },
        },
        duration_ms=(time.time() - started) * 1000,
    )


def _bottleneck_stage(dataset_id: str | None, store: SessionStore | None, artifact_root: Path | None) -> dict:
    from app.flow import get_analysis as get_flow, list_analyses as list_flow, run_bottleneck_analysis

    started = time.time()
    if not dataset_id or store is None or artifact_root is None:
        return _stage(
            "bottleneck",
            "Bottleneck / flow",
            "DATA_GAP",
            "No process dataset selected",
            epistemic="DATA GAP",
            detail="Flow analysis runs over the process dataset; none is loaded.",
            duration_ms=(time.time() - started) * 1000,
            required_inputs=["process dataset with per-station metrics"],
            available_inputs=["inspection result"],
        )
    analysis = store.get_analysis(dataset_id)
    if not analysis or analysis.get("status") != "complete":
        return _stage(
            "bottleneck",
            "Bottleneck / flow",
            "DATA_GAP",
            "Process analysis for the dataset is not complete",
            epistemic="DATA GAP",
            duration_ms=(time.time() - started) * 1000,
        )
    flow_dir = artifact_root / "bottleneck"
    registry = list_flow(flow_dir)
    payload = get_flow(flow_dir, registry[-1]["analysis_id"]) if registry else None
    if payload is None:
        try:
            result = run_bottleneck_analysis(dataset_id, analysis, artifact_root)
            payload = None if result.get("status") == "failed" else result
        except Exception:  # noqa: BLE001
            payload = None
    if payload is None:
        return _stage(
            "bottleneck",
            "Bottleneck / flow",
            "DATA_GAP",
            "No station-level metrics were available for flow analysis",
            epistemic="DATA GAP",
            detail="The dataset exposes no defensible utilization/queue/cycle metrics per station.",
            duration_ms=(time.time() - started) * 1000,
        )
    candidate = payload.get("candidate_bottleneck") or {}
    top = (payload.get("station_rankings") or [])[:3]
    return _stage(
        "bottleneck",
        "Bottleneck / flow",
        "COMPLETE",
        f"candidate constraint: {candidate.get('station') or 'none identified'}"
        + (f" (score {candidate.get('evidence_score'):.1f})" if candidate.get("evidence_score") is not None else ""),
        epistemic="EVIDENCE-BASED HYPOTHESIS",
        detail="Bottleneck identification is an evidence-based hypothesis, not a proven constraint.",
        payload={
            "analysis_id": payload.get("analysis_id"),
            "candidate": {
                "station": candidate.get("station"),
                "score": candidate.get("evidence_score"),
                "quality": (candidate.get("evidence_quality") or {}).get("label"),
                "why": candidate.get("why"),
            },
            "top_stations": [
                {
                    "station": finding.get("station"),
                    "score": finding.get("evidence_score"),
                    "status": finding.get("status"),
                    "components": {key: value for key, value in (finding.get("score_components") or {}).items() if value is not None},
                }
                for finding in top
            ],
            "flow_status": (payload.get("flow", {}).get("graph") or {}).get("status"),
        },
        duration_ms=(time.time() - started) * 1000,
    )


def _impact_stage(dataset_id: str | None, store: SessionStore | None, artifact_root: Path | None) -> dict:
    from app.economics import store as econ_store

    started = time.time()
    if not dataset_id or artifact_root is None:
        return _stage(
            "impact",
            "Production impact",
            "DATA_GAP",
            "No process dataset selected",
            epistemic="DATA GAP",
            detail="Impact requires observed process data plus user assumptions.",
            duration_ms=(time.time() - started) * 1000,
            required_inputs=["process dataset", "observed throughput", "user economic assumptions"],
            available_inputs=["inspection result"],
        )
    assumptions = econ_store.get_assumptions(artifact_root, dataset_id)
    entries = assumptions.get("assumptions") or {}
    supplied = [field for field, entry in entries.items() if (entry or {}).get("value") is not None]
    missing = [field for field, entry in entries.items() if (entry or {}).get("value") is None]
    if not supplied:
        return _stage(
            "impact",
            "Production impact",
            "AWAITING_INPUT",
            "Economic assumptions required",
            epistemic="USER ASSUMPTION",
            detail="No economic value is invented. Supply contribution margin, working hours and costs to compute impact.",
            payload={"assumptions_supplied": [], "assumptions_missing": missing[:12]},
            duration_ms=(time.time() - started) * 1000,
            required_inputs=missing[:12] or ["user economic assumptions"],
            available_inputs=["observed throughput (from process analysis)"],
        )
    try:
        baseline = econ_store.compute_baseline(artifact_root, dataset_id)
    except Exception as exc:  # noqa: BLE001
        return _stage(
            "impact",
            "Production impact",
            "FAILED",
            "Baseline computation failed",
            epistemic="DATA GAP",
            detail=str(exc),
            payload={"assumptions_supplied": supplied},
            duration_ms=(time.time() - started) * 1000,
        )
    base = baseline.get("baseline") or {}
    daily = (base.get("daily_contribution") or {}).get("value")
    return _stage(
        "impact",
        "Production impact",
        "COMPLETE",
        f"daily contribution {daily:,.0f} {baseline.get('currency') or ''}".strip()
        if daily is not None
        else "baseline computed with supplied assumptions",
        epistemic="CALCULATED",
        detail="Calculations use observed throughput and user-supplied assumptions only.",
        payload={
            "currency": baseline.get("currency"),
            "throughput_per_hour": (base.get("throughput_per_hour") or {}).get("value"),
            "units_per_day": (base.get("units_per_day") or {}).get("value"),
            "daily_contribution": daily,
            "monthly_contribution": (base.get("monthly_contribution") or {}).get("value"),
            "assumptions_supplied": supplied,
            "assumptions_missing": missing,
        },
        duration_ms=(time.time() - started) * 1000,
    )


def _what_if_stage(dataset_id: str | None, artifact_root: Path | None) -> dict:
    from app.economics import store as econ_store

    started = time.time()
    if not dataset_id or artifact_root is None:
        return _stage(
            "what_if",
            "What-if scenario",
            "DATA_GAP",
            "No process dataset selected",
            epistemic="DATA GAP",
            duration_ms=(time.time() - started) * 1000,
            required_inputs=["process dataset", "economic baseline"],
            available_inputs=["inspection result"],
        )
    scenarios = econ_store.list_scenarios(artifact_root)
    if not scenarios:
        return _stage(
            "what_if",
            "What-if scenario",
            "AWAITING_INPUT",
            "Scenario runs on demand",
            epistemic="SIMULATION",
            detail="What-if scenarios are assumption-based and run interactively; none has been executed for this dataset.",
            payload={"scenarios_run": 0},
            duration_ms=(time.time() - started) * 1000,
            required_inputs=["economic baseline", "user assumptions (margin, hours, costs)"],
            available_inputs=["observed throughput", "bottleneck analysis"],
        )
    latest = econ_store.get_scenario(artifact_root, scenarios[-1]["scenario_id"]) or {}
    return _stage(
        "what_if",
        "What-if scenario",
        "COMPLETE",
        f"latest scenario: {latest.get('scenario_type', 'scenario')}",
        epistemic="SIMULATION",
        detail="Assumption-based scenario - not observed production.",
        payload={
            "scenarios_run": len(scenarios),
            "scenario_id": latest.get("scenario_id"),
            "scenario_type": latest.get("scenario_type"),
            "net_daily_impact": ((latest.get("economic_output") or {}).get("net_daily_impact") or {}).get("value"),
        },
        duration_ms=(time.time() - started) * 1000,
    )


def _recommendation_stage(dataset_id: str | None, store: SessionStore | None, artifact_root: Path | None) -> dict:
    from app.recommend import generate_recommendations, list_recommendations

    started = time.time()
    if not dataset_id or store is None or artifact_root is None:
        return _stage(
            "recommendation",
            "Advisory actions",
            "DATA_GAP",
            "No process dataset selected",
            epistemic="DATA GAP",
            detail="Recommendations are generated from process analyses.",
            duration_ms=(time.time() - started) * 1000,
            required_inputs=["process analyses (root cause / bottleneck)"],
            available_inputs=["inspection result"],
        )
    session = store.get(dataset_id) or {}
    contract = session.get("contract") or {}
    registry = list_recommendations(artifact_root)
    if not registry:
        try:
            generate_recommendations(dataset_id, contract, artifact_root)
            registry = list_recommendations(artifact_root)
        except Exception:  # noqa: BLE001
            registry = []
    if not registry:
        return _stage(
            "recommendation",
            "Advisory actions",
            "DATA_GAP",
            "No recommendations could be generated",
            epistemic="DATA GAP",
            detail="The deterministic rule engine found no actionable evidence for this dataset.",
            duration_ms=(time.time() - started) * 1000,
        )
    top = registry[:3]
    return _stage(
        "recommendation",
        "Advisory actions",
        "COMPLETE",
        f"{len(registry)} advisory action(s) from deterministic rules",
        epistemic="ADVISORY",
        detail="Recommendations are advisory decision support; they never control machinery.",
        payload={
            "count": len(registry),
            "top": [
                {
                    "recommendation_id": entry.get("recommendation_id"),
                    "title": entry.get("title"),
                    "action_type": entry.get("action_type"),
                    "priority": entry.get("priority"),
                    "evidence_quality": entry.get("evidence_quality"),
                }
                for entry in top
            ],
        },
        duration_ms=(time.time() - started) * 1000,
    )


def run_investigation(
    inspection: dict,
    dataset_id: str | None = None,
    *,
    store: SessionStore | None = None,
    artifacts_dir: Path | None = None,
    models_dir: Path | None = None,
    investigations_dir: Path | None = None,
) -> dict:
    """Run the automatic investigation chain for one inspection result."""
    started = time.time()
    artifact_root = (Path(artifacts_dir) / dataset_id) if (artifacts_dir and dataset_id) else (
        (ARTIFACTS_DIR / dataset_id) if dataset_id else None
    )
    session_store = store
    if session_store is None:
        session_store = None  # process correlation degrades to DATA_GAP without a store

    stages = _from_inspection(inspection)
    stages.append(_process_correlation_stage(inspection, dataset_id, session_store, artifact_root))
    stages.append(_root_cause_stage(dataset_id, session_store, artifact_root, models_dir))
    stages.append(_bottleneck_stage(dataset_id, session_store, artifact_root))
    stages.append(_impact_stage(dataset_id, session_store, artifact_root))
    stages.append(_what_if_stage(dataset_id, artifact_root))
    stages.append(_recommendation_stage(dataset_id, session_store, artifact_root))

    decision = inspection.get("decision")
    if decision == "REVIEW":
        overall = "REVIEW_REQUIRED"
    elif dataset_id is None:
        overall = "DATA_GAP"
    elif any(stage["status"] in {"FAILED"} for stage in stages):
        overall = "PARTIAL"
    else:
        overall = "COMPLETE"

    generated_at = _now()
    investigation_id = f"inv_{uuid.uuid4().hex[:12]}"
    record = {
        "investigation_id": investigation_id,
        "inspection_id": inspection.get("inspection_id"),
        "source_id": inspection.get("source_id"),
        "dataset_id": dataset_id,
        "station_id": inspection.get("station_id"),
        "generated_at": generated_at,
        "status": overall,
        "decision": decision,
        "predicted_class": (inspection.get("prediction") or {}).get("predicted_class"),
        "confidence": (inspection.get("confidence") or {}).get("value"),
        "anomaly_score": (inspection.get("anomaly_score") or {}).get("value"),
        "novelty_status": (inspection.get("anomaly_score") or {}).get("novelty_status"),
        "review_reason": inspection.get("review_reason"),
        "filename": inspection.get("filename"),
        "stages": stages,
        "stage_summary": {
            "complete": sum(1 for stage in stages if stage["status"] in {"COMPLETE", "REVIEW"}),
            "data_gap": sum(1 for stage in stages if stage["status"] == "DATA_GAP"),
            "awaiting_input": sum(1 for stage in stages if stage["status"] == "AWAITING_INPUT"),
            "failed": sum(1 for stage in stages if stage["status"] == "FAILED"),
            "partial": sum(1 for stage in stages if stage["status"] == "PARTIAL"),
        },
        "total_duration_s": round(time.time() - started, 3),
        "limitations": [
            "Investigation stages reuse stored analyses; association is never presented as causation.",
            "Economic and what-if stages require explicit user assumptions.",
            "No machine control: all actions are advisory.",
        ],
    }
    events = investigation_events(record)
    record["events"] = events
    _persist(record, investigations_dir)
    return record


def investigation_events(record: dict) -> list[dict]:
    """Business-level event feed derived from the real investigation stages."""
    events: list[dict] = []
    base = record.get("generated_at")

    def add(at: str | None, event_type: str, message: str, epistemic: str) -> None:
        events.append(
            {
                "at": at or base,
                "type": event_type,
                "message": message,
                "epistemic": epistemic,
                "investigation_id": record.get("investigation_id"),
                "inspection_id": record.get("inspection_id"),
            }
        )

    add(base, "inspection_completed", f"Inspection completed — {record.get('predicted_class')} ({record.get('decision')})", "OBSERVED")
    if record.get("decision") == "DEFECT":
        add(base, "defect_detected", f"Defect decision recorded for {record.get('filename') or record.get('inspection_id')}", "MODEL OUTPUT")
    if record.get("decision") == "REVIEW":
        add(base, "review_required", record.get("review_reason") or "Sample flagged for human review", "MODEL OUTPUT")
    add(base, "investigation_triggered", "Automatic investigation triggered", "OBSERVED")
    for stage in record.get("stages", []):
        if stage["id"] in {"received", "classifying", "localizing", "checking_robustness"}:
            continue
        if stage["status"] in {"COMPLETE", "REVIEW"}:
            add(base, f"{stage['id']}_complete", f"{stage['label']}: {stage['summary']}", stage["epistemic"])
        elif stage["status"] == "DATA_GAP":
            add(base, f"{stage['id']}_data_gap", f"{stage['label']}: {stage['summary']}", "DATA GAP")
        elif stage["status"] == "AWAITING_INPUT":
            add(base, f"{stage['id']}_awaiting_input", f"{stage['label']}: {stage['summary']}", stage["epistemic"])
        elif stage["status"] == "FAILED":
            add(base, f"{stage['id']}_failed", f"{stage['label']}: {stage['summary']}", "DATA GAP")
    return events


def _persist(record: dict, base: Path | None = None) -> None:
    directory = _investigations_dir(base)
    with open(directory / f"{record['investigation_id']}.json", "w", encoding="utf-8") as handle:
        json.dump(record, handle, indent=2, default=str)
    index_path = directory / "index.json"
    index: list[dict] = []
    if index_path.exists():
        try:
            index = json.loads(index_path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            index = []
    index = [entry for entry in index if entry.get("investigation_id") != record["investigation_id"]]
    index.append(
        {
            "investigation_id": record["investigation_id"],
            "inspection_id": record["inspection_id"],
            "source_id": record.get("source_id"),
            "dataset_id": record["dataset_id"],
            "generated_at": record["generated_at"],
            "status": record["status"],
            "decision": record["decision"],
            "predicted_class": record["predicted_class"],
            "confidence": record["confidence"],
            "filename": record["filename"],
            "stage_summary": record["stage_summary"],
            "top_action": ((record["stages"][-1].get("payload") or {}).get("top") or [{}])[0].get("title"),
        }
    )
    with open(index_path, "w", encoding="utf-8") as handle:
        json.dump(index[-INDEX_LIMIT:], handle, indent=2, default=str)


def list_investigations(base: Path | None = None) -> list[dict]:
    index_path = _investigations_dir(base) / "index.json"
    if not index_path.exists():
        return []
    try:
        index = json.loads(index_path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return []
    return list(reversed(index))


def get_investigation(investigation_id: str, base: Path | None = None) -> dict | None:
    path = _investigations_dir(base) / f"{investigation_id}.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return None
