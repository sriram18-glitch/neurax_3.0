import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import App from "../App";

/**
 * V2 integration tests with a mocked backend:
 * 01 Command Center (automation-first), 02 Inspection (stream + evidence),
 * 03 Process Intelligence, 04 Investigation History.
 * Mocked values are deliberately unique (zx-prefixed) so rendering them proves
 * the UI consumes the API layer rather than hardcoded results.
 */

const STATION = "ZX-9";
const THROUGHPUT = 777.5;
const CLASS_NAME = "zxscratch";
const CONFIDENCE = 0.93;
const DECISION = "DEFECT";

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

const contract = {
  dataset_id: "testds000001",
  filename: "mock_process.csv",
  format: "text",
  size_bytes: 1024,
  sha256: "0".repeat(64),
  status: "analyzed",
  ingested_at: "2026-01-01T00:00:00Z",
  summary: { tables: 1, total_rows: 300, primary_table: "mock_process", primary_rows: 300, primary_columns: 8, stations: [STATION], station_metrics: {} },
  capabilities: {},
  vision: { status: "NOT_SUPPORTED", available: false, images_found: 0, supported_capabilities: [], reason: "No visual inspection/image training data is available." },
  provenance: { data_origin: "uploaded_dataset", labels: ["REAL DATA"], note: "" },
  tables: [],
  warnings: [],
  skipped_files: [],
};

const analysis = {
  dataset_id: contract.dataset_id,
  filename: contract.filename,
  status: "complete",
  error: null,
  generated_at: "2026-01-01T00:00:00Z",
  processing: { seed: 42, configuration: {}, versions: {} },
  stages: [],
  total_duration_s: 1,
  coverage: { dataset_id: contract.dataset_id, modules: {}, summary: { supported: 0, partially_supported: 0, requires_unsupported: 0, not_supported: 0 }, legend: {} },
  tables: [],
  cleaning: { dataset_id: contract.dataset_id, tables: [] },
  features: { derived_features: [], skipped_candidates: [] },
  model_inputs: [],
  rejected_model_inputs: [],
  splits: { model_input_splits: [], table_splits: [] },
  station_metrics: { tables: [] },
};

const ml = {
  dataset_id: contract.dataset_id,
  status: "complete",
  models: [],
  skipped_inputs: [],
  vision: { status: "NOT_SUPPORTED", reason: "No visual inspection/image training data is available." },
};

const bottleneck = {
  dataset_id: contract.dataset_id,
  analysis_id: "bnmock000001",
  status: "complete",
  generated_at: "2026-01-01T00:00:00Z",
  engine_version: "1.0.0",
  stations_analyzed: 1,
  station_rankings: [
    {
      station: STATION,
      rank: 1,
      status: "CANDIDATE_BOTTLENECK",
      evidence_score: 88.25,
      score_status: "SCORED",
      score_components: { utilization_pressure: 1.0, queue_pressure: null, cycle_time_pressure: null, throughput_constraint: null, root_cause_evidence: null, anomaly_evidence: null },
      score_weights: null,
      score_formula: "100 * sum(weight_i * component_i) / sum(weight_i over available components)",
      available_components: 2,
      consistency: 1.0,
      evidence_quality: { label: "MODERATE_EVIDENCE", reason: "2 components available" },
      utilization: { available: true, mean: 0.812, max: 0.99, samples: 300 },
      queue: { available: false, reason: "NOT AVAILABLE FROM DATASET" },
      cycle_time: { available: false, reason: "NOT AVAILABLE FROM DATASET" },
      throughput: { available: false, reason: "NOT AVAILABLE FROM DATASET" },
      capacity: { available: false, reason: "NOT AVAILABLE FROM DATASET" },
      anomaly_evidence: { available: false, rates: {}, note: "" },
      drift_evidence: [],
      root_cause_evidence: null,
      unavailable_metrics: ["queue", "cycle_time", "throughput", "capacity"],
      impact: null,
      assumptions: [],
      limitations: ["Bottleneck identification is an evidence-based hypothesis, not a proven constraint."],
      epistemic_status: "EVIDENCE-BASED HYPOTHESIS (not proven causation)",
    },
  ],
  candidate_bottleneck: {
    station: STATION,
    evidence_score: 88.25,
    evidence_quality: { label: "MODERATE_EVIDENCE", reason: "2 components available" },
    status: "CANDIDATE_BOTTLENECK",
    why: ["utilization_pressure: 1.0"],
    unavailable_metrics: ["queue"],
  },
  flow: {
    graph: { status: "SUPPORTED", nodes: [{ station: STATION, position: 0, metrics: {} }], edges: [] },
    blocking_starvation: {},
  },
  what_if_inputs: {
    station: STATION,
    current_utilization: { available: true, mean: 0.812, samples: 300 },
    current_queue: { available: false, reason: "NOT AVAILABLE FROM DATASET" },
    current_cycle_time: { available: false, reason: "NOT AVAILABLE FROM DATASET" },
    observed_impact: {
      status: "OBSERVED_COMPARISON",
      observed: {
        "Output rate": { output_column: "Output rate", constrained_mean: 700, unconstrained_mean: THROUGHPUT, difference: -77.5, relative_difference: -0.1, constrained_rows: 75, unconstrained_rows: 225, constrained_definition: "ZX_Util >= 0.95" },
      },
      note: "Observed comparison only.",
      limitations: [],
    },
    potential_interventions: [],
    expected_effect: "NOT YET SIMULATED",
    note: "no economic values",
  },
  epistemic_summary: { causal_claim: "NOT SUPPORTED: no interventional methodology was applied." },
  limitations: [],
  total_duration_s: 0.1,
};

