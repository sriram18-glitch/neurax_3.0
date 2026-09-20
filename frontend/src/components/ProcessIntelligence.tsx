import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import { Database, GitBranch, UploadCloud, Workflow } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { useSession } from "../session/SessionContext";
import type { BottleneckFinding, Recommendation, RootCauseFinding } from "../types/api";
import { BottleneckPanel } from "./BottleneckPanel";
import { EconomicPanel } from "./EconomicPanel";
import { AnimatedNumber, HudPanel } from "./neurax/Motion";
import { RankedSignals } from "./neurax/RankedSignals";
import { BottleneckVisualizer } from "./neurax/BottleneckVisualizer";
import { DataGap } from "./neurax/DataGap";
import { EvidenceBadge } from "./neurax/EvidenceBadge";
import { EvidenceGraph } from "./neurax/EvidenceGraph";
import { ImpactFlow } from "./neurax/ImpactFlow";
import { ProcessTimeline } from "./neurax/ProcessTimeline";
import { bottleneckRanked, rootCauseGraph, rootCauseRanked } from "./neurax/adapt";
import { PlantFlow, type FlowNodeState } from "./PlantFlow";
import { RecommendationPanel } from "./RecommendationPanel";
import { RootCausePanel } from "./RootCausePanel";
import { WhatIfSimulator } from "./WhatIfSimulator";

type StageId = "process" | "rootcause" | "flow" | "impact" | "action";

const STAGES: Array<{ id: StageId; index: string; label: string; question: string }> = [
  { id: "process", index: "01", label: "Process", question: "What did the data contain?" },
  { id: "rootcause", index: "02", label: "Root cause", question: "What is associated with the failure?" },
  { id: "flow", index: "03", label: "Flow", question: "Where is the constraint?" },
  { id: "impact", index: "04", label: "Impact", question: "What is it worth?" },
  { id: "action", index: "05", label: "Action", question: "What should be done?" },
];

