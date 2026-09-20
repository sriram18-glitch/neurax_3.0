# NeuraX — Industrial AI Inspection & Automated Root-Cause Decision System

An automation-first industrial AI control room. **A simulated production stream over the real image
dataset runs inspections automatically** — every frame goes through the real trained pipeline
(validation → preprocessing → backbone → calibrated classification → anomaly → localization →
robustness → PASS/DEFECT/REVIEW) and every actionable decision **automatically triggers an
investigation chain**: process correlation → root-cause hypotheses → bottleneck → impact → what-if →
advisory recommendation. Manual upload exists as a fallback, not as the product story.

**From detection to decision:** production event → automated inspection → defect decision → visual
localization → robustness check → process evidence → root-cause hypotheses → bottleneck →
production/economic impact → what-if → evidence-backed recommendation → human decision.
Every claim is traceable to data or an explicit assumption. Nothing is fabricated.

---

## Project overview

**Vision (implemented, real):** MobileNetV2 (ImageNet, frozen) embeddings + logistic-regression head,
temperature-scaled calibration, Mahalanobis normal-reference anomaly scoring, class-relative novelty,
class-activation-map localization, a 2-D PCA projection of the real training embeddings, and a
three-way PASS/DEFECT/REVIEW decision layer with measured false-accept / false-reject / review rates.

**Automation (implemented, real):** a deterministic production stream over the real dataset
(`app/vision/stream.py`), an automatic investigation orchestrator over the existing engines
(`app/investigations/`), process timeline aggregation (`app/flow/timeline.py`) and a stored
investigation history with stage-by-stage replay.

**Process (implemented, real):** dynamic dataset ingestion (CSV/MAT/XLSX/ZIP), leakage-safe ML,
process anomaly detection, evidence-scored root-cause ranking, bottleneck/flow analysis,
assumption-driven economics and deterministic advisory recommendations.

**Data provenance is explicit everywhere:** `OBSERVED` · `DATA_DERIVED` · `MODEL OUTPUT` ·
`MODEL-DERIVED` · `STATISTICAL ASSOCIATION` · `HYPOTHESIS` · `USER_ASSUMPTION` · `SIMULATION` ·
`DATA GAP`. Association is never presented as causation. Unsupported capabilities report
`NOT_SUPPORTED` / `NOT AVAILABLE` with the exact reason — never placeholder values.

## Architecture

