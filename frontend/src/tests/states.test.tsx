import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import App from "../App";

/**
 * Phase 12 states test - the app opens on the INSPECT area (image-first).
 * Uses a mocked backend; values are deliberately unique so rendering proves
 * they came from the API layer.
 */

const VISION_CLASS = "zxclass";
const MODEL_NAME = "zxbackbone";

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

const visionReady = {
  status: "READY",
  model_available: true,
  classes: [VISION_CLASS, "otherclass"],
  normal_class: "otherclass",
  metrics: {
    accuracy: 0.99,
    f1_weighted: 0.99,
    val_accuracy: 0.99,
    false_accept_rate: 0,
    false_reject_rate: 0,
    review_rate: 0.02,
    decisions: { PASS: 90, DEFECT: 400, REVIEW: 10 },
    per_class: {},
    confusion_matrix: [],
  },
  thresholds: { pass_confidence: 0.8, defect_confidence: 0.7, anomaly_review_percentile: 0.99 },
  temperature: 1.0,
  metadata: { backbone: { name: MODEL_NAME, pretrained: "imagenet", frozen: true, embedding_dim: 1280 }, calibration: "temperature scaling" },
  dataset_dir: "train/train",
  dataset_available: true,
};

let backendOnline = true;
let modelReady = true;

function routeFetch(url: string): Response {
  if (!backendOnline) throw new TypeError("Failed to fetch");
  if (url.endsWith("/api/health")) return jsonResponse({ status: "ok", service: "neurax-api", models_initialized: false });
  if (url.endsWith("/api/vision/status")) {
    return modelReady
      ? jsonResponse(visionReady)
      : jsonResponse({
          status: "NOT_TRAINED",
          model_available: false,
          reason: "No vision model has been trained yet.",
          dataset_available: true,
          dataset_dir: "train/train",
          requirements: { needs: "Class-folder image dataset.", minimum: "2+ classes." },
        });
  }
  if (url.endsWith("/api/vision/history")) return jsonResponse({ inspections: [], count: 0 });
  if (url.endsWith("/api/datasets")) return jsonResponse({ datasets: [] });
  return jsonResponse({}, 404);
}

beforeEach(() => {
  backendOnline = true;
  modelReady = true;
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL) => routeFetch(String(input))),
  );
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("phase 12 app shell", () => {
  it("opens on the command center with exactly four primary areas", async () => {
    render(<App />);
    await waitFor(() => expect(screen.getByRole("button", { name: "Command Center" })).toBeInTheDocument());
    for (const label of ["Command Center", "Inspection", "Process Intelligence", "Investigation History"]) {
      expect(screen.getByRole("button", { name: label })).toBeInTheDocument();
    }
    // the old eight-view navigation must not exist
    for (const removed of ["Process", "Flow", "Impact", "What-if", "Recommendations", "Root cause", "Console", "Decision", "Control Room"]) {
      expect(screen.queryByRole("button", { name: removed })).not.toBeInTheDocument();
    }
  });

  it("shows the real vision model status in the command bar", async () => {
    render(<App />);
    expect(await screen.findByText(new RegExp(`READY.*2 classes`, "i"))).toBeInTheDocument();
  });

  it("shows an honest not-trained state with a train action when no model exists", async () => {
    modelReady = false;
    const user = userEvent.setup();
    render(<App />);
    await user.click(await screen.findByRole("button", { name: "Inspection" }));
    expect(await screen.findByText(/visual inspection model not trained/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /train vision model/i })).toBeInTheDocument();
  });

  it("shows the backend-offline banner instead of a silent empty screen", async () => {
    backendOnline = false;
    render(<App />);
    expect(await screen.findByText(/backend offline/i)).toBeInTheDocument();
  });

  it("process intelligence explains that no process dataset is loaded", async () => {
    const user = userEvent.setup();
    render(<App />);
    await user.click(await screen.findByRole("button", { name: "Process Intelligence" }));
    expect(await screen.findByText(/process data not loaded/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /upload process dataset/i })).toBeInTheDocument();
  });

  it("inspection studio shows honest empty states before an inspection", async () => {
    const user = userEvent.setup();
    render(<App />);
    await user.click(await screen.findByRole("button", { name: "Inspection" }));
    expect(await screen.findByText(/start the automated inspection stream/i)).toBeInTheDocument();
    expect(screen.getByText(/awaiting decision/i)).toBeInTheDocument();
    expect((await screen.findAllByText(/no inspection yet/i)).length).toBeGreaterThan(0);
  });

  it("rejects an unreadable image upload with a structured error", async () => {
    const user = userEvent.setup();
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) => {
        const url = String(input);
        if (url.includes("/api/vision/inspect/stream")) {
          return jsonResponse(
            {
              detail: {
                error: true,
                code: "INVALID_IMAGE",
                message: "The uploaded file is not a readable image.",
                detail: null,
              },
            },
            503,
          );
        }
        return routeFetch(url);
      }),
    );
    render(<App />);
    await user.click(await screen.findByRole("button", { name: "Inspection" }));
    await user.click(await screen.findByRole("button", { name: /manual inspection/i }));
    await screen.findByRole("button", { name: /upload image/i });
    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    await user.upload(input, new File(["x"], "corrupt.png", { type: "image/png" }));
    expect(await screen.findByText(/not a readable image/i)).toBeInTheDocument();
  });
});