const inspection = {
  inspection_id: "zxinspect001",
  filename: "zxpart.png",
  generated_at: "2026-01-01T00:00:00Z",
  image_metadata: { width: 256, height: 256, mode: "L", format: "PNG", bytes: 20000 },
  preprocessing: { resize: "224x224", normalization: "mobilenet_v2.preprocess_input", preprocessed_png_base64: "aGVsbG8=" },
  prediction: { predicted_class: CLASS_NAME, is_normal: false },
  feature_vector: { dim: 1280, values: [0.11, -0.42, 0.83, 0.02, -0.19, 0.5, -0.7, 0.31] },
  class_distances: { [CLASS_NAME]: 1.24, normal: 3.41 },
  feature_space_point: [1.5, -0.5],
  class_probabilities: { [CLASS_NAME]: CONFIDENCE, normal: 0.05, other: 0.02 },
  confidence: { value: CONFIDENCE, level: "HIGH", method: "temperature scaled", limitations: "Confidence reflects model uncertainty, not physical certainty." },
  anomaly_score: { value: 1.0, novelty_score: 0.21, novelty_status: "NORMAL", method: "Mahalanobis percentile", note: "not a probability" },
  localization: {
    type: "MODEL-DERIVED LOCALIZATION",
    method: "class-activation mapping",
    ground_truth: false,
    bounding_box: { x: 10, y: 20, width: 100, height: 80, coordinates: "original image pixels", type: "MODEL-DERIVED" },
    heatmap_png_base64: "aGVsbG8=",
    note: "Model attention map - not a ground-truth defect boundary.",
  },
  decision: DECISION,
  review_reason: null,
  evidence: [{ statement: `Calibrated probability for '${CLASS_NAME}' is 93.00%.`, source: "classification", epistemic_status: "MODEL_OUTPUT" }],
  process_link: { status: "NOT_AVAILABLE", reason: "PROCESS LINK NOT AVAILABLE: no per-image metadata.", available_metadata: [] },
  model: { backbone: "mobilenet_v2", trained_at: "2026-01-01T00:00:00Z", classes: [CLASS_NAME, "normal"] },
  limitations: ["Decision support only - not an automated accept/reject control."],
  trace: [
    { id: "image_received", status: "complete", started_at: "2026-01-01T00:00:00Z", duration_ms: 1.2, summary: "Image received.", metrics: { bytes: 20000 } },
    { id: "validation", status: "complete", started_at: "2026-01-01T00:00:00Z", duration_ms: 4.5, summary: "Valid PNG image 256x256.", metrics: { width: 256, height: 256 } },
    { id: "preprocessing", status: "complete", started_at: "2026-01-01T00:00:00Z", duration_ms: 3.1, summary: "Resizing.", metrics: { resize: "224x224" } },
    { id: "feature_extraction", status: "complete", started_at: "2026-01-01T00:00:00Z", duration_ms: 150, summary: "Backbone.", metrics: { embedding_dim: 1280 } },
    { id: "classification", status: "complete", started_at: "2026-01-01T00:00:00Z", duration_ms: 2, summary: "Scoring.", metrics: { predicted_class: CLASS_NAME, calibrated_probability: CONFIDENCE } },
    { id: "anomaly_analysis", status: "complete", started_at: "2026-01-01T00:00:00Z", duration_ms: 2, summary: "Comparing.", metrics: { anomaly_score: 1.0, novelty_score: 0.21, novelty_status: "NORMAL" } },
    { id: "localization", status: "complete", started_at: "2026-01-01T00:00:00Z", duration_ms: 5, summary: "CAM.", metrics: { method: "class-activation mapping" } },
    { id: "confidence", status: "complete", started_at: "2026-01-01T00:00:00Z", duration_ms: 1, summary: "Summarizing.", metrics: { confidence_level: "HIGH", calibrated_probability: CONFIDENCE } },
    { id: "decision", status: "complete", started_at: "2026-01-01T00:00:00Z", duration_ms: 1, summary: "Thresholds.", metrics: { decision: DECISION } },
    { id: "process_link", status: "not_supported", started_at: "2026-01-01T00:00:00Z", duration_ms: 0.5, summary: "No metadata.", metrics: { status: "NOT_AVAILABLE" } },
  ],
};

