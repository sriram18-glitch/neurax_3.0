# NEURAX — Requirement Coverage Matrix

Every requirement from the problem statement, the V2 transformation brief and the
V2.1 judging-criteria pass is mapped to its implementation. **Status** is one of:

- `IMPLEMENTED` — working in the product, verified by tests
- `IMPLEMENTED (DATA-DEPENDENT)` — works when the input data supports it; honest
  `DATA GAP` / `NOT AVAILABLE` states otherwise
- `ADVISORY` — produces recommendations only; never controls machinery

## A. Judging criteria (explicit mapping, no invented scores)

| Criterion (marks) | Implemented feature | Backend evidence | UI evidence | Test | Status |
|---|---|---|---|---|---|
| Detection & classification (15) | Calibrated 5-class model; batch decision quality vs class-folder ground truth | `app/vision/training.py` metrics + decision matrix; `batch.py` TP/TN/FP/FN | Classification bars, decision matrix, batch dashboard | `test_vision*`, `test_v2_batch_review`, smoke batch flow | IMPLEMENTED |
| Localization (10) | Class-activation map + region box; ground truth honestly reported absent | `inference.py` CAM + `localization` payload | Heatmap/region overlay, `MODEL-DERIVED` + `NOT AVAILABLE` labels | `test_vision_pipeline`, Playwright | IMPLEMENTED |
| Robustness to unseen conditions (10) | Class-relative novelty + Mahalanobis anomaly; REVIEW escalation for novel samples | `training.py` novelty references; `review_reasons` on decision | Known-distribution gauge, NOVEL/REVIEW states, review reasons | `automation.test.tsx` (novel → REVIEW) | IMPLEMENTED |
| False accept / reject (5) | Measured test-split FAR/FRR; batch FAR/FRR vs labels when folders exist | `metrics.json`; `batch.py` `_decision_quality` | `DecisionQuality`, batch quality panel with trade-off note | `test_v2_batch_review` quality assertions | IMPLEMENTED (DATA-DEPENDENT) |
| Root-cause correlation (5) | Association engine with explicit causal disclaimer; honest join gap | `app/rootcause/`; `process_link` | Association graph, factor ranking, DATA GAP states | `test_rootcause`, `test_v2_automation` | IMPLEMENTED (DATA-DEPENDENT) |
| Explainability & confidence (5) | Temperature-calibrated confidence + `raw_probability` + `calibration_status` + `decision_reason` + `review_reasons`; epistemic labels | `inference.py` confidence/decision payloads | Calibrated ring, review reasons, evidence drawer, decision chain | `test_v2_batch_review` calibration fields | IMPLEMENTED |
| Technical implementation (5) | Real local stack, no paid APIs, artifact persistence, technical drawer | FastAPI + TF + sklearn monolith | `View technical evidence` drawer | 248 backend + 46 frontend + 4 browser tests | IMPLEMENTED |
| UI/UX & visualization (5) | Industrial control room, stream-first, batch gallery, review queue, coverage map | — | `components/neurax/*` | Playwright + visual review | IMPLEMENTED |

## B. Problem-statement requirements

