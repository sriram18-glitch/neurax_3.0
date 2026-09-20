"""NeuraX API - modular monolith.

Endpoints are intentionally thin: ingestion, profiling, pipeline processing and
artifact logic live in app.ingest / app.pipeline. No analysis result is
fabricated anywhere; every response is produced from the uploaded file or
reported as unavailable.
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path

import pandas as pd
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware

from app.core.settings import (
    ARTIFACTS_DIR,
    BACKEND_DIR,
    IMAGES_DIR,
    MODELS_DIR,
    RUNTIME_DIR,
    UPLOAD_DIR,
    VISION_DATASET_DIR,
    VISION_MODEL_DIR,
)
from app.core.store import SessionStore
from app.ingest import IngestError, analyze_path, ingest_path
from app.ml import load_model, run_ml_pipeline
from app.pipeline import run_pipeline
from app.rootcause import RootCauseError, discover_targets, list_analyses, run_root_cause
from app.rootcause import get_analysis as get_root_cause_analysis
from app.flow import FlowError, run_bottleneck_analysis
from app.flow import list_analyses as list_flow_analyses
from app.flow import get_analysis as get_flow_analysis
from app.economics import EconomicsError, run_scenario, sensitivity, validate_and_merge
from app.economics import store as econ_store
from app.recommend import (
    RecommendationError,
    generate_recommendations,
    get_decision_summary,
    get_recommendation,
    list_recommendations,
)
from app.vision.discovery import profile_image_directory
from app.vision.batch import BatchError, create_batch, get_batch, inspect_batch, list_batches, save_batch_raw
from app.vision.review import ReviewError, list_review_queue, record_human_decision, review_stats
from app.vision.source import (
    SourceError,
    SourceStream,
    add_files,
    create_demo_source,
    create_source,
    delete_source,
    get_source,
    inspect_source,
    list_sources,
)
from app.vision.inference import (
    VisionModel,
    VisionModelError,
    get_inspection,
    get_inspection_image,
    list_inspections,
)
from app.vision.service import inference_status, vision_status
from app.vision.stream import InspectionStream
from app.vision.training import dataset_fingerprint, discover_class_dataset, train_vision_model
from app.investigations import get_investigation, list_investigations, run_investigation
from app.flow.timeline import build_timeline

RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
MODELS_DIR.mkdir(parents=True, exist_ok=True)
IMAGES_DIR.mkdir(parents=True, exist_ok=True)

STORE = SessionStore(RUNTIME_DIR)

ALLOWED_SUFFIXES = {".csv", ".txt", ".tsv", ".mat", ".xls", ".xlsx", ".xlsm", ".zip"}

app = FastAPI(
    title="NeuraX - Visual Inspection & Defect Root-Cause Assistant",
    version="0.2.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:4173",
        "http://127.0.0.1:4173",
    ],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def _warm_vision_model() -> None:
    """Load the vision backbone in the background so the first inspection is fast."""
    import threading

    def warm() -> None:
        try:
            model = _get_vision_model()
            if model.available:
                model.warm_up()
        except Exception:  # noqa: BLE001 - warmup must never block startup
            pass

    threading.Thread(target=warm, daemon=True).start()


def _not_found(dataset_id: str) -> HTTPException:
    return HTTPException(
        status_code=404,
        detail=IngestError("DATASET_NOT_FOUND", f"No dataset session '{dataset_id}' exists.").to_dict(),
    )


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok", "service": "neurax-api", "models_initialized": False}


@app.post("/api/upload")
async def upload_dataset(file: UploadFile = File(...)) -> dict:
    original = Path(file.filename or "dataset").name
    suffix = Path(original).suffix.lower()
    if suffix not in ALLOWED_SUFFIXES:
        raise HTTPException(
            status_code=415,
            detail=IngestError(
                "UNSUPPORTED_FORMAT",
                f"'{original}' is not a supported upload. Supported: CSV/TXT/TSV, MAT, XLS/XLSX, ZIP.",
            ).to_dict(),
        )

    dest = UPLOAD_DIR / f"{uuid.uuid4().hex[:8]}_{original}"
    extract_dir = IMAGES_DIR / dest.stem
    try:
        with open(dest, "wb") as out:
            while True:
                chunk = await file.read(1024 * 1024)
                if not chunk:
                    break
                out.write(chunk)
        ingest_result = ingest_path(dest, extract_images_to=extract_dir)
        contract = analyze_path(dest, extract_images_to=extract_dir)
    except IngestError as exc:
        dest.unlink(missing_ok=True)
        raise HTTPException(status_code=422, detail=exc.to_dict())
    except Exception as exc:  # never leak a blank 500 to the UI
        dest.unlink(missing_ok=True)
        raise HTTPException(
            status_code=500,
            detail=IngestError("PROCESSING_FAILURE", "Dataset processing failed unexpectedly.", str(exc)).to_dict(),
        )

    dataset_id = STORE.create(dest, contract, ingest_result=ingest_result)
    analysis = run_pipeline(dataset_id, original, contract, ingest_result, ARTIFACTS_DIR)
    STORE.set_analysis(dataset_id, analysis)

    ml_summary = run_ml_pipeline(dataset_id, analysis, ARTIFACTS_DIR / dataset_id, MODELS_DIR)
    vision = contract.get("vision") or {}
    ml_summary["vision"] = {
        "status": vision.get("status", "NOT_SUPPORTED"),
        "available": vision.get("available", False),
        "images_found": vision.get("images_found", 0),
        "supported_capabilities": vision.get("supported_capabilities", []),
        "reason": vision.get("reason")
        or "Vision training is not implemented; the dataset was profiled but no vision model was trained.",
    }
    STORE.set_ml(dataset_id, ml_summary)

    contract["pipeline"] = {
        "status": analysis.get("status"),
        "stages": analysis.get("stages", []),
        "error": analysis.get("error"),
    }
    contract["ml"] = {
        "status": ml_summary.get("status"),
        "models_trained": len([m for m in ml_summary.get("models", []) if m.get("status") == "READY"]),
        "anomaly_status": ml_summary.get("anomaly", {}).get("status"),
        "vision_status": ml_summary.get("vision", {}).get("status"),
        "error": ml_summary.get("error"),
    }
    if analysis.get("status") == "failed":
        return contract
    return contract


@app.get("/api/datasets/{dataset_id}/vision/status")
def get_vision_status(dataset_id: str) -> dict:
    session = STORE.get(dataset_id)
    if session is None:
        raise _not_found(dataset_id)
    vision = dict(session["contract"].get("vision") or {})
    # Normalize contracts persisted before the vision block carried a status.
    if not vision.get("status"):
        available = bool(vision.get("available"))
        vision["status"] = "PROFILED" if available else "NOT_SUPPORTED"
        vision.setdefault(
            "reason",
            None
            if available
            else "No visual inspection/image training data is available in the current dataset.",
        )
        vision.setdefault("available", available)
        vision.setdefault("images_found", 0)
        vision.setdefault("supported_capabilities", [])
    return {"dataset_id": dataset_id, **vision}


@app.get("/api/datasets/{dataset_id}/vision/profile")
def get_vision_profile(dataset_id: str) -> dict:
    session = STORE.get(dataset_id)
    if session is None:
        raise _not_found(dataset_id)
    vision = session["contract"].get("vision") or {}
    if vision.get("profile") is None:
        return {
            "dataset_id": dataset_id,
            "status": vision.get("status", "NOT_SUPPORTED"),
            "available": False,
            "reason": vision.get("reason"),
            "requirements": vision.get("requirements"),
            "profile": None,
        }
    return {"dataset_id": dataset_id, "status": vision.get("status"), "available": True, "profile": vision["profile"]}


@app.post("/api/datasets/{dataset_id}/vision/train")
def train_vision(dataset_id: str) -> dict:
    session = STORE.get(dataset_id)
    if session is None:
        raise _not_found(dataset_id)
    vision = session["contract"].get("vision") or {}
    if not vision.get("available"):
        raise HTTPException(
            status_code=422,
            detail=IngestError(
                "VISION_NOT_SUPPORTED",
                vision.get("reason") or "No visual inspection data is available for this dataset.",
                "Supply a ZIP archive containing images (class folders and/or a normal/ folder). See requirements for details.",
            ).to_dict(),
        )
    supported = vision.get("supported_capabilities", [])
    if not supported:
        raise HTTPException(
            status_code=422,
            detail=IngestError(
                "VISION_STRUCTURE_INSUFFICIENT",
                "Images were found but the folder structure does not support any vision capability yet.",
                "See the vision profile: class folders need >= 10 images each, or a normal/ folder needs >= 20 images.",
            ).to_dict(),
        )
    raise HTTPException(
        status_code=501,
        detail=IngestError(
            "VISION_TRAINING_NOT_IMPLEMENTED",
            "Vision training is not implemented yet; this phase profiles real image data and reports readiness honestly.",
            "The dataset passed profiling. Model training will be implemented once this structure is confirmed on real data.",
        ).to_dict(),
    )


_VISION_MODEL: VisionModel | None = None


def _get_vision_model() -> VisionModel:
    global _VISION_MODEL
    if _VISION_MODEL is None:
        _VISION_MODEL = VisionModel(VISION_MODEL_DIR)
    return _VISION_MODEL


@app.get("/api/vision/status")
def vision_model_status() -> dict:
    model = _get_vision_model()
    dataset = profile_image_directory(VISION_DATASET_DIR) if VISION_DATASET_DIR.exists() else None
    if not model.available:
        return {
            "status": "NOT_TRAINED",
            "model_available": False,
            "reason": "No vision model has been trained yet.",
            "dataset_dir": str(VISION_DATASET_DIR),
            "dataset_available": bool(dataset and dataset["image_count"] > 0),
            "requirements": {
                "needs": "Class-folder image dataset with a normal/ class for PASS decisions.",
                "minimum": "2+ classes with a reasonable number of images per class.",
            },
        }
    return {
        "status": "READY",
        "model_available": True,
        "classes": model.class_names,
        "normal_class": model.class_names[model.normal_index],
        "metrics": model.metrics,
        "metadata": model.metadata,
        "thresholds": model.thresholds,
        "temperature": model.temperature,
        "dataset_dir": str(VISION_DATASET_DIR),
    }


@app.get("/api/vision/dataset")
def vision_dataset_profile() -> dict:
    if not VISION_DATASET_DIR.exists():
        raise HTTPException(
            status_code=404,
            detail=IngestError(
                "VISION_DATASET_NOT_FOUND",
                "No image dataset folder was found.",
                f"Expected a class-folder dataset at {VISION_DATASET_DIR}.",
            ).to_dict(),
        )
    profile = profile_image_directory(VISION_DATASET_DIR)
    classes = discover_class_dataset(VISION_DATASET_DIR)
    return {
        "dataset_dir": str(VISION_DATASET_DIR),
        "fingerprint": dataset_fingerprint(VISION_DATASET_DIR),
        "profile": profile,
        "class_counts": {name: len(files) for name, files in sorted(classes.items())},
        "annotations": profile.get("annotations"),
    }


@app.post("/api/vision/train")
def vision_train(body: dict | None = None) -> dict:
    global _VISION_MODEL
    body = body or {}
    dataset_dir = Path(body.get("dataset_dir", VISION_DATASET_DIR))
    resolved = dataset_dir.resolve()
    project_root = (BACKEND_DIR.parent).resolve()
    if project_root not in resolved.parents and resolved != project_root:
        raise HTTPException(
            status_code=422,
            detail=IngestError(
                "DATASET_PATH_NOT_ALLOWED",
                "The dataset path must be inside the project folder.",
                str(resolved),
            ).to_dict(),
        )
    if not resolved.exists():
        raise HTTPException(
            status_code=404,
            detail=IngestError("VISION_DATASET_NOT_FOUND", f"Dataset folder not found: {resolved}").to_dict(),
        )
    try:
        result = train_vision_model(
            resolved,
            VISION_MODEL_DIR,
            use_cached_embeddings=bool(body.get("use_cached_embeddings", False)),
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail=IngestError("VISION_DATASET_INVALID", str(exc)).to_dict(),
        )
    _VISION_MODEL = VisionModel(VISION_MODEL_DIR)
    return result


@app.post("/api/vision/inspect")
async def vision_inspect_image(file: UploadFile = File(...)) -> dict:
    filename = Path(file.filename or "inspection").name
    suffix = Path(filename).suffix.lower()
    if suffix not in {".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff", ".webp"}:
        raise HTTPException(
            status_code=415,
            detail=IngestError(
                "UNSUPPORTED_IMAGE_FORMAT",
                f"'{filename}' is not a supported image. Supported: PNG, JPG, JPEG, BMP, TIFF, WEBP.",
            ).to_dict(),
        )
    image_bytes = await file.read()
    if not image_bytes:
        raise HTTPException(
            status_code=422,
            detail=IngestError("EMPTY_IMAGE", "The uploaded image file is empty.").to_dict(),
        )
    model = _get_vision_model()
    try:
        return model.inspect(image_bytes, filename)
    except VisionModelError as exc:
        raise HTTPException(status_code=503, detail=exc.to_dict())


@app.post("/api/vision/inspect/stream")
async def vision_inspect_stream(file: UploadFile = File(...)):
    """Stream the inspection stage-by-stage as NDJSON.

    Each line is one JSON event: {"event": "stage", "stage": {...}} emitted the
    moment that stage completes (with its real metrics and intermediate
    artifacts), then {"event": "result", "result": {...}} or an error event.
    The UI animates from these real events.
    """
    from fastapi.responses import StreamingResponse

    filename = Path(file.filename or "inspection").name
    suffix = Path(filename).suffix.lower()
    if suffix not in {".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff", ".webp"}:
        raise HTTPException(
            status_code=415,
            detail=IngestError(
                "UNSUPPORTED_IMAGE_FORMAT",
                f"'{filename}' is not a supported image. Supported: PNG, JPG, JPEG, BMP, TIFF, WEBP.",
            ).to_dict(),
        )
    image_bytes = await file.read()
    if not image_bytes:
        raise HTTPException(
            status_code=422,
            detail=IngestError("EMPTY_IMAGE", "The uploaded image file is empty.").to_dict(),
        )
    model = _get_vision_model()

    def generate():
        try:
            for event in model.inspect_events(image_bytes, filename):
                yield json.dumps(event, default=str) + "\n"
        except VisionModelError as exc:
            yield json.dumps({"event": "error", "error": exc.to_dict()}, default=str) + "\n"
        except Exception as exc:  # noqa: BLE001 - never leak a broken stream
            yield json.dumps(
                {
                    "event": "error",
                    "error": {
                        "error": True,
                        "code": "INSPECTION_FAILURE",
                        "message": "Inspection failed unexpectedly.",
                        "detail": str(exc),
                    },
                },
                default=str,
            ) + "\n"

    return StreamingResponse(
        generate(),
        media_type="application/x-ndjson",
        headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
    )


@app.get("/api/vision/inspect/{inspection_id}")
def vision_inspection_get(inspection_id: str) -> dict:
    payload = get_inspection(VISION_MODEL_DIR, inspection_id)
    if payload is None:
        raise HTTPException(
            status_code=404,
            detail=IngestError("INSPECTION_NOT_FOUND", f"Inspection '{inspection_id}' does not exist.").to_dict(),
        )
    return payload


@app.get("/api/vision/inspect/{inspection_id}/trace")
def vision_inspection_trace(inspection_id: str) -> dict:
    payload = get_inspection(VISION_MODEL_DIR, inspection_id)
    if payload is None:
        raise HTTPException(
            status_code=404,
            detail=IngestError("INSPECTION_NOT_FOUND", f"Inspection '{inspection_id}' does not exist.").to_dict(),
        )
    trace = payload.get("trace", [])
    return {
        "inspection_id": inspection_id,
        "stage_count": len(trace),
        "stages": trace,
        "note": "Observable engineering pipeline stages - not model chain-of-thought.",
    }


@app.get("/api/vision/inspect/{inspection_id}/image")
def vision_inspection_image(inspection_id: str):
    from fastapi.responses import FileResponse

    path = get_inspection_image(VISION_MODEL_DIR, inspection_id)
    if path is None:
        raise HTTPException(
            status_code=404,
            detail=IngestError("INSPECTION_IMAGE_NOT_FOUND", f"No stored image for inspection '{inspection_id}'.").to_dict(),
        )
    return FileResponse(path, media_type="image/png", filename=f"{inspection_id}.png")


@app.get("/api/vision/history")
def vision_history() -> dict:
    inspections = list_inspections(VISION_MODEL_DIR)
    return {"inspections": inspections, "count": len(inspections)}


@app.get("/api/datasets/{dataset_id}/vision/models")
def list_vision_models(dataset_id: str) -> dict:
    session = STORE.get(dataset_id)
    if session is None:
        raise _not_found(dataset_id)
    return {
        "dataset_id": dataset_id,
        "status": "NOT_INITIALIZED",
        "models": [],
        "reason": "No vision model has been trained for this dataset.",
    }


def _rca_context(dataset_id: str) -> tuple[dict, Path]:
    session = STORE.get(dataset_id)
    if session is None:
        raise _not_found(dataset_id)
    analysis = STORE.get_analysis(dataset_id)
    if analysis is None or analysis.get("status") != "complete":
        raise HTTPException(
            status_code=409,
            detail=IngestError(
                "ANALYSIS_NOT_COMPLETE",
                f"Phase 3 analysis for dataset '{dataset_id}' is not complete; root-cause analysis is unavailable.",
            ).to_dict(),
        )
    return analysis, ARTIFACTS_DIR / dataset_id


@app.get("/api/datasets/{dataset_id}/root-cause/status")
def root_cause_status(dataset_id: str) -> dict:
    analysis, artifact_root = _rca_context(dataset_id)
    targets = discover_targets(dataset_id, analysis, artifact_root)
    rca_dir = artifact_root / "root_cause"
    registry = list_analyses(rca_dir)
    return {
        "dataset_id": dataset_id,
        "status": "READY" if targets else "NOT_SUPPORTED",
        "reason": None
        if targets
        else "No response/target columns with sufficient data were found for root-cause analysis.",
        "targets_available": len(targets),
        "analyses_run": len(registry),
        "last_analysis_id": registry[-1]["analysis_id"] if registry else None,
        "epistemic_note": "Findings are statistical associations and model contributions, never proven causes.",
    }


@app.get("/api/datasets/{dataset_id}/root-cause/targets")
def root_cause_targets(dataset_id: str) -> dict:
    analysis, artifact_root = _rca_context(dataset_id)
    targets = discover_targets(dataset_id, analysis, artifact_root)
    return {
        "dataset_id": dataset_id,
        "targets": targets,
        "count": len(targets),
        "note": "Events are defined as distribution tails (low/high quantile) of the selected target.",
    }


@app.post("/api/datasets/{dataset_id}/root-cause/analyze")
def root_cause_analyze(dataset_id: str, body: dict | None = None) -> dict:
    analysis, artifact_root = _rca_context(dataset_id)
    body = body or {}
    target = body.get("target")
    if not target:
        raise HTTPException(
            status_code=422,
            detail=IngestError("TARGET_REQUIRED", "Provide 'target' in the request body.").to_dict(),
        )
    direction = body.get("direction", "low")
    quantile = float(body.get("quantile", 0.10))
    input_name = body.get("input")
    result = run_root_cause(
        dataset_id,
        str(target),
        str(direction),
        quantile,
        analysis,
        artifact_root,
        MODELS_DIR,
        input_name=input_name,
    )
    if result.get("status") == "failed":
        error = result.get("error") or {}
        status_code = 422 if error.get("code") in {"TARGET_NOT_FOUND", "INVALID_DIRECTION", "INVALID_QUANTILE", "INSUFFICIENT_DATA"} else 500
        raise HTTPException(status_code=status_code, detail=error)
    return result


@app.get("/api/datasets/{dataset_id}/root-cause/findings")
def root_cause_findings(dataset_id: str) -> dict:
    analysis, artifact_root = _rca_context(dataset_id)
    rca_dir = artifact_root / "root_cause"
    registry = list_analyses(rca_dir)
    return {"dataset_id": dataset_id, "analyses": registry, "count": len(registry)}


@app.get("/api/datasets/{dataset_id}/root-cause/drift")
def root_cause_drift(dataset_id: str) -> dict:
    analysis, artifact_root = _rca_context(dataset_id)
    registry = list_analyses(artifact_root / "root_cause")
    if registry:
        latest = get_root_cause_analysis(artifact_root / "root_cause", registry[-1]["analysis_id"])
        if latest and latest.get("drift"):
            return {"dataset_id": dataset_id, "analysis_id": registry[-1]["analysis_id"], **latest["drift"]}
    return {
        "dataset_id": dataset_id,
        "status": "NOT_ANALYZED",
        "reason": "No root-cause analysis has been run yet; drift is computed during analysis.",
    }


@app.get("/api/datasets/{dataset_id}/root-cause/{analysis_id}")
def root_cause_get(dataset_id: str, analysis_id: str) -> dict:
    session = STORE.get(dataset_id)
    if session is None:
        raise _not_found(dataset_id)
    artifact_root = ARTIFACTS_DIR / dataset_id
    payload = get_root_cause_analysis(artifact_root / "root_cause", analysis_id)
    if payload is None:
        raise HTTPException(
            status_code=404,
            detail=IngestError("ANALYSIS_NOT_FOUND", f"Root-cause analysis '{analysis_id}' does not exist for dataset '{dataset_id}'.").to_dict(),
        )
    return payload


@app.get("/api/datasets/{dataset_id}/bottleneck/status")
def bottleneck_status(dataset_id: str) -> dict:
    session = STORE.get(dataset_id)
    if session is None:
        raise _not_found(dataset_id)
    analysis = STORE.get_analysis(dataset_id)
    if analysis is None or analysis.get("status") != "complete":
        raise HTTPException(
            status_code=409,
            detail=IngestError("ANALYSIS_NOT_COMPLETE", f"Phase 3 analysis for dataset '{dataset_id}' is not complete.").to_dict(),
        )
    artifact_root = ARTIFACTS_DIR / dataset_id
    station_metrics = None
    station_metrics_path = artifact_root / "station_metrics.json"
    if station_metrics_path.exists():
        try:
            import json as _json

            payload = _json.loads(station_metrics_path.read_text(encoding="utf-8"))
            for table in payload.get("tables", []):
                if table.get("station_count", 0) > 0:
                    station_metrics = table
                    break
        except Exception:  # noqa: BLE001
            station_metrics = None
    registry = list_flow_analyses(artifact_root / "bottleneck")
    return {
        "dataset_id": dataset_id,
        "status": "READY" if station_metrics else "NOT_SUPPORTED",
        "reason": None if station_metrics else "No station or cell identifiers were detected in this dataset.",
        "stations_available": station_metrics["station_count"] if station_metrics else 0,
        "analyses_run": len(registry),
        "last_analysis_id": registry[-1]["analysis_id"] if registry else None,
        "epistemic_note": "Bottleneck findings are evidence-based hypotheses, never proven constraints.",
    }


@app.get("/api/datasets/{dataset_id}/bottleneck/stations")
def bottleneck_stations(dataset_id: str) -> dict:
    session = STORE.get(dataset_id)
    if session is None:
        raise _not_found(dataset_id)
    artifact_root = ARTIFACTS_DIR / dataset_id
    registry = list_flow_analyses(artifact_root / "bottleneck")
    if registry:
        latest = get_flow_analysis(artifact_root / "bottleneck", registry[-1]["analysis_id"])
        if latest:
            return {
                "dataset_id": dataset_id,
                "analysis_id": latest["analysis_id"],
                "stations": latest["station_rankings"],
                "count": latest["stations_analyzed"],
            }
    # no analysis yet: return raw Phase 3 station metrics without scoring
    station_metrics_path = artifact_root / "station_metrics.json"
    if not station_metrics_path.exists():
        return {"dataset_id": dataset_id, "stations": [], "count": 0, "note": "No station metrics available."}
    import json as _json

    payload = _json.loads(station_metrics_path.read_text(encoding="utf-8"))
    table = next((t for t in payload.get("tables", []) if t.get("station_count", 0) > 0), None)
    return {
        "dataset_id": dataset_id,
        "stations": (table or {}).get("stations", []),
        "count": (table or {}).get("station_count", 0),
        "note": "Raw Phase 3 station metrics; run /bottleneck/analyze for scored findings.",
    }


@app.post("/api/datasets/{dataset_id}/bottleneck/analyze")
def bottleneck_analyze(dataset_id: str, body: dict | None = None) -> dict:
    session = STORE.get(dataset_id)
    if session is None:
        raise _not_found(dataset_id)
    analysis = STORE.get_analysis(dataset_id)
    if analysis is None or analysis.get("status") != "complete":
        raise HTTPException(
            status_code=409,
            detail=IngestError("ANALYSIS_NOT_COMPLETE", f"Phase 3 analysis for dataset '{dataset_id}' is not complete.").to_dict(),
        )
    body = body or {}
    result = run_bottleneck_analysis(
        dataset_id,
        analysis,
        ARTIFACTS_DIR / dataset_id,
        input_name=body.get("input"),
    )
    if result.get("status") == "failed":
        error = result.get("error") or {}
        status_code = 422 if error.get("code") == "NO_STATION_DATA" else 500
        raise HTTPException(status_code=status_code, detail=error)
    return result


@app.get("/api/datasets/{dataset_id}/bottleneck/findings")
def bottleneck_findings(dataset_id: str) -> dict:
    session = STORE.get(dataset_id)
    if session is None:
        raise _not_found(dataset_id)
    registry = list_flow_analyses(ARTIFACTS_DIR / dataset_id / "bottleneck")
    return {"dataset_id": dataset_id, "analyses": registry, "count": len(registry)}


@app.get("/api/datasets/{dataset_id}/bottleneck/flow")
def bottleneck_flow(dataset_id: str) -> dict:
    session = STORE.get(dataset_id)
    if session is None:
        raise _not_found(dataset_id)
    artifact_root = ARTIFACTS_DIR / dataset_id
    registry = list_flow_analyses(artifact_root / "bottleneck")
    if registry:
        latest = get_flow_analysis(artifact_root / "bottleneck", registry[-1]["analysis_id"])
        if latest:
            return {"dataset_id": dataset_id, "analysis_id": latest["analysis_id"], **latest["flow"]}
    flow_path = artifact_root / "bottleneck" / "flow.json"
    if flow_path.exists():
        import json as _json

        return {"dataset_id": dataset_id, **_json.loads(flow_path.read_text(encoding="utf-8"))}
    return {
        "dataset_id": dataset_id,
        "status": "NOT_ANALYZED",
        "reason": "No bottleneck analysis has been run yet.",
    }


@app.get("/api/datasets/{dataset_id}/bottleneck/{analysis_id}")
def bottleneck_get(dataset_id: str, analysis_id: str) -> dict:
    session = STORE.get(dataset_id)
    if session is None:
        raise _not_found(dataset_id)
    payload = get_flow_analysis(ARTIFACTS_DIR / dataset_id / "bottleneck", analysis_id)
    if payload is None:
        raise HTTPException(
            status_code=404,
            detail=IngestError("ANALYSIS_NOT_FOUND", f"Bottleneck analysis '{analysis_id}' does not exist for dataset '{dataset_id}'.").to_dict(),
        )
    return payload


def _economics_context(dataset_id: str) -> tuple[dict, Path]:
    session = STORE.get(dataset_id)
    if session is None:
        raise _not_found(dataset_id)
    artifact_root = ARTIFACTS_DIR / dataset_id
    bottleneck = econ_store.latest_bottleneck(artifact_root)
    return {"bottleneck": bottleneck}, artifact_root


@app.get("/api/datasets/{dataset_id}/economics/status")
def economics_status(dataset_id: str) -> dict:
    session = STORE.get(dataset_id)
    if session is None:
        raise _not_found(dataset_id)
    artifact_root = ARTIFACTS_DIR / dataset_id
    bottleneck = econ_store.latest_bottleneck(artifact_root)
    assumptions = econ_store.get_assumptions(artifact_root, dataset_id)
    entries = (assumptions.get("assumptions") or {})
    supplied = [field for field, entry in entries.items() if (entry or {}).get("value") is not None]
    missing = [field for field, entry in entries.items() if (entry or {}).get("value") is None]
    currency = (assumptions.get("currency") or {}).get("value")
    what_if = (bottleneck or {}).get("what_if_inputs") or {}
    observed = ((what_if.get("observed_impact") or {}).get("observed") or {})
    return {
        "dataset_id": dataset_id,
        "status": "READY" if bottleneck else "NOT_ANALYZED",
        "reason": None if bottleneck else "Run a bottleneck analysis first; economics build on Phase 7 outputs.",
        "bottleneck_analysis_id": (bottleneck or {}).get("analysis_id"),
        "bottleneck_station": ((bottleneck or {}).get("candidate_bottleneck") or {}).get("station"),
        "throughput_available": bool(observed) or what_if.get("throughput") is not None,
        "assumptions_supplied": supplied,
        "assumptions_missing": missing,
        "currency": currency,
        "epistemic_note": "Economic outputs require user assumptions and are advisory only.",
    }


@app.get("/api/datasets/{dataset_id}/economics/assumptions")
def economics_get_assumptions(dataset_id: str) -> dict:
    session = STORE.get(dataset_id)
    if session is None:
        raise _not_found(dataset_id)
    return econ_store.get_assumptions(ARTIFACTS_DIR / dataset_id, dataset_id)


@app.put("/api/datasets/{dataset_id}/economics/assumptions")
def economics_put_assumptions(dataset_id: str, body: dict | None = None) -> dict:
    session = STORE.get(dataset_id)
    if session is None:
        raise _not_found(dataset_id)
    artifact_root = ARTIFACTS_DIR / dataset_id
    existing = econ_store.get_assumptions(artifact_root, dataset_id)
    try:
        merged = validate_and_merge(existing, body or {})
    except EconomicsError as exc:
        raise HTTPException(status_code=422, detail=exc.to_dict())
    econ_store.put_assumptions(artifact_root, dataset_id, merged)
    return merged


@app.get("/api/datasets/{dataset_id}/economics/baseline")
def economics_baseline(dataset_id: str) -> dict:
    session = STORE.get(dataset_id)
    if session is None:
        raise _not_found(dataset_id)
    return econ_store.compute_baseline(ARTIFACTS_DIR / dataset_id, dataset_id)


@app.post("/api/datasets/{dataset_id}/economics/scenario")
def economics_scenario(dataset_id: str, body: dict | None = None) -> dict:
    session = STORE.get(dataset_id)
    if session is None:
        raise _not_found(dataset_id)
    artifact_root = ARTIFACTS_DIR / dataset_id
    bottleneck = econ_store.latest_bottleneck(artifact_root)
    if bottleneck is None:
        raise HTTPException(
            status_code=409,
            detail=IngestError(
                "BOTTLENECK_NOT_ANALYZED",
                f"No bottleneck analysis exists for dataset '{dataset_id}'; run /bottleneck/analyze first.",
            ).to_dict(),
        )
    body = body or {}
    assumptions = econ_store.get_assumptions(artifact_root, dataset_id)
    try:
        payload = run_scenario(
            dataset_id,
            bottleneck,
            assumptions,
            str(body.get("scenario_type", "")),
            body.get("changes") or {},
            seed=int(body.get("seed", 42)),
        )
    except EconomicsError as exc:
        raise HTTPException(status_code=422, detail=exc.to_dict())
    econ_store.save_scenario(artifact_root, payload)
    if body.get("sensitivity"):
        parameter = str(body["sensitivity"].get("parameter", "utilization_reduction"))
        values = body["sensitivity"].get("values") or [0.05, 0.10, 0.15, 0.20]
        payload["sensitivity"] = sensitivity(
            dataset_id, bottleneck, assumptions, payload["scenario_type"], parameter, [float(v) for v in values]
        )
    return payload


@app.get("/api/datasets/{dataset_id}/economics/scenarios")
def economics_scenarios(dataset_id: str) -> dict:
    session = STORE.get(dataset_id)
    if session is None:
        raise _not_found(dataset_id)
    registry = econ_store.list_scenarios(ARTIFACTS_DIR / dataset_id)
    return {"dataset_id": dataset_id, "scenarios": registry, "count": len(registry)}


@app.get("/api/datasets/{dataset_id}/economics/{scenario_id}")
def economics_scenario_get(dataset_id: str, scenario_id: str) -> dict:
    session = STORE.get(dataset_id)
    if session is None:
        raise _not_found(dataset_id)
    payload = econ_store.get_scenario(ARTIFACTS_DIR / dataset_id, scenario_id)
    if payload is None:
        raise HTTPException(
            status_code=404,
            detail=IngestError("SCENARIO_NOT_FOUND", f"Scenario '{scenario_id}' does not exist for dataset '{dataset_id}'.").to_dict(),
        )
    return payload


@app.post("/api/datasets/{dataset_id}/what-if")
def what_if(dataset_id: str, body: dict | None = None) -> dict:
    return economics_scenario(dataset_id, body)


@app.get("/api/datasets/{dataset_id}/what-if/{scenario_id}")
def what_if_get(dataset_id: str, scenario_id: str) -> dict:
    return economics_scenario_get(dataset_id, scenario_id)


@app.get("/api/datasets/{dataset_id}/recommendations/status")
def recommendations_status(dataset_id: str) -> dict:
    session = STORE.get(dataset_id)
    if session is None:
        raise _not_found(dataset_id)
    artifact_root = ARTIFACTS_DIR / dataset_id
    registry = list_recommendations(artifact_root)
    return {
        "dataset_id": dataset_id,
        "status": "GENERATED" if registry else "NOT_GENERATED",
        "reason": None if registry else "Run POST /recommendations/generate to produce recommendations.",
        "recommendation_count": len(registry),
        "generated_at": registry[0]["generated_at"] if registry else None,
        "epistemic_note": "Recommendations are advisory decision support, never machine-control commands.",
    }


@app.post("/api/datasets/{dataset_id}/recommendations/generate")
def recommendations_generate(dataset_id: str) -> dict:
    session = STORE.get(dataset_id)
    if session is None:
        raise _not_found(dataset_id)
    contract = session.get("contract") or {}
    payload = generate_recommendations(dataset_id, contract, ARTIFACTS_DIR / dataset_id)
    return payload


@app.get("/api/datasets/{dataset_id}/recommendations")
def recommendations_list(dataset_id: str) -> dict:
    session = STORE.get(dataset_id)
    if session is None:
        raise _not_found(dataset_id)
    artifact_root = ARTIFACTS_DIR / dataset_id
    registry = list_recommendations(artifact_root)
    summary = get_decision_summary(artifact_root)
    return {
        "dataset_id": dataset_id,
        "recommendations": registry,
        "count": len(registry),
        "decision_summary": summary,
    }


@app.get("/api/datasets/{dataset_id}/recommendations/{recommendation_id}/evidence")
def recommendations_evidence(dataset_id: str, recommendation_id: str) -> dict:
    session = STORE.get(dataset_id)
    if session is None:
        raise _not_found(dataset_id)
    payload = get_recommendation(ARTIFACTS_DIR / dataset_id, recommendation_id)
    if payload is None:
        raise HTTPException(
            status_code=404,
            detail=IngestError("RECOMMENDATION_NOT_FOUND", f"Recommendation '{recommendation_id}' does not exist for dataset '{dataset_id}'.").to_dict(),
        )
    return {
        "dataset_id": dataset_id,
        "recommendation_id": recommendation_id,
        "action_type": payload["action_type"],
        "why": payload["why"],
        "evidence": payload["evidence"],
        "assumptions": payload["assumptions"],
        "simulated_effect": payload["simulated_effect"],
        "economic_effect": payload["economic_effect"],
        "limitations": payload["limitations"],
        "epistemic_status": payload["epistemic_status"],
        "source_artifacts": payload["source_artifacts"],
    }


@app.get("/api/datasets/{dataset_id}/recommendations/{recommendation_id}")
def recommendations_get(dataset_id: str, recommendation_id: str) -> dict:
    session = STORE.get(dataset_id)
    if session is None:
        raise _not_found(dataset_id)
    payload = get_recommendation(ARTIFACTS_DIR / dataset_id, recommendation_id)
    if payload is None:
        raise HTTPException(
            status_code=404,
            detail=IngestError("RECOMMENDATION_NOT_FOUND", f"Recommendation '{recommendation_id}' does not exist for dataset '{dataset_id}'.").to_dict(),
        )
    return payload


@app.get("/api/datasets")
def list_datasets() -> dict:
    return {"datasets": STORE.list()}


@app.get("/api/datasets/{dataset_id}")
def get_dataset(dataset_id: str) -> dict:
    session = STORE.get(dataset_id)
    if session is None:
        raise _not_found(dataset_id)
    return session["contract"]


@app.get("/api/datasets/{dataset_id}/profile")
def get_profile(dataset_id: str) -> dict:
    session = STORE.get(dataset_id)
    if session is None:
        raise _not_found(dataset_id)
    return session["contract"]


@app.get("/api/datasets/{dataset_id}/status")
def get_status(dataset_id: str) -> dict:
    session = STORE.get(dataset_id)
    if session is None:
        raise _not_found(dataset_id)
    status = STORE.get_status(dataset_id)
    if status is not None:
        return status
    analysis = session.get("analysis")
    return {
        "dataset_id": dataset_id,
        "status": session.get("status", "unknown"),
        "stages": analysis.get("stages", []) if analysis else [],
        "error": analysis.get("error") if analysis else None,
    }


@app.get("/api/datasets/{dataset_id}/analysis")
def get_analysis(dataset_id: str) -> dict:
    session = STORE.get(dataset_id)
    if session is None:
        raise _not_found(dataset_id)
    analysis = STORE.get_analysis(dataset_id)
    if analysis is None:
        raise HTTPException(
            status_code=409,
            detail=IngestError(
                "ANALYSIS_NOT_READY",
                f"Analysis for dataset '{dataset_id}' is not available yet.",
            ).to_dict(),
        )
    return analysis


@app.post("/api/datasets/{dataset_id}/models/train")
def train_models(dataset_id: str) -> dict:
    session = STORE.get(dataset_id)
    if session is None:
        raise _not_found(dataset_id)
    analysis = STORE.get_analysis(dataset_id)
    if analysis is None or analysis.get("status") != "complete":
        raise HTTPException(
            status_code=409,
            detail=IngestError(
                "ANALYSIS_NOT_COMPLETE",
                f"Phase 3 analysis for dataset '{dataset_id}' is not complete; cannot train models.",
            ).to_dict(),
        )
    ml_summary = run_ml_pipeline(dataset_id, analysis, ARTIFACTS_DIR / dataset_id, MODELS_DIR)
    vision = session["contract"].get("vision") or {}
    ml_summary["vision"] = {
        "status": vision.get("status", "NOT_SUPPORTED"),
        "available": vision.get("available", False),
        "images_found": vision.get("images_found", 0),
        "supported_capabilities": vision.get("supported_capabilities", []),
        "reason": vision.get("reason")
        or "Vision training is not implemented; the dataset was profiled but no vision model was trained.",
    }
    STORE.set_ml(dataset_id, ml_summary)
    return ml_summary


@app.get("/api/datasets/{dataset_id}/models")
def list_models(dataset_id: str) -> dict:
    session = STORE.get(dataset_id)
    if session is None:
        raise _not_found(dataset_id)
    ml_summary = STORE.get_ml(dataset_id)
    if ml_summary is None:
        return {"dataset_id": dataset_id, "status": "NOT_INITIALIZED", "models": []}
    return {
        "dataset_id": dataset_id,
        "status": ml_summary.get("status"),
        "models": ml_summary.get("models", []),
        "skipped_inputs": ml_summary.get("skipped_inputs", []),
        "vision": ml_summary.get("vision"),
        "total_training_seconds": ml_summary.get("total_training_seconds"),
    }


@app.get("/api/datasets/{dataset_id}/models/{model_id}")
def get_model(dataset_id: str, model_id: str) -> dict:
    session = STORE.get(dataset_id)
    if session is None:
        raise _not_found(dataset_id)
    from app.ml.registry import ModelRegistry

    registry = ModelRegistry(MODELS_DIR)
    payload = registry.get_metadata(dataset_id, model_id)
    if payload is None:
        raise HTTPException(
            status_code=404,
            detail=IngestError("MODEL_NOT_FOUND", f"Model '{model_id}' does not exist for dataset '{dataset_id}'.").to_dict(),
        )
    return {"dataset_id": dataset_id, "model_id": model_id, **payload}


@app.get("/api/datasets/{dataset_id}/predictions")
def get_predictions(dataset_id: str) -> dict:
    session = STORE.get(dataset_id)
    if session is None:
        raise _not_found(dataset_id)
    ml_summary = STORE.get_ml(dataset_id)
    if ml_summary is None:
        raise HTTPException(
            status_code=409,
            detail=IngestError("MODELS_NOT_READY", f"No model run exists yet for dataset '{dataset_id}'.").to_dict(),
        )
    directory = ARTIFACTS_DIR / dataset_id / "predictions"
    previews = []
    for name in ml_summary.get("prediction_preview_files", []):
        path = directory / name
        if path.exists():
            frame = pd.read_csv(path)
            previews.append({"file": name, "rows": int(frame.shape[0]), "columns": list(frame.columns)})
    return {
        "dataset_id": dataset_id,
        "previews": previews,
        "models": ml_summary.get("models", []),
        "note": "Preview files contain test-split predictions only (leakage-safe).",
    }


@app.get("/api/datasets/{dataset_id}/anomalies")
def get_anomalies(dataset_id: str, limit: int = 100) -> dict:
    session = STORE.get(dataset_id)
    if session is None:
        raise _not_found(dataset_id)
    ml_summary = STORE.get_ml(dataset_id)
    if ml_summary is None:
        raise HTTPException(
            status_code=409,
            detail=IngestError("MODELS_NOT_READY", f"No model run exists yet for dataset '{dataset_id}'.").to_dict(),
        )
    anomaly = ml_summary.get("anomaly", {})
    examples = anomaly.get("top_examples", [])[: max(1, min(limit, 500))]
    return {
        "dataset_id": dataset_id,
        "status": anomaly.get("status"),
        "method": anomaly.get("method"),
        "detector_kind": anomaly.get("detector_kind"),
        "reason": anomaly.get("reason"),
        "features": anomaly.get("features", []),
        "summary": anomaly.get("summary"),
        "top_examples": examples,
        "terminology": "PROCESS / FEATURE-SPACE ANOMALY DETECTION - not a defect label and not visual OOD detection.",
    }


# ---------------------------------------------------------------------------
# V2: production stream, feature space, process timeline, investigations
# ---------------------------------------------------------------------------

STREAM = SourceStream()


def _stream_error(error: VisionModelError | SourceError) -> HTTPException:
    status = 503 if isinstance(error, VisionModelError) else 409
    return HTTPException(status_code=status, detail=error.to_dict())


@app.get("/api/vision/stream/status")
def vision_stream_status() -> dict:
    return STREAM.status()


@app.post("/api/vision/stream/start")
def vision_stream_start() -> dict:
    try:
        return STREAM.start()
    except (VisionModelError, SourceError) as error:
        raise _stream_error(error) from error


@app.post("/api/vision/stream/pause")
def vision_stream_pause() -> dict:
    return STREAM.pause()


@app.post("/api/vision/stream/resume")
def vision_stream_resume() -> dict:
    try:
        return STREAM.resume()
    except (VisionModelError, SourceError) as error:
        raise _stream_error(error) from error


@app.post("/api/vision/stream/reset")
def vision_stream_reset() -> dict:
    """Reset the CURRENT source's stream - never a hardcoded dataset."""
    return STREAM.reset()


