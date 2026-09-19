import { useState } from "react";
import { Activity, ChevronDown, ChevronRight, Database, FlaskConical, GitBranch, Layers, Sigma, Sparkles } from "lucide-react";

import { useSession } from "../session/SessionContext";
import { BottleneckPanel } from "./BottleneckPanel";
import { EconomicPanel } from "./EconomicPanel";
import { PlantFlow, type FlowNodeState } from "./PlantFlow";
import { PipelineFlow } from "./PipelineFlow";
import { RecommendationPanel } from "./RecommendationPanel";
import { RootCausePanel } from "./RootCausePanel";
import { WhatIfSimulator } from "./WhatIfSimulator";
import { NotAvailable, Panel, formatNumber, statusIcon, statusTone } from "./ui/Primitives";
import type { BottleneckFinding, Recommendation, RootCauseFinding } from "../types/api";

type SectionId = "processing" | "stations" | "rootcause" | "economics" | "whatif" | "recommendations";

export function ControlRoomView({
  onStationEvidence,
  onFactorEvidence,
  onRecommendationEvidence,
  onUploadClick,
}: {
  onStationEvidence: (station: string) => void;
  onFactorEvidence: (finding: RootCauseFinding) => void;
  onRecommendationEvidence: (recommendation: Recommendation) => void;
  onUploadClick: () => void;
}) {
  const { contract, bottleneck, recommendations, inspection, visionStatus, analysis, ml } = useSession();
  const [openSection, setOpenSection] = useState<SectionId | null>(null);
  const [selectedStation, setSelectedStation] = useState<string | null>(null);

  if (!contract) {
    return (
      <div className="mx-auto flex max-w-xl flex-col items-center gap-4 px-6 py-16 text-center">
        <Database size={22} className="text-ink-3" aria-hidden />
        <h1 className="text-lg font-semibold tracking-tight text-ink">No process dataset loaded</h1>
        <p className="text-xs leading-relaxed text-ink-2">
          Upload a manufacturing process dataset to analyze flow, identify the constraint and quantify impact. The
          inspection area works independently with the image model.
        </p>
        <button type="button" className="btn-primary" onClick={onUploadClick}>
          Upload process dataset
        </button>
      </div>
    );
  }

  const candidate = bottleneck?.candidate_bottleneck;
  const nodeStates: FlowNodeState[] = bottleneck
    ? bottleneck.station_rankings.map((finding) => ({
        station: finding.station,
        tone:
          finding.status === "CANDIDATE_BOTTLENECK"
            ? ("bad" as const)
            : finding.status === "POSSIBLE_CONTRIBUTOR"
              ? ("warn" as const)
              : finding.status === "INSUFFICIENT_EVIDENCE"
                ? ("idle" as const)
                : ("ok" as const),
        label: finding.status.replace(/_/g, " "),
        score: finding.evidence_score,
        evidenceQuality: finding.evidence_quality.label,
      }))
    : (contract.summary.stations ?? []).map((station) => ({
        station,
        tone: "idle" as const,
        label: "NO ANALYSIS",
        score: null,
      }));

  const observed = bottleneck?.what_if_inputs.observed_impact?.observed;
  const throughput = observed ? Object.values(observed)[0] : null;

  return (
    <div className="flex flex-col gap-3 p-3">
      <div className="grid grid-cols-2 divide-x divide-line border border-line bg-panel/40 lg:grid-cols-4">
        <MiniStat
          label="Throughput"
          value={throughput ? formatNumber(throughput.unconstrained_mean, 1) : null}
          unit={throughput ? throughput.output_column : undefined}
          unavailableReason="no observed comparison"
        />
        <MiniStat
          label="Constraint"
          value={candidate?.station ?? null}
          unavailableReason="no bottleneck analysis"
          hint={candidate?.evidence_quality?.label}
        />
        <MiniStat
          label="Quality"
          value={inspection ? inspection.decision : null}
          hint={
            inspection
              ? `${inspection.prediction.predicted_class} · ${(inspection.confidence.value * 100).toFixed(1)}% confidence`
              : visionStatus?.model_available
                ? "no inspection run yet"
                : "vision model not trained"
          }
          unavailableReason={visionStatus?.model_available ? "no inspection yet" : "vision not trained"}
        />
        <MiniStat
          label="Recommendations"
          value={recommendations?.count ? String(recommendations.count) : null}
          unavailableReason="none generated"
        />
      </div>

      <div className="grid gap-3 xl:grid-cols-[1fr_360px]">
        <Panel title="Process flow" subtitle="Click a station for evidence" className="min-h-[320px]">
          <PlantFlow
            graph={bottleneck?.flow.graph ?? null}
            nodeStates={nodeStates}
            onSelect={(station) => {
              setSelectedStation(station);
              onStationEvidence(station);
            }}
            selected={selectedStation}
          />
        </Panel>

        <div className="flex flex-col gap-3">
          <Panel title="Current constraint" subtitle={candidate ? `${candidate.evidence_quality?.label?.replace(/_/g, " ")}` : undefined}>
            {candidate?.station ? (
              <div className="flex flex-col gap-2 px-4 py-3">
                <div className="flex items-center justify-between">
                  <p className="text-sm font-semibold text-ink">{candidate.station}</p>
                  <span className={`chip ${statusTone(candidate.status)}`}>
                    {statusIcon(candidate.status)}
                    {candidate.status.replace(/_/g, " ")}
                  </span>
                </div>
                <ul className="flex flex-col gap-1">
                  {candidate.why.map((reason) => (
                    <li key={reason} className="text-2xs text-ink-2">
                      — {reason}
                    </li>
                  ))}
                </ul>
                <button type="button" className="btn-ghost mt-1 w-fit !px-2 !py-1" onClick={() => onStationEvidence(candidate.station as string)}>
                  WHY THIS STATION?
                </button>
              </div>
            ) : (
              <div className="px-4 py-4">
                <NotAvailable reason="No candidate constraint has been identified for this dataset." />
              </div>
            )}
          </Panel>

          <Panel title="Advisory action" subtitle="Top recommendation">
            {recommendations?.recommendations?.[0] ? (
              <button
                type="button"
                onClick={() => onRecommendationEvidence(recommendations.recommendations[0] as unknown as Recommendation)}
                className="flex w-full flex-col gap-1.5 px-4 py-3 text-left transition-colors hover:bg-panel-2/50"
              >
                <span className="text-2xs uppercase tracking-[0.12em] text-cyan">
                  {recommendations.recommendations[0].action_type.replace(/_/g, " ")}
                </span>
                <span className="text-xs text-ink">{recommendations.recommendations[0].title}</span>
                <span className="text-2xs text-ink-3">
                  {recommendations.recommendations[0].evidence_quality.replace(/_/g, " ")} · advisory only
                </span>
              </button>
            ) : (
              <div className="px-4 py-4">
                <NotAvailable reason="No recommendations generated. Open the recommendations section below and generate them from the current artifacts." />
              </div>
            )}
          </Panel>
        </div>
      </div>

      <div className="flex flex-col divide-y divide-line border border-line">
        <CollapsibleSection
          id="processing"
          label="Data processing & models"
          icon={<Layers size={12} aria-hidden />}
          open={openSection === "processing"}
          onToggle={() => setOpenSection(openSection === "processing" ? null : "processing")}
        >
          <DataProcessingPanel analysis={analysis} ml={ml} contract={contract} />
        </CollapsibleSection>
        <CollapsibleSection
          id="stations"
          label="Station constraint ranking"
          icon={<Activity size={12} aria-hidden />}
          open={openSection === "stations"}
          onToggle={() => setOpenSection(openSection === "stations" ? null : "stations")}
        >
          <BottleneckPanel onInspect={(finding: BottleneckFinding) => onStationEvidence(finding.station)} />
        </CollapsibleSection>
        <CollapsibleSection
          id="rootcause"
          label="Root-cause analysis"
          icon={<GitBranch size={12} aria-hidden />}
          open={openSection === "rootcause"}
          onToggle={() => setOpenSection(openSection === "rootcause" ? null : "rootcause")}
        >
          <RootCausePanel onInspect={onFactorEvidence} />
        </CollapsibleSection>
        <CollapsibleSection
          id="economics"
          label="Economics & assumptions"
          icon={<Sigma size={12} aria-hidden />}
          open={openSection === "economics"}
          onToggle={() => setOpenSection(openSection === "economics" ? null : "economics")}
        >
          <EconomicPanel />
        </CollapsibleSection>
        <CollapsibleSection
          id="whatif"
          label="What-if simulator"
          icon={<FlaskConical size={12} aria-hidden />}
          open={openSection === "whatif"}
          onToggle={() => setOpenSection(openSection === "whatif" ? null : "whatif")}
        >
          <WhatIfSimulator />
        </CollapsibleSection>
        <CollapsibleSection
          id="recommendations"
          label="Recommendations"
          icon={<Sparkles size={12} aria-hidden />}
          open={openSection === "recommendations"}
          onToggle={() => setOpenSection(openSection === "recommendations" ? null : "recommendations")}
        >
          <RecommendationPanel onInspect={onRecommendationEvidence} />
        </CollapsibleSection>
      </div>
    </div>
  );
}