| Requirement | Backend | API | Frontend | Visualization | Evidence | Demo | Status |
|---|---|---|---|---|---|---|---|
| Defect detection / classification | `app/vision/training.py` (frozen MobileNetV2 + logistic head), `inference.py` | `POST /api/vision/inspect`, `POST /api/vision/inspect/stream`, `POST /api/vision/stream/next` | `InspectionStudio`, `AIInferencePipeline` | Animated class-probability bars, calibrated confidence ring | `MODEL OUTPUT` badge on every probability | Demo mode frame → classification | IMPLEMENTED |
| Defect localization | CAM in `inference.py` (`render_heatmap`) | `GET /api/vision/inspect/{id}/image`, trace metrics | `LocalizationCompare`, viewer overlays | Heatmap + region box + original/localization/overlay comparison | `MODEL-DERIVED` badge; ground truth shown `NOT AVAILABLE` | Inspection view overlay | IMPLEMENTED |
| Robustness to unseen conditions | Mahalanobis percentile + class-relative novelty (`training.py`, `inference.py`) | inspection result `anomaly_score` | `NoveltyGauge` | Known-distribution track with current-sample marker; KNOWN / UNUSUAL / NOVEL / REVIEW | `MODEL OUTPUT` + explicit "not a probability" note | Foreign image → REVIEW | IMPLEMENTED |
| False accept / false reject handling | Decision layer + measured test metrics (`training.py`) | `GET /api/vision/status` (`metrics`, `decision_matrix`) | `DecisionQuality` | FAR / FRR / review-rate tiles + threshold bar + 3×3 decision matrix | Measured on held-out split; `NOT AVAILABLE` if untrained | Command Center + Inspection | IMPLEMENTED |
| Explainability | Evidence statements recorded per inspection; stage trace | `GET /api/vision/inspect/{id}/trace` | `AIInferencePipeline`, `EvidenceDrawer`, `EvidenceGraph`, `DecisionTrace` | Interactive evidence graph; technical evidence behind a button | Epistemic labels everywhere (`OBSERVED`, `MODEL OUTPUT`, `MODEL-DERIVED`, `STATISTICAL ASSOCIATION`, `HYPOTHESIS`, `USER ASSUMPTION`, `SIMULATION`, `DATA GAP`) | Pipeline node → technical drawer | IMPLEMENTED |
| Confidence / uncertainty | Temperature scaling on validation logits | `calibration.json`, inspection `confidence` | `ConfidenceRing` | Calibrated percentage ring, separate from anomaly/novelty | `CALCULATED` badge; method + limitations shown | Inspection view | IMPLEMENTED |
| Root-cause analysis | `app/rootcause/` (correlation, MI, group, temporal, anomaly, model contribution, drift) | `POST /api/datasets/{id}/root-cause/analyze` | `ProcessIntelligence` → Root cause | Ranked signal bars + association graph (event → factors → hypothesis) | `STATISTICAL ASSOCIATION` / `HYPOTHESIS`; never causation | Stage 02 | IMPLEMENTED (DATA-DEPENDENT) |
| Process analysis | `app/pipeline/`, `app/flow/timeline.py` | `GET /api/datasets/{id}/process/timeline` | `ProcessTimeline` | Binned real series, drift markers, event rows | `OBSERVED`; order basis stated; no wall-clock claim | Stage 01 | IMPLEMENTED (DATA-DEPENDENT) |
| Bottleneck identification | `app/flow/scoring.py` (6 weighted components) | `POST /api/datasets/{id}/bottleneck/analyze` | `BottleneckVisualizer`, `RankedSignals` | Component bars, why-list, station ranking | `EVIDENCE-BASED HYPOTHESIS` badge | Stage 03 | IMPLEMENTED (DATA-DEPENDENT) |
| Flow analysis | `app/flow/graph.py` (sequence inference) | `GET /api/datasets/{id}/bottleneck/flow` | `PlantFlow` | Animated station flow with utilization/queue indicators and bottleneck highlight | Derived sequence; rationale shown | Stage 01/03 | IMPLEMENTED (DATA-DEPENDENT) |
| Economic / production impact | `app/economics/` (assumptions, baseline, cost blocks, break-even) | `/economics/assumptions`, `/baseline`, `/scenario` | `ImpactFlow`, `EconomicPanel` | Observed → assumptions → calculated chain with formulas | `USER ASSUMPTION` required; `NOT AVAILABLE` until supplied | Stage 04 | IMPLEMENTED (DATA-DEPENDENT) |
| What-if analysis | `app/economics/scenarios.py` (utilization reduction, throughput scaling, demand uplift) | `POST /api/datasets/{id}/economics/scenario` | `WhatIfSimulator` | Interactive sliders, baseline vs scenario vs delta | `SIMULATION` badge; assumption acknowledgement guard | Stage 04 | IMPLEMENTED (DATA-DEPENDENT) |
| Recommendations | `app/recommend/` deterministic rules + language safety | `POST /api/datasets/{id}/recommendations/generate` | `RecommendationPanel` | Advisory action cards with priority, evidence quality, source signals | `ADVISORY`; investigate/review/evaluate wording only | Stage 05 | IMPLEMENTED |
| AI automation | `app/vision/stream.py`, `app/investigations/` | `/api/vision/stream/*`, `/api/investigations/*` | `AutomationControl`, `ProductionStream`, `InvestigationReplay`, `useStreamLoop` | Live stream rail, investigation pipeline states, replay player | Stream labelled `SIMULATED PRODUCTION STREAM`; stages carry real statuses | Demo mode | IMPLEMENTED |
| Strong UI / UX and visualization | — | — | `components/neurax/*` design system | Control-room aesthetic, semantic colors, motion system | Every result carries provenance | All views | IMPLEMENTED |