@app.post("/api/vision/stream/speed")
def vision_stream_speed(body: dict | None = None) -> dict:
    body = body or {}
    return STREAM.set_speed(body.get("speed", 1.0))


@app.post("/api/vision/stream/next")
def vision_stream_next() -> dict:
    """Process the next real frame from the active user-selected source."""
    try:
        return STREAM.next_frame(_get_vision_model())
    except (VisionModelError, SourceError) as error:
        raise _stream_error(error) from error


# ---------------------------------------------------------------------------
# V2.3: runtime inspection sources (no hardcoded production paths)
# ---------------------------------------------------------------------------

def _source_error(error: SourceError) -> HTTPException:
    return HTTPException(status_code=409, detail=error.to_dict())


@app.get("/api/inspection/sources")
def inspection_sources_list(limit: int = 20) -> dict:
    return {"sources": list_sources(limit=limit), "count": len(list_sources(limit=limit))}


@app.get("/api/inspection/sources/current")
def inspection_sources_current() -> dict:
    record = STREAM.active_source()
    if record is None:
        return {"source": None, "note": "No inspection source selected. Add an image, image set, or dataset to begin."}
    return {"source": record}


@app.get("/api/inspection/sources/{source_id}")
def inspection_sources_get(source_id: str) -> dict:
    record = get_source(source_id)
    if record is None:
        raise _source_error(SourceError("SOURCE_NOT_FOUND", f"Source '{source_id}' does not exist.", None))
    return record


