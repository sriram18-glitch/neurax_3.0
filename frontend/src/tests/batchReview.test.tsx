import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import App from "../App";

/**
 * V2.1 tests: batch/dataset inspection, per-image confidence, the human review
 * queue and the add-data flow. All mocked values are zx-prefixed (unique) so
 * rendering them proves the UI consumes the API rather than hardcoded results.
 */

const calls: string[] = [];
let resolvedIds: string[] = [];

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

const batchValidated = {
  batch_id: "zxbatch01",
  created_at: "2026-01-01T00:00:00Z",
  status: "validated",
  source: "uploaded files",
  summary: {
    total: 4,
    valid: 3,
    invalid: 1,
    unsupported: 0,
    duplicates: 0,
    classes: ["normal", "zxclass"],
    class_counts: { normal: 2, zxclass: 1 },
    labels_available: true,
    labels_note: "class folders present; used as ground truth for decision quality",
    class_balance: "BALANCED",
    localization_annotations: "NOT AVAILABLE",
    localization_note: "no annotations",
    process_join: "NOT AVAILABLE",
    process_join_note: "no per-image metadata",
  },
  images: [
    { original_name: "normal/a.png", status: "valid", class_folder: "normal", sha256: "a" },
    { original_name: "normal/b.png", status: "valid", class_folder: "normal", sha256: "b" },
    { original_name: "zxclass/c.png", status: "valid", class_folder: "zxclass", sha256: "c" },
    { original_name: "broken.png", status: "invalid", reason: "unreadable image", sha256: "d" },
  ],
  progress: { inspected: 0, total: 3 },
  decisions: { PASS: 0, DEFECT: 0, REVIEW: 0 },
  review_queue: 0,
  quality: null,
  results: [],
  note: "",
};

const batchComplete = {
  ...batchValidated,
  status: "complete",
  duration_s: 1.2,
  avg_confidence: 0.9,
  progress: { inspected: 3, total: 3 },
  decisions: { PASS: 2, DEFECT: 0, REVIEW: 1 },
  review_queue: 1,
  quality: {
    basis: "measured against class-folder ground truth (DEFECT = positive; normal = PASS)",
    tp: 0,
    tn: 2,
    fp: 0,
    fn: 0,
    false_accept_rate: 0.0,
    false_reject_rate: 0.0,
    precision: null,
    recall: null,
    f1: null,
    review_rate: 0.3333,
    note: "REVIEW decisions are escalations, not accept/reject errors.",
  },
  results: [
    {
      index: 0,
      inspection_id: "zxbatchinspect001",
      filename: "normal/a.png",
      class_folder: "normal",
      ground_truth: "normal",
      decision: "PASS",
      confidence: 0.99,
      raw_probability: 0.95,
      anomaly_score: 0.2,
      novelty_score: 0.1,
      novelty_status: "NORMAL",
      localization: true,
      review_reason: null,
      review_reasons: [],
    },
    {
      index: 1,
      inspection_id: "zxbatchinspect002",
      filename: "normal/b.png",
      class_folder: "normal",
      ground_truth: "normal",
      decision: "PASS",
      confidence: 0.98,
      raw_probability: 0.94,
      anomaly_score: 0.3,
      novelty_score: 0.05,
      novelty_status: "NORMAL",
      localization: true,
      review_reason: null,
      review_reasons: [],
    },
    {
      index: 2,
      inspection_id: "zxbatchinspect003",
      filename: "zxclass/c.png",
      class_folder: "zxclass",
      ground_truth: "zxclass",
      decision: "REVIEW",
      confidence: 0.61,
      raw_probability: 0.55,
      anomaly_score: 0.9,
      novelty_score: 0.995,
      novelty_status: "HIGH",
      localization: false,
      review_reason: "Unfamiliar condition",
      review_reasons: ["novelty 0.995 exceeds the 0.99 review gate (unseen-condition guard)"],
    },
  ],
};

const reviewQueueItems = [
  {
    inspection_id: "zxbatchinspect003",
    filename: "zxclass/c.png",
    generated_at: "2026-01-01T00:00:01Z",
    predicted_class: "zxclass",
    confidence: 0.61,
    anomaly_score: 0.9,
    novelty_score: 0.995,
    novelty_status: "HIGH",
    localization: false,
    review_reason: "Unfamiliar condition",
    review_reasons: ["novelty 0.995 exceeds the 0.99 review gate (unseen-condition guard)"],
    human_review: null,
  },
];

