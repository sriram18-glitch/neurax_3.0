"""Model input preparation.

Builds explicit predictor/response frames with documented imputation and
invariant checks (no NaN/Inf, disjoint predictor/response sets). Tables that
cannot yield a valid model input are rejected with an explicit reason.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from .errors import PipelineError

MIN_USABLE_ROWS = 10
NUMERIC_ROLES = {"process_metric", "numeric", "input_factor", "response_candidate", "ml_variable"}


@dataclass
class ModelInput:
    name: str
    frame: pd.DataFrame
    predictors: list[str]
    input_factors: list[str]
    responses: list[str]
    origin: str
    rows_original: int
    dropped_missing_response: int = 0
    imputed_cells: dict = field(default_factory=dict)
    dropped_constants: list = field(default_factory=list)
    dropped_non_numeric: list = field(default_factory=list)
    notes: list = field(default_factory=list)
    status: str = "READY"
    split_meta: dict | None = None

    def summary(self) -> dict:
        return {
            "name": self.name,
            "status": self.status,
            "origin": self.origin,
            "rows": int(self.frame.shape[0]),
            "rows_original": self.rows_original,
            "predictors": self.predictors,
            "input_factors": self.input_factors,
            "responses": self.responses,
            "dropped_missing_response_rows": self.dropped_missing_response,
            "dropped_constant_predictors": self.dropped_constants,
            "dropped_non_numeric_predictors": self.dropped_non_numeric,
            "imputed_cells": self.imputed_cells,
            "notes": self.notes,
            "split": self.split_meta,
        }


def _roles(profile: dict) -> dict[str, dict]:
    return {c["name"]: c for c in profile["columns_detail"]}


def _finalize(
    name: str,
    frame: pd.DataFrame,
    profile: dict,
    predictors: list[str],
    input_factors: list[str],
    responses: list[str],
    origin: str,
    notes: list[str],
) -> tuple[ModelInput | None, dict | None]:
    roles = {c["name"]: c for c in profile.get("columns_detail", [])}
    rows_original = int(frame.shape[0])
    numeric_predictors = [
        c
        for c in predictors
        if c in frame.columns and (roles.get(c, {}).get("role") in NUMERIC_ROLES or pd.api.types.is_numeric_dtype(frame[c]))
    ]
    numeric_predictors = [c for c in numeric_predictors if pd.api.types.is_numeric_dtype(frame[c])]
    non_numeric = [c for c in predictors if c in frame.columns and c not in numeric_predictors and c not in responses]
    constants = [c for c in numeric_predictors if frame[c].nunique(dropna=True) <= 1]
    numeric_predictors = [c for c in numeric_predictors if c not in constants]
    numeric_responses = [c for c in responses if c in frame.columns and pd.api.types.is_numeric_dtype(frame[c])]

    if len(numeric_predictors) == 0 or len(numeric_responses) == 0:
        return None, {
            "name": name,
            "status": "NOT_SUPPORTED",
            "reason": "no numeric predictor/response pair available in this table",
            "rows": rows_original,
        }

    frame = frame[numeric_predictors + numeric_responses].copy()
    before = int(frame.shape[0])
    frame = frame.dropna(subset=numeric_responses)
    dropped_missing = before - int(frame.shape[0])

    if frame.shape[0] < MIN_USABLE_ROWS:
        return None, {
            "name": name,
            "status": "INSUFFICIENT_DATA",
            "reason": f"only {frame.shape[0]} row(s) with complete response values; at least {MIN_USABLE_ROWS} required",
            "rows": rows_original,
        }

    imputed: dict[str, int] = {}
    for column in numeric_predictors:
        missing = int(frame[column].isna().sum())
        if missing:
            frame[column] = frame[column].fillna(frame[column].median())
            imputed[column] = missing

    values = frame.to_numpy(dtype="float64")
    if np.isnan(values).any() or np.isinf(values).any():
        raise PipelineError(
            "MODEL_INPUT_INVARIANT",
            f"Model input '{name}' still contains NaN/Inf after preparation.",
        )

    return (
        ModelInput(
            name=name,
            frame=frame.reset_index(drop=True),
            predictors=numeric_predictors,
            input_factors=[c for c in input_factors if c in numeric_predictors],
            responses=numeric_responses,
            origin=origin,
            rows_original=rows_original,
            dropped_missing_response=dropped_missing,
            imputed_cells=imputed,
            dropped_constants=constants,
            dropped_non_numeric=non_numeric,
            notes=notes,
        ),
        None,
    )


def _common_name(names: list[str], rows: int) -> str:
    import os as _os

    common = _os.path.commonprefix(sorted(names)).rstrip("_ -:")
    return common if len(common) >= 3 else f"fused_{rows}"


def build_model_inputs(
    feature_frames: dict[str, pd.DataFrame],
    profiles_by_name: dict[str, dict],
) -> tuple[list[ModelInput], list[dict]]:
    inputs: list[ModelInput] = []
    rejected: list[dict] = []
    handled: set[str] = set()

    # 1) tables that are complete on their own ---------------------------------
    for name, frame in feature_frames.items():
        profile = profiles_by_name[name]
        roles = _roles(profile)
        predictors = [str(c) for c in frame.columns if roles.get(str(c), {}).get("role") == "input_factor"]
        responses = [
            str(c)
            for c in frame.columns
            if roles.get(str(c), {}).get("role") in {"response_candidate", "ml_variable"}
        ]
        derived = [str(c) for c in frame.columns if str(c) not in roles]
        all_predictors = predictors + derived
        if predictors and responses:
            model_input, rejection = _finalize(
                name,
                frame,
                profile,
                all_predictors,
                predictors,
                responses,
                origin="single_table",
                notes=["Derived features included as predictors." if derived else "No derived predictors."],
            )
            if model_input:
                inputs.append(model_input)
            elif rejection:
                rejected.append(rejection)
            handled.add(name)

    # 2) MAT-style multi-variable datasets: fuse tables with equal row counts --
    # Grouping also respects variable families (Model1*, Model2*, Model3*) so
    # variables from different simulation models are never fused together.
    import re as _re

    def _family(name: str) -> str | None:
        match = _re.match(r"^(Model\d+)", name)
        return match.group(1) if match else None

    groups: dict[tuple, list[str]] = {}
    for name, frame in feature_frames.items():
        profile = profiles_by_name[name]
        family = _family(name)
        groups.setdefault((profile["source_file"], int(frame.shape[0]), family), []).append(name)

    for (source, rows, family), names in sorted(groups.items(), key=lambda item: (item[0][0], item[0][1], str(item[0][2]))):
        remaining = sorted(n for n in names if n not in handled)
        if len(remaining) < 2 or rows < MIN_USABLE_ROWS:
            continue
        predictors: list[str] = []
        input_factors: list[str] = []
        responses: list[str] = []
        plates: list[pd.DataFrame] = []
        used_tables: list[str] = []
        for name in remaining:
            frame = feature_frames[name]
            roles = _roles(profiles_by_name[name])
            preds = [str(c) for c in frame.columns if roles.get(str(c), {}).get("role") == "input_factor"]
            resp = [
                str(c)
                for c in frame.columns
                if roles.get(str(c), {}).get("role") in {"response_candidate", "ml_variable"}
            ]
            derived = [str(c) for c in frame.columns if str(c) not in roles]
            if not preds and not resp:
                continue
            selected = preds + derived + resp
            plate = frame[selected].reset_index(drop=True)
            plates.append(plate)
            predictors.extend(preds + derived)
            input_factors.extend(preds)
            responses.extend(resp)
            used_tables.append(name)

        if len(plates) < 2 or not predictors or not responses:
            continue
        fused = pd.concat(plates, axis=1)
        fused = fused.loc[:, ~fused.columns.duplicated()]
        name = _common_name(used_tables, rows)
        fused_profile = {
            "columns_detail": [
                {"name": column, "role": "input_factor" if column in predictors else "ml_variable"}
                for column in fused.columns
            ]
        }
        model_input, rejection = _finalize(
            name,
            fused,
            fused_profile,
            predictors,
            input_factors,
            responses,
            origin=f"fused_aligned_tables:{','.join(used_tables)}",
            notes=[
                "Fused from MAT variables with equal sample counts, aligned by row order (same source file)."
            ],
        )
        if model_input:
            inputs.append(model_input)
        elif rejection:
            rejected.append(rejection)

    inputs.sort(key=lambda mi: (-mi.frame.shape[0], mi.name))
    return inputs, rejected
