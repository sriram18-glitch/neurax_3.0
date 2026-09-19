"""Phase 10 integration check: real backend <-> frontend wiring.

Starts the real FastAPI backend, verifies the API surface the frontend consumes
(health, datasets list, CORS for the dev origin), and confirms the frontend
build artifacts exist. This is not a browser test - component behaviour is
covered by the vitest suite; this verifies the real integration surface.

Run: python backend/tests/verify_phase10_integration.py
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
PROJECT = BACKEND.parent
FRONTEND = PROJECT / "frontend"

failures: list[str] = []


def verify(name: str, condition: bool, detail: str = "") -> None:
    print(f"  [{'PASS' if condition else 'FAIL'}] {name}{'' if condition else ' -> ' + detail}")
    if not condition:
        failures.append(name)


def http(url: str, method: str = "GET", origin: str | None = None) -> tuple[int, dict, dict]:
    request = urllib.request.Request(url, method=method)
    if origin:
        request.add_header("Origin", origin)
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            headers = {key.lower(): value for key, value in response.headers.items()}
            body = json.loads(response.read().decode("utf-8") or "{}")
            return response.status, body, headers
    except urllib.error.HTTPError as error:
        return error.code, {}, {key.lower(): value for key, value in error.headers.items()}


print("=" * 92)
print("PHASE 10 - FRONTEND / BACKEND INTEGRATION VERIFICATION")
print("=" * 92)

# 1) frontend build artifacts -------------------------------------------------
print("\n### Frontend build artifacts")
dist = FRONTEND / "dist"
verify("dist/index.html exists", (dist / "index.html").exists())
assets = list((dist / "assets").glob("*.js")) if (dist / "assets").exists() else []
verify("production bundle exists", len(assets) > 0)
verify("frontend source tree exists", (FRONTEND / "src" / "App.tsx").exists())
verify("static-data guard test exists", (FRONTEND / "src" / "tests" / "staticDataGuard.test.ts").exists())

# 2) start real backend --------------------------------------------------------
print("\n### Real backend boot")
server = subprocess.Popen(
    [sys.executable, "-m", "uvicorn", "app.main:app", "--port", "8000", "--log-level", "warning"],
    cwd=str(BACKEND),
    stdout=subprocess.DEVNULL,
    stderr=subprocess.DEVNULL,
)
try:
    ready = False
    for _ in range(60):
        try:
            status, body, _ = http("http://127.0.0.1:8000/api/health")
            if status == 200 and body.get("status") == "ok":
                ready = True
                break
        except Exception:
            time.sleep(0.5)
    verify("backend health endpoint responds", ready)

    if ready:
        status, body, headers = http("http://127.0.0.1:8000/api/datasets")
        verify("datasets list endpoint responds", status == 200 and "datasets" in body)
        print(f"    datasets available: {len(body.get('datasets', []))}")

        # CORS for the dev origin
        status, _, headers = http("http://127.0.0.1:8000/api/health", origin="http://localhost:5173")
        allow = headers.get("access-control-allow-origin", "")
        verify("CORS allows the frontend dev origin", allow in {"http://localhost:5173", "*"}, allow or "no header")

        # real dataset artifacts are reachable (used by the UI's dataset selector)
        if body.get("datasets"):
            dataset_id = body["datasets"][0]["dataset_id"]
            status, contract, _ = http(f"http://127.0.0.1:8000/api/datasets/{dataset_id}")
            verify(f"contract loads for real dataset {dataset_id}", status == 200 and contract.get("dataset_id") == dataset_id)
            status, analysis, _ = http(f"http://127.0.0.1:8000/api/datasets/{dataset_id}/analysis")
            verify("analysis artifact loads", status == 200 and analysis.get("status") == "complete")
            status, bottleneck, _ = http(f"http://127.0.0.1:8000/api/datasets/{dataset_id}/bottleneck/findings")
            verify("bottleneck findings load", status == 200 and "analyses" in bottleneck)
            status, recommendations, _ = http(f"http://127.0.0.1:8000/api/datasets/{dataset_id}/recommendations")
            verify("recommendations load", status == 200 and "recommendations" in recommendations)
            status, vision, _ = http(f"http://127.0.0.1:8000/api/datasets/{dataset_id}/vision/status")
            verify("vision status loads and is honest", status == 200 and vision.get("status") in {"NOT_SUPPORTED", "PROFILED", "PROFILED_NO_SUPPORTED_CAPABILITY"})
finally:
    server.terminate()
    try:
        server.wait(timeout=10)
    except subprocess.TimeoutExpired:
        server.kill()

print("\n" + "=" * 92)
print(f"RESULT: {'ALL CHECKS PASSED' if not failures else str(len(failures)) + ' FAILURES'}")
for failure in failures:
    print(f"  FAILED: {failure}")
print("=" * 92)
raise SystemExit(1 if failures else 0)