const streamSummary = {
  inspection_id: inspection.inspection_id,
  filename: inspection.filename,
  class_folder: CLASS_NAME,
  decision: DECISION,
  predicted_class: CLASS_NAME,
  confidence: CONFIDENCE,
  novelty_status: "NORMAL",
  at: "2026-01-01T00:00:01Z",
};

const streamStatus = {
  label: "SIMULATED PRODUCTION STREAM",
  note: "Frames are served from the real image dataset in a deterministic order.",
  station_id: "Camera 01",
  dataset_available: true,
  dataset_error: null,
  running: false,
  speed: 1,
  speeds: [0.5, 1, 2, 5],
  cursor: 0,
  frame_number: 0,
  total_frames: 9600,
  processed: 0,
  remaining: 9600,
  session_started_at: null,
  next_frame: { class_folder: CLASS_NAME, filename: "zxpart.png" },
  class_plan: { order: "one defect frame, then two normal frames, rotating defect classes", counts: {}, normal_class: "normal", total_frames: 9600 },
  last_summary: null,
  history: [],
  decision_counts: {},
};

const investigationStages = [
  { id: "received", label: "Inspection received", status: "COMPLETE", summary: "256x256 PNG", detail: null, epistemic: "OBSERVED", payload: null, duration_ms: 0.1 },
  { id: "classifying", label: "Classification", status: "COMPLETE", summary: `${CLASS_NAME} · calibrated probability 93.0%`, detail: "temperature scaled", epistemic: "MODEL OUTPUT", payload: { predicted_class: CLASS_NAME, confidence: CONFIDENCE }, duration_ms: 2 },
  { id: "localizing", label: "Localization", status: "COMPLETE", summary: "attention region derived", detail: null, epistemic: "MODEL-DERIVED", payload: null, duration_ms: 5 },
  { id: "checking_robustness", label: "Robustness check", status: "COMPLETE", summary: "anomaly percentile 1.000 · novelty 0.210 (NORMAL)", detail: null, epistemic: "MODEL OUTPUT", payload: null, duration_ms: 1 },
  { id: "process_correlation", label: "Process correlation", status: "DATA_GAP", summary: "No process dataset selected", detail: "Select a processed dataset to attach dataset-level process context.", epistemic: "DATA GAP", payload: null, duration_ms: 0.1 },
  { id: "root_cause", label: "Root-cause hypotheses", status: "DATA_GAP", summary: "No process dataset selected", detail: null, epistemic: "DATA GAP", payload: null, duration_ms: 0.1 },
  { id: "bottleneck", label: "Bottleneck / flow", status: "DATA_GAP", summary: "No process dataset selected", detail: null, epistemic: "DATA GAP", payload: null, duration_ms: 0.1 },
  { id: "impact", label: "Production impact", status: "DATA_GAP", summary: "No process dataset selected", detail: null, epistemic: "DATA GAP", payload: null, duration_ms: 0.1 },
  { id: "what_if", label: "What-if scenario", status: "DATA_GAP", summary: "No process dataset selected", detail: null, epistemic: "DATA GAP", payload: null, duration_ms: 0.1 },
  { id: "recommendation", label: "Advisory actions", status: "DATA_GAP", summary: "No process dataset selected", detail: null, epistemic: "DATA GAP", payload: null, duration_ms: 0.1 },
];

