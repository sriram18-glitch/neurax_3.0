"""Phase 2 integration test: real dataset ingestion through the real API.

Run:  python backend/tests/test_ingest.py
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
PROJECT = BACKEND.parent
sys.path.insert(0, str(BACKEND))

DATASET = PROJECT / "Manufacturing Data Shared Facility - Discrete-Event Simulation"
CORRUPT_MAT = Path(r"C:\Users\Sriram\Downloads\3000Samplesv3.mat")

from app.ingest import IngestError, analyze_path  # noqa: E402

PASSED: list[str] = []
FAILED: list[str] = []


def check(name: str, fn) -> None:
    t0 = time.time()
    try:
        fn()
        PASSED.append(name)
        print(f"  PASS  {name}  ({time.time() - t0:.1f}s)")
    except Exception as exc:  # noqa: BLE001
        FAILED.append(name)
        print(f"  FAIL  {name}  -> {type(exc).__name__}: {exc}")


def summarize(contract: dict) -> None:
    s, c, v = contract["summary"], contract["capabilities"], contract["vision"]
    print(f"        dataset_id={contract['dataset_id']}  format={contract['format']}")
    print(f"        tables={s['tables']}  total_rows={s['total_rows']}  primary={s['primary_table']} "
          f"({s['primary_rows']}x{s['primary_columns']})")
    print(f"        stations={s['stations']}")
    print(f"        capabilities: vision={c['supports_vision']} process={c['has_process_data']} "
          f"regression={c['supports_process_regression']} anomaly={c['supports_anomaly_detection']} "
          f"defect_labels={c['has_defect_labels']}")
    if v["reason"]:
        print(f"        vision: {v['reason']}")


def run_csv_check(path: Path, expect_rows: int, expect_station: str):
    def _run() -> None:
        contract = analyze_path(path)
        assert contract["status"] == "analyzed"
        assert contract["summary"]["total_rows"] >= expect_rows, contract["summary"]
        assert contract["capabilities"]["supports_vision"] is False
        assert contract["vision"]["available"] is False
        assert expect_station in contract["summary"]["stations"], contract["summary"]["stations"]
        summarize(contract)
    return _run


def run_mat_check() -> None:
    contract = analyze_path(DATASET / "3000Samplesv3.mat")
    assert contract["summary"]["tables"] >= 30, contract["summary"]
    assert contract["capabilities"]["supports_process_regression"] is True
    names = [t["name"] for t in contract["tables"]]
    assert any("Model1Response" in n for n in names), names[:5]
    summarize(contract)
    print(f"        tables loaded: {len(names)} (first 6: {names[:6]})")


def run_corrupt_mat_check() -> None:
    if not CORRUPT_MAT.exists():
        print("        (skipped - corrupted sample not present)")
        return
    try:
        analyze_path(CORRUPT_MAT)
    except IngestError as exc:
        assert exc.code == "MAT_CORRUPT", exc.code
        print(f"        rejected as expected: [{exc.code}] {exc.message}")
        return
    raise AssertionError("corrupt MAT was not rejected")


def run_api_check() -> None:
    from fastapi.testclient import TestClient

    from app.main import app

    client = TestClient(app)
    assert client.get("/api/health").json()["status"] == "ok"

    sample = DATASET / "Model 1" / "Model_1.csv"
    with open(sample, "rb") as fh:
        response = client.post("/api/upload", files={"file": (sample.name, fh, "text/csv")})
    assert response.status_code == 200, response.text
    contract = response.json()
    dataset_id = contract["dataset_id"]
    print(f"        upload -> {response.status_code}, dataset_id={dataset_id}, status={contract['status']}")

    fetched = client.get(f"/api/datasets/{dataset_id}")
    assert fetched.status_code == 200
    assert fetched.json()["dataset_id"] == dataset_id

    assert client.get("/api/datasets/does-not-exist").status_code == 404

    bad = client.post("/api/upload", files={"file": ("notes.exe", b"MZ", "application/octet-stream")})
    assert bad.status_code == 415, bad.text

    if CORRUPT_MAT.exists():
        with open(CORRUPT_MAT, "rb") as fh:
            corrupt = client.post("/api/upload", files={"file": (CORRUPT_MAT.name, fh, "application/octet-stream")})
        assert corrupt.status_code == 422, corrupt.text
        assert corrupt.json()["detail"]["code"] == "MAT_CORRUPT"


def main() -> int:
    print("=" * 78)
    print("PHASE 2 - INGESTION CORE TEST (real dataset, real API)")
    print("=" * 78)
    check("Model_1.csv (3000x10, Drilling/Milling/Assembly)", run_csv_check(DATASET / "Model 1" / "Model_1.csv", 3000, "Drilling"))
    check("Model_2.csv (3000x17)", run_csv_check(DATASET / "Model 2" / "Model_2.csv", 3000, "Assembly"))
    check("Model_3.csv (605620x78, Cells/Press/Quality)", run_csv_check(DATASET / "Model 3" / "Model_3.csv", 605620, "Cell1"))
    check("3000Samplesv3.mat (33 vars)", run_mat_check)
    check("corrupt MAT rejected with clear error", run_corrupt_mat_check)
    check("FastAPI /api/upload + /api/datasets/{id}", run_api_check)

    print("-" * 78)
    print(f"RESULT: {len(PASSED)} passed, {len(FAILED)} failed")
    for name in FAILED:
        print(f"  FAILED: {name}")
    print("=" * 78)
    return 1 if FAILED else 0


if __name__ == "__main__":
    raise SystemExit(main())
