import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import App from "../App";

/**
 * Phase 12 integration test with a mocked backend.
 * All mocked values are deliberately unique (zx-prefixed) so rendering them
 * proves the UI consumes the API layer rather than hardcoded results.
 */

const STATION = "ZX-9";
const THROUGHPUT = 777.5;
const CLASS_NAME = "zxscratch";
const CONFIDENCE = 0.93;
const DECISION = "DEFECT";

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

/** NDJSON stream response mirroring POST /api/vision/inspect/stream. */
function streamResponse(inspection: { trace: Array<Record<string, unknown>> }): Response {
  const lines = [
    ...inspection.trace.map((stage) => JSON.stringify({ event: "stage", stage })),
    JSON.stringify({ event: "result", result: inspection }),
  ].join("\n") + "\n";
  const stream = new ReadableStream({
    start(controller) {
      controller.enqueue(new TextEncoder().encode(lines));
      controller.close();
    },
  });
  return new Response(stream, { status: 200, headers: { "Content-Type": "application/x-ndjson" } });
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
    { id: "classification", status: "complete", started_at: "2026-01-01T00:00:00Z", duration_ms: 2, summary: "Scoring.", metrics: { predicted_class: CLASS_NAME } },
    { id: "anomaly_analysis", status: "complete", started_at: "2026-01-01T00:00:00Z", duration_ms: 2, summary: "Comparing.", metrics: { anomaly_score: 1.0 } },
    { id: "localization", status: "complete", started_at: "2026-01-01T00:00:00Z", duration_ms: 5, summary: "CAM.", metrics: { method: "class-activation mapping" } },
    { id: "confidence", status: "complete", started_at: "2026-01-01T00:00:00Z", duration_ms: 1, summary: "Summarizing.", metrics: { confidence_level: "HIGH" } },
    { id: "decision", status: "complete", started_at: "2026-01-01T00:00:00Z", duration_ms: 1, summary: "Thresholds.", metrics: { decision: DECISION } },
    { id: "process_link", status: "not_supported", started_at: "2026-01-01T00:00:00Z", duration_ms: 0.5, summary: "No metadata.", metrics: { status: "NOT_AVAILABLE" } },
  ],
};

const recommendations = {
  dataset_id: contract.dataset_id,
  recommendations: [
    {
      recommendation_id: "recmock000001",
      action_type: "INVESTIGATE_HIGH_UTILIZATION",
      title: `Investigate high utilization at ${STATION}`,
      target: STATION,
      station: STATION,
      priority: 8,
      evidence_quality: "MODERATE_EVIDENCE",
      rank: 1,
      generated_at: "2026-01-01T00:00:00Z",
    },
  ],
  count: 1,
  decision_summary: null,
};

function routeFetch(url: string): Response {
  if (url.endsWith("/api/health")) return jsonResponse({ status: "ok", service: "neurax-api", models_initialized: false });
  if (url.endsWith("/api/vision/status"))
    return jsonResponse({
      status: "READY",
      model_available: true,
      classes: [CLASS_NAME, "normal"],
      normal_class: "normal",
      metrics: { accuracy: 0.99, f1_weighted: 0.99, val_accuracy: 0.99, false_accept_rate: 0, false_reject_rate: 0, review_rate: 0.02, decisions: { PASS: 9, DEFECT: 40, REVIEW: 1 }, per_class: {}, confusion_matrix: [] },
      thresholds: { pass_confidence: 0.8, defect_confidence: 0.7, anomaly_review_percentile: 0.99 },
      metadata: { backbone: { name: "mobilenet_v2" }, calibration: "temperature scaling" },
      dataset_available: true,
    });
  if (url.includes("/api/vision/inspect/stream")) return streamResponse(inspection);
  if (url.includes("/api/vision/inspect")) return jsonResponse(inspection);
  if (url.endsWith("/api/vision/history")) return jsonResponse({ inspections: [], count: 0 });
  if (url.endsWith("/api/datasets"))
    return jsonResponse({ datasets: [{ dataset_id: contract.dataset_id, filename: contract.filename, status: "complete", ingested_at: null, rows: 300 }] });
  if (url.endsWith("/analysis")) return jsonResponse(analysis);
  if (url.endsWith("/models")) return jsonResponse(ml);
  if (url.includes("/root-cause/targets")) return jsonResponse({ dataset_id: contract.dataset_id, targets: [], count: 0 });
  if (url.includes("/bottleneck/findings")) return jsonResponse({ dataset_id: contract.dataset_id, analyses: [{ analysis_id: bottleneck.analysis_id }], count: 1 });
  if (url.includes("/bottleneck/")) return jsonResponse(bottleneck);
  if (url.endsWith("/recommendations")) return jsonResponse(recommendations);
  if (url.match(/\/api\/datasets\/[a-z0-9]+$/)) return jsonResponse(contract);
  return jsonResponse({}, 404);
}

