"""Shared pytest fixtures. All runtime state is isolated per test session."""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

_TMP = tempfile.mkdtemp(prefix="neurax_test_runtime_")
os.environ["NEURAX_RUNTIME_DIR"] = _TMP

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import pytest  # noqa: E402

PROJECT = BACKEND.parent
DATASET_DIR = PROJECT / "Manufacturing Data Shared Facility - Discrete-Event Simulation"


@pytest.fixture(scope="session")
def runtime_dir() -> Path:
    return Path(_TMP)


@pytest.fixture(scope="session")
def dataset_dir() -> Path:
    return DATASET_DIR


@pytest.fixture(scope="session")
def small_csv(tmp_path_factory) -> Path:
    rng = np.random.default_rng(7)
    rows = 200
    frame = pd.DataFrame(
        {
            "Demand": rng.integers(1, 20, rows),
            "Part 1 VA Time": rng.normal(3.0, 0.01, rows),
            "Drilling Queue Time": rng.uniform(0, 2, rows),
            "Assembly Time": rng.normal(3.0, 0.01, rows),
            "Drilling Utilization": rng.uniform(0.2, 0.9, rows),
            "Milling Utilization": rng.uniform(0.1, 0.8, rows),
            "Assembly Utilization": rng.uniform(0.3, 0.95, rows),
            "Total parts": rng.integers(500, 5000, rows),
        }
    )
    path = tmp_path_factory.mktemp("data") / "small_process.csv"
    frame.to_csv(path, index=False)
    return path


@pytest.fixture(scope="session")
def small_csv_b(tmp_path_factory) -> Path:
    rng = np.random.default_rng(99)
    rows = 150
    frame = pd.DataFrame(
        {
            "Demand": rng.integers(5, 30, rows),
            "Part 1 VA Time": rng.normal(4.5, 0.02, rows),
            "Drilling Queue Time": rng.uniform(0, 9, rows),
            "Assembly Time": rng.normal(4.0, 0.02, rows),
            "Drilling Utilization": rng.uniform(0.5, 0.99, rows),
            "Milling Utilization": rng.uniform(0.2, 0.6, rows),
            "Assembly Utilization": rng.uniform(0.6, 0.99, rows),
            "Total parts": rng.integers(100, 900, rows),
        }
    )
    path = tmp_path_factory.mktemp("data") / "small_process_b.csv"
    frame.to_csv(path, index=False)
    return path


@pytest.fixture(scope="session")
def analyze():
    from app.ingest import analyze_path

    def _analyze(path: Path) -> dict:
        return analyze_path(Path(path))

    return _analyze


@pytest.fixture(scope="session")
def client():
    from fastapi.testclient import TestClient

    from app.main import app

    return TestClient(app)


@pytest.fixture()
def fresh_contract(analyze, tmp_path):
    """Contract for a tiny generated dataset; avoids re-reading big files."""
    from app.ingest import ingest_path
    from app.ingest.contract import build_contract
    from app.ingest.profiler import profile_ingest

    def _make(frame: pd.DataFrame, name: str = "toy.csv"):
        path = tmp_path / name
        frame.to_csv(path, index=False)
        result = ingest_path(path)
        profiles = profile_ingest(result)
        return build_contract(result, profiles), result

    return _make
