# NeuraX — Visual Inspection & Defect Root-Cause Assistant

An industrial AI decision-support workstation. **Visual inspection is the primary experience:**
upload a part image, watch the real pipeline execute (validation → preprocessing → feature extraction
→ classification → anomaly analysis → localization → decision), and get a calibrated
PASS / DEFECT / REVIEW decision with model-derived localization. Process datasets extend the story
into root-cause analysis, bottleneck detection, economics and advisory recommendations.

**From detection to decision:** inspection → defect decision → localization → novelty/uncertainty →
process correlation → root cause → bottleneck → throughput → economics → what-if → recommendation.
Every claim is traceable to data or an explicit assumption. Nothing is fabricated.

---

## Project overview

**Vision (implemented, real):** MobileNetV2 (ImageNet, frozen) embeddings + logistic-regression head,
temperature-scaled calibration, Mahalanobis normal-reference anomaly scoring, class-relative novelty,
class-activation-map localization, and a three-way PASS/DEFECT/REVIEW decision layer with measured
false-accept / false-reject / review rates.

**Process (implemented, real):** dynamic dataset ingestion (CSV/MAT/XLSX/ZIP), leakage-safe ML,
process anomaly detection, evidence-scored root-cause ranking, bottleneck/flow analysis,
assumption-driven economics and deterministic advisory recommendations.

**Data provenance is explicit everywhere:** `OBSERVED` · `DATA_DERIVED` · `MODEL OUTPUT` ·
`MODEL-DERIVED` · `STATISTICAL ASSOCIATION` · `USER_ASSUMPTION` · `SIMULATED` · `ADVISORY`.
Association is never presented as causation. Unsupported capabilities report `NOT_SUPPORTED` with
the exact reason — never placeholder values.

## Architecture

```
frontend/ (React + TS + Vite + Tailwind)  — 4 areas: INSPECT · CONSOLE · DECISION · CONTROL ROOM
    │  typed REST client
    ▼
backend/ (FastAPI modular monolith)
    ├─ app/vision/      image dataset discovery, training, inference, CAM localization, trace
    ├─ app/ingest/      file readers, schema inference, dataset contract
    ├─ app/pipeline/    cleaning, features, leakage-safe splits, station metrics
    ├─ app/ml/          regression/classification, anomaly detection, model registry
    ├─ app/rootcause/   correlation, MI, group/temporal/anomaly evidence, evidence scoring
    ├─ app/flow/        bottleneck scoring, flow graph, observed throughput comparison
    ├─ app/economics/   user assumptions, baseline, scenarios, sensitivity
    ├─ app/recommend/   deterministic rule engine + language-safety validation
    └─ app/core/        session store, settings
train/train/            image dataset (5 classes × 2,400 images, 256×256 PNG)
runtime/                artifacts/, models/, vision_model/, sessions/, uploads/
```

## Tech stack

- **Backend:** Python 3.13, FastAPI, TensorFlow 2.20 (MobileNetV2), scikit-learn, pandas, NumPy, SciPy, joblib
- **Frontend:** React 18, TypeScript, Vite 5, Tailwind CSS 3, Framer Motion, Lucide (SVG flow — 106 KB gzip bundle)
- **Cost:** $0 — no paid APIs, no cloud services, no LLM anywhere in the product

## How to run

**One command (recommended for judging):**

```powershell
.\start_demo.ps1
```

Then open **http://localhost:4173**.

**Manual:**

```powershell
# Backend
cd backend
python -m uvicorn app.main:app --port 8000

# Frontend (separate terminal)
cd frontend
npm install          # first time only
npm run build
npm run preview      # http://localhost:4173
```

## How to use

1. **INSPECT** (opens by default) — drag an inspection image (PNG/JPG/JPEG/BMP/TIFF/WEBP). The real
   pipeline runs; the decision panel shows class, calibrated confidence, anomaly score, novelty and
   PASS/DEFECT/REVIEW. The image viewer overlays the model-derived heatmap and region.
2. **CONSOLE** — the observable AI trace: every stage with its real metrics and duration.
3. **DECISION** — the chain WHAT → WHERE → HOW CERTAIN → WHY → WHAT NEXT, decision thresholds and
   the measured false-accept / false-reject / review rates.
4. **CONTROL ROOM** — upload/select a process dataset (CSV/MAT/ZIP) for flow, constraint,
   throughput, root cause, economics, what-if and recommendations. Detailed sections expand on demand.

## Supported data

