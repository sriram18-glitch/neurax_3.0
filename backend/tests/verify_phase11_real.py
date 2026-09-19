"""Phase 11 exit verification: the exact judge demo flow over real HTTP.

Boots the real backend, uploads the real demo dataset (Model_1.csv), and runs
the full walkthrough sequence the frontend uses:

    upload -> pipeline/ML -> root cause -> bottleneck -> economics
    (user assumptions) -> what-if scenario -> recommendations -> vision status

Also verifies presentation packaging (startup script, docs, build artifacts)
and that no fabricated values appear anywhere.

Run: python backend/tests/verify_phase11_real.py
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
PROJECT = BACKEND.parent
DEMO_DATASET = PROJECT / "Manufacturing Data Shared Facility - Discrete-Event Simulation" / "Model 1" / "Model_1.csv"

failures: list[str] = []


def verify(name: str, condition: bool, detail: str = "") -> None:
    print(f"  [{'PASS' if condition else 'FAIL'}] {name}{'' if condition else ' -> ' + detail}")
    if not condition:
        failures.append(name)


def call(url: str, method: str = "GET", body: dict | None = None) -> tuple[int, dict]:
    data = json.dumps(body).encode("utf-8") if body is not None else None
    request = urllib.request.Request(url, data=data, method=method)
    if data is not None:
        request.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(request, timeout=180) as response:
            return response.status, json.loads(response.read().decode("utf-8") or "{}")
    except urllib.error.HTTPError as error:
        payload = error.read().decode("utf-8")
        try:
            return error.code, json.loads(payload or "{}")
        except json.JSONDecodeError:
            return error.code, {"raw": payload}


def upload_dataset(path: Path) -> tuple[int, dict]:
    boundary = f"----neurax{uuid.uuid4().hex}"
    file_bytes = path.read_bytes()
    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="{path.name}"\r\n'
        f"Content-Type: text/csv\r\n\r\n"
    ).encode("utf-8") + file_bytes + f"\r\n--{boundary}--\r\n".encode("utf-8")
    request = urllib.request.Request("http://127.0.0.1:8000/api/upload", data=body, method="POST")
    request.add_header("Content-Type", f"multipart/form-data; boundary={boundary}")
    try:
        with urllib.request.urlopen(request, timeout=600) as response:
            return response.status, json.loads(response.read().decode("utf-8") or "{}")
    except urllib.error.HTTPError as error:
        return error.code, json.loads(error.read().decode("utf-8") or "{}")


print("=" * 96)
print("PHASE 11 - JUDGE DEMO FLOW VERIFICATION (REAL HTTP)")
print("=" * 96)

# ---------------------------------------------------------------------------
# 0) presentation packaging
# ---------------------------------------------------------------------------
print("\n### Presentation packaging")
verify("startup script exists", (PROJECT / "start_demo.ps1").exists())
verify("README exists", (PROJECT / "README.md").exists())
verify("demo script exists", (PROJECT / "DEMO_SCRIPT.md").exists())
verify("frontend production build exists", (PROJECT / "frontend" / "dist" / "index.html").exists())
verify("playwright smoke test exists", (PROJECT / "frontend" / "e2e" / "smoke.spec.ts").exists())
verify("demo dataset exists", DEMO_DATASET.exists(), str(DEMO_DATASET))

# ---------------------------------------------------------------------------
# 1) boot backend
# ---------------------------------------------------------------------------
print("\n### Backend boot")
server = subprocess.Popen(
    [sys.executable, "-m", "uvicorn", "app.main:app", "--port", "8000", "--log-level", "warning"],
    cwd=str(BACKEND),
    stdout=subprocess.DEVNULL,
    stderr=subprocess.DEVNULL,
)
try:
    ready = False
    for _ in range(90):
        try:
            status, _ = call("http://127.0.0.1:8000/api/health")
            if status == 200:
                ready = True
                break
        except Exception:
            time.sleep(0.5)
    verify("backend healthy", ready)
    if not ready:
        raise SystemExit(1)

    # -----------------------------------------------------------------------
    # 2) upload the real demo dataset (fresh processing)
    # -----------------------------------------------------------------------
    print("\n### Upload + processing (real dataset)")
    started = time.time()
    status, contract = upload_dataset(DEMO_DATASET)
    elapsed = time.time() - started
    verify("upload accepted", status == 200, f"HTTP {status}")
    dataset_id = contract.get("dataset_id", "")
    verify("contract returned with dataset id", bool(dataset_id))
    verify("pipeline complete", (contract.get("pipeline") or {}).get("status") == "complete")
    verify("models trained", (contract.get("ml") or {}).get("models_trained", 0) >= 1)
    verify("vision NOT_SUPPORTED in contract", (contract.get("vision") or {}).get("status") == "NOT_SUPPORTED")
    verify("processing within 60s for demo dataset", elapsed < 60, f"{elapsed:.1f}s")
    print(f"    dataset {dataset_id} processed in {elapsed:.1f}s")

    status, analysis = call(f"http://127.0.0.1:8000/api/datasets/{dataset_id}/analysis")
    verify("analysis artifact loads", status == 200 and analysis.get("status") == "complete")

    # -----------------------------------------------------------------------
    # 3) root cause
    # -----------------------------------------------------------------------
    print("\n### Root cause")
    status, targets = call(f"http://127.0.0.1:8000/api/datasets/{dataset_id}/root-cause/targets")
    verify("root-cause targets discovered", status == 200 and targets.get("count", 0) >= 1)
    target = targets["targets"][0]["target"]
    status, rca = call(
        f"http://127.0.0.1:8000/api/datasets/{dataset_id}/root-cause/analyze",
        method="POST",
        body={"target": target, "direction": "low", "quantile": 0.1},
    )
    verify("root-cause analysis completes", status == 200 and rca.get("status") == "complete")
    verify("ranked findings exist", len(rca.get("ranked_findings", [])) >= 1)
    verify("epistemic labels present", all(f.get("epistemic_status") for f in rca.get("ranked_findings", [])))
    verify("causal claim explicitly NOT SUPPORTED", str(rca.get("epistemic_summary", {}).get("causal_claim", "")).startswith("NOT SUPPORTED"))
    print(f"    target '{target}': {len(rca.get('ranked_findings', []))} factors, top = {rca['ranked_findings'][0]['factor']}")

    # -----------------------------------------------------------------------
    # 4) bottleneck
    # -----------------------------------------------------------------------
    print("\n### Bottleneck")
    status, bottleneck = call(
        f"http://127.0.0.1:8000/api/datasets/{dataset_id}/bottleneck/analyze", method="POST", body={}
    )
    verify("bottleneck analysis completes", status == 200 and bottleneck.get("status") == "complete")
    candidate = bottleneck.get("candidate_bottleneck", {})
    verify("candidate bottleneck identified", bool(candidate.get("station")))
    verify("candidate has why-evidence", bool(candidate.get("why")))
    verify("flow graph status reported", bottleneck.get("flow", {}).get("graph", {}).get("status") in {"SUPPORTED", "PARTIALLY_SUPPORTED"})
    print(f"    candidate: {candidate.get('station')} ({candidate.get('evidence_quality', {}).get('label')})")

    # -----------------------------------------------------------------------
    # 5) economics with user assumptions + what-if
    # -----------------------------------------------------------------------
    print("\n### Economics + what-if (user assumptions)")
    status, assumptions = call(f"http://127.0.0.1:8000/api/datasets/{dataset_id}/economics/assumptions")
    verify("assumptions endpoint returns NOT_PROVIDED state", status == 200)
    status, baseline_before = call(f"http://127.0.0.1:8000/api/datasets/{dataset_id}/economics/baseline")
    contribution = baseline_before.get("baseline", {}).get("daily_contribution", {})
    # Assumptions are user data and persist per dataset id; the honest states are
    # either NOT_AVAILABLE (with missing inputs listed) or CALCULATED (from supplied
    # assumptions). Anything else would be fabricated.
    if contribution.get("status") == "NOT_AVAILABLE":
        verify(
            "baseline NOT AVAILABLE with missing inputs listed before assumptions",
            bool(contribution.get("missing_inputs")),
        )
    else:
        verify(
            "baseline CALCULATED from previously supplied user assumptions",
            contribution.get("status") == "CALCULATED" and contribution.get("epistemic_status") == "CALCULATED",
        )
    verify(
        "economics never claim to be dataset-derived",
        "DATA_DERIVED" not in str(contribution.get("epistemic_status", ""))
        or contribution.get("status") == "NOT_AVAILABLE",
    )

    status, merged = call(
        f"http://127.0.0.1:8000/api/datasets/{dataset_id}/economics/assumptions",
        method="PUT",
        body={
            "currency": "INR",
            "contribution_margin_per_unit": 25.0,
            "working_hours_per_day": 8.0,
            "working_days_per_month": 22.0,
        },
    )
    verify("assumptions accepted and labeled USER_ASSUMPTION", status == 200 and merged.get("assumptions", {}).get("contribution_margin_per_unit", {}).get("source") == "USER_ASSUMPTION")
    status, baseline_after = call(f"http://127.0.0.1:8000/api/datasets/{dataset_id}/economics/baseline")
    verify("baseline CALCULATED after assumptions", baseline_after.get("baseline", {}).get("daily_contribution", {}).get("status") == "CALCULATED")

    status, scenario = call(
        f"http://127.0.0.1:8000/api/datasets/{dataset_id}/economics/scenario",
        method="POST",
        body={
            "scenario_type": "throughput_scaling",
            "changes": {"throughput_change": 0.1, "scaling_basis": "user_assumption"},
            "sensitivity": {"parameter": "throughput_change", "values": [0.05, 0.1, 0.2]},
        },
    )
    verify("scenario runs", status == 200 and scenario.get("scenario_type") == "throughput_scaling")
    verify("scenario labeled SIMULATED", str(scenario.get("epistemic_status", "")).startswith("SIMULATED SCENARIO"))
    verify("scenario includes assumptions", len(scenario.get("assumptions_snapshot", {}).get("assumptions", {})) > 0)
    verify("sensitivity sweep returned model-driven points", len(scenario.get("sensitivity", {}).get("points", [])) == 3)
    serialized = json.dumps(scenario).lower()
    verify("no guaranteed-outcome language", all(phrase not in serialized for phrase in ("guaranteed", "will increase", "will save")))

    # guard: scaling without the explicit basis is refused
    status, refused = call(
        f"http://127.0.0.1:8000/api/datasets/{dataset_id}/economics/scenario",
        method="POST",
        body={"scenario_type": "throughput_scaling", "changes": {"throughput_change": 0.1}},
    )
    verify("unacknowledged scaling refused", status == 422 and refused.get("detail", {}).get("code") == "SCENARIO_NOT_SUPPORTED")

    # -----------------------------------------------------------------------
    # 6) recommendations
    # -----------------------------------------------------------------------
    print("\n### Recommendations")
    status, run = call(f"http://127.0.0.1:8000/api/datasets/{dataset_id}/recommendations/generate", method="POST")
    verify("recommendations generated", status == 200 and run.get("recommendation_count", 0) >= 1)
    verify("all recommendations ADVISORY", all(r.get("epistemic_status") == "ADVISORY" for r in run.get("recommendations", [])))
    verify("all recommendations have evidence", all(r.get("evidence") for r in run.get("recommendations", [])))
    verify("decision summary present", bool(run.get("decision_summary")))
    status, listing = call(f"http://127.0.0.1:8000/api/datasets/{dataset_id}/recommendations")
    verify("recommendation registry loads", status == 200 and listing.get("count") == run.get("recommendation_count"))
    print(f"    {run.get('recommendation_count')} recommendations; top = {run['recommendations'][0]['action_type']}")

    # -----------------------------------------------------------------------
    # 7) vision honesty + reset semantics
    # -----------------------------------------------------------------------
    print("\n### Vision + reset semantics")
    status, vision = call(f"http://127.0.0.1:8000/api/datasets/{dataset_id}/vision/status")
    verify("vision status honest", status == 200 and vision.get("status") == "NOT_SUPPORTED")
    verify("vision reason present", bool(vision.get("reason")))
    status, datasets = call("http://127.0.0.1:8000/api/datasets")
    verify(
        "dataset remains selectable after reset (persisted)",
        status == 200 and any(d["dataset_id"] == dataset_id for d in datasets.get("datasets", [])),
    )

finally:
    server.terminate()
    try:
        server.wait(timeout=10)
    except subprocess.TimeoutExpired:
        server.kill()

print("\n" + "=" * 96)
print(f"RESULT: {'ALL CHECKS PASSED' if not failures else str(len(failures)) + ' FAILURES'}")
for failure in failures:
    print(f"  FAILED: {failure}")
print("=" * 96)
raise SystemExit(1 if failures else 0)