@app.post("/api/inspection/sources")
async def inspection_sources_create(
    files: list[UploadFile] = File(default=[]),
    source_type: str = Form("IMAGE_SET"),
    display_name: str | None = Form(default=None),
) -> dict:
    """Ingest user-selected files into a session source (generated ID)."""
    try:
        uploaded: list[tuple[str, bytes]] = []
        for file in files:
            if not file.filename:
                continue
            data = await file.read()
            uploaded.append((file.filename, data))
        if source_type == "BUILT_IN_DEMO":
            record = create_demo_source(demo_dir=DEMO_DATASET_DIR)
        else:
            record = create_source(uploaded, str(source_type), display_name=display_name)
        return record
    except SourceError as error:
        raise _source_error(error) from error


@app.post("/api/inspection/sources/{source_id}/files")
async def inspection_sources_add(source_id: str, files: list[UploadFile] = File(default=[])) -> dict:
    try:
        uploaded: list[tuple[str, bytes]] = []
        for file in files:
            if not file.filename:
                continue
            uploaded.append((file.filename, await file.read()))
        return add_files(source_id, uploaded)
    except SourceError as error:
        raise _source_error(error) from error


@app.post("/api/inspection/sources/{source_id}/start")
def inspection_sources_start(source_id: str) -> dict:
    """Activate the source for the production stream and start it."""
    try:
        STREAM.set_source(source_id)
        return STREAM.start()
    except (VisionModelError, SourceError) as error:
        raise _stream_error(error) from error


