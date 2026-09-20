import { motion } from "framer-motion";
import { useEffect, useState } from "react";

import { useSession } from "../session/SessionContext";
import { AnimatedNumber, HudPanel } from "./neurax/Motion";
import { DataGap } from "./neurax/DataGap";
import { EvidenceBadge } from "./neurax/EvidenceBadge";
import { IndustrialEventFeed } from "./neurax/IndustrialEventFeed";
import { InvestigationReplay } from "./neurax/InvestigationReplay";
import { ReviewWorkspace } from "./neurax/ReviewWorkspace";

const STATUS_TONE: Record<string, string> = {
  COMPLETE: "border-ok/40 text-ok",
  REVIEW_REQUIRED: "border-warn/40 text-warn",
  DATA_GAP: "border-line-2 text-ink-3",
  PARTIAL: "border-cyan/40 text-cyan",
};

const DECISION_TONE: Record<string, string> = {
  PASS: "text-ok",
  DEFECT: "text-bad",
  REVIEW: "text-warn",
};

/** 04 — investigation history + the human review queue. */
export function InvestigationHistory({ onGoInspection, reviewRequest = 0 }: { onGoInspection: () => void; reviewRequest?: number }) {
  const { investigations, investigation, loadInvestigation, refreshInvestigations, loadInspection, reviewQueue } = useSession();
  const [tab, setTab] = useState<"investigations" | "review">("investigations");
  const [selectedId, setSelectedId] = useState<string | null>(null);

  useEffect(() => {
    if (reviewRequest > 0) setTab("review");
  }, [reviewRequest]);

  useEffect(() => {
    void refreshInvestigations();
  }, [refreshInvestigations]);

  useEffect(() => {
    if (!selectedId && investigations.length > 0) {
      setSelectedId(investigations[0].investigation_id);
    }
  }, [investigations, selectedId]);

  useEffect(() => {
    if (selectedId && investigation?.investigation_id !== selectedId) {
      void loadInvestigation(selectedId);
    }
  }, [selectedId, investigation, loadInvestigation]);

  return (
    <div className="flex flex-col gap-3 p-3">
      <nav className="flex items-stretch gap-px bg-line/40" aria-label="History sections">
        <button
          type="button"
          onClick={() => setTab("investigations")}
          aria-current={tab === "investigations" ? "page" : undefined}
          className={`relative flex flex-1 items-center justify-center gap-2 px-4 py-2.5 text-2xs font-semibold uppercase tracking-[0.12em] transition-colors ${
            tab === "investigations" ? "bg-panel-2/90 text-cyan" : "bg-panel/60 text-ink-3 hover:text-ink-2"
          }`}
        >
          Investigations
          {investigations.length > 0 && <span className="font-mono text-[9px] text-ink-3">({investigations.length})</span>}
          {tab === "investigations" && <motion.span layoutId="history-tab" className="absolute inset-x-0 bottom-0 h-px bg-cyan" />}
        </button>
        <button
          type="button"
          onClick={() => setTab("review")}
          aria-current={tab === "review" ? "page" : undefined}
          className={`relative flex flex-1 items-center justify-center gap-2 px-4 py-2.5 text-2xs font-semibold uppercase tracking-[0.12em] transition-colors ${
            tab === "review" ? "bg-panel-2/90 text-warn" : "bg-panel/60 text-ink-3 hover:text-ink-2"
          }`}
        >
          Human review
          {reviewQueue.length > 0 && <span className="font-mono text-[9px] text-warn">({reviewQueue.length})</span>}
          {tab === "review" && <motion.span layoutId="history-tab" className="absolute inset-x-0 bottom-0 h-px bg-warn" />}
        </button>
      </nav>

      {tab === "review" ? (
        <HudPanel title="Human review queue" subtitle="actual review images · AI result · explicit reasons · human decision">
          <ReviewWorkspace onOpenInspection={onGoInspection} />
        </HudPanel>
      ) : (
        <div className="grid gap-3 xl:grid-cols-[380px_minmax(0,1fr)]">
      <HudPanel
        title="Investigation history"
        subtitle="stored on the backend — every stage carries its epistemic status"
        actions={
          <button type="button" className="btn-ghost !px-2 !py-1" onClick={() => void refreshInvestigations()}>
            Refresh
          </button>
        }
      >
        {investigations.length === 0 ? (
          <div className="px-4 py-3">
            <DataGap
              title="No investigations recorded yet"
              reason="Investigations are created automatically when the automated stream produces a DEFECT or REVIEW decision (auto investigation must be on). Start the stream in the Command Center."
              action={
                <button type="button" className="btn-ghost !px-2.5 !py-1" onClick={onGoInspection}>
                  Open inspection
                </button>
              }
            />
          </div>
        ) : (
          <ul className="max-h-[70vh] overflow-y-auto">
            {investigations.map((entry) => (
              <li key={entry.investigation_id}>
                <button
                  type="button"
                  onClick={() => setSelectedId(entry.investigation_id)}
                  className={`flex w-full flex-col gap-1 border-b border-line/40 px-4 py-3 text-left transition-colors hover:bg-panel-2/40 ${
                    selectedId === entry.investigation_id ? "bg-cyan/5" : ""
                  }`}
                >
                  <span className="flex w-full items-center justify-between gap-2">
                    <span className={`font-mono text-2xs ${DECISION_TONE[entry.decision] ?? "text-ink-2"}`}>
                      {entry.decision} · {entry.predicted_class}
                    </span>
                    <span className={`chip ${STATUS_TONE[entry.status] ?? "border-line text-ink-3"}`}>
                      {entry.status.replace(/_/g, " ")}
                    </span>
                  </span>
                  <span className="truncate text-2xs text-ink-2">{entry.filename ?? entry.inspection_id}</span>
                  <span className="flex flex-wrap items-center gap-x-3 gap-y-0.5 text-[9px] text-ink-3">
                    <span className="font-mono">{new Date(entry.generated_at).toLocaleString("en-GB", { hour12: false })}</span>
                    <span>{entry.stage_summary.complete} complete</span>
                    {entry.stage_summary.data_gap > 0 && <span>{entry.stage_summary.data_gap} data gap</span>}
                    {entry.stage_summary.awaiting_input > 0 && <span>{entry.stage_summary.awaiting_input} awaiting input</span>}
                    {entry.top_action && <span className="truncate text-cyan">→ {entry.top_action}</span>}
                  </span>
                </button>
              </li>
            ))}
          </ul>
        )}
      </HudPanel>

      <div className="flex min-w-0 flex-col gap-3">
        <HudPanel
          title="Investigation replay"
          subtitle={investigation ? `${investigation.investigation_id} · ${investigation.total_duration_s.toFixed(2)} s` : "select an investigation"}
          actions={
            investigation ? (
              <span className={`chip ${STATUS_TONE[investigation.status] ?? "border-line text-ink-3"}`}>
                {investigation.status.replace(/_/g, " ")}
              </span>
            ) : null
          }
        >
          {investigation ? (
            <InvestigationReplay
              record={investigation}
              onOpenInspection={(inspectionId) => {
                void loadInspection(inspectionId);
                onGoInspection();
              }}
            />
          ) : (
            <p className="px-4 py-3 text-2xs text-ink-3">Select an investigation to replay its stage chain.</p>
          )}
        </HudPanel>

        {investigation && (
          <>
            <HudPanel title="Decision chain summary" subtitle="inspection → evidence → action">
              <div className="grid gap-px bg-line/40 sm:grid-cols-2 lg:grid-cols-4">
                <SummaryStat label="decision" value={investigation.decision} tone={DECISION_TONE[investigation.decision]} />
                <SummaryStat label="class" value={investigation.predicted_class ?? "—"} />
                <SummaryStat
                  label="confidence"
                  value={investigation.confidence !== null ? `${(investigation.confidence * 100).toFixed(1)}%` : "—"}
                  animated={investigation.confidence !== null ? investigation.confidence * 100 : null}
                />
                <SummaryStat label="novelty" value={investigation.novelty_status ?? "—"} />
              </div>
              <div className="flex flex-col gap-2 px-4 py-3">
                {investigation.stages.map((stage) => (
                  <motion.div
                    key={stage.id}
                    initial={{ opacity: 0, y: 4 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ duration: 0.25 }}
                    className="flex flex-wrap items-center gap-2 border-b border-line/40 pb-1.5 last:border-b-0 last:pb-0"
                  >
                    <span className="w-40 shrink-0 text-2xs font-medium text-ink-2">{stage.label}</span>
                    <span className={`chip ${STATUS_TONE[stage.status] ?? "border-line text-ink-3"}`}>{stage.status.replace(/_/g, " ")}</span>
                    <EvidenceBadge status={stage.epistemic} />
                    <span className="min-w-0 flex-1 truncate text-2xs text-ink-3">{stage.summary}</span>
                  </motion.div>
                ))}
              </div>
              {investigation.limitations.length > 0 && (
                <ul className="border-t border-line/60 px-4 py-2">
                  {investigation.limitations.map((limitation) => (
                    <li key={limitation} className="text-2xs leading-relaxed text-ink-3">
                      {limitation}
                    </li>
                  ))}
                </ul>
              )}
            </HudPanel>

            <HudPanel title="Industrial event feed" subtitle="events from this session">
              <IndustrialEventFeed />
            </HudPanel>
          </>
        )}
      </div>
      </div>
      )}
    </div>
  );
}

function SummaryStat({ label, value, tone, animated }: { label: string; value: string; tone?: string; animated?: number | null }) {
  return (
    <div className="flex flex-col gap-0.5 bg-panel/70 px-4 py-3">
      <span className="label">{label}</span>
      {animated !== undefined && animated !== null ? (
        <AnimatedNumber value={animated} digits={1} suffix="%" className={`text-lg ${tone ?? "text-ink"}`} />
      ) : (
        <span className={`font-mono text-sm ${tone ?? "text-ink"}`}>{value}</span>
      )}
    </div>
  );
}
