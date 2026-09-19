"""Phase 12 exit verification: real vision pipeline over HTTP.

Boots the backend and verifies the complete inspection experience against the
REAL trained model and REAL image dataset:

  dataset -> model status/metrics -> inspect normal/defect/foreign images
  -> decisions -> trace ordering -> history -> no-fabrication checks
  -> process pipeline regression

Run: python backend/tests/verify_phase12_real.py
"""

from __future__ import annotations

import io
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
DATASET = PROJECT / "train" / "train"
ARTIFACTS = BACKEND / "runtime" / "vision_model"

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
        with urllib.request.urlopen(request, timeout=300) as response:
            return response.status, json.loads(response.read().decode("utf-8") or "{}")
    except urllib.error.HTTPError as error:
        payload = error.read().decode("utf-8")
        try:
            return error.code, json.loads(payload or "{}")
        except json.JSONDecodeError:
            return error.code, {"raw": payload}


def inspect_image(path: Path) -> tuple[int, dict]:
    boundary = f"----neurax{uuid.uuid4().hex}"
    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="{path.name}"\r\n'
        f"Content-Type: image/png\r\n\r\n"
    ).encode("utf-8") + path.read_bytes() + f"\r\n--{boundary}--\r\n".encode("utf-8")
    request = urllib.request.Request("http://127.0.0.1:8000/api/vision/inspect", data=body, method="POST")
    request.add_header("Content-Type", f"multipart/form-data; boundary={boundary}")
    try:
        with urllib.request.urlopen(request, timeout=300) as response:
            return response.status, json.loads(response.read().decode("utf-8") or "{}")
    except urllib.error.HTTPError as error:
        return error.code, json.loads(error.read().decode("utf-8") or "{}")


print("=" * 96)
print("PHASE 12 - REAL VISION PIPELINE VERIFICATION")
print("=" * 96)

# ---------------------------------------------------------------------------
# 1) dataset and artifacts on disk
# ---------------------------------------------------------------------------
print("\n### Image dataset and trained artifacts")
verify("image dataset exists", DATASET.exists(), str(DATASET))
for class_name in ("normal", "scratch", "rust", "hole", "crack"):
    count = len(list((DATASET / class_name).glob("*.png")))
    verify(f"class '{class_name}' present", count >= 1000, str(count))
verify("trained model artifacts exist", (ARTIFACTS / "classifier.joblib").exists())
verify("calibration artifact exists", (ARTIFACTS / "calibration.json").exists())
verify("anomaly/novelty reference exists", (ARTIFACTS / "normal_reference.npz").exists())

with open(ARTIFACTS / "metadata.json", "r", encoding="utf-8") as handle:
    metadata = json.load(handle)
with open(ARTIFACTS / "metrics.json", "r", encoding="utf-8") as handle:
    metrics = json.load(handle)
with open(ARTIFACTS / "calibration.json", "r", encoding="utf-8") as handle:
    calibration = json.load(handle)

verify("backbone recorded (frozen, pretrained)", metadata["backbone"]["frozen"] is True and metadata["backbone"]["pretrained"] == "imagenet")
verify("leakage-safe split recorded", "hash" in metadata["split"]["strategy"].lower() or "grouped" in metadata["split"]["strategy"].lower())
verify("test accuracy is a real measured value", 0 <= metrics["accuracy"] <= 1)
verify("false accept rate measured", metrics["false_accept_rate"] is not None)
verify("false reject rate measured", metrics["false_reject_rate"] is not None)
verify("calibration is temperature scaling", calibration["method"] == "temperature_scaling")
print(f"    test accuracy {metrics['accuracy']:.4f} · decisions {metrics['decisions']} · temperature {calibration['temperature']:.4f}")