function DataProcessingPanel({
  analysis,
  ml,
  contract,
}: {
  analysis: ReturnType<typeof useSession>["analysis"];
  ml: ReturnType<typeof useSession>["ml"];
  contract: ReturnType<typeof useSession>["contract"];
}) {
  if (!analysis) {
    return (
      <div className="px-4 py-4">
        <NotAvailable reason="No processing analysis is loaded for the active dataset." />
      </div>
    );
  }

  const flowStages = [
    ...analysis.stages.map((stage) => ({
      id: stage.id,
      label: stage.label.replace(/ &.*$/, "").replace(/ .*$/, ""),
      status: stage.status,
      duration_ms: stage.duration_s !== null ? stage.duration_s * 1000 : null,
      detail: stage.detail ? stage.detail.slice(0, 24) : null,
    })),
  ];
  if (ml) {
    flowStages.push({
      id: "model_training",
      label: "Models",
      status: ml.status === "complete" ? "complete" : "failed",
      duration_ms: ml.total_training_seconds !== undefined ? ml.total_training_seconds * 1000 : null,
      detail: `${ml.models.filter((model) => model.status === "READY").length} ready`,
    });
  }

  const readyModels = (ml?.models ?? []).filter((model) => model.status === "READY");

  return (
    <div className="flex flex-col">
      <div className="px-4 py-3">
        <p className="label mb-2">Pipeline stages (real durations)</p>
        <PipelineFlow stages={flowStages} />
      </div>

      <div className="grid grid-cols-2 gap-px border-t border-line bg-line sm:grid-cols-4">
        <div className="bg-bg-2/80 px-4 py-2.5">
          <p className="label">Rows ingested</p>
          <p className="mono-value text-sm text-ink">{contract ? contract.summary.total_rows.toLocaleString() : "—"}</p>
        </div>
        <div className="bg-bg-2/80 px-4 py-2.5">
          <p className="label">Tables</p>
          <p className="mono-value text-sm text-ink">{analysis.tables.length}</p>
        </div>
        <div className="bg-bg-2/80 px-4 py-2.5">
          <p className="label">Derived features</p>
          <p className="mono-value text-sm text-ink">{analysis.features.derived_features.length}</p>
        </div>
        <div className="bg-bg-2/80 px-4 py-2.5">
          <p className="label">Models ready</p>
          <p className="mono-value text-sm text-ink">{readyModels.length}</p>
        </div>
      </div>

      <div className="border-t border-line">
        <p className="label px-4 pt-3">Trained models and measured test performance</p>
        {readyModels.length === 0 ? (
          <div className="px-4 py-3">
            <NotAvailable reason="No predictive targets were supported by this dataset." />
          </div>
        ) : (
          <ul className="divide-y divide-line">
            {readyModels.slice(0, 12).map((model) => {
              const r2 = (model.test_metrics as { r2?: number | null }).r2;
              const rmse = (model.test_metrics as { rmse?: number | null }).rmse;
              return (
                <li key={model.model_id} className="flex items-center justify-between gap-3 px-4 py-2.5">
                  <div className="min-w-0">
                    <p className="truncate text-xs text-ink">
                      {model.target} <span className="text-ink-3">← {model.input}</span>
                    </p>
                    <p className="text-2xs text-ink-3">
                      {model.model_type} · {model.candidates.length} candidate(s) compared
                    </p>
                  </div>
                  <div className="shrink-0 text-right font-mono text-2xs text-ink-2">
                    {r2 !== undefined && r2 !== null && <p>R² {formatNumber(r2, 4)}</p>}
                    {rmse !== undefined && rmse !== null && <p>RMSE {formatNumber(rmse, 2)}</p>}
                  </div>
                </li>
              );
            })}
          </ul>
        )}
        <p className="border-t border-line px-4 py-2 text-2xs leading-relaxed text-ink-3">
          Models are trained once per uploaded dataset on leakage-safe splits; metrics shown are measured on the
          untouched test split. Anomaly states and model importance from these models feed the root-cause evidence.
        </p>
      </div>
    </div>
  );
}