@app.post("/api/inspection/sources/{source_id}/pause")
def inspection_sources_pause(source_id: str) -> dict:
    return STREAM.pause()


@app.post("/api/inspection/sources/{source_id}/next")
def inspection_sources_next(source_id: str) -> dict:
    try:
        if STREAM.active_source_id != source_id:
            STREAM.set_source(source_id)
        return STREAM.next_frame(_get_vision_model())
    except (VisionModelError, SourceError) as error:
        raise _stream_error(error) from error


@app.post("/api/inspection/sources/{source_id}/reset")
def inspection_sources_reset(source_id: str) -> dict:
    """Reset the CURRENT source's stream state (never a hardcoded dataset)."""
    try:
        if STREAM.active_source_id != source_id:
            STREAM.set_source(source_id)
        return STREAM.reset()
    except SourceError as error:
        raise _source_error(error) from error


@app.post("/api/inspection/sources/{source_id}/inspect")
def inspection_sources_inspect(source_id: str) -> dict:
    """Run the real pipeline over every valid image in the source (batch-style)."""
    import threading

    record = get_source(source_id)
    if record is None:
        raise _source_error(SourceError("SOURCE_NOT_FOUND", f"Source '{source_id}' does not exist.", None))
    if record["status"] in {"inspecting", "complete"} and record.get("results"):
        return record

    def run() -> None:
        try:
            from app.vision.inference import VisionModel as _VisionModel

            model = _VisionModel(VISION_MODEL_DIR)
            inspect_source(source_id, model)
        except Exception:  # noqa: BLE001 - failures are reflected in the record
            current = get_source(source_id)
            if current is not None:
                current["status"] = "failed"
                from app.vision.source import _save as _save_source

                _save_source(current)

    threading.Thread(target=run, daemon=True).start()
    return get_source(source_id)