const investigationRecord = {
  investigation_id: "zxinv000001",
  inspection_id: inspection.inspection_id,
  dataset_id: null,
  station_id: "Camera 01",
  generated_at: "2026-01-01T00:00:02Z",
  status: "DATA_GAP",
  decision: DECISION,
  predicted_class: CLASS_NAME,
  confidence: CONFIDENCE,
  anomaly_score: 1.0,
  novelty_status: "NORMAL",
  review_reason: null,
  filename: inspection.filename,
  stages: investigationStages,
  stage_summary: { complete: 4, data_gap: 6, awaiting_input: 0, failed: 0, partial: 0 },
  total_duration_s: 0.42,
  limitations: ["Investigation stages reuse stored analyses; association is never presented as causation."],
  events: [
    { at: "2026-01-01T00:00:02Z", type: "inspection_completed", message: `Inspection completed — ${CLASS_NAME} (${DECISION})`, epistemic: "OBSERVED", investigation_id: "zxinv000001", inspection_id: inspection.inspection_id },
    { at: "2026-01-01T00:00:02Z", type: "investigation_triggered", message: "Automatic investigation triggered", epistemic: "OBSERVED", investigation_id: "zxinv000001", inspection_id: inspection.inspection_id },
  ],
};

const investigationSummary = {
  investigation_id: investigationRecord.investigation_id,
  inspection_id: inspection.inspection_id,
  dataset_id: null,
  generated_at: investigationRecord.generated_at,
  status: investigationRecord.status,
  decision: DECISION,
  predicted_class: CLASS_NAME,
  confidence: CONFIDENCE,
  filename: inspection.filename,
  stage_summary: investigationRecord.stage_summary,
  top_action: null,
};

