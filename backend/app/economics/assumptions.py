"""User economic assumptions.

No default values exist anywhere in this module. An assumption is either
supplied by the user (source USER_ASSUMPTION, timestamped) or reported as
NOT_PROVIDED. Currency is metadata, never guessed.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from .errors import EconomicsError

# field -> (unit, min, max or None)
ASSUMPTION_FIELDS: dict[str, tuple[str, float | None, float | None]] = {
    "currency": ("currency code", None, None),  # handled separately (string)
    "contribution_margin_per_unit": ("currency/unit", 0.0, None),
    "scrap_cost_per_unit": ("currency/unit", 0.0, None),
    "rework_cost_per_unit": ("currency/unit", 0.0, None),
    "downtime_cost_per_hour": ("currency/hour", 0.0, None),
    "downtime_hours_per_day": ("hours/day", 0.0, 24.0),
    "operating_cost_per_hour": ("currency/hour", 0.0, None),
    "working_hours_per_day": ("hours/day", 0.0, 24.0),
    "working_days_per_month": ("days/month", 0.0, 31.0),
    "baseline_demand": ("units/day", 0.0, None),
    "expected_defect_rate": ("ratio", 0.0, 1.0),
    "expected_rework_rate": ("ratio", 0.0, 1.0),
    "intervention_cost": ("currency", 0.0, None),
}

NUMERIC_FIELDS = [field for field in ASSUMPTION_FIELDS if field != "currency"]


def empty_assumptions(dataset_id: str) -> dict:
    return {
        "dataset_id": dataset_id,
        "currency": {"value": None, "source": "NOT_PROVIDED"},
        "assumptions": {
            field: {"value": None, "unit": unit, "source": "NOT_PROVIDED", "provided_at": None, "notes": None}
            for field, (unit, _, _) in ASSUMPTION_FIELDS.items()
            if field != "currency"
        },
        "updated_at": None,
        "note": "No economic values are assumed. Every field is NOT_PROVIDED until the user supplies it.",
    }


def validate_and_merge(existing: dict, updates: dict) -> dict:
    """Merge user-supplied assumptions into the stored payload with validation."""
    if not isinstance(updates, dict):
        raise EconomicsError("INVALID_ASSUMPTIONS", "Assumptions payload must be a JSON object.")

    payload = json.loads(json.dumps(existing))  # deep copy
    unknown = [key for key in updates if key not in ASSUMPTION_FIELDS]
    if unknown:
        raise EconomicsError(
            "UNKNOWN_ASSUMPTION",
            f"Unknown assumption field(s): {', '.join(sorted(unknown))}.",
            f"Supported fields: {', '.join(sorted(ASSUMPTION_FIELDS))}.",
        )

    now = datetime.now(timezone.utc).isoformat()
    for key, raw in updates.items():
        if raw is None:
            payload["assumptions"][key]["value"] = None
            payload["assumptions"][key]["source"] = "NOT_PROVIDED"
            payload["assumptions"][key]["provided_at"] = None
            continue
        if key == "currency":
            value = str(raw).strip().upper()
            if not value or len(value) > 8:
                raise EconomicsError("INVALID_ASSUMPTION", "Currency must be a short code such as 'INR', 'USD' or 'EUR'.")
            payload["currency"] = {"value": value, "source": "USER_ASSUMPTION", "provided_at": now}
            continue
        unit, minimum, maximum = ASSUMPTION_FIELDS[key]
        try:
            value = float(raw)
        except (TypeError, ValueError):
            raise EconomicsError("INVALID_ASSUMPTION", f"'{key}' must be numeric; received {raw!r}.")
        if value != value or value in (float("inf"), float("-inf")):
            raise EconomicsError("INVALID_ASSUMPTION", f"'{key}' must be a finite number.")
        if minimum is not None and value < minimum:
            raise EconomicsError("INVALID_ASSUMPTION", f"'{key}' must be >= {minimum} ({unit}).")
        if maximum is not None and value > maximum:
            raise EconomicsError("INVALID_ASSUMPTION", f"'{key}' must be <= {maximum} ({unit}).")
        payload["assumptions"][key] = {
            "value": value,
            "unit": unit,
            "source": "USER_ASSUMPTION",
            "provided_at": now,
            "notes": None,
        }

    payload["updated_at"] = now
    return payload


def get_value(payload: dict, field: str) -> float | None:
    entry = (payload.get("assumptions") or {}).get(field)
    if not entry or entry.get("value") is None:
        return None
    return float(entry["value"])


def currency_of(payload: dict) -> str | None:
    entry = payload.get("currency") or {}
    return entry.get("value")


def load_assumptions(path: Path, dataset_id: str) -> dict:
    if not path.exists():
        return empty_assumptions(dataset_id)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if payload.get("dataset_id") != dataset_id:
            return empty_assumptions(dataset_id)
        return payload
    except Exception:  # noqa: BLE001
        return empty_assumptions(dataset_id)


def save_assumptions(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, default=str)


def assumptions_fingerprint(payload: dict) -> str:
    import hashlib

    relevant = {
        "currency": (payload.get("currency") or {}).get("value"),
        "values": {
            field: entry.get("value")
            for field, entry in sorted((payload.get("assumptions") or {}).items())
        },
    }
    return hashlib.sha256(json.dumps(relevant, sort_keys=True).encode("utf-8")).hexdigest()[:12]
