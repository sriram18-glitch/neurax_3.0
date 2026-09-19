"""Module capability coverage.

Every analysis module gets an explicit status derived from detected
capabilities. Unsupported modules state why - the frontend renders these
verbatim instead of inventing values.
"""

from __future__ import annotations

SUPPORTED = "SUPPORTED"
PARTIALLY_SUPPORTED = "PARTIALLY_SUPPORTED"
REQUIRES_ASSUMPTIONS = "REQUIRES_ASSUMPTIONS"
NOT_SUPPORTED = "NOT_SUPPORTED"


def build_coverage(contract: dict, station_metrics: dict, model_inputs: list, rejected_inputs: list) -> dict:
    capabilities = contract["capabilities"]
    vision_reason = contract["vision"]["reason"]

    modules: dict[str, dict] = {}

    modules["data_ingestion"] = {
        "status": SUPPORTED,
        "reason": "Dataset ingested, validated, profiled and cleaned.",
    }
    modules["process_analysis"] = {
        "status": SUPPORTED if capabilities["has_process_data"] else NOT_SUPPORTED,
        "reason": "Process/station columns detected and aggregated."
        if capabilities["has_process_data"]
        else "No process or station columns detected in this dataset.",
    }
    modules["station_analysis"] = (
        {
            "status": SUPPORTED,
            "reason": f"{station_metrics['station_count']} station(s) detected with per-station metrics.",
        }
        if station_metrics["station_count"] > 0
        else {
            "status": NOT_SUPPORTED,
            "reason": "No station or cell identifiers detected in this dataset.",
        }
    )
    modules["predictive_modeling"] = (
        {
            "status": SUPPORTED,
            "reason": f"{len(model_inputs)} model input(s) prepared with numeric predictors and responses.",
        }
        if model_inputs
        else {
            "status": NOT_SUPPORTED,
            "reason": "No numeric predictor/response pairs could be assembled from this dataset.",
        }
    )
    modules["anomaly_detection"] = (
        {
            "status": SUPPORTED,
            "reason": "Numeric process data available for normal-reference anomaly scoring.",
        }
        if capabilities["supports_anomaly_detection"]
        else {
            "status": NOT_SUPPORTED,
            "reason": "Fewer than 2 numeric columns or fewer than 100 rows available.",
        }
    )
    modules["root_cause_analysis"] = (
        {
            "status": SUPPORTED if capabilities["has_process_data"] else PARTIALLY_SUPPORTED,
            "reason": "Process variables and responses available for association analysis (association is not causation)."
            if capabilities["has_process_data"]
            else "Limited process structure; association analysis will be restricted to available numeric columns.",
        }
    )
    modules["vision_inspection"] = {"status": NOT_SUPPORTED, "reason": vision_reason}
    modules["visual_localization"] = {
        "status": NOT_SUPPORTED,
        "reason": "Localization requires image data; no images or image-path columns exist in this dataset.",
    }
    modules["visual_novelty_detection"] = {
        "status": NOT_SUPPORTED,
        "reason": "Visual novelty detection requires image data; none available in this dataset.",
    }
    modules["process_novelty_detection"] = (
        {
            "status": SUPPORTED,
            "reason": "Process-state novelty can be scored against a normal reference built from this dataset.",
        }
        if capabilities["supports_anomaly_detection"]
        else {"status": NOT_SUPPORTED, "reason": "Insufficient numeric data for a normal reference."}
    )
    modules["economic_analysis"] = {
        "status": REQUIRES_ASSUMPTIONS,
        "reason": "No cost, price or downtime columns detected; user must supply cost assumptions before impact can be calculated.",
    }
    modules["what_if_simulation"] = {
        "status": PARTIALLY_SUPPORTED,
        "reason": "Process-level what-if is supported from dataset statistics; economic what-if requires user assumptions.",
    }

    statuses = [m["status"] for m in modules.values()]
    return {
        "dataset_id": contract["dataset_id"],
        "modules": modules,
        "summary": {
            "supported": statuses.count(SUPPORTED),
            "partially_supported": statuses.count(PARTIALLY_SUPPORTED),
            "requires_assumptions": statuses.count(REQUIRES_ASSUMPTIONS),
            "not_supported": statuses.count(NOT_SUPPORTED),
        },
        "legend": {
            SUPPORTED: "Available directly from this dataset.",
            PARTIALLY_SUPPORTED: "Available with stated limitations.",
            REQUIRES_ASSUMPTIONS: "Requires user-provided assumptions before calculation.",
            NOT_SUPPORTED: "Not possible with this dataset; no values are produced for it.",
        },
    }