| Input | Status |
|---|---|
| Inspection images (PNG/JPG/JPEG/BMP/TIFF/WEBP) | SUPPORTED (5-class model trained on `train/train`) |
| Process/tabular datasets (CSV, MAT, XLSX, ZIP) | SUPPORTED (auto-detected schema) |
| Economic columns (cost/price/margin) | REQUIRES_ASSUMPTIONS (user supplies assumptions) |
| Ground-truth defect annotations (boxes/masks) | NOT AVAILABLE in the image dataset → localization is model-derived (CAM) |

## Vision model (real, measured)

| Property | Value |
|---|---|
| Backbone | MobileNetV2, ImageNet pretrained, frozen (1280-d embeddings) |
| Head | Logistic regression (multinomial) |
| Calibration | Temperature scaling on validation logits |
| Anomaly | Mahalanobis distance percentile vs normal-class reference |
| Novelty | Distance to predicted-class centroid vs that class's training distribution |
| Localization | Class-activation mapping — **model-derived, not ground truth** |
| Split | Perceptual-hash grouped split (near-duplicates never cross splits) |
| Classes | crack · hole · normal · rust · scratch (2,400 images each, 256×256) |
| Test set | 500 held-out images: accuracy 1.00, PASS 98 / DEFECT 394 / REVIEW 8, FAR 0%, FRR 0% |

Retrain any time: `POST /api/vision/train` (or the train action in the UI when no model exists).

## Current vision status

**IMPLEMENTED.** A real image dataset exists and a real model is trained and serving inspections.
Localization is explicitly labeled model-derived because the dataset contains no ground-truth
annotations. Foreign/unfamiliar images are flagged **REVIEW** with novelty `HIGH` — the system
never forces an unknown condition into a known defect class.

## Economic assumptions

The process datasets contain **no economic columns**. Impact figures require user-supplied
assumptions (currency, contribution margin, working hours, ...). Until supplied, economic outputs
read `NOT AVAILABLE` with the missing fields listed.

## API overview

| Area | Endpoints |
|---|---|
| Core | `GET /api/health`, `GET /api/datasets`, `POST /api/upload`, `GET /api/datasets/{id}`, `/status`, `/profile`, `/analysis` |
| Vision | `GET /api/vision/status`, `/dataset`, `/history`; `POST /api/vision/train`; `POST /api/vision/inspect`; `GET /api/vision/inspect/{id}`, `/{id}/trace`, `/{id}/image` |
| Models | `GET /api/datasets/{id}/models`, `/predictions`, `/anomalies`; `POST /models/train` |
| Root cause | `GET .../root-cause/status|targets|findings|drift`; `POST .../root-cause/analyze` |
| Bottleneck | `GET .../bottleneck/status|stations|findings|flow`; `POST .../bottleneck/analyze` |
| Economics | `GET/PUT .../economics/assumptions`; `GET .../baseline|scenarios`; `POST .../economics/scenario` (alias `/what-if`) |
| Recommendations | `GET .../recommendations/status|list|{id}|{id}/evidence`; `POST .../recommendations/generate` |

## Test results

| Suite | Result |
|---|---|
| Backend (`pytest tests -q`) | **216 passed** |
| Frontend (`npm test`) | **24 passed** |
| Browser smoke (`npx playwright test`, system Edge) | **3 passed** |
| Lint / typecheck / build | clean |
| `verify_phase3_real.py` … `verify_phase12_real.py` | ALL CHECKS PASSED |

## Known limitations

- Localization is model-derived (CAM) — the dataset has no bounding-box or mask annotations.
- The synthetic image dataset is cleanly separable (100% test accuracy); real-world imagery would
  lower accuracy and raise review rates.
- Inspection images carry no batch/station/unit metadata → `PROCESS LINK NOT AVAILABLE` (honest).
- Economics depend entirely on user assumptions.
- The 605k-row Model_3 process dataset takes ~1–2 minutes to process; use Model_1 for live demos.

## Judge 60-second explanation

> "Our system is an industrial AI inspection workstation. An image is processed by a real pipeline:
> a frozen pretrained backbone extracts features, a calibrated classifier predicts the defect class,
> an anomaly model compares against a normal reference, and a model-derived activation map localizes
> the defect — then a PASS/DEFECT/REVIEW decision is made with configurable thresholds and measured
> error rates. Unfamiliar images are flagged REVIEW instead of being forced into a known class.
> Process datasets extend the same evidence chain into root cause, bottleneck, economics and
> advisory recommendations. Every result is traceable to data or an explicit assumption."