const reviewStats = {
  total: 3,
  auto_resolved: 2,
  human_reviewed: 0,
  pending_review: 1,
  auto_resolved_rate: 0.6667,
  human_review_rate: 0.0,
  pending_review_rate: 0.3333,
  distribution: { PASS: 2, DEFECT: 0, REVIEW: 1 },
  distribution_rates: { PASS: 0.6667, DEFECT: 0.0, REVIEW: 0.3333 },
  avg_confidence: 0.86,
  note: "Auto-resolved = decisions made by the AI without human intervention.",
};

const inspection = {
  inspection_id: "zxbatchinspect003",
  filename: "zxclass/c.png",
  generated_at: "2026-01-01T00:00:01Z",
  image_metadata: { width: 256, height: 256, mode: "L", format: "PNG", bytes: 1000 },
  preprocessing: { resize: "224x224", normalization: "n" },
  prediction: { predicted_class: "zxclass", is_normal: false },
  class_probabilities: { zxclass: 0.61, normal: 0.2 },
  confidence: { value: 0.61, raw_probability: 0.55, level: "LOW", method: "temperature scaled", calibration_status: "CALIBRATED", calibration_method: "temperature_scaling", model_version: "2026-01-01", limitations: "" },
  anomaly_score: { value: 0.9, novelty_score: 0.995, novelty_status: "HIGH", method: "m", note: "n" },
  localization: { type: "MODEL-DERIVED LOCALIZATION", method: "cam", ground_truth: false, bounding_box: null, note: "n" },
  decision: "REVIEW",
  decision_reason: "REVIEW: defect hypothesis below the validated decision region — novelty 0.995 exceeds the 0.99 review gate",
  review_reason: "Unfamiliar condition",
  review_reasons: ["novelty 0.995 exceeds the 0.99 review gate (unseen-condition guard)"],
  human_review: null,
  evidence: [],
  process_link: { status: "NOT_AVAILABLE", reason: "PROCESS LINK NOT AVAILABLE: no per-image metadata.", available_metadata: [] },
  model: { backbone: "mobilenet_v2", classes: ["zxclass", "normal"] },
  limitations: [],
  trace: [],
};

function route(url: string, method: string): Response {
  calls.push(`${method} ${url}`);
  if (url.endsWith("/api/health")) return jsonResponse({ status: "ok" });
  if (url.endsWith("/api/vision/status"))
    return jsonResponse({
      status: "READY",
      model_available: true,
      classes: ["zxclass", "normal"],
      thresholds: { pass_confidence: 0.8, defect_confidence: 0.7, anomaly_review_percentile: 0.99 },
      metadata: {},
    });
  if (url.endsWith("/api/vision/feature-space")) return jsonResponse({ status: "NOT_TRAINED", reason: "none", clouds: {} });
  if (url.includes("/api/vision/stream/status")) return jsonResponse({ label: "SIMULATED PRODUCTION STREAM", note: "", station_id: "Camera 01", dataset_available: true, dataset_error: null, running: false, speed: 1, speeds: [0.5, 1, 2, 5], cursor: 0, frame_number: 0, total_frames: 100, processed: 0, remaining: 100, session_started_at: null, next_frame: null, class_plan: null, last_summary: null, history: [], decision_counts: {} });
  if (url.includes("/api/vision/stream/next"))
    return jsonResponse({ inspection, exhausted: false, status: { label: "SIMULATED PRODUCTION STREAM", note: "", station_id: "Camera 01", dataset_available: true, dataset_error: null, running: false, speed: 1, speeds: [0.5, 1, 2, 5], cursor: 1, frame_number: 1, total_frames: 100, processed: 1, remaining: 99, session_started_at: null, next_frame: null, class_plan: null, last_summary: null, history: [], decision_counts: { REVIEW: 1 } } });
  if (url.includes("/api/vision/batch/zxbatch01/inspect")) return jsonResponse({ ...batchValidated, status: "inspecting" });
  if (url.includes("/api/vision/batch/zxbatch01")) return jsonResponse(batchComplete);
  if (url.endsWith("/api/vision/batch")) return jsonResponse(batchValidated);
  if (url.endsWith("/api/vision/batches")) return jsonResponse({ batches: [{ batch_id: "zxbatch01", status: "complete", summary: batchValidated.summary, progress: { inspected: 3, total: 3 }, decisions: batchComplete.decisions, review_queue: 1 }], count: 1 });
  if (url.includes("/api/vision/review/queue")) {
    const pending = reviewQueueItems.filter((entry) => !resolvedIds.includes(entry.inspection_id));
    return jsonResponse({ items: pending, count: pending.length, include_reviewed: false });
  }
  if (url.endsWith("/api/vision/review/stats")) {
    const pending = reviewQueueItems.length - resolvedIds.length;
    return jsonResponse({
      ...reviewStats,
      pending_review: pending,
      pending_review_rate: pending / 3,
      human_reviewed: resolvedIds.length,
      human_review_rate: resolvedIds.length / 3,
    });
  }
  if (url.includes("/api/vision/inspect/zxbatchinspect003/review")) {
    resolvedIds.push("zxbatchinspect003");
    return jsonResponse({ inspection_id: "zxbatchinspect003", human_review: { action: "confirm_defect", action_label: "CONFIRM DEFECT", decision: "DEFECT", at: "2026-01-01T00:00:02Z", note: null, ai_decision_preserved: "REVIEW" }, ai_decision: "REVIEW", ai_confidence: 0.61, note: "" });
  }
  if (url.includes("/api/vision/inspect")) return jsonResponse(inspection);
  if (url.endsWith("/api/vision/history")) return jsonResponse({ inspections: [], count: 0 });
  if (url.endsWith("/api/investigations")) return jsonResponse({ investigations: [], count: 0, note: "" });
  if (url.endsWith("/api/datasets")) return jsonResponse({ datasets: [] });
  return jsonResponse({}, 404);
}

