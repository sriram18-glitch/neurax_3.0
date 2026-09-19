"""Target type detection.

Classification is only claimed when the column name itself indicates a
class-like outcome AND the values are consistent with it. Counts, times and
other continuous quantities are always treated as regression targets - they
are never silently reinterpreted as classes or defect probabilities.
"""

from __future__ import annotations

import re

import numpy as np
import pandas as pd

TARGET_HINT = re.compile(r"pass|fail|defect|reject|scrap|rework|quality|status|result|outcome|label|class|grade", re.I)

REGRESSION = "regression"
BINARY = "binary_classification"
MULTICLASS = "multiclass_classification"
UNSUPPORTED = "unsupported"


def detect_target_type(name: str, series: pd.Series) -> dict:
    values = series.dropna()
    n = int(values.size)
    n_unique = int(values.nunique())
    hint = bool(TARGET_HINT.search(str(name)))

    base = {
        "name": str(name),
        "n_samples": n,
        "n_unique": n_unique,
        "hint_class_like": hint,
        "dtype": str(series.dtype),
    }

    if n == 0:
        return {**base, "type": UNSUPPORTED, "reason": "target contains no non-null values"}
    if n_unique <= 1:
        return {**base, "type": UNSUPPORTED, "reason": "target is constant; nothing to learn"}
    if not pd.api.types.is_numeric_dtype(series):
        return {
            **base,
            "type": UNSUPPORTED,
            "reason": "non-numeric target; categorical encoding is not implemented for this phase",
        }

    integer_valued = bool(np.allclose(values.to_numpy(dtype="float64"), np.round(values.to_numpy(dtype="float64"))))
    base["integer_valued"] = integer_valued

    if hint and n_unique == 2:
        return {**base, "type": BINARY, "reason": "class-like name with exactly 2 distinct numeric values"}
    if hint and integer_valued and 3 <= n_unique <= 12:
        return {**base, "type": MULTICLASS, "reason": "class-like name with 3-12 distinct integer values"}
    return {
        **base,
        "type": REGRESSION,
        "reason": "continuous or count-like target; modeled as regression",
    }