beforeEach(() => {
  vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => routeFetch(String(input))));
});

afterEach(() => {
  vi.unstubAllGlobals();
});

async function inspectImage() {
  const user = userEvent.setup();
  render(<App />);
  const uploadButton = await screen.findByRole("button", { name: /upload image/i });
  expect(uploadButton).toBeInTheDocument();
  // raw speed for tests (cinematic pacing is display-only)
  await user.click(screen.getByRole("button", { name: /cinematic/i }));
  const input = document.querySelector('input[type="file"]') as HTMLInputElement;
  await user.upload(input, new File(["fake"], "zxpart.png", { type: "image/png" }));
  await screen.findAllByText(DECISION);
  return user;
}

async function loadProcessDataset() {
  const user = userEvent.setup();
  render(<App />);
  await user.click(await screen.findByRole("button", { name: /no process dataset/i }));
  await user.click(await screen.findByText(contract.filename));
  await user.click(screen.getByRole("button", { name: "Control Room" }));
  await screen.findByText(/current constraint/i);
  return user;
}

describe("inspection (primary experience)", () => {
  it("renders the real decision, class, confidence and anomaly from the API", async () => {
    await inspectImage();
    expect(screen.getAllByText(CLASS_NAME).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/93\.0%/).length).toBeGreaterThan(0);
    expect(screen.getAllByText(DECISION).length).toBeGreaterThan(0);
  });

  it("shows the real processing artifacts: original → preprocessed → anomaly map", async () => {
    await inspectImage();
    expect(screen.getByText(/recorded artifacts/i)).toBeInTheDocument();
    expect(screen.getByText("ORIGINAL")).toBeInTheDocument();
    expect(screen.getByText("PREPROCESSED")).toBeInTheDocument();
    expect(screen.getByText("MODEL ANOMALY MAP")).toBeInTheDocument();
    const images = screen.getAllByRole("img");
    expect(images.length).toBeGreaterThanOrEqual(3);
  });

  it("labels localization as model-derived", async () => {
    await inspectImage();
    expect(screen.getAllByText(/MODEL-DERIVED/i).length).toBeGreaterThan(0);
  });

  it("shows the process link as not available with the reason", async () => {
    await inspectImage();
    expect(screen.getByText(/PROCESS LINK NOT AVAILABLE/i)).toBeInTheDocument();
  });
});

describe("AI console", () => {
  it("renders the real trace stages in order with a visual pipeline flow", async () => {
    const user = await inspectImage();
    await user.click(screen.getByRole("button", { name: "Console" }));
    expect(await screen.findByText("Processing pipeline")).toBeInTheDocument();
    expect(screen.getByText("AI inspection console")).toBeInTheDocument();
    const stages = screen.getAllByText(/image received|validation|preprocessing|feature extraction|classification|anomaly analysis|localization|confidence|decision|process link/i);
    expect(stages.length).toBeGreaterThanOrEqual(10);
    expect(screen.getByText(/not private model chain-of-thought/i)).toBeInTheDocument();
  });
});

describe("decision chain", () => {
  it("renders WHAT / WHERE / HOW CERTAIN / WHY / WHAT NEXT from real outputs", async () => {
    const user = await inspectImage();
    await user.click(screen.getByRole("button", { name: "Decision" }));
    for (const label of ["WHAT", "WHERE", "HOW CERTAIN", "WHY", "05 · WHAT NEXT"]) {
      expect(await screen.findByText(label)).toBeInTheDocument();
    }
    expect(screen.getByText(/false accept rate/i)).toBeInTheDocument();
    expect(screen.getByText(/not a ground-truth defect boundary/i)).toBeInTheDocument();
  });
});

describe("control room", () => {
  it("renders the real station, throughput and constraint from the API", async () => {
    await loadProcessDataset();
    expect((await screen.findAllByText(STATION)).length).toBeGreaterThan(0);
    expect(screen.getByText(/777\.5/)).toBeInTheDocument();
  });

  it("opens the station evidence drawer", async () => {
    const user = await loadProcessDataset();
    await user.click(screen.getByRole("button", { name: /why this station/i }));
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByText(/why this station/i)).toBeInTheDocument();
    expect(within(dialog).getAllByText(/bottleneck\/findings/).length).toBeGreaterThan(0);
  });

  it("exposes detailed sections through progressive disclosure", async () => {
    const user = await loadProcessDataset();
    expect(screen.queryByText(/evidence-based hypothesis/i)).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /station constraint ranking/i }));
    expect(await screen.findByText(/evidence-based hypothesis/i)).toBeInTheDocument();
  });
});
