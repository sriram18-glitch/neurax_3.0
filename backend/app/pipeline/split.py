"""Leakage-safe dataset splitting.

Strategy is chosen from the actual structure of the data, never blindly:

1. Usable monotonic timestamp (>10 distinct values) -> chronological holdout.
2. Large sequential runs (rows > 50,000, no usable time) -> positional
   holdout, because random splits would leak autocorrelated neighbouring rows.
3. Low-cardinality process inputs -> grouped holdout on input bins, so the
   same operating condition never appears in both train and held-out sets.
4. Otherwise -> seeded random split.

All splits are reproducible for a fixed seed and are mutually exclusive by
construction.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

TRAIN, VALIDATION, TEST, UNSPLIT = "train", "validation", "test", "unsplit"
MIN_ROWS_FOR_SPLIT = 30
LARGE_RUN_THRESHOLD = 50_000


def _empty_meta(name: str, rows: int, seed: int) -> dict:
    return {
        "name": name,
        "rows": int(rows),
        "seed": int(seed),
        "strategy": None,
        "rationale": None,
        "group_key": None,
        "counts": {TRAIN: 0, VALIDATION: 0, TEST: 0},
        "fallback": False,
        "status": "COMPUTED",
        "reason": None,
    }


def _apply_positional(n: int, cuts: tuple[int, int]) -> np.ndarray:
    assignments = np.empty(n, dtype=object)
    assignments[: cuts[0]] = TRAIN
    assignments[cuts[0] : cuts[1]] = VALIDATION
    assignments[cuts[1] :] = TEST
    return assignments


def _assign_groups(groups: np.ndarray, rng: np.random.Generator) -> np.ndarray:
    unique = list(dict.fromkeys(groups.tolist()))
    rng.shuffle(unique)  # type: ignore[arg-type]
    sizes = {g: int((groups == g).sum()) for g in unique}
    total = sum(sizes.values())
    targets = {TRAIN: 0.70 * total, VALIDATION: 0.85 * total}
    buckets: dict[str, list] = {TRAIN: [], VALIDATION: [], TEST: []}

    queue = list(unique)
    if len(queue) >= 3:
        buckets[TEST].append(queue.pop())
        buckets[VALIDATION].append(queue.pop())

    cumulative = 0
    for group in queue:
        if cumulative < targets[TRAIN] or not buckets[TEST]:
            buckets[TRAIN].append(group)
            cumulative += sizes[group]
        elif cumulative < targets[VALIDATION] or not buckets[VALIDATION] or not buckets[TEST]:
            buckets[VALIDATION].append(group)
            cumulative += sizes[group]
        else:
            buckets[TEST].append(group)

    if not buckets[TRAIN] or not buckets[VALIDATION] or not buckets[TEST]:
        return np.array([], dtype=object)

    lookup = {group: split for split, members in buckets.items() for group in members}
    return np.array([lookup[g] for g in groups], dtype=object)


def compute_split(
    frame: pd.DataFrame,
    group_candidates: list[str],
    time_candidates: list[str],
    seed: int = 42,
    name: str = "model_input",
) -> tuple[np.ndarray, dict]:
    n = len(frame)
    meta = _empty_meta(name, n, seed)

    if n < MIN_ROWS_FOR_SPLIT:
        meta.update(
            {
                "status": "NOT_APPLICABLE",
                "reason": f"only {n} usable row(s); at least {MIN_ROWS_FOR_SPLIT} are required for a leakage-safe split",
            }
        )
        return np.array([UNSPLIT] * n, dtype=object), meta

    rng = np.random.default_rng(seed)
    cut1, cut2 = int(n * 0.70), int(n * 0.85)

    usable_time = [
        column
        for column in time_candidates
        if column in frame.columns
        and frame[column].nunique(dropna=True) > 10
        and frame[column].is_monotonic_increasing
    ]
    if usable_time:
        assignments = _apply_positional(n, (cut1, cut2))
        meta.update(
            {
                "strategy": "chronological_holdout",
                "rationale": f"ordered by monotonic timestamp '{usable_time[0]}'; a chronological 70/15/15 holdout prevents temporal leakage",
                "group_key": usable_time[0],
            }
        )

    elif n > LARGE_RUN_THRESHOLD:
        assignments = _apply_positional(n, (cut1, cut2))
        meta.update(
            {
                "strategy": "sequential_holdout",
                "rationale": f"{n} sequential records with no usable time base; positional 70/15/15 holdout avoids leakage between autocorrelated neighbouring rows",
            }
        )

    else:
        group_key = None
        for column in group_candidates:
            if column in frame.columns and 2 <= frame[column].nunique(dropna=True) <= 50:
                group_key = column
                break

        assignments = np.array([], dtype=object)
        if group_key:
            series = frame[group_key]
            if series.nunique(dropna=True) > 10:
                raw_groups = pd.qcut(series.rank(method="first"), 5, labels=False, duplicates="drop")
                groups = raw_groups.to_numpy()
            else:
                groups = pd.factorize(series)[0]
            if len(set(groups.tolist())) >= 3:
                assignments = _assign_groups(groups, rng)

        if assignments.size:
            meta.update(
                {
                    "strategy": "grouped_holdout",
                    "rationale": f"grouped by process input '{group_key}' so the same operating conditions never appear in both training and held-out sets",
                    "group_key": group_key,
                }
            )
        else:
            permutation = rng.permutation(n)
            assignments = np.empty(n, dtype=object)
            assignments[permutation[:cut1]] = TRAIN
            assignments[permutation[cut1:cut2]] = VALIDATION
            assignments[permutation[cut2:]] = TEST
            meta.update(
                {
                    "strategy": "seeded_random_holdout",
                    "rationale": "independent samples without scenario identifiers or usable ordering; seeded 70/15/15 random holdout",
                    "fallback": bool(group_key),
                }
            )

    counts = {split: int((assignments == split).sum()) for split in (TRAIN, VALIDATION, TEST)}
    meta["counts"] = counts
    if sum(counts.values()) != n:
        meta["status"] = "FAILED"
        meta["reason"] = "split sizes do not reconstruct the full row count"
    return assignments, meta
