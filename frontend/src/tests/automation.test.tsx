import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import App from "../App";

/**
 * V2 automation tests: production stream controls, automatic investigation
 * triggering and honest failure states. The mocked backend records every call
 * so we can assert which real endpoints the automation used.
 */

const calls: string[] = [];

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

const inspectionBase = {
  inspection_id: "autoinspect01",
  filename: "auto.png",
  generated_at: "2026-01-01T00:00:00Z",
  image_metadata: { width: 256, height: 256, mode: "L", format: "PNG", bytes: 1000 },
  preprocessing: { resize: "224x224", normalization: "n", preprocessed_png_base64: "aGVsbG8=" },
  prediction: { predicted_class: "autoclass", is_normal: false },
  class_probabilities: { autoclass: 0.95, normal: 0.05 },
  confidence: { value: 0.95, level: "HIGH", method: "temperature scaled", limitations: "" },
  anomaly_score: { value: 1.0, novelty_score: 0.995, novelty_status: "HIGH", method: "m", note: "n" },
  localization: { type: "MODEL-DERIVED LOCALIZATION", method: "cam", ground_truth: false, bounding_box: null, note: "n" },
  decision: "REVIEW",
  review_reason: "Sample differs significantly from the known distribution.",
  evidence: [],
  process_link: { status: "NOT_AVAILABLE", reason: "PROCESS LINK NOT AVAILABLE: no per-image metadata.", available_metadata: [] },
  model: { backbone: "mobilenet_v2", classes: ["autoclass", "normal"] },
  limitations: [],
  trace: [
    { id: "image_received", status: "complete", started_at: "t", duration_ms: 1, summary: "s", metrics: {} },
    { id: "validation", status: "complete", started_at: "t", duration_ms: 1, summary: "s", metrics: {} },
    { id: "preprocessing", status: "complete", started_at: "t", duration_ms: 1, summary: "s", metrics: {} },
    { id: "feature_extraction", status: "complete", started_at: "t", duration_ms: 1, summary: "s", metrics: {} },
    { id: "classification", status: "complete", started_at: "t", duration_ms: 1, summary: "s", metrics: {} },
    { id: "anomaly_analysis", status: "complete", started_at: "t", duration_ms: 1, summary: "s", metrics: {} },
    { id: "localization", status: "not_supported", started_at: "t", duration_ms: 1, summary: "s", metrics: {} },
    { id: "confidence", status: "complete", started_at: "t", duration_ms: 1, summary: "s", metrics: {} },
    { id: "decision", status: "complete", started_at: "t", duration_ms: 1, summary: "s", metrics: {} },
    { id: "process_link", status: "not_supported", started_at: "t", duration_ms: 1, summary: "s", metrics: {} },
  ],
};

const investigationRecord = {
  investigation_id: "autoinv01",
  inspection_id: "autoinspect01",
  dataset_id: null,
  station_id: "Camera 01",
  generated_at: "2026-01-01T00:00:01Z",
  status: "REVIEW_REQUIRED",
  decision: "REVIEW",
  predicted_class: "autoclass",
  confidence: 0.95,
  anomaly_score: 1.0,
  novelty_status: "HIGH",
  review_reason: "Sample differs significantly from the known distribution.",
  filename: "auto.png",
  stages: [
    { id: "checking_robustness", label: "Robustness check", status: "REVIEW", summary: "novelty HIGH", detail: "review", epistemic: "MODEL OUTPUT", payload: null, duration_ms: 1 },
  ],
  stage_summary: { complete: 1, data_gap: 0, awaiting_input: 0, failed: 0, partial: 0 },
  total_duration_s: 0.2,
  limitations: [],
  events: [],
};

const streamStatus = {
  label: "SIMULATED PRODUCTION STREAM",
  note: "deterministic order",
  station_id: "Camera 01",
  dataset_available: true,
  dataset_error: null,
  running: false,
  speed: 1,
  speeds: [0.5, 1, 2, 5],
  cursor: 0,
  frame_number: 0,
  total_frames: 100,
  processed: 0,
  remaining: 100,
  session_started_at: null,
  next_frame: { class_folder: "autoclass", filename: "auto.png" },
  class_plan: null,
  last_summary: null,
  history: [],
  decision_counts: {},
};