# ---------------------------------------------------------------------------
# 2) boot backend and query the model
# ---------------------------------------------------------------------------
print("\n### Backend and model status")
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

    status, model_status = call("http://127.0.0.1:8000/api/vision/status")
    verify("vision status READY", status == 200 and model_status["status"] == "READY")
    verify("classes exposed from the model", set(model_status["classes"]) == {"crack", "hole", "normal", "rust", "scratch"})

    status, dataset_profile = call("http://127.0.0.1:8000/api/vision/dataset")
    verify("dataset profile endpoint returns real counts", status == 200 and sum(dataset_profile["class_counts"].values()) == 12000)
    verify("annotations honestly reported absent", dataset_profile["annotations"]["bounding_boxes_available"] is False)

    # -----------------------------------------------------------------------
    # 3) real inspections
    # -----------------------------------------------------------------------
    print("\n### Real inspections (via HTTP)")

    def first_image(class_name: str) -> Path:
        return sorted((DATASET / class_name).glob("*.png"))[10]

    cases = [
        ("normal", first_image("normal"), "PASS"),
        ("scratch", first_image("scratch"), "DEFECT"),
        ("rust", first_image("rust"), "DEFECT"),
        ("hole", first_image("hole"), "DEFECT"),
        ("crack", first_image("crack"), "DEFECT"),
    ]
    inspected_ids = []
    for label, path, expected in cases:
        status, result = inspect_image(path)
        verify(f"{label}: inspection completes", status == 200 and "inspection_id" in result, f"HTTP {status}")
        if status != 200:
            continue
        inspected_ids.append(result["inspection_id"])
        verify(f"{label}: decision {expected}", result["decision"] == expected, result["decision"])
        verify(f"{label}: confidence calibrated in [0,1]", 0 <= result["confidence"]["value"] <= 1)
        verify(f"{label}: localization labeled model-derived", result["localization"]["type"] == "MODEL-DERIVED LOCALIZATION")
        verify(f"{label}: heatmap produced", len(result["localization"]["heatmap_png_base64"]) > 1000)
        verify(f"{label}: process link honest", result["process_link"]["status"] == "NOT_AVAILABLE")
        verify(f"{label}: trace has 10 ordered stages",
               [s["id"] for s in result["trace"]] == [
                   "image_received", "validation", "preprocessing", "feature_extraction", "classification",
                   "anomaly_analysis", "localization", "confidence", "decision", "process_link",
               ])
        verify(f"{label}: no chain-of-thought fields", "reasoning" not in json.dumps(result).lower() or "not private model chain-of-thought" in json.dumps(result).lower())

    # -----------------------------------------------------------------------
    # 4) unseen condition -> REVIEW (robustness)
    # -----------------------------------------------------------------------
    print("\n### Unseen condition handling")
    foreign = Path(r"C:\Users\Sriram\Downloads\adorable-cat-lifestyle.jpg")
    if foreign.exists():
        boundary = f"----neurax{uuid.uuid4().hex}"
        body = (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="file"; filename="{foreign.name}"\r\n'
            f"Content-Type: image/jpeg\r\n\r\n"
        ).encode("utf-8") + foreign.read_bytes() + f"\r\n--{boundary}--\r\n".encode("utf-8")
        request = urllib.request.Request("http://127.0.0.1:8000/api/vision/inspect", data=body, method="POST")
        request.add_header("Content-Type", f"multipart/form-data; boundary={boundary}")
        with urllib.request.urlopen(request, timeout=120) as response:
            foreign_result = json.loads(response.read().decode())
        verify("foreign image -> REVIEW (not forced into a known class)", foreign_result["decision"] == "REVIEW", foreign_result["decision"])
        verify("foreign image flagged novel", foreign_result["anomaly_score"]["novelty_status"] == "HIGH")
        verify("foreign review reason explains unfamiliarity", "Unfamiliar" in (foreign_result["review_reason"] or ""))
    else:
        print("  (foreign-image check skipped: sample not present)")

    # -----------------------------------------------------------------------
    # 5) trace endpoint, image serving, history
    # -----------------------------------------------------------------------
    print("\n### Trace, image serving and history")
    inspection_id = inspected_ids[0]
    status, trace = call(f"http://127.0.0.1:8000/api/vision/inspect/{inspection_id}/trace")
    verify("trace endpoint returns stages", status == 200 and trace["stage_count"] == 10)
    verify("trace note disclaims chain-of-thought", "chain-of-thought" in trace["note"])

    status, history = call("http://127.0.0.1:8000/api/vision/history")
    verify("history contains real inspections", status == 200 and history["count"] >= len(inspected_ids))
    verify("history records carry decisions", all(entry["decision"] in {"PASS", "DEFECT", "REVIEW"} for entry in history["inspections"]))

    image_url = f"http://127.0.0.1:8000/api/vision/inspect/{inspection_id}/image"
    with urllib.request.urlopen(image_url, timeout=30) as response:
        image_bytes = response.read()
    verify("stored inspection image is served", response.status == 200 and len(image_bytes) > 100)

    # -----------------------------------------------------------------------
    # 6) no fabricated values
    # -----------------------------------------------------------------------
    print("\n### No-fabrication checks")
    status, fresh = inspect_image(first_image("normal"))
    serialized = json.dumps(fresh).lower()
    for forbidden in ("guaranteed", "will fix", "100% certain", "proven cause"):
        verify(f"no forbidden phrase '{forbidden}'", forbidden not in serialized)
    verify("confidence carries limitation text", "not physical certainty" in serialized)

    # -----------------------------------------------------------------------
    # 7) process pipeline regression
    # -----------------------------------------------------------------------
    print("\n### Process pipeline regression")
    status, datasets = call("http://127.0.0.1:8000/api/datasets")
    verify("process datasets still listed", status == 200 and len(datasets.get("datasets", [])) >= 1)
    if datasets.get("datasets"):
        dataset_id = datasets["datasets"][0]["dataset_id"]
        status, bottleneck = call(f"http://127.0.0.1:8000/api/datasets/{dataset_id}/bottleneck/findings")
        verify("bottleneck artifacts still load", status == 200)
        status, recommendations = call(f"http://127.0.0.1:8000/api/datasets/{dataset_id}/recommendations")
        verify("recommendations still load", status == 200)

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
