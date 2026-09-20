import { motion, useReducedMotion } from "framer-motion";
import { useCallback } from "react";
import { AlertTriangle, ArrowRight, CircleDot, ScanSearch } from "lucide-react";

import { API_BASE } from "../api/client";
import { useSession } from "../session/SessionContext";
import type { EvidenceItem } from "./EvidenceDrawer";
import { AutomationControl } from "./neurax/AutomationControl";
import { AnimatedNumber, HudPanel, MotionSection } from "./neurax/Motion";
import { DataCoverage } from "./neurax/DataCoverage";
import { DecisionState, type Decision } from "./neurax/DecisionState";
import { EvidenceBadge } from "./neurax/EvidenceBadge";
import { AutomationPrinciple, EvaluationCoverage } from "./neurax/EvaluationCoverage";
import { IndustrialEventFeed } from "./neurax/IndustrialEventFeed";
import { NeuraxDifference } from "./neurax/NeuraxDifference";
import { NoveltyGauge } from "./neurax/NoveltyGauge";
import { ProbabilityBars } from "./neurax/ProbabilityBars";
import { ProductionStream } from "./neurax/ProductionStream";
import { ReviewQueue, ReviewStatsPanel } from "./neurax/ReviewQueue";

const DECISION_TONE: Record<string, string> = {
  PASS: "text-ok text-glow-ok",
  DEFECT: "text-bad text-glow-bad",
  REVIEW: "text-warn text-glow-warn",
};

const STAGE_RAIL = [
  { id: "received", label: "Inspection" },
  { id: "classifying", label: "Classification" },
  { id: "localizing", label: "Localization" },
  { id: "checking_robustness", label: "Robustness" },
  { id: "process_correlation", label: "Process link" },
  { id: "root_cause", label: "Root cause" },
  { id: "bottleneck", label: "Bottleneck" },
  { id: "impact", label: "Impact" },
  { id: "what_if", label: "What-if" },
  { id: "recommendation", label: "Action" },
];

const STATUS_TONE: Record<string, string> = {
  COMPLETE: "border-ok/40 text-ok",
  REVIEW: "border-warn/40 text-warn",
  DATA_GAP: "border-line-2 text-ink-3",
  AWAITING_INPUT: "border-warn/40 text-warn",
  FAILED: "border-bad/40 text-bad",
  PARTIAL: "border-cyan/40 text-cyan",
};

const STATUS_META: Record<string, { tone: string; word: string; dot: string }> = {
  COMPLETE: { tone: "text-ok", word: "COMPLETE", dot: "bg-ok" },
  REVIEW: { tone: "text-warn", word: "REVIEW REQUIRED", dot: "bg-warn" },
  PARTIAL: { tone: "text-warn", word: "PARTIAL", dot: "bg-warn" },
  DATA_GAP: { tone: "text-warn", word: "DATA GAP", dot: "bg-warn" },
  AWAITING_INPUT: { tone: "text-warn", word: "INPUT REQUIRED", dot: "bg-warn" },
  FAILED: { tone: "text-bad", word: "FAILED", dot: "bg-bad" },
  WAITING: { tone: "text-ink-3", word: "WAITING", dot: "bg-idle" },
};

