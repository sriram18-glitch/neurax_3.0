"""In-memory session store for ingested datasets.

The JSON contract and pipeline state live in memory; raw frames stay in memory
for fast analysis. No database, no queues - appropriate for a single-process
monolith. Analysis artifacts are persisted to disk by the pipeline runner.
"""

from __future__ import annotations

import json
import threading
from pathlib import Path

STAGE_LABELS = {
    "ingestion": "Data ingestion",
    "cleaning": "Cleaning & validation",
    "feature_engineering": "Feature engineering",
    "model_inputs": "Model input preparation",
    "splitting": "Leakage-safe splitting",
    "station_aggregation": "Station aggregation",
    "artifacts": "Artifact generation",
    "model_training": "Model training & evaluation",
}


def _initial_stages() -> list[dict]:
    return [
        {"id": stage, "label": STAGE_LABELS[stage], "status": "pending", "detail": None, "duration_s": None}
        for stage in STAGE_LABELS
    ]


def _normalize_contract(contract: dict) -> None:
    """Backfill fields for contracts persisted by older pipeline versions so
    every consumer sees a consistent shape."""
    vision = contract.get("vision")
    if not isinstance(vision, dict):
        contract["vision"] = {
            "status": "NOT_SUPPORTED",
            "available": False,
            "images_found": 0,
            "supported_capabilities": [],
            "reason": "No visual inspection/image training data is available in the current dataset.",
            "requirements": {},
        }
        return
    available = bool(vision.get("available"))
    if not vision.get("status"):
        vision["status"] = "PROFILED" if available else "NOT_SUPPORTED"
    if not vision.get("reason"):
        vision["reason"] = (
            None
            if available
            else "No visual inspection/image training data is available in the current dataset."
        )
    vision.setdefault("available", available)
    vision.setdefault("images_found", 0)
    vision.setdefault("supported_capabilities", [])
    vision.setdefault("requirements", {})