## B. V2 transformation requirements

| Requirement | Implementation | Status |
|---|---|
| Automated stream primary, manual demoted | `InspectionStudio` mode switch: AUTO PRODUCTION STREAM / BATCH INSPECTION / MANUAL INSPECTION / CONNECT DATA SOURCE | IMPLEMENTED |
| Real images, deterministic order | `InspectionStream._build_sequence` (defect + 2 normal, rotating; no randomness) | IMPLEMENTED |
| Stream controls (start/pause/next/reset/speed) | `/api/vision/stream/*` + `AutomationControl` | IMPLEMENTED |
| Automatic investigation engine | `run_investigation` orchestrating existing engines; triggers on DEFECT/REVIEW when armed | IMPLEMENTED |
| Investigation state machine | Stages `RECEIVED → … → RECOMMENDATION` with `COMPLETE / REVIEW / DATA_GAP / AWAITING_INPUT / FAILED / PARTIAL` | IMPLEMENTED |
| No fake AI thinking | Observable outputs only; no chain-of-thought; epistemic labels on every stage | IMPLEMENTED |
| Visual AI pipeline | `AIInferencePipeline` (8 nodes, WAITING/PROCESSING/COMPLETE/REVIEW/NOT_AVAILABLE/FAILED) | IMPLEMENTED |
| Visual classification | `ProbabilityBars` from real calibrated outputs | IMPLEMENTED |
| Confidence only when legitimate | Temperature-scaled softmax; separate anomaly percentile and novelty score | IMPLEMENTED |
| PASS / DEFECT / REVIEW with reasons | Decision layer + `DecisionState` reason + review gate explanation | IMPLEMENTED |
| Localization comparison | `LocalizationCompare` (original / localization / overlay, intensity slider) | IMPLEMENTED |
| Feature-space visualization | PCA of real training embeddings stored at train time; live sample projected with the same components | IMPLEMENTED |
| Root-cause evidence graph | `EvidenceGraph` (event → factors → hypothesis) with click-through detail | IMPLEMENTED |
| Process correlation only when valid | Dataset-level `PARTIAL` context; per-unit join reported `NOT AVAILABLE` with reason | IMPLEMENTED |
| Process timeline | `ProcessTimeline` (real binned series, drift, event rows) | IMPLEMENTED |
| Bottleneck explanation | `BottleneckVisualizer` component bars + why list + missing metrics | IMPLEMENTED |
| Impact chain + honest assumptions | `ImpactFlow` + full assumption field set (margin, scrap, rework, downtime, operating, hours, demand, rates, intervention) | IMPLEMENTED |
| Evidence drawer | `EvidenceDrawer` from every result (WHY?, stage evidence, station/factor/recommendation) | IMPLEMENTED |
| Decision chain | `DecisionChain` (WHAT → WHERE → HOW CERTAIN → WHY → FLOW → IMPACT → WHAT NEXT) | IMPLEMENTED |
| Investigation replay | `InvestigationReplay` (play/pause/prev/next over stored stages) | IMPLEMENTED |
| Industrial event feed | `IndustrialEventFeed` (business events with timestamps and epistemic badges) | IMPLEMENTED |
| Developer console removed from primary UI | Raw metrics only inside the technical-evidence drawer; main UI uses plain language | IMPLEMENTED |
| Data coverage | `DataCoverage` (vision, process, join, timeline, root cause, flow, economics) | IMPLEMENTED |
| Demo mode using real functionality | `Start demo` = real stream + real auto-investigation + real replay; banner states this | IMPLEMENTED |
| No machine control claims | Recommendation engine wording (investigate/review/evaluate); disclaimers on every stage | ADVISORY |
| Zero fake data | Static-data guard test scans all sources for hardcoded results, station names, currency literals, `Math.random` | IMPLEMENTED |
| Responsive + accessibility | Desktop-first; mobile stacks into a vertical investigation; aria labels, focus states, reduced-motion support | IMPLEMENTED |
| Performance | Server-side aggregation (timeline bins, small payloads); browser never receives raw 600k-row frames | IMPLEMENTED |
| Tests | Backend 248 passed · Frontend 46 passed · Playwright 4 passed (real backend/model) | IMPLEMENTED |