function routeFetch(url: string): Response {
  if (url.endsWith("/api/health")) return jsonResponse({ status: "ok", service: "neurax-api", models_initialized: false });
  if (url.endsWith("/api/vision/status"))
    return jsonResponse({
      status: "READY",
      model_available: true,
      classes: [CLASS_NAME, "normal"],
      normal_class: "normal",
      metrics: {
        accuracy: 0.99,
        f1_weighted: 0.99,
        val_accuracy: 0.99,
        false_accept_rate: 0,
        false_reject_rate: 0,
        review_rate: 0.02,
        decisions: { PASS: 9, DEFECT: 40, REVIEW: 1 },
        decision_matrix: [
          { actual: "PASS (normal)", counts: { PASS: 9, DEFECT: 0, REVIEW: 1 } },
          { actual: "DEFECT (defective)", counts: { PASS: 0, DEFECT: 40, REVIEW: 0 } },
        ],
        decision_matrix_columns: ["PASS", "DEFECT", "REVIEW"],
        per_class: {},
        confusion_matrix: [],
      },
      thresholds: { pass_confidence: 0.8, defect_confidence: 0.7, anomaly_review_percentile: 0.99 },
      temperature: 0.1353,
      metadata: { backbone: { name: "mobilenet_v2", pretrained: "imagenet", frozen: true, embedding_dim: 1280 }, calibration: "temperature scaling" },
      dataset_available: true,
    });
  if (url.endsWith("/api/vision/feature-space"))
    return jsonResponse({
      status: "AVAILABLE",
      method: "PCA via SVD over standardized training embeddings (real data only)",
      components: 2,
      explained_variance_ratio: [0.4, 0.2],
      sampling: "deterministic evenly-spaced subsample, up to 90 points per class",
      clouds: { [CLASS_NAME]: [[1, 2], [1.5, 1.5]], normal: [[-1, -2], [-2, -1]] },
      counts: { [CLASS_NAME]: 400, normal: 434 },
    });
  if (url.includes("/api/vision/stream/status")) return jsonResponse(streamStatus);
  if (url.includes("/api/vision/stream/start") || url.includes("/api/vision/stream/resume"))
    return jsonResponse({ ...streamStatus, running: true });
  if (url.includes("/api/vision/stream/pause")) return jsonResponse(streamStatus);
  if (url.includes("/api/vision/stream/reset")) return jsonResponse(streamStatus);
  if (url.includes("/api/vision/stream/speed")) return jsonResponse({ ...streamStatus, speed: 2 });
  if (url.includes("/api/vision/stream/next"))
    return jsonResponse({
      inspection,
      exhausted: false,
      status: { ...streamStatus, frame_number: 1, processed: 1, history: [streamSummary], last_summary: streamSummary, decision_counts: { [DECISION]: 1 } },
    });
  if (url.includes("/api/vision/inspect/stream")) {
    const lines =
      inspection.trace.map((stage) => JSON.stringify({ event: "stage", stage })).join("\n") +
      "\n" +
      JSON.stringify({ event: "result", result: inspection }) +
      "\n";
    const stream = new ReadableStream({
      start(controller) {
        controller.enqueue(new TextEncoder().encode(lines));
        controller.close();
      },
    });
    return new Response(stream, { status: 200, headers: { "Content-Type": "application/x-ndjson" } });
  }
  if (url.includes("/api/vision/inspect")) return jsonResponse(inspection);
  if (url.endsWith("/api/vision/history")) return jsonResponse({ inspections: [], count: 0 });
  if (url.includes("/api/investigations/run")) return jsonResponse(investigationRecord);
  if (/\/api\/investigations\/[a-z0-9]+$/.test(url)) return jsonResponse(investigationRecord);
  if (url.includes("/api/investigations")) return jsonResponse({ investigations: [investigationSummary], count: 1, note: "" });
  if (url.includes("/api/datasets/testds000001/process/timeline"))
    return jsonResponse({
      dataset_id: contract.dataset_id,
      status: "AVAILABLE",
      table: "mock_process",
      bins: 8,
      order_basis: "recorded row order of the processed dataset (sequence position, not wall-clock time)",
      series: [{ station: STATION, metric: "utilization", unit: "ratio", column: "ZX-9 Utilization", values: [0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9] }],
      drift_markers: [{ column: "ZX-9 Utilization", bin: 5, direction: "up", peak_ewma_z: 3.1, epistemic: "STATISTICAL ASSOCIATION" }],
      event_markers: [{ bin: 6, label: "event" }],
      event_definition: null,
      note: "Series are server-side aggregates of the real processed data.",
      limitations: [],
    });
  if (url.endsWith("/api/datasets"))
    return jsonResponse({ datasets: [{ dataset_id: contract.dataset_id, filename: contract.filename, status: "complete", ingested_at: null, rows: 300 }] });
  if (url.endsWith("/analysis")) return jsonResponse(analysis);
  if (url.endsWith("/models")) return jsonResponse(ml);
  if (url.includes("/root-cause/targets")) return jsonResponse({ dataset_id: contract.dataset_id, targets: [], count: 0 });
  if (url.includes("/bottleneck/findings")) return jsonResponse({ dataset_id: contract.dataset_id, analyses: [{ analysis_id: bottleneck.analysis_id }], count: 1 });
  if (url.includes("/bottleneck/")) return jsonResponse(bottleneck);
  if (url.endsWith("/economics/assumptions"))
    return jsonResponse({ dataset_id: contract.dataset_id, currency: { value: null, source: "NOT_PROVIDED" }, assumptions: {}, updated_at: null, note: "" });
  if (url.endsWith("/recommendations")) return jsonResponse({ dataset_id: contract.dataset_id, recommendations: [], count: 0, decision_summary: null });
  if (url.match(/\/api\/datasets\/[a-z0-9]+$/)) return jsonResponse(contract);
  return jsonResponse({}, 404);
}