@app.delete("/api/inspection/sources/{source_id}")
def inspection_sources_delete(source_id: str) -> dict:
    if STREAM.active_source_id == source_id:
        STREAM.clear_source()
    delete_source(source_id)
    return {"deleted": source_id, "note": "Source and its ingested files were removed."}


@app.get("/api/vision/feature-space")
def vision_feature_space() -> dict:
    model = _get_vision_model()
    if not model.available:
        return {
            "status": "NOT_TRAINED",
            "reason": "No vision model has been trained yet; the feature space is unavailable.",
            "clouds": {},
        }
    payload = model.feature_space_payload()
    if payload is None:
        return {
            "status": "NOT_AVAILABLE",
            "reason": "The trained artifacts predate the feature-space projection; retrain to generate it.",
            "clouds": {},
        }
    return {"status": "AVAILABLE", **payload}


@app.get("/api/datasets/{dataset_id}/process/timeline")
def process_timeline(dataset_id: str, bins: int = 48) -> dict:
    session = STORE.get(dataset_id)
    if session is None:
        raise _not_found(dataset_id)
    contract = session.get("contract") or {}
    summary = contract.get("summary") or {}
    return build_timeline(
        dataset_id,
        ARTIFACTS_DIR / dataset_id,
        stations=list(summary.get("stations") or []),
        preferred_table=summary.get("primary_table"),
        bins=bins,
    )


