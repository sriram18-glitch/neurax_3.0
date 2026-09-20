import { ArrowRight, PlusCircle, View } from "lucide-react";

import { useSession } from "../../session/SessionContext";

type DataState = "ready" | "input_required" | "data_gap" | "not_supported" | "failed";

const STATE_DOT: Record<DataState, string> = {
  ready: "bg-ok",
  input_required: "bg-warn",
  data_gap: "bg-warn",
  not_supported: "bg-idle",
  failed: "bg-bad",
};

const STATE_WORD: Record<DataState, string> = {
  ready: "READY",
  input_required: "INPUT REQUIRED",
  data_gap: "DATA GAP",
  not_supported: "NOT SUPPORTED",
  failed: "FAILED",
};

const STATE_TONE: Record<DataState, string> = {
  ready: "text-ok",
  input_required: "text-warn",
  data_gap: "text-warn",
  not_supported: "text-ink-3",
  failed: "text-bad",
};

/**
 * Data coverage distinguishes WHAT NEURAX CAN DO (capability) from WHAT THIS
 * DATASET ALLOWS (data). A valid capability waiting for input is amber
 * "INPUT REQUIRED" — never grey "unavailable".
 */
export function DataCoverage({
  onAddProcessData,
  onAddAssumptions,
  onViewJoinFields,
}: {
  onAddProcessData?: () => void;
  onAddAssumptions?: () => void;
  onViewJoinFields?: () => void;
}) {
  const { visionStatus, contract, inspection, baseline, rootCause, bottleneck, timeline } = useSession();

  const capabilityReady = "READY";
  const capabilityNotSupported = "NOT SUPPORTED";

  const rows: Array<{
    label: string;
    capability: string;
    capabilityTone: "ready" | "not_supported";
    data: DataState;
    detail: string;
    action?: { label: string; onClick: () => void; icon?: typeof PlusCircle };
  }> = [
    {
      label: "Vision",
      capability: visionStatus?.model_available ? capabilityReady : capabilityNotSupported,
      capabilityTone: visionStatus?.model_available ? "ready" : "not_supported",
      data: visionStatus?.model_available ? "ready" : "not_supported",
      detail: visionStatus?.model_available
        ? "classification, localization, robustness, confidence — all operational"
        : "train the vision model to enable inspection",
    },
    {
      label: "Process analysis",
      capability: capabilityReady,
      capabilityTone: "ready",
      data: contract ? "ready" : "input_required",
      detail: contract
        ? `${contract.filename} · ${contract.summary.total_rows.toLocaleString("en-US")} rows loaded`
        : "no process dataset loaded — add one to enable timeline, flow and impact",
      action: contract ? undefined : { label: "ADD PROCESS DATA", onClick: () => onAddProcessData?.() },
    },
    {
      label: "Process timeline",
      capability: capabilityReady,
      capabilityTone: "ready",
      data: timeline?.status === "AVAILABLE" ? "ready" : contract ? "input_required" : "input_required",
      detail:
        timeline?.status === "AVAILABLE"
          ? `${timeline.series.length} station series aggregated from processed data`
          : contract
            ? "processed data present — open Process Intelligence to build the timeline"
            : "requires a processed dataset",
    },
    {
      label: "Root cause",
      capability: capabilityReady,
      capabilityTone: "ready",
      data: rootCause ? "ready" : "data_gap",
      detail: rootCause
        ? `${rootCause.factors_analyzed} factors analyzed · statistical association only`
        : "requires a process dataset with a numeric response column (association engine exists)",
    },
    {
      label: "Flow / bottleneck",
      capability: capabilityReady,
      capabilityTone: "ready",
      data: bottleneck ? "ready" : "data_gap",
      detail: bottleneck
        ? bottleneck.candidate_bottleneck.station
          ? `candidate: ${bottleneck.candidate_bottleneck.station} (evidence-based hypothesis)`
          : "analysis complete, no station reached the threshold"
        : "requires station metrics (utilization/queue/cycle per station)",
    },
    {
      label: "Image → process join",
      capability: capabilityReady,
      capabilityTone: "ready",
      data: "data_gap",
      detail: inspection?.process_link.reason ??
        "no per-image batch/station/unit/timestamp metadata — per-unit correlation is not possible",
      action: { label: "VIEW REQUIRED FIELDS", onClick: () => onViewJoinFields?.(), icon: View },
    },
    {
      label: "Economic impact",
      capability: capabilityReady,
      capabilityTone: "ready",
      data: baseline ? "ready" : "input_required",
      detail: baseline
        ? "baseline computed from observed throughput + supplied assumptions"
        : "no economic columns in the data — user assumptions (margin, hours, costs) required",
      action: baseline ? undefined : { label: "ADD ASSUMPTIONS", onClick: () => onAddAssumptions?.() },
    },
    {
      label: "What-if",
      capability: capabilityReady,
      capabilityTone: "ready",
      data: baseline ? "ready" : "input_required",
      detail: baseline
        ? "assumption-based scenarios run against the observed baseline"
        : "requires an economic baseline (process data + assumptions)",
    },
  ];

  return (
    <ul className="grid gap-px bg-line/40 sm:grid-cols-2">
      {rows.map((row) => (
        <li key={row.label} className="flex flex-col gap-1.5 bg-panel/70 px-4 py-3">
          <span className="flex items-center justify-between gap-2">
            <span className="text-2xs font-semibold uppercase tracking-[0.1em] text-ink-2">{row.label}</span>
            <span className={`flex items-center gap-1.5 font-mono text-[9px] tracking-[0.08em] ${row.capabilityTone === "ready" ? "text-ok" : "text-ink-3"}`}>
              <span className={`h-1.5 w-1.5 rounded-full ${row.capabilityTone === "ready" ? "bg-ok" : "bg-idle"}`} aria-hidden />
              capability: {row.capability}
            </span>
          </span>
          <span className="flex items-center gap-1.5">
            <span className={`h-1.5 w-1.5 ${STATE_DOT[row.data]}`} aria-hidden />
            <span className={`font-mono text-[9px] tracking-[0.08em] ${STATE_TONE[row.data]}`}>{STATE_WORD[row.data]}</span>
          </span>
          <span className="text-[9px] leading-relaxed text-ink-3">{row.detail}</span>
          {row.action && (
            <button
              type="button"
              className="mt-0.5 flex w-fit items-center gap-1.5 border border-cyan/40 bg-cyan/5 px-2 py-0.5 font-mono text-[9px] uppercase tracking-[0.08em] text-cyan transition-colors hover:bg-cyan/15"
              onClick={row.action.onClick}
            >
              {row.action.icon ? <row.action.icon size={10} aria-hidden /> : <PlusCircle size={10} aria-hidden />}
              {row.action.label}
              <ArrowRight size={9} aria-hidden />
            </button>
          )}
        </li>
      ))}
    </ul>
  );
}