beforeEach(() => {
  calls.length = 0;
  resolvedIds = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => route(String(input), (init?.method ?? "GET").toUpperCase())),
  );
});

afterEach(() => vi.unstubAllGlobals());

async function waitForEnabled(name: RegExp) {
  const button = await screen.findByRole("button", { name });
  await waitFor(() => expect(button).toBeEnabled());
  return button;
}

async function openBatchMode() {
  const user = userEvent.setup();
  render(<App />);
  await user.click(await screen.findByRole("button", { name: /^Inspection$/ }));
  await user.click(await screen.findByRole("button", { name: /batch inspection/i }));
  return user;
}

describe("batch / dataset inspection", () => {
  it("ingests files and shows the data-health report with real validation counts", async () => {
    const user = await openBatchMode();
    expect((await screen.findAllByText(/add inspection data/i)).length).toBeGreaterThan(0);
    const input = screen.getByLabelText("Add inspection images") as HTMLInputElement;
    await user.upload(input, [new File(["x"], "normal/a.png", { type: "image/png" }), new File(["y"], "broken.png", { type: "image/png" })]);
    expect(await screen.findByText(/data health/i)).toBeInTheDocument();
    expect(screen.getByText("4")).toBeInTheDocument();
    expect(screen.getByText("3")).toBeInTheDocument();
    expect(screen.getAllByText(/invalid/i).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/labels/i).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/NOT AVAILABLE/i).length).toBeGreaterThan(0);
    expect(calls.some((entry) => entry.includes("/api/vision/batch") && !entry.includes("/api/vision/batches"))).toBe(true);
  });

  it("starts the auto check and shows per-image results with confidence bars and review warning", async () => {
    const user = await openBatchMode();
    const input = screen.getByLabelText("Add inspection images") as HTMLInputElement;
    await user.upload(input, [new File(["x"], "normal/a.png", { type: "image/png" })]);
    await screen.findByText(/data health/i);
    await user.click(await screen.findByRole("button", { name: /start auto check/i }));
    expect(await screen.findByText(/dataset inspection complete/i, {}, { timeout: 6000 })).toBeInTheDocument();
    expect(screen.getAllByText(/normal\/a\.png/).length).toBeGreaterThan(0);
    expect(screen.getAllByText("99.0%").length).toBeGreaterThan(0);
    expect(screen.getAllByText(/human review/i).length).toBeGreaterThan(0);
    expect(screen.getByText(/measured against class-folder ground truth/i)).toBeInTheDocument();
  });

  it("filters the gallery by decision and novelty", async () => {
    const user = await openBatchMode();
    const input = screen.getByLabelText("Add inspection images") as HTMLInputElement;
    await user.upload(input, [new File(["x"], "normal/a.png", { type: "image/png" })]);
    await screen.findByText(/data health/i);
    await user.click(await screen.findByRole("button", { name: /start auto check/i }));
    await screen.findByText(/dataset inspection complete/i, {}, { timeout: 6000 });
    await user.click(screen.getByRole("button", { name: /^REVIEW$/ }));
    expect(screen.getAllByText(/zxclass\/c\.png/).length).toBeGreaterThan(0);
    await user.click(screen.getByRole("button", { name: /^NOVEL$/ }));
    expect(screen.getAllByText(/zxclass\/c\.png/).length).toBeGreaterThan(0);
  });
});