@app.post("/api/investigations/run")
def investigations_run(body: dict | None = None) -> dict:
    body = body or {}
    inspection_id = body.get("inspection_id")
    if not inspection_id:
        raise HTTPException(
            status_code=422,
            detail=IngestError("INSPECTION_REQUIRED", "Provide 'inspection_id' in the request body.").to_dict(),
        )
    inspection = get_inspection(VISION_MODEL_DIR, str(inspection_id))
    if inspection is None:
        raise HTTPException(
            status_code=404,
            detail=IngestError("INSPECTION_NOT_FOUND", f"Inspection '{inspection_id}' does not exist.").to_dict(),
        )
    dataset_id = body.get("dataset_id")
    if dataset_id is not None and STORE.get(str(dataset_id)) is None:
        raise HTTPException(
            status_code=404,
            detail=IngestError("DATASET_NOT_FOUND", f"Dataset '{dataset_id}' is not loaded in this session.").to_dict(),
        )
    return run_investigation(
        inspection,
        str(dataset_id) if dataset_id else None,
        store=STORE,
        artifacts_dir=ARTIFACTS_DIR,
        models_dir=MODELS_DIR,
    )


@app.get("/api/investigations")
def investigations_list(limit: int = 50) -> dict:
    records = list_investigations()
    limit = max(1, min(int(limit), 200))
    return {
        "investigations": records[:limit],
        "count": len(records),
        "note": "Investigations are stored on the backend; every stage carries its epistemic status.",
    }


