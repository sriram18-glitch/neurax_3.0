# NeuraX — Judge Demo Script (3–4 minutes, automation-first)

**Setup:** run `.\start_demo.ps1`, wait for `WORKSTATION: http://localhost:4173`, open it.
Keep a foreign image (e.g., a cat photo) on the desktop for the robustness moment.

**The story in one sentence:** NEURAX automatically turns production inspection events into an
evidence-backed industrial investigation — detection is only the first step.

---

## 0:00 — Start automation

- The app opens on **COMMAND CENTER**. Point out the command bar: **Backend ONLINE**,
  **Vision model READY · 5 classes**.
- Press **START DEMO** (top right) — or **START AUTOMATED INSPECTION** in the automation strip.
- Say: *"This starts a simulated production stream over the real image dataset — real frames,
  deterministic order, no randomness. Every frame runs the real trained pipeline."*

## 0:15 — The first inspection event

- Watch the **Production Stream** panel: frame counter advances, PASS/DEFECT/REVIEW counters move,
  recent frames list fills with real filenames.
- The **Active Event** panel shows the current image, decision, class and calibrated confidence.
- Say: *"No upload step. The system observes the line and decides by itself."*

## 0:30 — The AI investigation pipeline

- The **AI investigation pipeline** chips light up: inspection → classification → localization →
  robustness → process link → root cause → bottleneck → impact → what-if → action.
- Say: *"On an actionable decision the investigation chain runs automatically — the operator does
  not open eight pages."*

## 0:40 — Add data: the three input workflows

- Press **+ ADD INSPECTION DATA** (top bar). The modal shows the three workflows:
  **INSPECT IMAGE**, **ADD BATCH / DATASET**, **AUTO PRODUCTION STREAM**.
- Choose **ADD BATCH / DATASET** and drop several real images.
- The **data-health report** appears immediately: valid / invalid / unsupported / duplicates,
  labels available from class folders, localization annotations and process join honestly
  reported as NOT AVAILABLE.
- Press **START AUTO CHECK** — every image runs through the real pipeline with live progress.

## 1:00 — Batch results, gallery and measured quality

- The **dataset inspection complete** dashboard shows real PASS / DEFECT / REVIEW counts, average
  confidence, and **decision quality measured against the class-folder ground truth**: TP / TN /
  FP / FN, false accept, false reject, precision, recall, F1.
- Walk the **inspection gallery** — every card has its image, result, confidence bar and novelty
  tag; use the ALL / PASS / DEFECT / REVIEW / NOVEL / LOW CONFIDENCE filters and filename search.
- Click a card to open the full inspection view.

## 1:15 — Human review queue

- Return to the **COMMAND CENTER**. If any sample was uncertain, the banner reads
  **⚠ N INSPECTIONS REQUIRE HUMAN REVIEW**.
- The **AI investigation pipeline** is a result timeline: each stage shows its real result and
  status — COMPLETE (green), DATA GAP / INPUT REQUIRED (amber) with the exact inputs needed,
  FAILED (red). The **data coverage** grid shows *capability: READY* for every engine and marks
  the *data* state (INPUT REQUIRED / DATA GAP) with actions like + ADD PROCESS DATA.
- Click **Review queue** → the **human review workspace**: the actual review images, the AI
  decision with confidence, novelty, anomaly, thresholds and explicit reasons — then decide:
  **CONFIRM DEFECT**, **CONFIRM SCRATCH/…**, **MARK PASS**, **KEEP IN REVIEW** or **ESCALATE**.
- Say: *"Automate the certain, escalate the uncertain. The AI decision and its evidence are
  preserved next to the human decision — nothing is overwritten."*

## 1:30 — The visual AI pipeline and evidence (Inspection view)

- Click **INSPECTION**. Scroll to **FEATURE SPACE**: the real training embeddings (2-D PCA) with
  the current sample projected into the same space.
- Click a pipeline node (e.g., **Classify**) → plain-language output → **View technical evidence**
  → the drawer with the raw metrics.
- Optional: switch to **MANUAL INSPECTION** and drop the foreign photo → **REVIEW** with the
  unknown-condition reason.
- Say: *"The main screen shows meaning; the raw engineering values live behind this button.
  No private chain-of-thought is exposed — only observable outputs."*

## 1:45 — The investigation and replay

- Click **INVESTIGATION HISTORY**. The stored investigation is listed with its stage summary.
- Press **PLAY INVESTIGATION** and step through the stages; point at the **DATA GAP** stages.
- Say: *"Honest gaps: without a process dataset the correlation stages report DATA GAP with the
  reason — they do not invent a relationship."*

## 2:00 — Root cause

- Click **PROCESS INTELLIGENCE**; select a processed dataset (`Model_1.csv`) in the top bar.
- Stage **02 ROOT CAUSE**: run it, then walk the **Factor associations** ranking and the
  **association graph** (event → factors → leading hypothesis).
- Say: *"Statistical association, never causation."*

## 2:15 — Bottleneck and flow

- Stage **03 FLOW**: the process map with the candidate constraint highlighted, the
  **Bottleneck evidence** component bars and the observed constrained-vs-unconstrained comparison.
- Say: *"A bottleneck is an evidence-based hypothesis with named supporting signals — not a claim."*

## 2:30 — Impact

- Stage **04 IMPACT**: the **Impact flow** chain — observed throughput → units/day → daily →
  monthly contribution, each step a stored value with its formula and epistemic badge.
- Without assumptions everything reads **NOT AVAILABLE**; supply margin/hours and press
  **Recompute baseline**.
- Say: *"We never invent economics. Under supplied assumptions the numbers are CALCULATED."*

## 2:40 — What-if

- Run a **utilization reduction** scenario. Point at BASELINE → SCENARIO → DELTA and the
  **SIMULATION** badge.
- Say: *"Assumption-based simulation, labelled as such — not a forecast."*

## 2:50 — Recommendation

- Stage **05 ACTION**: advisory cards with priority, evidence quality, why-text and source signals.
- Say: *"Deterministic rules over the stored evidence — investigate, review, evaluate. NEURAX is
  advisory; it never touches the machine."*

## 3:00 — Close

- Return to **COMMAND CENTER**; point at the review statistics, the event feed, the automation
  principle (**automate the certain, escalate the uncertain**) and the **evaluation coverage** map.
- Say: *"Detect, explain, correlate, investigate, constrain, simulate, recommend — from detection
  to decision. Every claim is traceable to a model output, the data, or an explicit assumption."*

---

## Recovery / troubleshooting

| Symptom | Recovery |
|---|---|
| Backend offline banner | Start `start_demo.ps1`, click Refresh |
| Vision model NOT TRAINED | Inspection → **Train vision model** (≈2–3 min CPU) |
| Stream paused / exhausted | Press **Restart stream** (or Reset, then Start) |
| No investigation appears | Auto investigation is off, or the decisions so far were PASS — keep the stream running until a DEFECT/REVIEW |
| Process stages show DATA GAP | Select a processed dataset in the top bar |
| Economics NOT AVAILABLE | Supply assumptions in stage 04 IMPACT |
| Batch shows no labels | Add images with class-folder names (`normal/…`, `scratch/…`) so ground truth is measured |