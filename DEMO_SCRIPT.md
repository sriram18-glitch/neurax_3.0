# NeuraX — Judge Demo Script (3–5 minutes, inspection-first)

**Setup before judging:** run `.\start_demo.ps1` from the project root, wait for
`CONTROL ROOM: http://localhost:4173`, open it. Keep a defect image and a normal image from
`train\train\scratch\` and `train\train\normal\` on the desktop for quick dragging.

**Demo images (real dataset):** `train\train\scratch\scratch_00000.png` (defect),
`train\train\normal\normal_00000.png` (normal). Any cat photo works for the novelty moment.

---

## 00:00–00:20 — Open the workstation

- The app opens on **INSPECT**. Point out the command bar: **Backend ONLINE**, **Vision model READY
  · 5 classes**.
- Say: *"This is an industrial inspection workstation. The image is processed by a real pipeline —
  a pretrained backbone, a calibrated classifier, an anomaly model and a localization stage — and
  every decision is traceable. No mock data anywhere."*

## 00:20–01:00 — Inspect a defective part (live animated pipeline)

- Drag `scratch_00000.png` into the theater.
- **The inspection plays like a video**: a scanline sweeps the part while the backend works; stages light
  up one by one in the **Live pipeline** rail (validation → preprocessing → feature extraction →
  classification → anomaly analysis → localization → confidence → decision), each with its real
  duration and output.
- The **preprocessed 224×224 tensor flips in**, the **anomaly heatmap fades over the image**, the
  **region box draws itself**, and the **DEFECT stamp slams in** — all driven by real backend events.
- The three live panels below fill as the stages complete: animated class-probability bars, the
  anomaly gauge sweeping to its real percentile, and the decision card with calibrated confidence.
- Say: *"This is a live event stream from the backend — not a replay. Each stage appears the moment
  it actually completes. Cinematic pacing only slows the display so you can read it; the toggle
  switches to raw backend speed."*

## 01:00–01:40 — The AI Console (show the real processing)

- Switch to **CONSOLE**.
- Walk down the ten stages with their real metrics: image dimensions, resize, backbone name,
  embedding size, predicted class and probabilities, Mahalanobis distance, CAM method, confidence
  level, decision thresholds.
- Say: *"This is the observable engineering pipeline — every value was produced by the backend
  during this inspection. It is not the model's private reasoning; it's what we can measure."*

## 01:40–02:20 — Unseen-condition honesty (the differentiator)

- Back in **INSPECT**, drag a foreign image (e.g., a photo that is clearly not a part).
- Result: **REVIEW** with **novelty HIGH** and the reason: *"the sample does not resemble the known
  class it was assigned to; not forced into a known defect class."*
- Say: *"This is robustness to unseen conditions: the system refuses to invent a defect label for
  something it has never seen. That is exactly what a factory inspection station must do."*
- Then drag `normal_00000.png` → **PASS**.

## 02:20–03:00 — Decision chain

- Switch to **DECISION**.
- Walk the chain: **WHAT** (class + probabilities), **WHERE** (region coordinates, model-derived),
  **HOW CERTAIN** (confidence, anomaly, novelty, calibration), **WHY** (evidence with epistemic
  labels), **WHAT NEXT** (process context).
- Show the **thresholds panel**: pass/defect confidence gates and the **measured** false-accept,
  false-reject and review rates on the held-out test split.
- Say: *"Operators can see exactly why the threshold produced this decision — and what it costs in
  false accepts versus manual review."*

## 03:00–04:00 — Process context and the wider chain

- Switch to **CONTROL ROOM**. Select a previously processed dataset (e.g., `Model_1.csv`) from the
  process dataset dropdown.
- Show the **process flow** with the candidate constraint, the observed throughput, and the top
  advisory action.
- Open **Station constraint ranking** and click **WHY THIS STATION?** → evidence drawer with the real
  utilization, queue, score formula and epistemic labels.
- Say: *"Inspection is the entry point; the same evidence discipline extends to the production line —
  bottleneck, root cause and recommendations."*

## 04:00–04:40 — Economics and what-if (optional if time)

- Open **Economics & assumptions**: the datasets have no cost columns, so everything reads
  `NOT AVAILABLE` until assumptions are supplied. Enter margin/hours → baseline becomes
  **CALCULATED**.
- Open **What-if simulator** → run **Throughput change (user assumption)** → BASELINE vs SIMULATED
  with the explicit acknowledgement guard.
- Say: *"We never invent economics. Under supplied assumptions, the simulation indicates a change —
  labeled SIMULATED, not a forecast."*

## 04:40–05:00 — Closing

- Return to **INSPECT**.
- Say: *"One workstation: a real image pipeline with calibrated confidence and honest novelty
  handling, connected to a real process analytics chain — root cause, bottleneck, economics and
  advisory recommendations. Every claim is traceable to data or an explicit assumption, and
  anything we cannot support is reported as NOT AVAILABLE instead of being fabricated."*

---

## Recovery / troubleshooting

| Symptom | Recovery |
|---|---|
| Backend offline banner | Start the backend (`start_demo.ps1`), click Refresh |
| Vision model NOT TRAINED | Click **Train vision model** (≈2–3 min on CPU) |
| Wrong image / want to re-run | Click **New image** and drop another file |
| Process dataset not selected | Command bar → process dataset dropdown → pick a processed dataset |
| Economics NOT AVAILABLE | Supply the assumptions listed in the panel |
| Slow first inspection | The first inference warms the backbone (~1–2 s); later images run in ~0.3 s |