/** 01 — the active industrial event dominates this screen. */
export function CommandCenter({
  onGoInspection,
  onGoAnalysis,
  onGoHistory,
  onGoReview,
  onOpenEvidence,
  onAddProcessData,
}: {
  onGoInspection: () => void;
  onGoAnalysis: () => void;
  onGoHistory: () => void;
  onGoReview: () => void;
  onOpenEvidence: (title: string, subtitle: string, items: EvidenceItem[], limitations?: string[]) => void;
  onAddProcessData: () => void;
}) {
  const { inspection, investigation, investigating, recommendations, bottleneck, baseline, stream, autoInvestigation, reviewStats, reviewQueue } = useSession();
  const reduceMotion = useReducedMotion();
  const decision = (inspection?.decision ?? null) as Decision | null;
  const pendingReview = reviewStats?.pending_review ?? reviewQueue.length;

  const openStageEvidence = useCallback(
    (stage: { id: string; label: string; status: string; summary: string; detail?: string | null; required?: string[]; available?: string[] }) => {
      const items: EvidenceItem[] = [
        {
          statement: stage.summary || "no result recorded for this stage",
          detail: stage.detail ?? "",
          source_artifact: `investigations/${investigation?.investigation_id ?? ""}/stages/${stage.id}`,
          epistemic_status: stage.status === "DATA_GAP" || stage.status === "AWAITING_INPUT" ? "DATA_GAP" : "CALCULATED",
        },
      ];
      if (stage.available?.length) {
        items.push({
          statement: "Inputs available to this stage",
          detail: stage.available.join(", "),
          source_artifact: "investigation/stage inputs",
          epistemic_status: "OBSERVED",
        });
      }
      if (stage.required?.length) {
        items.push({
          statement: "Inputs this stage still requires",
          detail: stage.required.join(", "),
          source_artifact: "investigation/stage inputs",
          epistemic_status: "DATA_GAP",
        });
      }
      onOpenEvidence(`${stage.label} — ${STATUS_META[stage.status]?.word ?? stage.status}`, investigation?.investigation_id ?? "", items, [
        "The capability exists; the current input set is insufficient where a stage reports DATA GAP.",
      ]);
    },
    [investigation, onOpenEvidence],
  );

  return (
    <div className="flex flex-col gap-3 p-3">
      {pendingReview > 0 && (
        <MotionSection>
          <div className="flex flex-wrap items-center justify-between gap-3 border border-warn/50 bg-warn/10 px-4 py-3">
            <p className="flex items-center gap-2 font-mono text-sm uppercase tracking-[0.12em] text-warn">
              <AlertTriangle size={14} aria-hidden />
              {pendingReview} inspection(s) require human review
            </p>
            <button type="button" className="btn border-warn/50 bg-warn/10 text-warn !px-3 !py-1.5" onClick={onGoReview}>
              Review queue
              <ArrowRight size={11} aria-hidden />
            </button>
          </div>
        </MotionSection>
      )}
      <div className="flex flex-wrap items-center justify-between gap-3 border border-line/60 bg-panel/60 px-3 py-2.5">
        <AutomationControl />
        <div className="flex items-center gap-3 text-2xs text-ink-3">
          <span className="flex items-center gap-1.5">
            <CircleDot size={10} className={stream?.running ? "text-ok" : "text-idle"} aria-hidden />
            {stream?.running ? "automation running" : "automation idle"}
          </span>
          <span className="hidden sm:inline">{autoInvestigation ? "auto investigation armed" : "auto investigation off"}</span>
          <button type="button" className="btn-ghost !px-2 !py-1" onClick={onGoHistory}>
            Investigation history
            <ArrowRight size={10} aria-hidden />
          </button>
        </div>
      </div>

      <div className="grid gap-3 xl:grid-cols-[300px_minmax(0,1fr)_340px]">
        <MotionSection className="flex min-w-0 flex-col gap-3">
          <HudPanel title="Production stream" subtitle="real frames, deterministic order" className="min-h-0">
            <ProductionStream onSelectInspection={onGoInspection} />
          </HudPanel>
          <HudPanel title="Data coverage" subtitle="capability vs what the current data allows">
            <DataCoverage
              onAddProcessData={onAddProcessData}
              onAddAssumptions={onGoAnalysis}
              onViewJoinFields={() =>
                onOpenEvidence(
                  "Image → process join",
                  "what a valid join requires",
                  [
                    {
                      statement: "Per-unit join key not available in the inspection dataset",
                      detail: "Inspection images carry no batch, station, unit or timestamp metadata.",
                      source_artifact: "vision/inspection/process_link",
                      epistemic_status: "NOT_AVAILABLE",
                    },
                    {
                      statement: "Required fields for a valid join",
                      detail: "unit ID · batch ID · station ID · timestamp / production run window",
                      source_artifact: "investigations/stage inputs",
                      epistemic_status: "DATA_GAP",
                    },
                  ],
                  ["With a valid join key, inspection events could be linked to station utilization, queue and cycle metrics for root-cause correlation."],
                )
              }
            />
          </HudPanel>
        </MotionSection>

        <MotionSection delay={0.05} className="flex min-w-0 flex-col gap-3">
          <HudPanel
            title="Active event"
            subtitle={inspection ? `${inspection.filename ?? inspection.inspection_id} · ${inspection.generated_at}` : "waiting for the stream"}
            className="min-h-0"
            actions={
              <button type="button" className="btn-primary !px-3 !py-1.5" onClick={onGoInspection}>
                <ScanSearch size={12} aria-hidden />
                Open inspection
              </button>
            }
          >
            <div className="flex flex-col gap-3 px-4 py-4">
              {inspection ? (
                <>
                  <div className="grid gap-3 sm:grid-cols-[minmax(0,240px)_minmax(0,1fr)]">
                    <div className="relative border border-line-2 bg-black/50">
                      <img
                        src={`${API_BASE}/api/vision/inspect/${inspection.inspection_id}/image`}
                        alt="Current inspected unit"
                        className="h-48 w-full object-contain"
                      />
                      {decision && (
                        <motion.span
                          key={decision}
                          initial={reduceMotion ? false : { opacity: 0, scale: 1.6, rotate: -12 }}
                          animate={{ opacity: 1, scale: 1, rotate: -6 }}
                          transition={{ type: "spring", stiffness: 320, damping: 18 }}
                          className={`absolute right-2 top-2 border-2 px-2 py-0.5 font-mono text-xs tracking-[0.14em] ${DECISION_TONE[decision] ?? "text-ink"}`}
                        >
                          {decision}
                        </motion.span>
                      )}
                    </div>
                    <div className="flex flex-col gap-2">
                      <div className="flex flex-wrap items-end gap-x-6 gap-y-2">
                        <p className={`font-mono text-4xl font-semibold tracking-[0.12em] ${decision ? DECISION_TONE[decision] : "text-ink-3"}`}>
                          {decision ?? "—"}
                        </p>
                        <div>
                          <p className="label">assigned class</p>
                          <p className="font-mono text-sm text-ink">{inspection.prediction.predicted_class}</p>
                        </div>
                        <div>
                          <p className="label">calibrated confidence</p>
                          <p className="font-mono text-sm text-ink">
                            <AnimatedNumber value={inspection.confidence.value * 100} digits={1} suffix="%" />
                          </p>
                        </div>
                      </div>
                      <ProbabilityBars probabilities={inspection.class_probabilities} winner={inspection.prediction.predicted_class} />
                      <p className="text-2xs leading-relaxed text-ink-3">
                        {inspection.review_reason ?? "Decision thresholds applied to calibrated output; localization and robustness checks recorded below."}
                      </p>
                    </div>
                  </div>

                  <div className="border-t border-line/60 pt-2">
                    <NoveltyGauge
                      noveltyScore={inspection.anomaly_score.novelty_score}
                      noveltyStatus={inspection.anomaly_score.novelty_status}
                      anomalyScore={inspection.anomaly_score.value}
                      decision={inspection.decision}
                      gate={undefined}
                    />
                  </div>
                </>
              ) : (
                <div className="flex flex-col items-center gap-3 py-10 text-center">
                  <ScanSearch size={22} className="text-ink-3" aria-hidden />
                  <p className="text-sm text-ink-2">No active inspection yet</p>
                  <p className="max-w-md text-2xs leading-relaxed text-ink-3">
                    Press <span className="text-cyan">Start automated inspection</span> — real frames from the image
                    dataset flow through the trained pipeline, and every actionable decision automatically triggers an
                    investigation.
                  </p>
                </div>
              )}
            </div>
          </HudPanel>

          <HudPanel
            title="AI investigation pipeline"
            subtitle={investigation ? `investigation ${investigation.investigation_id}` : "automatic chain from inspection to recommendation"}
            actions={investigating ? <span className="chip border-cyan/50 bg-cyan/10 text-cyan">INVESTIGATING…</span> : null}
          >
            <div className="flex flex-col gap-3 px-4 py-3">
              <ol className="flex flex-col gap-0.5">
                {STAGE_RAIL.map((stage, index) => {
                  const record = investigation?.stages.find((entry) => entry.id === stage.id) ?? null;
                  const status = record?.status ?? "WAITING";
                  const meta = STATUS_META[status] ?? STATUS_META.WAITING;
                  const result = record?.summary ?? (stage.id === "received" ? null : "waiting for upstream evidence");
                  return (
                    <motion.li
                      key={stage.id}
                      initial={reduceMotion ? false : { opacity: 0, x: -6 }}
                      animate={{ opacity: 1, x: 0 }}
                      transition={{ duration: 0.25, delay: index * 0.03 }}
                    >
                      <button
                        type="button"
                        onClick={() =>
                          openStageEvidence({
                            id: stage.id,
                            label: stage.label,
                            status,
                            summary: result ?? "no inspection yet",
                            detail: record?.detail,
                            required: record?.required_inputs,
                            available: record?.available_inputs,
                          })
                        }
                        className="flex w-full items-start gap-2.5 rounded-sm px-2 py-1.5 text-left transition-colors hover:bg-panel-2/40"
                      >
                        <span className="mt-1 flex w-6 shrink-0 items-center gap-1">
                          <span className="font-mono text-[9px] text-ink-3">{String(index + 1).padStart(2, "0")}</span>
                          <span className={`h-1.5 w-1.5 ${meta.dot}`} aria-hidden />
                        </span>
                        <span className="min-w-0 flex-1">
                          <span className="flex flex-wrap items-center gap-2">
                            <span className={`text-2xs font-semibold uppercase tracking-[0.1em] ${status === "COMPLETE" ? "text-ink" : "text-ink-2"}`}>
                              {stage.label}
                            </span>
                            <span className={`font-mono text-[9px] tracking-[0.08em] ${meta.tone}`}>{meta.word}</span>
                          </span>
                          <span className="mt-0.5 block truncate text-2xs text-ink-3">{result}</span>
                        </span>
                      </button>
                    </motion.li>
                  );
                })}
              </ol>

              {investigation ? (
                <div className="flex flex-col gap-1.5 border-t border-line/60 pt-2">
                  <p className="text-2xs text-ink-3">
                    investigation status <span className="font-mono text-ink-2">{investigation.status.replace(/_/g, " ")}</span> ·{" "}
                    {investigation.stage_summary.complete} stage(s) completed ·{" "}
                    {investigation.stage_summary.data_gap + investigation.stage_summary.awaiting_input + investigation.stage_summary.partial} stage(s) require
                    additional data · {investigation.total_duration_s.toFixed(2)} s
                  </p>
                  <ul className="flex flex-col gap-0.5">
                    {investigation.stages
                      .filter((stage) => ["DATA_GAP", "AWAITING_INPUT", "PARTIAL"].includes(stage.status))
                      .map((stage) => (
                        <li key={stage.id} className="flex items-center gap-2 text-2xs text-warn">
                          <span className="h-1 w-1 shrink-0 rounded-full bg-warn" aria-hidden />
                          {stage.label}: {stage.required_inputs?.join(", ") || stage.summary.toLowerCase()}
                        </li>
                      ))}
                  </ul>
                  <button type="button" className="w-fit text-2xs text-cyan hover:underline" onClick={onGoHistory}>
                    replay →
                  </button>
                </div>
              ) : (
                <p className="border-t border-line/60 pt-2 text-2xs leading-relaxed text-ink-3">
                  The investigation chain runs automatically on DEFECT / REVIEW decisions when auto investigation is on.
                  PASS decisions are recorded without an investigation. Downstream stages below report what input they
                  still need — the capability exists, the data decides.
                </p>
              )}
            </div>
          </HudPanel>
        </MotionSection>

        <MotionSection delay={0.1} className="flex min-w-0 flex-col gap-3">
          <HudPanel title="Decision" subtitle="thresholds on calibrated output">
            <DecisionState
              decision={decision}
              reason={inspection?.review_reason ?? null}
              confidence={inspection?.confidence.value ?? null}
              thresholds={null}
            />
          </HudPanel>
          <HudPanel title="Process context" subtitle="dataset-level, honest about joins">
            <div className="flex flex-col gap-2 px-4 py-3">
              <p className="text-2xs leading-relaxed text-ink-3">
                {inspection?.process_link.reason ??
                  "Inspection images carry no batch/station/unit metadata, so per-unit process correlation is not possible. Dataset-level process analysis is available in Process Intelligence."}
              </p>
              <div className="grid grid-cols-2 gap-px bg-line/40">
                <div className="flex flex-col gap-0.5 bg-panel/70 px-3 py-2">
                  <span className="label">candidate constraint</span>
                  <span className="font-mono text-xs text-ink">{bottleneck?.candidate_bottleneck.station ?? "not analyzed"}</span>
                </div>
                <div className="flex flex-col gap-0.5 bg-panel/70 px-3 py-2">
                  <span className="label">economic baseline</span>
                  <span className="font-mono text-xs text-ink">{baseline ? "computed" : "assumptions required"}</span>
                </div>
                <div className="flex flex-col gap-0.5 bg-panel/70 px-3 py-2">
                  <span className="label">recommendations</span>
                  <span className="font-mono text-xs text-ink">{recommendations?.count ?? 0}</span>
                </div>
                <div className="flex flex-col gap-0.5 bg-panel/70 px-3 py-2">
                  <span className="label">dataset</span>
                  <span className="truncate font-mono text-xs text-ink">{baseline?.dataset_id ?? "none loaded"}</span>
                </div>
              </div>
              <button type="button" className="btn-ghost w-fit !px-2.5 !py-1" onClick={onGoAnalysis}>
                Open process intelligence
                <ArrowRight size={10} aria-hidden />
              </button>
            </div>
          </HudPanel>
          <HudPanel title="Industrial event feed" subtitle="business events, not diagnostics">
            <IndustrialEventFeed />
          </HudPanel>
          <HudPanel title="Human review queue" subtitle="AI escalates the uncertain — humans decide">
            <ReviewQueue onOpenInspection={onGoInspection} />
          </HudPanel>
          <HudPanel title="Review statistics" subtitle="auto-resolved vs human review, real values">
            <ReviewStatsPanel />
          </HudPanel>
          {investigation && (
            <HudPanel title="Latest investigation evidence" subtitle={investigation.filename ?? investigation.inspection_id ?? ""}>
              <div className="flex flex-col gap-2 px-4 py-3">
                {investigation.stages
                  .filter((stage) => ["process_correlation", "root_cause", "bottleneck", "impact", "recommendation"].includes(stage.id))
                  .slice(0, 5)
                  .map((stage) => (
                    <div key={stage.id} className="border-b border-line/40 pb-1.5 last:border-b-0 last:pb-0">
                      <span className="flex flex-wrap items-center gap-2">
                        <span className="text-2xs font-medium text-ink-2">{stage.label}</span>
                        <span className={`chip ${STATUS_TONE[stage.status] ?? "border-line text-ink-3"}`}>{stage.status.replace(/_/g, " ")}</span>
                        <EvidenceBadge status={stage.epistemic} />
                      </span>
                      <p className="mt-0.5 text-2xs leading-relaxed text-ink-3">{stage.summary}</p>
                    </div>
                  ))}
              </div>
            </HudPanel>
          )}
        </MotionSection>
      </div>

      <MotionSection delay={0.15}>
        <HudPanel title="The NEURAX difference" subtitle="detection is only the first step">
          <NeuraxDifference />
        </HudPanel>
      </MotionSection>

      <MotionSection delay={0.2}>
        <HudPanel title="Automation principle" subtitle="the core of responsible AI automation">
          <AutomationPrinciple />
        </HudPanel>
      </MotionSection>

      <MotionSection delay={0.25}>
        <HudPanel title="Evaluation coverage" subtitle="where each judging criterion is demonstrated — not a score">
          <EvaluationCoverage />
        </HudPanel>
      </MotionSection>
    </div>
  );
}