class SessionStore:
    def __init__(self, runtime_dir: Path):
        self.runtime_dir = Path(runtime_dir)
        self.sessions_dir = self.runtime_dir / "sessions"
        self.artifacts_dir = self.runtime_dir / "artifacts"
        self.sessions_dir.mkdir(parents=True, exist_ok=True)
        self.artifacts_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._memory: dict[str, dict] = {}

    # -- lifecycle ---------------------------------------------------------

    def create(self, uploaded_path: Path, contract: dict, ingest_result=None) -> str:
        dataset_id = contract["dataset_id"]
        with self._lock:
            self._memory[dataset_id] = {
                "path": str(uploaded_path),
                "contract": contract,
                "ingest": ingest_result,
                "analysis": None,
                "ml": None,
                "status": "processing",
                "error": None,
                "stages": _initial_stages(),
            }
            for entry in self._memory[dataset_id]["stages"]:
                if entry["id"] == "ingestion":
                    entry["status"] = "complete"
                    entry["detail"] = f"{contract['summary']['total_rows']} rows across {contract['summary']['tables']} table(s)"
            self._persist(contract)
        return dataset_id

    def get(self, dataset_id: str) -> dict | None:
        with self._lock:
            session = self._memory.get(dataset_id)
            if session:
                return session
            stored = self.sessions_dir / f"{dataset_id}.json"
            if stored.exists():
                with open(stored, "r", encoding="utf-8") as fh:
                    contract = json.load(fh)
                _normalize_contract(contract)
                analysis_file = self.artifacts_dir / dataset_id / "analysis.json"
                analysis = None
                if analysis_file.exists():
                    with open(analysis_file, "r", encoding="utf-8") as fh:
                        analysis = json.load(fh)
                return {
                    "path": None,
                    "contract": contract,
                    "ingest": None,
                    "analysis": analysis,
                    "status": "complete" if analysis else "unknown",
                    "error": None,
                    "stages": _initial_stages(),
                }
            return None

    def list(self) -> list[dict]:
        with self._lock:
            entries = {
                sid: {
                    "dataset_id": sid,
                    "filename": s["contract"].get("filename"),
                    "status": s["status"],
                    "ingested_at": s["contract"].get("ingested_at"),
                    "rows": s["contract"].get("summary", {}).get("total_rows"),
                }
                for sid, s in self._memory.items()
            }
        # Include datasets persisted on disk (e.g. after a backend restart) so a
        # previously processed real dataset can be re-selected without re-upload.
        for stored in sorted(self.sessions_dir.glob("*.json")):
            dataset_id = stored.stem
            if dataset_id in entries:
                continue
            try:
                with open(stored, "r", encoding="utf-8") as fh:
                    contract = json.load(fh)
            except Exception:  # noqa: BLE001
                continue
            analysis_exists = (self.artifacts_dir / dataset_id / "analysis.json").exists()
            entries[dataset_id] = {
                "dataset_id": dataset_id,
                "filename": contract.get("filename"),
                "status": "complete" if analysis_exists else "unknown",
                "ingested_at": contract.get("ingested_at"),
                "rows": contract.get("summary", {}).get("total_rows"),
            }
        return list(entries.values())

    # -- pipeline state ----------------------------------------------------

    def get_ingest(self, dataset_id: str):
        with self._lock:
            session = self._memory.get(dataset_id)
            return session.get("ingest") if session else None

    def set_stage(self, dataset_id: str, stage: str, status: str, detail: str | None = None, duration_s: float | None = None) -> None:
        with self._lock:
            session = self._memory.get(dataset_id)
            if not session:
                return
            for entry in session["stages"]:
                if entry["id"] == stage:
                    entry["status"] = status
                    if detail is not None:
                        entry["detail"] = detail
                    if duration_s is not None:
                        entry["duration_s"] = round(duration_s, 3)
                    break

    def set_status(self, dataset_id: str, status: str, error: dict | None = None) -> None:
        with self._lock:
            session = self._memory.get(dataset_id)
            if session:
                session["status"] = status
                session["error"] = error

    def set_analysis(self, dataset_id: str, analysis: dict) -> None:
        with self._lock:
            session = self._memory.get(dataset_id)
            if session:
                session["analysis"] = analysis
                session["status"] = analysis.get("status", "complete")
                session["error"] = analysis.get("error")
                completed = {s["id"]: s for s in analysis.get("stages", [])}
                for entry in session["stages"]:
                    if entry["id"] in completed:
                        entry.update(
                            {
                                "status": completed[entry["id"]].get("status", entry["status"]),
                                "detail": completed[entry["id"]].get("detail"),
                                "duration_s": completed[entry["id"]].get("duration_s"),
                            }
                        )
                    elif analysis.get("status") == "complete" and entry["status"] == "pending":
                        entry["status"] = "skipped"
                        entry["detail"] = "not applicable for this dataset"

    def set_ml(self, dataset_id: str, ml_summary: dict) -> None:
        with self._lock:
            session = self._memory.get(dataset_id)
            if session:
                session["ml"] = ml_summary
                for entry in session["stages"]:
                    if entry["id"] == "model_training":
                        models = ml_summary.get("models", [])
                        ready = [m for m in models if m.get("status") == "READY"]
                        entry["status"] = "failed" if ml_summary.get("status") == "failed" else "complete"
                        entry["detail"] = (
                            f"{len(ready)} model(s) trained and evaluated"
                            if ready
                            else "no predictive targets were supported by this dataset"
                        )
                        entry["duration_s"] = ml_summary.get("total_training_seconds")

    def get_ml(self, dataset_id: str) -> dict | None:
        with self._lock:
            session = self._memory.get(dataset_id)
            if session and session.get("ml") is not None:
                return session["ml"]
        stored = self.artifacts_dir / dataset_id / "ml_summary.json"
        if stored.exists():
            with open(stored, "r", encoding="utf-8") as fh:
                return json.load(fh)
        return None

    def get_status(self, dataset_id: str) -> dict | None:
        with self._lock:
            session = self._memory.get(dataset_id)
            if not session:
                return None
            return {
                "dataset_id": dataset_id,
                "status": session["status"],
                "stages": [dict(s) for s in session["stages"]],
                "error": session["error"],
            }

    def get_analysis(self, dataset_id: str) -> dict | None:
        with self._lock:
            session = self._memory.get(dataset_id)
            if session and session.get("analysis") is not None:
                return session["analysis"]
        # Fall back to the persisted artifact so previously processed datasets
        # remain fully usable after a backend restart.
        analysis_file = self.artifacts_dir / dataset_id / "analysis.json"
        if analysis_file.exists():
            try:
                with open(analysis_file, "r", encoding="utf-8") as fh:
                    return json.load(fh)
            except Exception:  # noqa: BLE001
                return None
        return None

    # -- persistence -------------------------------------------------------

    def _persist(self, contract: dict) -> None:
        target = self.sessions_dir / f"{contract['dataset_id']}.json"
        with open(target, "w", encoding="utf-8") as fh:
            json.dump(contract, fh, indent=2, default=str)
