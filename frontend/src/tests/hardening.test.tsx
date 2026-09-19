import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import App from "../App";

/** Phase 12 hardening: backend status, reset, honest empty states. */

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

const contract = {
  dataset_id: "demo00000001",
  filename: "demo_process.csv",
  format: "text",
  size_bytes: 2048,
  sha256: "1".repeat(64),
  status: "analyzed",
  ingested_at: "2026-01-01T00:00:00Z",
  summary: { tables: 1, total_rows: 100, primary_table: "demo", primary_rows: 100, primary_columns: 5, stations: [], station_metrics: {} },
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
  total_duration_s: 0.5,
  coverage: { dataset_id: contract.dataset_id, modules: {}, summary: { supported: 0, partially_supported: 0, requires_assumptions: 0, not_supported: 0 }, legend: {} },
  tables: [],
  cleaning: { dataset_id: contract.dataset_id, tables: [] },
  features: { derived_features: [], skipped_candidates: [] },
  model_inputs: [],
  rejected_model_inputs: [],
  splits: { model_input_splits: [], table_splits: [] },
  station_metrics: { tables: [] },
};

const ml = { dataset_id: contract.dataset_id, status: "complete", models: [], skipped_inputs: [], vision: { status: "NOT_SUPPORTED", reason: "No visual inspection/image training data is available." } };

let online = true;

function routeFetch(url: string): Response {
  if (!online) throw new TypeError("Failed to fetch");
  if (url.endsWith("/api/health")) return jsonResponse({ status: "ok", service: "neurax-api", models_initialized: false });
  if (url.endsWith("/api/vision/status"))
    return jsonResponse({
      status: "READY",
      model_available: true,
      classes: ["normal", "other"],
      normal_class: "normal",
      thresholds: { pass_confidence: 0.8, defect_confidence: 0.7, anomaly_review_percentile: 0.99 },
      metadata: { backbone: { name: "mobilenet_v2" } },
      dataset_available: true,
    });
  if (url.endsWith("/api/vision/history")) return jsonResponse({ inspections: [], count: 0 });
  if (url.endsWith("/api/datasets")) return jsonResponse({ datasets: [{ dataset_id: contract.dataset_id, filename: contract.filename, status: "complete", ingested_at: null, rows: 100 }] });
  if (url.endsWith("/analysis")) return jsonResponse(analysis);
  if (url.endsWith("/models")) return jsonResponse(ml);
  if (url.includes("/root-cause/targets")) return jsonResponse({ dataset_id: contract.dataset_id, targets: [], count: 0 });
  if (url.includes("/bottleneck/findings")) return jsonResponse({ dataset_id: contract.dataset_id, analyses: [], count: 0 });
  if (url.endsWith("/recommendations")) return jsonResponse({ dataset_id: contract.dataset_id, recommendations: [], count: 0, decision_summary: null });
  if (url.match(/\/api\/datasets\/[a-z0-9]+$/)) return jsonResponse(contract);
  return jsonResponse({}, 404);
}

beforeEach(() => {
  online = true;
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL) => routeFetch(String(input))),
  );
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("presentation hardening", () => {
  it("detects backend online in the command bar", async () => {
    render(<App />);
    await waitFor(() => expect(screen.getByText(/^ONLINE$/)).toBeInTheDocument());
    expect(screen.queryByText(/backend offline/i)).not.toBeInTheDocument();
  });

  it("shows a visible backend-offline banner instead of a silent empty screen", async () => {
    online = false;
    render(<App />);
    expect(await screen.findByText(/backend offline/i)).toBeInTheDocument();
  });

  it("reset clears the active process session and preserves the dataset list", async () => {
    const user = userEvent.setup();
    render(<App />);
    await user.click(await screen.findByRole("button", { name: /no process dataset/i }));
    await user.click(await screen.findByText(contract.filename));
    await user.click(screen.getByRole("button", { name: "Control Room" }));
    await screen.findByText(/no candidate constraint/i);

    await user.click(screen.getByRole("button", { name: /reset/i }));
    expect(await screen.findByText(/no process dataset loaded/i)).toBeInTheDocument();
    // dataset list still available
    await user.click(screen.getByRole("button", { name: /no process dataset/i }));
    expect(await screen.findByText(contract.filename)).toBeInTheDocument();
  });

  it("vision status is honest in the command bar", async () => {
    render(<App />);
    await waitFor(() => expect(screen.getByText(/READY.*2 classes/i)).toBeInTheDocument());
  });
});
