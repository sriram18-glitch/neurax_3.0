import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import { useCallback, useState } from "react";
import { FolderPlus, History, LayoutDashboard, Play, ScanSearch, Square, Workflow } from "lucide-react";

import { CommandBar } from "./components/CommandBar";
import { CommandCenter } from "./components/CommandCenter";
import { EvidenceDrawer, type EvidenceItem } from "./components/EvidenceDrawer";
import type { OpenEvidence } from "./components/evidence";
import { InspectionStudio } from "./components/InspectionStudio";
import { InvestigationHistory } from "./components/InvestigationHistory";
import { ProcessIntelligence } from "./components/ProcessIntelligence";
import { AddDataModal } from "./components/neurax/AddDataModal";
import { useSession } from "./session/SessionContext";
import { SessionProvider } from "./session/SessionContext";
import { useStreamLoop } from "./session/useStreamLoop";
import type { BottleneckFinding, Recommendation, RootCauseFinding } from "./types/api";

type ViewId = "command" | "inspection" | "process" | "history";

interface AddDataTarget {
  view: ViewId;
  mode?: "auto" | "imageset" | "folder" | "single";
}

const VIEWS: Array<{ id: ViewId; label: string; icon: typeof ScanSearch }> = [
  { id: "command", label: "Command Center", icon: LayoutDashboard },
  { id: "inspection", label: "Inspection", icon: ScanSearch },
  { id: "process", label: "Process Intelligence", icon: Workflow },
  { id: "history", label: "Investigation History", icon: History },
];

interface DrawerState {
  open: boolean;
  title: string;
  subtitle?: string;
  items: EvidenceItem[];
  limitations?: string[];
}

const CLOSED_DRAWER: DrawerState = { open: false, title: "", items: [] };