## B2. V2.1 judging-criteria enhancements

| Requirement | Implementation | Status |
|---|---|
| Three input modes | AUTO PRODUCTION STREAM (primary) · MANUAL IMAGE INSPECTION (+ INSPECT IMAGE) · DATASET/BATCH INSPECTION (+ ADD INSPECTION DATA, ZIP/multi-file/drag-drop) | IMPLEMENTED |
| Dataset ingestion screen | `AddDataModal` (3 workflows) + `BatchPanel` drop zone | IMPLEMENTED |
| Automatic data check | `app/vision/batch.py` validation: format, readability, dimensions, duplicates (content hash), class structure, unsupported files — nothing silently dropped | IMPLEMENTED |
| Data health report | `ValidationReport`: valid/invalid/unsupported/duplicates, labels/class balance, localization annotations, process join availability | IMPLEMENTED |
| Automatic batch inspection | Background thread over the real pipeline, pollable per-image progress, real PASS/DEFECT/REVIEW counts | IMPLEMENTED |
| Individual result per input | Every image gets `inspection_id`, decision, confidence, raw probability, anomaly, novelty, localization, review status/reasons | IMPLEMENTED |
| Confidence for every input | `raw_probability` + `calibrated_probability` + `calibration_status` + `calibration_method` + `model_version` stored per inspection | IMPLEMENTED |
| Confidence is not decision | Decision policy considers calibrated confidence AND novelty AND anomaly gates; `decision_reason` + `review_reasons[]` returned and traceable | IMPLEMENTED |
| Human review gate | REVIEW decisions (low confidence / high novelty / high anomaly) never forced into PASS/DEFECT | IMPLEMENTED |
| Review decision engine | `decision_reason`, `review_required`, `review_reasons` on every result; policy thresholds stored in `thresholds.json` | IMPLEMENTED |
| Human review queue | `ReviewQueue` with pending items, image, reasons, and CONFIRM DEFECT / MARK PASS / ESCALATE actions | IMPLEMENTED |
| Human-in-the-loop model | `human_review` stored separately; AI decision fields preserved (`ai_decision_preserved`) | IMPLEMENTED |
| Review queue statistics | `review_stats`: auto-resolved rate, human-review rate, pending, distribution, avg confidence — all real | IMPLEMENTED |
| Batch decision quality | TP/TN/FP/FN + FAR/FRR + precision/recall/F1 measured against class-folder ground truth when labels exist | IMPLEMENTED (DATA-DEPENDENT) |
| Threshold / review band | PASS–REVIEW–DEFECT band rendered from validated thresholds with the trade-off explanation | IMPLEMENTED |
| Defect classification breakdown | Per-class counts from class folders; batch confusion metrics | IMPLEMENTED (DATA-DEPENDENT) |
| Robustness review trigger | NOVEL sample → REVIEW with explicit `review_reasons` (unseen-condition guard) | IMPLEMENTED |
| Explainability per prediction | WHAT / CONFIDENCE / WHY / WHERE / HOW NOVEL / WHY REVIEW / LIMITATIONS visible per result | IMPLEMENTED |
| Technical details secondary | Model version, calibration, thresholds, methods in `View technical evidence` drawer | IMPLEMENTED |
| Image gallery with confidence | `BatchGallery`: thumbnails, decision chips, confidence bars, novelty tags, review badges | IMPLEMENTED |
| Filtering | ALL / PASS / DEFECT / REVIEW / NOVEL / LOW CONFIDENCE + filename search | IMPLEMENTED |
| Review visual priority | Command Center banner `⚠ N inspections require human review` → review queue | IMPLEMENTED |
| Automation philosophy | `AutomationPrinciple`: AUTOMATE THE CERTAIN · ESCALATE THE UNCERTAIN | IMPLEMENTED |
| Evaluation coverage map | `EvaluationCoverage`: 8 criteria mapped to where their evidence lives (not a score) | IMPLEMENTED |
| Dashboard priority | Active event → human review → AI decision → investigation → process → impact hierarchy | IMPLEMENTED |
| Static-data audit | Guard test + manual grep: no `Math.random`, no hardcoded percentages/counts/currency | IMPLEMENTED |