/** 03 — process intelligence: one connected investigation workspace. */
export function ProcessIntelligence({
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
  const {
    contract,
    analysis,
    ml,
    rootCause,
    bottleneck,
    scenario,
    baseline,
    assumptions,
    recommendationRun,
    busy,
    runBottleneck,
    refreshBaseline,
    refreshTimeline,
    timeline,
    timelineBusy,
  } = useSession();
  const [stage, setStage] = useState<StageId | null>(null);
  const [selectedStation, setSelectedStation] = useState<string | null>(null);
  const reduceMotion = useReducedMotion();

  useEffect(() => {
    if (contract && !timeline && !timelineBusy) void refreshTimeline();
  }, [contract, timeline, timelineBusy, refreshTimeline]);

  const activeStage: StageId = stage ?? (bottleneck ? "flow" : "process");
  const meta = STAGES.find((entry) => entry.id === activeStage) as (typeof STAGES)[number];

  const nodeStates = useMemo<FlowNodeState[]>(() => {
    if (!bottleneck) return [];
    return bottleneck.station_rankings.map((finding) => ({
      station: finding.station,
      tone: finding.station === bottleneck.candidate_bottleneck.station ? "bad" : finding.rank <= 3 ? "warn" : "idle",
      label: finding.evidence_score !== null ? `score ${finding.evidence_score.toFixed(1)}` : "not scored",
      score: finding.evidence_score,
      evidenceQuality: finding.evidence_quality.label,
    }));
  }, [bottleneck]);

  const observedImpact = bottleneck?.what_if_inputs.observed_impact?.observed ?? null;
  const observedEntry = observedImpact ? Object.values(observedImpact)[0] : null;

  const coverageCounts = useMemo(() => {
    const modules = analysis?.coverage?.modules ?? {};
    const counts = new Map<string, number>();
    for (const module of Object.values(modules)) {
      const status = (module as { status?: string }).status ?? "unknown";
      counts.set(status, (counts.get(status) ?? 0) + 1);
    }
    return [...counts.entries()];
  }, [analysis]);

  if (!contract) {
    return (
      <div className="mx-auto flex max-w-xl flex-col items-center gap-4 px-6 py-16 text-center">
        <div className="flex h-10 w-10 items-center justify-center border border-line">
          <Database size={18} className="text-ink-3" aria-hidden />
        </div>
        <h1 className="text-lg font-semibold tracking-tight text-ink">Process data not loaded</h1>
        <p className="max-w-md text-xs leading-relaxed text-ink-2">
          Upload or connect a process dataset to enable process correlation, root-cause hypotheses, flow analysis,
          assumption-based impact and advisory actions. The automated vision stream runs without it.
        </p>
        <button type="button" className="btn-primary" onClick={onUploadClick}>
          <UploadCloud size={12} aria-hidden />
          Upload process dataset
        </button>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-3 p-3">
      <HudPanel
        title={`Process workspace · ${contract.filename}`}
        subtitle={`${contract.summary.total_rows.toLocaleString("en-US")} rows · ${contract.summary.tables} table(s) · ${contract.summary.stations.length} station(s) detected`}
        actions={<span className="chip border-line text-ink-3">{busy ?? `provenance: ${contract.provenance.labels.join(", ")}`}</span>}
      >
        <div className="grid gap-px bg-line/40 sm:grid-cols-2 lg:grid-cols-4">
          <StripStat
            label="Current constraint"
            value={bottleneck?.candidate_bottleneck.station ?? "No candidate constraint"}
            detail={
              bottleneck?.candidate_bottleneck.evidence_score !== null && bottleneck?.candidate_bottleneck.evidence_score !== undefined
                ? `evidence score ${bottleneck.candidate_bottleneck.evidence_score.toFixed(1)} · hypothesis, not proof`
                : bottleneck
                  ? "no station reached the evidence threshold"
                  : "bottleneck analysis not run"
            }
          />
          <StripStat
            label="Observed output rate"
            value={observedEntry ? observedEntry.unconstrained_mean.toLocaleString("en-US", { maximumFractionDigits: 2 }) : "not available"}
            detail={
              observedEntry
                ? `constrained ${observedEntry.constrained_mean.toLocaleString("en-US", { maximumFractionDigits: 2 })} · ${observedEntry.constrained_rows} vs ${observedEntry.unconstrained_rows} rows`
                : "requires an observed comparison in the bottleneck analysis"
            }
          />
          <StripStat
            label="Root-cause top factor"
            value={rootCause?.ranked_findings[0]?.factor ?? "not analyzed"}
            detail={
              rootCause?.ranked_findings[0]?.evidence_score !== null && rootCause?.ranked_findings[0]?.evidence_score !== undefined
                ? `score ${rootCause.ranked_findings[0].evidence_score.toFixed(1)} · ${rootCause.ranked_findings.length} findings · association only`
                : "run the root-cause stage"
            }
          />
          <StripStat
            label="Economic baseline"
            value={
              baseline?.baseline.monthly_contribution.value !== null && baseline?.baseline.monthly_contribution.value !== undefined
                ? `${baseline.baseline.monthly_contribution.value.toLocaleString("en-US", { maximumFractionDigits: 0 })} ${baseline.currency ?? ""}`
                : "assumptions required"
            }
            detail={
              assumptions
                ? `${Object.values(assumptions.assumptions).filter((entry) => entry.value !== null).length} user assumption(s) supplied`
                : "no user assumptions supplied — no economic value is invented"
            }
          />
        </div>
      </HudPanel>

      <nav className="flex items-stretch gap-px overflow-x-auto bg-line/40" aria-label="Analysis stages">
        {STAGES.map((entry) => {
          const active = entry.id === activeStage;
          return (
            <button
              key={entry.id}
              type="button"
              onClick={() => setStage(entry.id)}
              aria-current={active ? "step" : undefined}
              className={`relative flex min-w-[150px] flex-1 flex-col items-start gap-0.5 px-4 py-3 text-left transition-colors ${
                active ? "bg-panel-2/90" : "bg-panel/60 hover:bg-panel-2/60"
              }`}
            >
              <span className={`font-mono text-[9px] ${active ? "text-cyan" : "text-ink-3"}`}>{entry.index}</span>
              <span className={`text-2xs font-semibold uppercase tracking-[0.14em] ${active ? "text-cyan" : "text-ink-2"}`}>{entry.label}</span>
              <span className="truncate text-[9px] text-ink-3">{entry.question}</span>
              {active && <motion.span layoutId="process-stage-underline" className="absolute inset-x-0 bottom-0 h-px bg-cyan" />}
            </button>
          );
        })}
      </nav>

      <AnimatePresence mode="wait" initial={false}>
        <motion.div
          key={activeStage}
          initial={reduceMotion ? false : { opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          exit={reduceMotion ? undefined : { opacity: 0, y: -6 }}
          transition={{ duration: 0.3, ease: [0.22, 1, 0.36, 1] }}
          className="flex flex-col gap-3"
        >
          <header className="flex items-center gap-3 px-1">
            <h2 className="text-sm font-semibold tracking-tight text-ink">{meta.question}</h2>
            <span className="h-px flex-1 bg-line/60" aria-hidden />
            <span className="font-mono text-2xs text-ink-3">
              {meta.index} · {meta.label.toLowerCase()}
            </span>
          </header>

          {activeStage === "process" && (
            <div className="flex flex-col gap-3">
              <HudPanel title="Process timeline" subtitle="binned real series · drift · event rows">
                <ProcessTimeline />
              </HudPanel>
              <div className="grid gap-3 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
                <HudPanel title="Dataset composition" subtitle="from the ingestion profile">
                  <div className="grid grid-cols-2 gap-px bg-line/40 sm:grid-cols-3">
                    <Mini label="rows" value={contract.summary.total_rows} />
                    <Mini label="columns (primary)" value={contract.summary.primary_columns} />
                    <Mini label="tables" value={contract.summary.tables} />
                    <Mini label="stations" value={contract.summary.stations.length} />
                    <Mini label="process models" value={ml?.models.length ?? 0} />
                    <Mini label="model inputs" value={analysis?.model_inputs.length ?? 0} />
                  </div>
                  <div className="flex flex-col gap-2 px-4 py-3">
                    <p className="label">Pipeline coverage</p>
                    <div className="flex flex-wrap gap-1.5">
                      {coverageCounts.length > 0 ? (
                        coverageCounts.map(([status, count]) => (
                          <span key={status} className="chip border-line-2 text-ink-2">
                            {status.replace(/_/g, " ")}: {count}
                          </span>
                        ))
                      ) : (
                        <span className="text-2xs text-ink-3">coverage not reported for this dataset</span>
                      )}
                    </div>
                  </div>
                </HudPanel>
                <HudPanel title="Process map" subtitle="station sequence derived from the data — not assumed">
                  <div className="h-64">
                    <PlantFlow
                      graph={bottleneck?.flow.graph ?? null}
                      nodeStates={nodeStates}
                      onSelect={(station) => {
                        setSelectedStation(station);
                        onStationEvidence(station);
                      }}
                      selected={selectedStation}
                    />
                  </div>
                  <p className="border-t border-line/60 px-4 py-2 text-2xs leading-relaxed text-ink-3">
                    {bottleneck?.flow.graph.rationale ??
                      "Flow ordering appears after the bottleneck analysis runs. No sequence is invented when the data cannot support one."}
                  </p>
                </HudPanel>
              </div>
            </div>
          )}

          {activeStage === "rootcause" && (
            <div className="grid gap-3 xl:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
              <div className="flex min-w-0 flex-col gap-3">
                <RootCausePanel onInspect={onFactorEvidence} />
              </div>
              <div className="flex min-w-0 flex-col gap-3">
                <HudPanel title="Factor associations" subtitle="ranked evidence scores — association, not causation">
                  {rootCause ? (
                    <RankedSignals
                      items={rootCauseRanked(rootCause)}
                      onSelect={(id) => {
                        const finding = rootCause.ranked_findings.find((entry) => entry.factor === id);
                        if (finding) onFactorEvidence(finding);
                      }}
                      selectedId={null}
                    />
                  ) : (
                    <p className="px-4 py-3 text-2xs leading-relaxed text-ink-3">
                      No root-cause analysis for this session yet. Choose a target and run it — the engine scores correlation,
                      mutual information, group difference, temporal precedence, anomaly enrichment and model contribution.
                    </p>
                  )}
                </HudPanel>
                {rootCause && (
                  <HudPanel title="Association graph" subtitle={`${rootCause.factors_analyzed} factors analyzed`}>
                    <EvidenceGraph {...rootCauseGraph(rootCause)} caption="Select a factor to inspect its epistemic status. Drift and event definition shown as computed." />
                  </HudPanel>
                )}
              </div>
            </div>
          )}

          {activeStage === "flow" && (
            <div className="grid gap-3 xl:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
              <div className="flex min-w-0 flex-col gap-3">
                <HudPanel
                  title="Bottleneck evidence"
                  subtitle="why this station — component scores"
                  actions={
                    <button type="button" className="btn-ghost !px-2 !py-1" onClick={() => void runBottleneck()} disabled={Boolean(busy)}>
                      <Workflow size={11} aria-hidden />
                      Run analysis
                    </button>
                  }
                >
                  <BottleneckVisualizer bottleneck={bottleneck} />
                </HudPanel>
                {bottleneck && (
                  <HudPanel title="Constraint ranking" subtitle="evidence score per station">
                    <RankedSignals
                      items={bottleneckRanked(bottleneck)}
                      onSelect={(station) => {
                        setSelectedStation(station);
                        onStationEvidence(station);
                      }}
                      selectedId={selectedStation}
                    />
                  </HudPanel>
                )}
                {bottleneck && (
                  <HudPanel title="Observed impact" subtitle="constrained vs unconstrained observed rows">
                    {observedEntry ? (
                      <div className="flex flex-col gap-2 px-4 py-3">
                        <div className="grid grid-cols-2 gap-px border border-line/60 bg-line/40 sm:grid-cols-4">
                          <Mini label="constrained mean" value={observedEntry.constrained_mean} digits={2} />
                          <Mini label="unconstrained mean" value={observedEntry.unconstrained_mean} digits={2} />
                          <Mini label="difference" value={observedEntry.difference} digits={2} signed />
                          <Mini label="rows (c/u)" value={observedEntry.constrained_rows} hint={`${observedEntry.unconstrained_rows} unconstrained`} />
                        </div>
                        <p className="text-2xs leading-relaxed text-ink-3">
                          {observedEntry.constrained_definition} · {bottleneck.what_if_inputs.observed_impact?.note}
                        </p>
                        <div className="flex flex-wrap gap-1.5">
                          <EvidenceBadge status="OBSERVED" />
                          <EvidenceBadge status="STATISTICAL ASSOCIATION" />
                        </div>
                      </div>
                    ) : (
                      <p className="px-4 py-3 text-2xs leading-relaxed text-ink-3">
                        {bottleneck.what_if_inputs.observed_impact?.reason ??
                          "No observed constrained/unconstrained comparison is available for this dataset."}
                      </p>
                    )}
                  </HudPanel>
                )}
              </div>
              <div className="flex min-w-0 flex-col gap-3">
                <HudPanel title="Station constraint detail" subtitle="progressive disclosure of the ranking evidence">
                  <BottleneckPanel
                    onInspect={(finding: BottleneckFinding) => {
                      setSelectedStation(finding.station);
                      onStationEvidence(finding.station);
                    }}
                  />
                </HudPanel>
              </div>
            </div>
          )}

          {activeStage === "impact" && (
            <div className="flex flex-col gap-3">
              <HudPanel
                title="Impact flow"
                subtitle="observed production → user assumptions → calculated impact"
                actions={
                  <button type="button" className="btn-ghost !px-2 !py-1" onClick={() => void refreshBaseline()} disabled={Boolean(busy)}>
                    Recompute baseline
                  </button>
                }
              >
                <ImpactFlow />
              </HudPanel>
              <div className="grid gap-3 xl:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
                <EconomicPanel />
                <WhatIfSimulator />
              </div>
              {scenario && (
                <HudPanel title="Scenario epistemic status" subtitle={scenario.scenario_id}>
                  <div className="flex flex-wrap items-center gap-2 px-4 py-3">
                    <EvidenceBadge status="SIMULATION" />
                    <EvidenceBadge status={scenario.epistemic_status.replace(/_/g, " ")} />
                    {scenario.warnings.map((warning) => (
                      <span key={warning} className="border border-warn/30 bg-warn/5 px-1.5 py-0.5 text-[9px] text-ink-2">
                        {warning}
                      </span>
                    ))}
                    <span className="text-2xs text-ink-3">Simulated results are assumption-dependent and are not forecasts.</span>
                  </div>
                </HudPanel>
              )}
            </div>
          )}

          {activeStage === "action" && (
            <div className="flex flex-col gap-3">
              {recommendationRun?.decision_summary && (
                <HudPanel title="Decision summary" subtitle="deterministic rule output over stored artifacts">
                  <div className="grid gap-px bg-line/40 sm:grid-cols-2 lg:grid-cols-3">
                    {Object.entries(recommendationRun.decision_summary.situation).map(([key, value]) => (
                      <StripStat key={key} label={key.replace(/_/g, " ")} value={value === null ? "not available" : String(value)} detail="from stored analysis artifacts" />
                    ))}
                  </div>
                </HudPanel>
              )}
              <HudPanel title="Advisory actions" subtitle="deterministic rules — not model guesses">
                <RecommendationPanel onInspect={onRecommendationEvidence} />
              </HudPanel>
            </div>
          )}
        </motion.div>
      </AnimatePresence>

      <p className="px-1 text-2xs leading-relaxed text-ink-3">
        <GitBranch size={10} className="mr-1 inline" aria-hidden />
        Associations are statistical, not causal. Bottlenecks are evidence-based hypotheses. Economic values exist only when
        user assumptions are supplied. NEURAX is advisory — it never controls machinery.
      </p>
    </div>
  );
}

function StripStat({ label, value, detail }: { label: string; value: string; detail: string }) {
  return (
    <div className="flex flex-col gap-0.5 bg-panel/70 px-4 py-3">
      <span className="label">{label}</span>
      <span className="truncate font-mono text-sm text-ink">{value}</span>
      <span className="truncate text-[9px] text-ink-3">{detail}</span>
    </div>
  );
}

function Mini({
  label,
  value,
  digits = 0,
  signed = false,
  hint,
}: {
  label: string;
  value: number;
  digits?: number;
  signed?: boolean;
  hint?: string;
}) {
  return (
    <div className="flex flex-col gap-0.5 bg-panel/70 px-3 py-2.5">
      <span className="label">{label}</span>
      <span className="font-mono text-sm text-ink">
        {signed && value > 0 ? "+" : ""}
        <AnimatedNumber value={value} digits={digits} />
      </span>
      {hint && <span className="text-[9px] text-ink-3">{hint}</span>}
    </div>
  );
}

export { DataGap };
