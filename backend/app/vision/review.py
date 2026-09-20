"""Human review queue.

AI decisions are never overwritten: a human decision is stored separately on
the inspection record (human_review). REVIEW decisions without a human decision
form the pending queue; stats report auto-resolved vs human-reviewed rates.
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path

from .inference import INSPECTION_DIRNAME

HUMAN_ACTIONS = {
    "confirm_defect": {"decision": "DEFECT", "label": "CONFIRM DEFECT"},
    "mark_pass": {"decision": "PASS", "label": "MARK PASS"},
    "keep_in_review": {"decision": "REVIEW", "label": "KEEP IN REVIEW"},
    "escalate": {"decision": "ESCALATED", "label": "ESCALATE"},
}

QUEUE_LIMIT = 200


class ReviewError(Exception):
    def __init__(self, code: str, message: str, detail: str | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.detail = detail

    def to_dict(self) -> dict:
        return {"error": True, "code": self.code, "message": self.message, "detail": self.detail}


def _inspections_dir(artifacts_dir: Path) -> Path:
    return Path(artifacts_dir) / INSPECTION_DIRNAME


def _load_index(artifacts_dir: Path) -> list[dict]:
    index_path = _inspections_dir(artifacts_dir) / "index.json"
    if not index_path.exists():
        return []
    try:
        return json.loads(index_path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return []


def _load_inspection(artifacts_dir: Path, inspection_id: str) -> dict | None:
    path = _inspections_dir(artifacts_dir) / f"{inspection_id}.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return None


def record_human_decision(
    artifacts_dir: Path,
    inspection_id: str,
    action: str,
    note: str | None = None,
    class_name: str | None = None,
) -> dict:
    """Store a human decision. The AI decision fields are left untouched."""
    if action not in HUMAN_ACTIONS:
        raise ReviewError(
            "INVALID_REVIEW_ACTION",
            f"Unknown review action '{action}'.",
            "Supported actions: " + ", ".join(sorted(HUMAN_ACTIONS)),
        )
    inspection = _load_inspection(artifacts_dir, inspection_id)
    if inspection is None:
        raise ReviewError("INSPECTION_NOT_FOUND", f"Inspection '{inspection_id}' does not exist.", None)
    entry = HUMAN_ACTIONS[action]
    human_review = {
        "action": action,
        "action_label": entry["label"],
        "decision": entry["decision"],
        "class_name": class_name,
        "at": datetime.now(timezone.utc).isoformat(),
        "note": note,
        "ai_decision_preserved": inspection.get("decision"),
    }
    inspection["human_review"] = human_review
    path = _inspections_dir(artifacts_dir) / f"{inspection_id}.json"
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(inspection, handle, indent=2, default=str)
    return {
        "inspection_id": inspection_id,
        "human_review": human_review,
        "ai_decision": inspection.get("decision"),
        "ai_confidence": inspection.get("confidence", {}).get("value"),
        "note": "The AI decision and evidence are preserved; the human decision is stored separately.",
    }


def list_review_queue(artifacts_dir: Path, include_reviewed: bool = False, limit: int = 100) -> list[dict]:
    entries = []
    for summary in reversed(_load_index(artifacts_dir)):
        if summary.get("decision") != "REVIEW":
            continue
        inspection = _load_inspection(artifacts_dir, summary.get("inspection_id", ""))
        if inspection is None:
            continue
        human = inspection.get("human_review")
        if human and human.get("decision") != "REVIEW" and not include_reviewed:
            continue
        entries.append(
            {
                "inspection_id": inspection["inspection_id"],
                "source_id": inspection.get("source_id"),
                "filename": inspection.get("filename"),
                "generated_at": inspection.get("generated_at"),
                "predicted_class": inspection.get("prediction", {}).get("predicted_class"),
                "confidence": inspection.get("confidence", {}).get("value"),
                "anomaly_score": inspection.get("anomaly_score", {}).get("value"),
                "novelty_score": inspection.get("anomaly_score", {}).get("novelty_score"),
                "novelty_status": inspection.get("anomaly_score", {}).get("novelty_status"),
                "localization": bool(inspection.get("localization", {}).get("bounding_box")),
                "review_reason": inspection.get("review_reason"),
                "review_reasons": inspection.get("review_reasons", []),
                "human_review": human,
            }
        )
        if len(entries) >= min(limit, QUEUE_LIMIT):
            break
    return entries


def review_stats(artifacts_dir: Path) -> dict:
    index = _load_index(artifacts_dir)
    total = len(index)
    if total == 0:
        return {
            "total": 0,
            "auto_resolved": 0,
            "human_reviewed": 0,
            "pending_review": 0,
            "auto_resolved_rate": None,
            "human_review_rate": None,
            "distribution": {"PASS": 0, "DEFECT": 0, "REVIEW": 0},
            "avg_confidence": None,
            "note": "No inspections recorded yet.",
        }
    distribution = {"PASS": 0, "DEFECT": 0, "REVIEW": 0}
    human_reviewed = 0
    pending = 0
    confidence_sum = 0.0
    confidence_count = 0
    for summary in index:
        decision = summary.get("decision")
        if decision in distribution:
            distribution[decision] += 1
        inspection = _load_inspection(artifacts_dir, summary.get("inspection_id", ""))
        if decision == "REVIEW":
            if inspection and inspection.get("human_review"):
                if inspection["human_review"].get("decision") != "REVIEW":
                    human_reviewed += 1
                else:
                    pending += 1
            else:
                pending += 1
        value = summary.get("confidence")
        if value is not None:
            confidence_sum += float(value)
            confidence_count += 1
    auto_resolved = total - distribution["REVIEW"]
    return {
        "total": total,
        "auto_resolved": auto_resolved,
        "human_reviewed": human_reviewed,
        "pending_review": pending,
        "auto_resolved_rate": round(auto_resolved / total, 4),
        "human_review_rate": round(human_reviewed / total, 4),
        "pending_review_rate": round(pending / total, 4),
        "distribution": distribution,
        "distribution_rates": {key: round(value / total, 4) for key, value in distribution.items()},
        "avg_confidence": round(confidence_sum / confidence_count, 4) if confidence_count else None,
        "note": "Auto-resolved = decisions made by the AI without human intervention. REVIEW decisions enter the human review queue.",
    }