@app.get("/api/investigations/{investigation_id}")
def investigations_get(investigation_id: str) -> dict:
    record = get_investigation(investigation_id)
    if record is None:
        raise HTTPException(
            status_code=404,
            detail=IngestError("INVESTIGATION_NOT_FOUND", f"Investigation '{investigation_id}' does not exist.").to_dict(),
        )
    return record


# ---------------------------------------------------------------------------
# V2.1: batch / dataset inspection and the human review queue
# ---------------------------------------------------------------------------

def _batch_error(error: BatchError | ReviewError) -> HTTPException:
    return HTTPException(status_code=422, detail=error.to_dict())


@app.post("/api/vision/batch")
async def vision_batch_create(files: list[UploadFile] = File(default=[]), zip: UploadFile | None = File(default=None)) -> dict:
    """Ingest + validate a batch of images (or a ZIP). Returns the data-health report."""
    try:
        if zip is not None and zip.filename:
            zip_bytes = await zip.read()
            if len(zip_bytes) > 500 * 1024 * 1024:
                raise BatchError("BATCH_TOO_LARGE", "ZIP exceeds 500 MB.", None)
            zip_path = RUNTIME_DIR / "batches" / "uploads" / f"{uuid.uuid4().hex}.zip"
            zip_path.parent.mkdir(parents=True, exist_ok=True)
            zip_path.write_bytes(zip_bytes)
            entries = None
            zip_source = zip_path
        else:
            uploaded: list[tuple[str, bytes]] = []
            for file in files:
                data = await file.read()
                if not file.filename:
                    continue
                uploaded.append((file.filename, data))
            if not uploaded:
                raise BatchError("BATCH_NO_IMAGES", "No image files were uploaded.", None)
            entries = uploaded
            zip_source = None
        record = create_batch(entries, zip_source)
        save_batch_raw(record["batch_id"], entries, zip_source)
        return record
    except BatchError as error:
        raise _batch_error(error) from error