describe("human review queue", () => {
  it("surfaces pending reviews prominently and records the human decision", async () => {
    const user = userEvent.setup();
    render(<App />);
    expect((await screen.findAllByText(/1 inspection\(s\) require human review/i)).length).toBeGreaterThan(0);
    expect(screen.getByText(/auto resolved/i)).toBeInTheDocument();
    const item = screen.getByRole("button", { name: /zxclass\/c\.png/i });
    await user.click(item);
    expect(await screen.findByText(/novelty 0\.995 exceeds/i)).toBeInTheDocument();
    expect(screen.getAllByText(/^AI: REVIEW$/).length).toBeGreaterThan(0);
    await user.click(screen.getByRole("button", { name: /confirm defect/i }));
    await waitFor(() => expect(calls.some((entry) => entry.includes("/review") && entry.includes("POST"))).toBe(true));
  });

  it("preserves the AI decision alongside the human decision", async () => {
    const user = userEvent.setup();
    render(<App />);
    const item = await screen.findByRole("button", { name: /zxclass\/c\.png/i });
    await user.click(item);
    expect(await screen.findByText(/the AI decision and evidence are preserved/i)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /confirm defect/i }));
  });
});

describe("review workspace (V2.2)", () => {
  it("opens from the banner with the actual image, reasons and resolves the item", async () => {
    const user = userEvent.setup();
    render(<App />);
    await user.click(await screen.findByRole("button", { name: /review queue/i }));
    expect(await screen.findByText(/human review queue/i)).toBeInTheDocument();
    expect(screen.getAllByText(/zxclass\/c\.png/).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/why human review\?/i).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/novelty 0\.995 exceeds/i).length).toBeGreaterThan(0);
    const images = screen.getAllByRole("img");
    expect(images.some((img) => (img as HTMLImageElement).src.includes("/inspect/zxbatchinspect003/image"))).toBe(true);
    await user.click(screen.getByRole("button", { name: /^confirm defect$/i }));
    await waitFor(() => expect(calls.some((entry) => entry.includes("/review") && entry.includes("POST"))).toBe(true));
    expect(await screen.findByText(/review queue empty/i)).toBeInTheDocument();
  });

  it("shows the automation gate blocking automatic decisions for REVIEW", async () => {
    const user = userEvent.setup();
    render(<App />);
    await user.click(await screen.findByRole("button", { name: /^Inspection$/ }));
    await screen.findByText(/ai inference pipeline/i);
    await user.click(await waitForEnabled(/^next$/i));
    await waitFor(() => expect(calls.some((entry) => entry.includes("/api/vision/stream/next"))).toBe(true));
    await waitFor(() => expect(screen.queryAllByText(/awaiting decision/i).length).toBe(0));
    expect(await screen.findByText(/automatic decision blocked/i)).toBeInTheDocument();
    expect((await screen.findAllByText(/human review required/i)).length).toBeGreaterThan(0);
  });
});

describe("add data flow", () => {
  it("shows the three input workflows and navigates to each mode", async () => {
    const user = userEvent.setup();
    render(<App />);
    await user.click((await screen.findAllByRole("button", { name: /add inspection data/i }))[0]);
    expect(await screen.findByRole("dialog", { name: /add inspection data/i })).toBeInTheDocument();
    await user.click((await screen.findAllByRole("button", { name: /inspect image/i }))[0]);
    expect(await screen.findByRole("button", { name: /manual inspection/i })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /add inspection data/i }));
    await user.click((await screen.findAllByRole("button", { name: /add batch \/ dataset/i }))[0]);
    expect(await screen.findByText(/drop images here/i)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /add inspection data/i }));
    await user.click((await screen.findAllByRole("button", { name: /auto production stream/i }))[0]);
    expect((await screen.findAllByText(/simulated production stream/i)).length).toBeGreaterThan(0);
  });

  it("shows the evaluation coverage map without claiming scores", async () => {
    render(<App />);
    expect(await screen.findByText(/evaluation coverage/i)).toBeInTheDocument();
    expect(screen.getAllByText(/detection & classification/i).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/localization/i).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/false accept \/ reject/i).length).toBeGreaterThan(0);
    expect(screen.getByText(/automate the certain/i)).toBeInTheDocument();
    expect(screen.getByText(/escalate the uncertain/i)).toBeInTheDocument();
  });
});