beforeEach(() => {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL) => routeFetch(String(input))),
  );
});

afterEach(() => {
  vi.unstubAllGlobals();
});

async function inspectImage() {
  const user = userEvent.setup();
  render(<App />);
  await user.click(await screen.findByRole("button", { name: /^Inspection$/ }));
  await user.click(await screen.findByRole("button", { name: /manual inspection/i }));
  // raw speed for tests (cinematic pacing is display-only)
  await user.click(screen.getByRole("button", { name: /cinematic/i }));
  const input = document.querySelector('input[type="file"]') as HTMLInputElement;
  await user.upload(input, new File(["fake"], "zxpart.png", { type: "image/png" }));
  await screen.findAllByText(DECISION);
  await screen.findAllByText(/93\.0%/);
  return user;
}

async function loadProcessDataset() {
  const user = userEvent.setup();
  render(<App />);
  await user.click(await screen.findByRole("button", { name: /no process dataset/i }));
  await user.click(await screen.findByText(contract.filename));
  await user.click(screen.getByRole("button", { name: "Process Intelligence" }));
  await screen.findByText(/current constraint/i);
  return user;
}

describe("command center (01)", () => {
  it("is automation-first: stream controls, coverage and the difference strip", async () => {
    render(<App />);
    expect(await screen.findByRole("button", { name: /start automated inspection/i })).toBeInTheDocument();
    expect(screen.getByText("SIMULATED PRODUCTION STREAM")).toBeInTheDocument();
    expect(screen.getByText(/data coverage/i)).toBeInTheDocument();
    expect(screen.getByText(/from detection to decision/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /start demo/i })).toBeInTheDocument();
  });

  it("shows honest data coverage including the missing image→process join", async () => {
    render(<App />);
    expect(await screen.findByText(/image → process join/i)).toBeInTheDocument();
    expect(screen.getByText(/no per-image batch\/station\/unit\/timestamp metadata/i)).toBeInTheDocument();
    expect(screen.getAllByText(/capability: READY/i).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/INPUT REQUIRED/i).length).toBeGreaterThan(0);
  });
});