function Workspace() {
  const session = useSession();
  const { bottleneck, busy, error, errorStage, backendOnline, stream, setAutoInvestigation } = session;
  const [view, setView] = useState<ViewId>("command");
  const [drawer, setDrawer] = useState<DrawerState>(CLOSED_DRAWER);
  const [uploadOpen, setUploadOpen] = useState(false);
  const [addDataOpen, setAddDataOpen] = useState(false);
  const [addDataTarget, setAddDataTarget] = useState<AddDataTarget | null>(null);
  const [reviewRequest, setReviewRequest] = useState(0);
  const [demoActive, setDemoActive] = useState(false);
  const reduceMotion = useReducedMotion();
  useStreamLoop();

  const openAddData = useCallback((target: AddDataTarget) => {
    setAddDataTarget(target);
    setAddDataOpen(false);
    setView(target.view);
  }, []);

  const closeDrawer = useCallback(() => setDrawer((current) => ({ ...current, open: false })), []);

  const openEvidence = useCallback<OpenEvidence>((title, subtitle, items, limitations) => {
    setDrawer({ open: true, title, subtitle, items, limitations });
  }, []);

  const startDemo = useCallback(async () => {
    setAutoInvestigation(true);
    setDemoActive(true);
    setView("command");
    // demo uses the optional bundled dataset, clearly labelled BUILT-IN DEMO;
    // the normal production flow never falls back to it
    await session.createDemoSource();
    await session.startStream();
  }, [session, setAutoInvestigation]);

  const openStationEvidence = useCallback(
    (station: string) => {
      const finding = bottleneck?.station_rankings.find((entry) => entry.station === station);
      if (!finding) {
        setDrawer({
          open: true,
          title: station,
          subtitle: "No bottleneck analysis available for this station",
          items: [],
        });
        return;
      }
      const items: EvidenceItem[] = [
        {
          statement: `Utilization for ${station}.`,
          detail: finding.utilization.available
            ? `mean ${finding.utilization.mean}, max ${finding.utilization.max}, samples ${finding.utilization.samples}`
            : "NOT AVAILABLE FROM DATASET",
          source_artifact: "bottleneck/findings",
          epistemic_status: finding.utilization.available ? "DATA_DERIVED" : "NOT_AVAILABLE",
          value: finding.utilization.mean ?? null,
        },
        {
          statement: `Queue pressure for ${station}.`,
          detail: finding.queue.available ? `mean ${finding.queue.mean}` : "NOT AVAILABLE FROM DATASET",
          source_artifact: "bottleneck/findings",
          epistemic_status: finding.queue.available ? "DATA_DERIVED" : "NOT_AVAILABLE",
          value: finding.queue.mean ?? null,
        },
        {
          statement: `Evidence score ${finding.evidence_score ?? "not scored"}.`,
          detail: finding.score_formula,
          source_artifact: "bottleneck/findings",
          epistemic_status: "CALCULATED",
          value: finding.evidence_score,
        },
        {
          statement: `Evidence quality: ${finding.evidence_quality.label}.`,
          detail: finding.evidence_quality.reason,
          source_artifact: "bottleneck/findings",
          epistemic_status: "CALCULATED",
        },
      ];
      if (finding.root_cause_evidence?.best_factor) {
        items.push({
          statement: `Root-cause evidence: '${finding.root_cause_evidence.best_factor}' (score ${finding.root_cause_evidence.best_score}).`,
          detail: "Statistical association from the root-cause engine — not causation.",
          source_artifact: "root_cause/findings",
          epistemic_status: "STATISTICAL_ASSOCIATION",
          value: finding.root_cause_evidence.best_score,
        });
      }
      setDrawer({
        open: true,
        title: `${station} — why this station?`,
        subtitle: `${finding.status.replace(/_/g, " ")} · ${finding.evidence_quality.label.replace(/_/g, " ")}`,
        items,
        limitations: finding.limitations,
      });
    },
    [bottleneck],
  );

  const openFactorEvidence = useCallback((finding: RootCauseFinding) => {
    const items: EvidenceItem[] = [
      {
        statement: "Spearman correlation with the target.",
        detail: finding.evidence.correlation.available
          ? `rho=${finding.evidence.correlation.spearman_r}, n=${finding.evidence.correlation.n}`
          : (finding.evidence.correlation.reason ?? "unavailable"),
        source_artifact: "root_cause/findings",
        epistemic_status: finding.evidence.correlation.available ? "STATISTICAL_ASSOCIATION" : "NOT_AVAILABLE",
        value: finding.evidence.correlation.spearman_r ?? null,
      },
      {
        statement: "Mutual information vs permutation baseline.",
        detail: finding.evidence.mutual_information.available
          ? `MI=${finding.evidence.mutual_information.mi}, baseline=${finding.evidence.mutual_information.mi_permutation_baseline}`
          : (finding.evidence.mutual_information.reason ?? "unavailable"),
        source_artifact: "root_cause/findings",
        epistemic_status: finding.evidence.mutual_information.available ? "STATISTICAL_ASSOCIATION" : "NOT_AVAILABLE",
        value: finding.evidence.mutual_information.mi ?? null,
      },
      {
        statement: "Process-model contribution.",
        detail: finding.evidence.model_contribution.available
          ? `importance ${finding.evidence.model_contribution.importance} via ${finding.evidence.model_contribution.method}`
          : (finding.evidence.model_contribution.reason ?? "not in saved top features"),
        source_artifact: "models/<model_id>/feature_importance.json",
        epistemic_status: finding.evidence.model_contribution.available ? "MODEL_CONTRIBUTION" : "NOT_AVAILABLE",
        value: finding.evidence.model_contribution.importance ?? null,
      },
    ];
    setDrawer({
      open: true,
      title: `${finding.factor} — why this factor?`,
      subtitle: `${finding.association_status.replace(/_/g, " ")} · score ${finding.evidence_score ?? "—"}`,
      items,
      limitations: finding.limitations,
    });
  }, []);

  const openRecommendationEvidence = useCallback((recommendation: Recommendation) => {
    setDrawer({
      open: true,
      title: recommendation.title,
      subtitle: `${recommendation.action_type.replace(/_/g, " ")} · ${recommendation.evidence_quality.replace(/_/g, " ")}`,
      items: recommendation.evidence.map((entry) => ({
        statement: entry.statement,
        detail: entry.detail,
        source_artifact: entry.source_artifact,
        epistemic_status: entry.epistemic_status,
        value: entry.value,
      })),
      limitations: recommendation.limitations,
    });
  }, []);

  return (
    <div className="flex h-screen min-h-0 flex-col">
      <CommandBar onUploadClick={() => setUploadOpen(true)} onAddInspectionData={() => setAddDataOpen(true)} />
      <nav className="flex items-stretch overflow-x-auto border-b border-line bg-bg-2/40 px-1 sm:px-2" aria-label="Primary navigation">
        {VIEWS.map(({ id, label, icon: Icon }, index) => (
          <button
            key={id}
            type="button"
            onClick={() => setView(id)}
            aria-current={view === id ? "page" : undefined}
            className={`relative flex shrink-0 items-center gap-2 px-2.5 py-3 text-left transition-colors sm:gap-2.5 sm:px-4 ${
              view === id ? "text-cyan" : "text-ink-3 hover:text-ink-2"
            }`}
          >
            <span className="hidden font-mono text-2xs text-ink-3 sm:inline" aria-hidden>
              {String(index + 1).padStart(2, "0")}
            </span>
            <Icon size={14} aria-hidden />
            <span className="text-2xs font-semibold uppercase tracking-[0.12em] sm:text-xs sm:tracking-[0.14em]">{label}</span>
            {view === id && <motion.span layoutId="primary-nav-underline" className="absolute inset-x-2 bottom-0 h-px bg-cyan" aria-hidden />}
          </button>
        ))}
        <div className="ml-auto flex items-center gap-3 px-3">
          <button
            type="button"
            className="btn-primary !px-3 !py-1.5"
            onClick={() => setAddDataOpen(true)}
            title="Add inspection data: one image, a batch, or the automated stream"
          >
            <FolderPlus size={12} aria-hidden />
            Add inspection data
          </button>
          {demoActive ? (
            <button
              type="button"
              className="btn border-warn/50 bg-warn/10 text-warn !px-3 !py-1.5"
              onClick={() => {
                setDemoActive(false);
                void session.pauseStream();
              }}
            >
              <Square size={11} aria-hidden />
              Stop demo
            </button>
          ) : (
            <button
              type="button"
              className="btn-primary !px-3 !py-1.5"
              onClick={startDemo}
              disabled={!stream?.dataset_available}
              title="Starts the real automated stream and the real investigation chain."
            >
              <Play size={11} aria-hidden />
              Start demo
            </button>
          )}
          <span className="hidden text-2xs text-ink-3 lg:inline">
            {backendOnline === false ? "API unreachable" : "visual decision engine · industrial inspection workstation"}
          </span>
        </div>
      </nav>

      {demoActive && (
        <div className="border-b border-cyan/30 bg-cyan/5 px-4 py-1.5">
          <p className="text-center font-mono text-2xs text-cyan">
            DEMO MODE — running the real application: automated stream → inspection → decision → auto investigation.
            {" "}Use the navigation to follow the chain; nothing here is prerecorded.
          </p>
        </div>
      )}

      {backendOnline === false && (
        <div className="border-b border-bad/40 bg-bad/10 px-4 py-1.5 text-center">
          <p className="text-2xs font-semibold uppercase tracking-[0.14em] text-bad">
            Backend offline — start the analysis API and refresh
          </p>
        </div>
      )}
      <main className="min-h-0 flex-1 overflow-y-auto">
        <AnimatePresence mode="wait" initial={false}>
          <motion.div
            key={view}
            initial={reduceMotion ? false : { opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            exit={reduceMotion ? undefined : { opacity: 0, y: -6 }}
            transition={{ duration: 0.25, ease: [0.22, 1, 0.36, 1] }}
          >
            {view === "command" && (
              <CommandCenter
                onGoInspection={() => setView("inspection")}
                onGoAnalysis={() => setView("process")}
                onGoHistory={() => setView("history")}
                onGoReview={() => {
                  setReviewRequest((current) => current + 1);
                  setView("history");
                }}
                onOpenEvidence={openEvidence}
                onAddProcessData={() => setUploadOpen(true)}
              />
            )}
            {view === "inspection" && (
              <InspectionStudio
                onOpenEvidence={openEvidence}
                onGoAnalysis={() => setView("process")}
                modeRequest={addDataTarget && addDataTarget.view === "inspection" ? addDataTarget : null}
                onAddData={() => setAddDataOpen(true)}
              />
            )}
            {view === "process" && (
              <ProcessIntelligence
                onStationEvidence={openStationEvidence}
                onFactorEvidence={openFactorEvidence}
                onRecommendationEvidence={openRecommendationEvidence}
                onUploadClick={() => setUploadOpen(true)}
              />
            )}
            {view === "history" && <InvestigationHistory onGoInspection={() => setView("inspection")} reviewRequest={reviewRequest} />}
          </motion.div>
        </AnimatePresence>
      </main>

      {busy && (
        <div className="border-t border-cyan/30 bg-cyan/5 px-4 py-1.5 text-center">
          <p className="font-mono text-2xs text-cyan">{busy}…</p>
        </div>
      )}
      {error && (
        <div className="border-t border-bad/40 bg-bad/10 px-4 py-2 text-center">
          <p className="text-2xs font-semibold uppercase tracking-[0.12em] text-bad">
            {error.message} {errorStage ? `(${errorStage})` : ""}
          </p>
        </div>
      )}

      <EvidenceDrawer
        open={drawer.open}
        title={drawer.title}
        subtitle={drawer.subtitle}
        items={drawer.items}
        limitations={drawer.limitations}
        onClose={closeDrawer}
        footer={
          <p className="text-2xs leading-relaxed text-ink-3">
            Every statement above is traceable to a backend artifact. Epistemic labels are preserved exactly as produced
            by the pipeline.
          </p>
        }
      />

      {uploadOpen && <UploadModal onClose={() => setUploadOpen(false)} />}

      {addDataOpen && (
        <AddDataModal
          onClose={() => setAddDataOpen(false)}
          onImage={() => openAddData({ view: "inspection", mode: "single" })}
          onImageSet={() => openAddData({ view: "inspection", mode: "imageset" })}
          onFolder={() => openAddData({ view: "inspection", mode: "folder" })}
        />
      )}
    </div>
  );
}

function UploadModal({ onClose }: { onClose: () => void }) {
  const { uploadFile, busy } = useSession();
  const [dragging, setDragging] = useState(false);
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 px-6" role="dialog" aria-modal="true">
      <div
        className={`hud w-full max-w-md px-6 py-6 ${dragging ? "border-cyan/50" : ""}`}
        onDragOver={(event) => {
          event.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(event) => {
          event.preventDefault();
          setDragging(false);
          const file = event.dataTransfer.files?.[0];
          if (file) {
            void uploadFile(file).then(onClose);
          }
        }}
      >
        <p className="label mb-2">Upload process dataset</p>
        <p className="text-sm text-ink">Drop a CSV / MAT / ZIP dataset here</p>
        <p className="mt-1 text-2xs text-ink-3">
          The backend runs the full process pipeline: profiling, cleaning, ML models, root cause, bottleneck and
          recommendations.
        </p>
        <div className="mt-5 flex items-center justify-between gap-3">
          <p className="font-mono text-2xs text-ink-3">{busy ?? ""}</p>
          <button type="button" className="btn-ghost" onClick={onClose} disabled={Boolean(busy)}>
            Cancel
          </button>
        </div>
      </div>
    </div>
  );
}

export default function App() {
  return (
    <SessionProvider>
      <Workspace />
    </SessionProvider>
  );
}

export { EvidenceDrawer };
export type { BottleneckFinding };