```
frontend/ (React + TS + Vite + Tailwind)  — 4 areas:
    COMMAND CENTER · INSPECTION · PROCESS INTELLIGENCE · INVESTIGATION HISTORY
    components/neurax/  design system: stream, pipeline, evidence graph, novelty gauge,
                        feature-space map, timeline, decision chain, replay, event feed
    │  typed REST client
    ▼
backend/ (FastAPI modular monolith)
    ├─ app/vision/          dataset discovery, training (incl. feature-space PCA), inference,
    │                       CAM localization, event-stream trace, production stream engine
    ├─ app/investigations/  automatic investigation orchestrator + persisted history
    ├─ app/ingest/          file readers, schema inference, dataset contract
    ├─ app/pipeline/        cleaning, features, leakage-safe splits, station metrics
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
- **Frontend:** React 18, TypeScript, Vite 5, Tailwind CSS 3, Framer Motion, Lucide (SVG visuals — 119 KB gzip bundle)
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

1. **COMMAND CENTER** (opens by default) — automation-first. The **AI investigation pipeline** is a
   result timeline: every stage shows its real status (COMPLETE / REVIEW / DATA GAP / INPUT REQUIRED /
   FAILED), its result text, and what inputs it still requires — the capability always exists, the
   data decides. The **data coverage** grid separates *capability* (READY) from *data* (INPUT
   REQUIRED / DATA GAP) with actions (+ ADD PROCESS DATA, + ADD ASSUMPTIONS). The **human review
   queue** banner is dynamic and opens the actual review workspace. **START DEMO** runs the real
   application end to end.
2. **INSPECTION** — three input modes plus the process connector: **AUTO PRODUCTION STREAM**
   (primary), **BATCH INSPECTION** (add images/ZIP → automatic validation → data-health report →
   auto check with per-image results, confidence bars, filters and a gallery), **MANUAL
   INSPECTION** (single image, drag-drop/browse/paste), **CONNECT DATA SOURCE**. The **visual AI
   pipeline** shows plain-language stage outputs with raw metrics behind **View technical
   evidence**; the **evidence graph** exposes every node of the decision with its epistemic
   label; **feature space** projects the live sample into the real training PCA; **robustness**
   shows novelty vs the known distribution; **decision quality** shows FAR/FRR/review rate and the
   real thresholds; the **decision chain** ties WHAT → WHERE → HOW CERTAIN → WHY → FLOW → IMPACT →
   WHAT NEXT together. **Replay decision** replays the stored trace.
3. **PROCESS INTELLIGENCE** — upload/connect a process dataset (CSV/MAT/ZIP) and walk five stages:
   PROCESS (composition + real process timeline) → ROOT CAUSE (factor ranking + association graph +
   drift) → FLOW (process map, bottleneck evidence bars, constraint ranking, observed impact) →
   IMPACT (calculation chain, all assumption fields, what-if simulator) → ACTION (deterministic
   advisory recommendations with evidence).
4. **INVESTIGATION HISTORY** — two sections: **Investigations** (stored investigations, stage
   replay) and **Human review** (the review workspace). The workspace shows the actual review
   images, the AI decision with confidence/novelty/anomaly/thresholds, explicit reasons for the
   review, and human actions — CONFIRM DEFECT, CONFIRM <defect class>, MARK PASS, KEEP IN REVIEW,
   ESCALATE — stored separately from the AI result (automate the certain, escalate the uncertain).

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
| Decision matrix | PASS(normal) → 98 PASS / 0 DEFECT / 2 REVIEW · DEFECT(defective) → 0 PASS / 394 DEFECT / 6 REVIEW |

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
| Vision | `GET /api/vision/status`, `/dataset`, `/history`, `/feature-space`; `POST /api/vision/train`; `POST /api/vision/inspect`; `POST /api/vision/inspect/stream` (NDJSON stage events); `GET /api/vision/inspect/{id}`, `/{id}/trace`, `/{id}/image` |
| Automation | `GET /api/vision/stream/status`; `POST /api/vision/stream/start|pause|resume|reset|speed|next`; `GET /api/investigations`, `/api/investigations/{id}`; `POST /api/investigations/run` |
| Batch + review | `POST /api/vision/batch` (multi-file/ZIP); `POST /api/vision/batch/{id}/inspect`; `GET /api/vision/batch/{id}`, `/api/vision/batches`; `GET /api/vision/review/queue`, `/api/vision/review/stats`; `POST /api/vision/inspect/{id}/review` |
| Process | `GET /api/datasets/{id}/process/timeline` (binned real series + drift + event rows) |
| Models | `GET /api/datasets/{id}/models`, `/predictions`, `/anomalies`; `POST /models/train` |
| Root cause | `GET .../root-cause/status|targets|findings|drift`; `POST .../root-cause/analyze` |
| Bottleneck | `GET .../bottleneck/status|stations|findings|flow`; `POST .../bottleneck/analyze` |
| Economics | `GET/PUT .../economics/assumptions`; `GET .../baseline|scenarios`; `POST .../economics/scenario` (alias `/what-if`) |
| Recommendations | `GET .../recommendations/status|list|{id}|{id}/evidence`; `POST .../recommendations/generate` |

## Test results

| Suite | Result |
|---|---|
| Backend (`pytest tests -q`) | **250 passed** |
| Frontend (`npm test`) | **48 passed** |
| Browser smoke (`npx playwright test`, system Edge) | **5 passed** (real backend/model: stream → investigation, process intelligence, batch, full human-review workflow, mobile) |
| Lint / typecheck / build | clean |
| `verify_phase3_real.py` … `verify_phase12_real.py` | ALL CHECKS PASSED |

## Known limitations

- The production stream is **simulated** (real dataset frames in deterministic order) — it is labelled
  as such everywhere; no live camera is claimed.
- Localization is model-derived (CAM) — the dataset has no bounding-box or mask annotations.
- The synthetic image dataset is cleanly separable (100% test accuracy); real-world imagery would
  lower accuracy and raise review rates.
- Inspection images carry no batch/station/unit metadata → per-unit process correlation is
  `NOT AVAILABLE`; investigations report dataset-level process context as `PARTIAL` (honest).
- Economics depend entirely on user assumptions.
- The 605k-row Model_3 process dataset takes ~1–2 minutes to process; use Model_1 for live demos.

## Requirement traceability

See [`REQUIREMENT_MATRIX.md`](REQUIREMENT_MATRIX.md) for the full requirement → implementation map,
including the honest limitations table. See [`DEMO_SCRIPT.md`](DEMO_SCRIPT.md) for the 3-minute
judge walkthrough.

## Judge 60-second explanation

> "NEURAX is an industrial AI control room. A simulated production stream over a real image dataset
> feeds a real trained pipeline — a frozen pretrained backbone, a calibrated classifier, an anomaly
> reference and a model-derived activation map — and produces PASS/DEFECT/REVIEW decisions with
> measured error rates. Unfamiliar samples are flagged REVIEW instead of being forced into a known
> class. Every actionable decision automatically triggers an investigation: process evidence where a
> valid join exists, statistical root-cause candidates, bottleneck hypotheses, assumption-based
> economics, what-if scenarios and advisory recommendations. Everything is traceable to model
> output, data, or an explicit assumption — and anything we cannot support is reported as a data gap."