describe("inspection studio (02)", () => {
  it("renders the real decision, class and calibrated confidence from the API", async () => {
    await inspectImage();

    expect(screen.getAllByText(CLASS_NAME).length).toBeGreaterThan(0);
    expect((await screen.findAllByText(/93\.0%/)).length).toBeGreaterThan(0);
    expect(screen.getAllByText(DECISION).length).toBeGreaterThan(0);
  });

  it("labels localization as model-derived with ground truth not available", async () => {
    await inspectImage();
    expect(screen.getAllByText(/MODEL-DERIVED/i).length).toBeGreaterThan(0);
    expect((await screen.findAllByText(/NOT AVAILABLE/i)).length).toBeGreaterThan(0);
  });

  it("shows the process link as not available with the reason", async () => {
    await inspectImage();
    expect(screen.getAllByText(/PROCESS LINK NOT AVAILABLE/i).length).toBeGreaterThan(0);
  });

  it("renders the visual AI pipeline with plain language and technical evidence behind a button", async () => {
    const user = await inspectImage();
    await user.click(screen.getByRole("button", { name: /^Classify/i }));
    expect(await screen.findByText(/zxscratch · 93\.0% calibrated probability/i)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /view technical evidence/i }));
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByText(/predicted class/i)).toBeInTheDocument();
  });

  it("renders the evidence graph with real node values and click-through detail", async () => {
    const user = await inspectImage();
    expect(await screen.findByText(/evidence graph/i)).toBeInTheDocument();
    const node = screen.getByRole("button", { name: new RegExp(`Decision: ${DECISION}`) });
    await user.click(node);
    expect(await screen.findByText(/threshold rules applied to calibrated confidence and anomaly/i)).toBeInTheDocument();
  });

  it("projects the real sample into the training feature space", async () => {
    await inspectImage();
    expect(screen.getByText(/feature space/i)).toBeInTheDocument();
    expect((await screen.findAllByText("current")).length).toBeGreaterThan(0);
    expect(screen.getByText(/60\.0% of the training variance/i)).toBeInTheDocument();
  });

  it("separates novelty from confidence and shows the known distribution", async () => {
    await inspectImage();
    expect((await screen.findAllByText(/known distribution/i)).length).toBeGreaterThan(0);
    expect((await screen.findAllByText(/^KNOWN$/)).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/0\.210/).length).toBeGreaterThan(0);
  });

  it("shows measured decision quality with the real thresholds", async () => {
    await inspectImage();
    expect((await screen.findAllByText(/pass ≥ 0\.80/)).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/defect < 0\.70/).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/false accept/i).length).toBeGreaterThan(0);
  });

  it("renders the decision chain steps", async () => {
    await inspectImage();
    for (const label of ["WHAT", "WHERE", "HOW CERTAIN", "WHY", "FLOW", "IMPACT", "WHAT NEXT"]) {
      expect(screen.getAllByText(label).length).toBeGreaterThan(0);
    }
  });
});

describe("process intelligence (03)", () => {
  it("renders the real station, throughput and constraint from the API", async () => {
    await loadProcessDataset();
    expect((await screen.findAllByText(STATION)).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/777\.5/).length).toBeGreaterThan(0);
  });

  it("opens the station evidence drawer from the constraint ranking", async () => {
    const user = await loadProcessDataset();
    await user.click(screen.getByRole("button", { name: /open evidence/i }));
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByText(/why this station/i)).toBeInTheDocument();
    expect(within(dialog).getAllByText(/bottleneck\/findings/).length).toBeGreaterThan(0);
  });

  it("renders the process timeline and bottleneck evidence components", async () => {
    const user = await loadProcessDataset();
    await user.click(screen.getByRole("button", { name: /^01 process/i }));
    expect(await screen.findByText(/process timeline/i)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /^03 flow/i }));
    expect(await screen.findByText(/bottleneck evidence/i)).toBeInTheDocument();
    expect(screen.getAllByText(/utilization/i).length).toBeGreaterThan(0);
  });

  it("switches stages and shows honest empty states", async () => {
    const user = await loadProcessDataset();
    await user.click(screen.getByRole("button", { name: /^02 root cause/i }));
    expect((await screen.findAllByText(/no root-cause analysis/i)).length).toBeGreaterThan(0);
    await user.click(screen.getByRole("button", { name: /^04 impact/i }));
    expect(await screen.findByText(/no baseline has been computed/i)).toBeInTheDocument();
  });
});

describe("investigation history (04)", () => {
  it("lists stored investigations and replays the recorded stages", async () => {
    const user = userEvent.setup();
    render(<App />);
    await user.click(await screen.findByRole("button", { name: "Investigation History" }));
    expect(await screen.findByText(/zxinv000001/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /play investigation/i }));
    expect(screen.getAllByText("Inspection received").length).toBeGreaterThan(0);
    await user.click(screen.getByRole("button", { name: /next stage/i }));
    expect((await screen.findAllByText(/classification/i)).length).toBeGreaterThan(0);
  });

  it("shows data-gap stages honestly in the replay", async () => {
    const user = userEvent.setup();
    render(<App />);
    await user.click(await screen.findByRole("button", { name: "Investigation History" }));
    await screen.findByText(/zxinv000001/);
    expect(screen.getAllByText(/DATA GAP/).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/No process dataset selected/).length).toBeGreaterThan(0);
  });
});
