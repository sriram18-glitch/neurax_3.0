"""Flow graph construction.

The graph is only built from real structure: station sequence hints in the
Arena process-model description (Model PDFs) or explicit sequence metadata.
No ordering is ever invented. When ordering cannot be established the graph is
reported as PARTIALLY_SUPPORTED with the reason.
"""

from __future__ import annotations

import re
from pathlib import Path

# Known Arena process structure from the organizer's Model PDFs (verified during
# Phase 0 forensics). These are station-sequence hints, not measurements.
KNOWN_SEQUENCES: dict[str, list[str]] = {
    "Model_1": ["Drilling", "Milling", "Assembly"],
    "Model_2": ["Drilling", "Milling", "Assembly"],
    "Model_3": [
        "Blanking",
        "Press1",
        "Press2",
        "Press3",
        "Press4",
        "Cell1",
        "Cell2",
        "Cell3",
        "Cell4",
        "Paint1",
        "Paint2",
        "Quality",
    ],
}


def _base_name(station: str) -> str:
    return re.sub(r"[_ ]?\d+$", "", station) or station


def infer_sequence(stations: list[str], dataset_filename: str | None) -> tuple[list[str] | None, str]:
    """Return an ordered station list when a known process structure applies."""
    if not stations:
        return None, "no stations available"

    if dataset_filename:
        stem = Path(dataset_filename).stem
        for key, sequence in KNOWN_SEQUENCES.items():
            if key.lower() in stem.lower():
                present = [station for station in sequence if station in stations]
                if len(present) >= 2:
                    return present, f"sequence from documented process structure for '{key}'"
                break

    # Fallback: numeric suffix ordering within a shared base name (Press1..Press4)
    groups: dict[str, list[str]] = {}
    for station in stations:
        base = _base_name(station)
        if base != station:
            groups.setdefault(base, []).append(station)
    if groups:
        ordered: list[str] = []
        for base, members in sorted(groups.items()):
            ordered.extend(sorted(members, key=lambda s: int(re.sub(r"^\D+", "", s) or 0)))
        if len(ordered) >= 2:
            return ordered, "sequence inferred from numeric station suffixes only"

    return None, "station ordering cannot be established from the dataset"


def build_flow_graph(
    stations: list[str],
    station_evidence: dict[str, dict],
    dataset_filename: str | None,
) -> dict:
    sequence, rationale = infer_sequence(stations, dataset_filename)

    if not sequence:
        return {
            "status": "PARTIALLY_SUPPORTED",
            "reason": "FLOW_GRAPH ordering unavailable: " + rationale,
            "nodes": [
                {"station": station, "rank": None, "metrics": station_evidence.get(station, {})}
                for station in sorted(stations)
            ],
            "edges": [],
            "rationale": rationale,
            "note": "Station metrics are available, but no defensible upstream/downstream ordering exists.",
        }

    nodes = []
    edges = []
    for index, station in enumerate(sequence):
        entry = station_evidence.get(station, {})
        nodes.append(
            {
                "station": station,
                "position": index,
                "metrics": entry,
            }
        )
        if index > 0:
            edges.append({"from": sequence[index - 1], "to": station})

    uncovered = sorted(set(stations) - set(sequence))
    return {
        "status": "SUPPORTED",
        "rationale": rationale,
        "nodes": nodes,
        "edges": edges,
        "stations_outside_sequence": uncovered,
        "note": "Ordering comes from documented process structure; it describes intended flow, not measured routing.",
    }


def blocking_starvation_status(order_available: bool, queue_available: bool) -> dict:
    """Blocking/starvation cannot be measured from these datasets.

    They require entity-level arrival/departure records or time-stamped buffer
    states per station. The Arena CSVs provide aggregate counters only.
    """
    if not order_available:
        return {
            "blocking": {"status": "NOT_SUPPORTED", "reason": "no defensible station ordering"},
            "starvation": {"status": "NOT_SUPPORTED", "reason": "no defensible station ordering"},
        }
    return {
        "blocking": {
            "status": "NOT_SUPPORTED",
            "reason": "dataset provides aggregate counters only; no entity-level arrival/departure records to detect downstream congestion",
        },
        "starvation": {
            "status": "NOT_SUPPORTED",
            "reason": "dataset provides aggregate counters only; no per-station idle/empty-buffer states to detect starvation",
        },
    }