function route(url: string, method: string): Response {
  calls.push(`${method} ${url}`);
  if (url.endsWith("/api/health")) return jsonResponse({ status: "ok" });
  if (url.endsWith("/api/vision/status"))
    return jsonResponse({
      status: "READY",
      model_available: true,
      classes: ["autoclass", "normal"],
      thresholds: { pass_confidence: 0.8, defect_confidence: 0.7, anomaly_review_percentile: 0.99 },
      metadata: {},
    });
  if (url.endsWith("/api/vision/feature-space"))
    return jsonResponse({ status: "NOT_TRAINED", reason: "No vision model has been trained yet; the feature space is unavailable.", clouds: {} });
  if (url.includes("/api/vision/stream/start")) return jsonResponse({ ...streamStatus, running: true });
  if (url.includes("/api/vision/stream/pause")) return jsonResponse(streamStatus);
  if (url.includes("/api/vision/stream/status")) return jsonResponse(streamStatus);
  if (url.includes("/api/vision/stream/next"))
    return jsonResponse({ inspection: inspectionBase, exhausted: false, status: { ...streamStatus, frame_number: 1, processed: 1 } });
  if (url.includes("/api/vision/inspect/stream")) {
    const lines =
      inspectionBase.trace.map((stage) => JSON.stringify({ event: "stage", stage })).join("\n") +
      "\n" +
      JSON.stringify({ event: "result", result: inspectionBase }) +
      "\n";
    return new Response(
      new ReadableStream({
        start(controller) {
          controller.enqueue(new TextEncoder().encode(lines));
          controller.close();
        },
      }),
      { status: 200 },
    );
  }
  if (url.includes("/api/investigations/run")) return jsonResponse(investigationRecord);
  if (url.includes("/api/investigations")) return jsonResponse({ investigations: [], count: 0, note: "" });
  if (url.endsWith("/api/vision/history")) return jsonResponse({ inspections: [], count: 0 });
  if (url.endsWith("/api/datasets")) return jsonResponse({ datasets: [] });
  return jsonResponse({}, 404);
}

beforeEach(() => {
  calls.length = 0;
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

describe("production stream controls", () => {
  it("start/pause hit the real stream endpoints and reflect the status", async () => {
    const user = userEvent.setup();
    render(<App />);
    await user.click(await waitForEnabled(/start automated inspection/i));
    expect(calls.some((entry) => entry.includes("POST") && entry.includes("/api/vision/stream/start"))).toBe(true);
    const pause = await screen.findByRole("button", { name: /pause/i });
    await user.click(pause);
    expect(calls.some((entry) => entry.includes("/api/vision/stream/pause"))).toBe(true);
  });

  it("'Next' processes a real frame and auto investigation fires on REVIEW", async () => {
    const user = userEvent.setup();
    render(<App />);
    await user.click(await waitForEnabled(/^next$/i));
    expect((await screen.findAllByText(/^REVIEW$/)).length).toBeGreaterThan(0);
    expect(calls.some((entry) => entry.includes("/api/vision/stream/next"))).toBe(true);
    expect(calls.some((entry) => entry.includes("/api/investigations/run"))).toBe(true);
  });

  it("auto investigation OFF suppresses the investigation call", async () => {
    const user = userEvent.setup();
    render(<App />);
    const toggle = await screen.findByRole("button", { name: /auto investigation on/i });
    await user.click(toggle);
    await user.click(await waitForEnabled(/^next$/i));
    await screen.findAllByText(/^REVIEW$/);
    expect(calls.some((entry) => entry.includes("/api/investigations/run"))).toBe(false);
  });
});

describe("robustness and honest states", () => {
  it("shows REVIEW for a novel sample with the review reason", async () => {
    const user = userEvent.setup();
    render(<App />);
    await user.click(await waitForEnabled(/^next$/i));
    expect((await screen.findAllByText(/^REVIEW$/)).length).toBeGreaterThan(0);
    expect((await screen.findAllByText(/known distribution/i)).length).toBeGreaterThan(0);
    expect(await screen.findByText(/unfamiliar enough that the decision moved to human review/i)).toBeInTheDocument();
  });

  it("reports the feature space as unavailable instead of inventing points", async () => {
    const user = userEvent.setup();
    render(<App />);
    await user.click(await screen.findByRole("button", { name: "Inspection" }));
    expect(await screen.findByText(/feature space unavailable/i)).toBeInTheDocument();
    expect(screen.getByText(/no vision model has been trained yet/i)).toBeInTheDocument();
  });
});

describe("demo mode", () => {
  it("starts the real stream and shows the demo banner", async () => {
    const user = userEvent.setup();
    render(<App />);
    await user.click(await screen.findByRole("button", { name: /start demo/i }));
    expect(calls.some((entry) => entry.includes("/api/vision/stream/start"))).toBe(true);
    expect(await screen.findByText(/demo mode/i)).toBeInTheDocument();
    const stop = await screen.findByRole("button", { name: /stop demo/i });
    await user.click(stop);
    expect(calls.some((entry) => entry.includes("/api/vision/stream/pause"))).toBe(true);
  });
});