## B3. V2.2 UX/semantics correction

| Requirement | Implementation | Status |
|---|---|
| Stage status model (COMPLETE / AVAILABLE / DATA_GAP / NOT_SUPPORTED / FAILED / REVIEW_REQUIRED / WAITING) | Investigation stages carry `status` + `result` (summary) + `reason` (detail) + `required_inputs` + `available_inputs` + `epistemic`; frontend maps to green/amber/red/grey | IMPLEMENTED |
| Capability vs data availability | `DataCoverage` shows `capability: READY` per engine AND the data state (READY / INPUT REQUIRED / DATA GAP / NOT SUPPORTED / FAILED) | IMPLEMENTED |
| No misleading "unavailable" | Data gaps render amber `INPUT REQUIRED` / `DATA GAP` with the required inputs listed — never grey "unavailable" for a valid capability | IMPLEMENTED |
| Actionable data coverage | `+ ADD PROCESS DATA`, `+ ADD ASSUMPTIONS`, `VIEW REQUIRED FIELDS` buttons on coverage rows | IMPLEMENTED |
| Investigation pipeline shows results | Command Center pipeline is a result timeline: per-stage result text, status word, color; every stage clickable → evidence drawer with inputs required/available | IMPLEMENTED |
| Investigation result summary | "N stage(s) completed · M require additional data" + a list of exactly what each blocked stage requires | IMPLEMENTED |
| Decision chain with real values | `DecisionChain` renders `result` (e.g., `NORMAL · PASS`, `61.2% CALIBRATED`), status, source per step — dynamic per inspection | IMPLEMENTED |
| Review queue opens actual images | `ReviewWorkspace`: left item list with real thumbnails; right panel with the actual image, localization badge, probabilities, confidence, anomaly, novelty, thresholds | IMPLEMENTED |
| Every review item explains why | `review_reasons[]` (human-readable: "novelty 0.995 exceeds the 0.99 review gate (unseen-condition guard)") + "the model should not make an automatic decision" | IMPLEMENTED |
| Human actions incl. class confirm and keep-in-review | CONFIRM DEFECT · CONFIRM <defect class> · MARK PASS · KEEP IN REVIEW · ESCALATE; `keep_in_review` keeps the item pending; class confirm records `class_name` | IMPLEMENTED |
| Human decision stored separately | `human_review` with `ai_decision_preserved`; AI fields never overwritten | IMPLEMENTED |
| Dynamic review counter | Banner count from `review_stats.pending_review`; refreshes after every action and stream frame; banner disappears at zero | IMPLEMENTED |
| Automation gate | `AutomationGate` near the decision: automatic decision / blocked → HUMAN REVIEW REQUIRED with confidence + novelty | IMPLEMENTED |
| Process join honesty | `IMAGE → PROCESS JOIN: DATA GAP` with required fields (unit/batch/station/timestamp); root cause stays `DATA GAP` until a valid join exists | IMPLEMENTED |
| No fabricated downstream results | Stages report `INPUT REQUIRED` / `DATA GAP` with `required_inputs`; nothing is computed without its inputs | IMPLEMENTED |
| Tests | Backend 250 · Frontend 48 · Playwright 5 (incl. full review workflow with real images) | IMPLEMENTED |

## C. Honest limitations (shown in the product, not hidden)

| Limitation | Where it is shown |
|---|---|
| No per-image batch/station/unit metadata → no per-unit process join | `DataCoverage`, `Evidence` panel, investigation `PROCESS_CORRELATION` stage |
| Localization is model-derived (CAM); no ground-truth annotations exist | Localization footer, evidence graph node, `MODEL-DERIVED` badges |
| The image dataset is cleanly separable (100% test accuracy) | Command Center performance panel reports the measured value as-is |
| Economic values require user assumptions | `ImpactFlow`, investigation `IMPACT` stage (`AWAITING_INPUT`) |
| Bottleneck identification is a hypothesis, not proof | `BottleneckVisualizer`, stage epistemic label |
| Stream is simulated (real dataset frames, not a live camera) | Stream header label `SIMULATED PRODUCTION STREAM` everywhere |
| Model_3 (605k rows) is slow to process | README known-limitations section |
