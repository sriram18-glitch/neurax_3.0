from __future__ import annotations

import json
import re
from pathlib import Path

import pandas as pd


def sanitize_name(name: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "_", name).strip("_")
    return cleaned or "table"


def write_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, default=str)


def write_frame_gz(path: Path, frame: pd.DataFrame, row_cap: int | None = None) -> dict:
    meta = {"file": path.name, "rows": int(frame.shape[0]), "truncated": False}
    if row_cap is not None and frame.shape[0] > row_cap:
        stored = frame.head(row_cap)
        meta.update(
            {
                "stored_rows": int(stored.shape[0]),
                "truncated": True,
                "reason": "artifact size control; full data is reproducible from the source upload through the pipeline",
            }
        )
        frame = stored
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(path, index=False, compression="gzip")
    return meta