@app.post("/api/vision/batch/{batch_id}/inspect")
def vision_batch_inspect(batch_id: str) -> dict:
    """Start the real inspection over the validated images (background, pollable)."""
    import threading

    record = get_batch(batch_id)
    if record is None:
        raise _batch_error(BatchError("BATCH_NOT_FOUND", f"Batch '{batch_id}' does not exist.", None))
    if record["status"] in {"inspecting", "complete"}:
        return record
    from app.vision.batch import mark_inspecting

    mark_inspecting(batch_id)

    def run() -> None:
        try:
            from app.vision.inference import VisionModel as _VisionModel

            model = _VisionModel(VISION_MODEL_DIR)
            inspect_batch(batch_id, model)
        except Exception:  # noqa: BLE001 - failures are reflected in the batch record
            record = get_batch(batch_id)
            if record is not None:
                record["status"] = "failed"
                from app.vision.batch import _save as _save_batch

                _save_batch(record)

    threading.Thread(target=run, daemon=True).start()
    return get_batch(batch_id)


@app.get("/api/vision/batch/{batch_id}")
def vision_batch_get(batch_id: str) -> dict:
    record = get_batch(batch_id)
    if record is None:
        raise _batch_error(BatchError("BATCH_NOT_FOUND", f"Batch '{batch_id}' does not exist.", None))
    return record


@app.get("/api/vision/batches")
def vision_batches_list(limit: int = 20) -> dict:
    return {"batches": list_batches(limit=limit), "count": len(list_batches(limit=limit))}


@app.get("/api/vision/review/queue")
def vision_review_queue(include_reviewed: bool = False, limit: int = 100) -> dict:
    queue = list_review_queue(VISION_MODEL_DIR, include_reviewed=include_reviewed, limit=limit)
    return {"items": queue, "count": len(queue), "include_reviewed": include_reviewed}


@app.get("/api/vision/review/stats")
def vision_review_stats() -> dict:
    return review_stats(VISION_MODEL_DIR)


@app.post("/api/vision/inspect/{inspection_id}/review")
def vision_inspect_review(inspection_id: str, body: dict | None = None) -> dict:
    body = body or {}
    action = body.get("action")
    note = body.get("note")
    class_name = body.get("class_name")
    if not action:
        raise _batch_error(ReviewError("REVIEW_ACTION_REQUIRED", "Provide 'action' in the request body.", None))
    try:
        return record_human_decision(VISION_MODEL_DIR, inspection_id, str(action), note, class_name)
    except ReviewError as error:
        raise _batch_error(error) from error