function MiniStat({
  label,
  value,
  unit,
  hint,
  unavailableReason,
}: {
  label: string;
  value: string | null;
  unit?: string;
  hint?: string;
  unavailableReason: string;
}) {
  return (
    <div className="flex flex-col gap-1 px-4 py-3" title={hint}>
      <span className="label">{label}</span>
      {value ? (
        <span className="mono-value text-base text-ink">
          {value}
          {unit && <span className="ml-1 text-2xs text-ink-3">{unit}</span>}
        </span>
      ) : (
        <span className="flex items-baseline gap-1.5">
          <span className="mono-value text-xs text-ink-3">NOT AVAILABLE</span>
          <span className="truncate text-2xs text-ink-3">{unavailableReason}</span>
        </span>
      )}
    </div>
  );
}

function CollapsibleSection({
  label,
  icon,
  open,
  onToggle,
  children,
}: {
  id: string;
  label: string;
  icon: React.ReactNode;
  open: boolean;
  onToggle: () => void;
  children: React.ReactNode;
}) {
  return (
    <div>
      <button
        type="button"
        onClick={onToggle}
        aria-expanded={open}
        className="flex w-full items-center gap-2 px-4 py-2.5 text-left transition-colors hover:bg-panel-2/40"
      >
        {open ? <ChevronDown size={12} className="text-ink-3" aria-hidden /> : <ChevronRight size={12} className="text-ink-3" aria-hidden />}
        <span className="text-ink-3">{icon}</span>
        <span className="text-xs font-semibold uppercase tracking-[0.12em] text-ink-2">{label}</span>
      </button>
      {open && <div className="border-t border-line">{children}</div>}
    </div>
  );
}
