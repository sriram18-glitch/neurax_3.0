import { AlertTriangle, ArrowRight, CheckCircle2, CircleHelp, Crosshair, Gauge, Link2Off, MessageSquare } from "lucide-react";

import { useSession } from "../session/SessionContext";
import { NotAvailable, Panel, formatNumber, statusTone } from "./ui/Primitives";

const DECISION_ICON: Record<string, typeof CheckCircle2> = {
  PASS: CheckCircle2,
  DEFECT: AlertTriangle,
  REVIEW: CircleHelp,
};

export function DecisionView() {
  const { inspection, visionStatus, bottleneck, rootCause, recommendations, contract } = useSession();

  if (!inspection) {
    return (
      <div className="mx-auto max-w-2xl px-6 py-14">
        <Panel title="Decision chain" subtitle="WHAT → WHERE → HOW CERTAIN → WHY → WHAT NEXT">
          <div className="px-4 py-4">
            <NotAvailable reason="Run an image inspection first; the decision chain is built from its real outputs." />
          </div>
        </Panel>
      </div>
    );
  }

  const DecisionIcon = DECISION_ICON[inspection.decision] ?? CircleHelp;
  const topRecommendation = recommendations?.recommendations?.[0];
  const candidate = bottleneck?.candidate_bottleneck;
  const topFactor = rootCause?.ranked_findings?.[0];

  return (
    <div className="mx-auto flex max-w-5xl flex-col gap-3 p-3">
      <div className="grid gap-3 lg:grid-cols-2">
        {/* WHAT */}
        <ChainCard index="01" title="WHAT">
          <div className="flex items-center gap-3">
            <DecisionIcon size={18} className={inspection.decision === "PASS" ? "text-ok" : inspection.decision === "DEFECT" ? "text-bad" : "text-warn"} aria-hidden />
            <div>
              <p className="text-lg font-semibold text-ink">{inspection.prediction.predicted_class}</p>
              <p className="text-2xs text-ink-3">
                {inspection.decision}
                {inspection.review_reason ? ` — ${inspection.review_reason}` : ""}
              </p>
            </div>
          </div>
          <ul className="mt-3 flex flex-col gap-1.5">
            {Object.entries(inspection.class_probabilities)
              .sort((a, b) => b[1] - a[1])
              .slice(0, 3)
              .map(([name, probability]) => (
                <li key={name} className="flex items-center justify-between text-2xs text-ink-2">
                  <span>{name}</span>
                  <span className="font-mono">{(probability * 100).toFixed(1)}%</span>
                </li>
              ))}
          </ul>
        </ChainCard>

        {/* WHERE */}
        <ChainCard index="02" title="WHERE" icon={<Crosshair size={12} className="text-ink-3" aria-hidden />}>
          <p className="text-xs text-ink-2">
            {inspection.localization.bounding_box
              ? `Region x=${inspection.localization.bounding_box.x}, y=${inspection.localization.bounding_box.y}, ` +
                `${inspection.localization.bounding_box.width}×${inspection.localization.bounding_box.height} px`
              : "No localized region above the activation threshold."}
          </p>
          <p className="mt-2 text-2xs text-novel">
            {inspection.localization.type} — {inspection.localization.note}
          </p>
          <p className="mt-1 text-2xs text-ink-3">
            Method: {inspection.localization.method}. Ground-truth annotations: {String(inspection.localization.ground_truth)}
          </p>
        </ChainCard>

        {/* HOW CERTAIN */}
        <ChainCard index="03" title="HOW CERTAIN" icon={<Gauge size={12} className="text-ink-3" aria-hidden />}>
          <dl className="grid grid-cols-2 gap-x-4 gap-y-2">
            <div>
              <dt className="label">Confidence</dt>
              <dd className="mono-value text-sm text-ink">
                {(inspection.confidence.value * 100).toFixed(1)}%
                <span className="ml-1 text-2xs text-ink-3">{inspection.confidence.level}</span>
              </dd>
            </div>
            <div>
              <dt className="label">Anomaly score</dt>
              <dd className="mono-value text-sm text-ink">{formatNumber(inspection.anomaly_score.value, 3)}</dd>
            </div>
            <div>
              <dt className="label">Novelty</dt>
              <dd className="text-sm text-ink">{inspection.anomaly_score.novelty_status}</dd>
            </div>
            <div>
              <dt className="label">Calibration</dt>
              <dd className="text-2xs text-ink-2">{visionStatus?.metadata?.calibration ?? "temperature scaling"}</dd>
            </div>
          </dl>
          <p className="mt-2 text-2xs text-ink-3">{inspection.confidence.limitations}</p>
        </ChainCard>

        {/* WHY */}
        <ChainCard index="04" title="WHY" icon={<MessageSquare size={12} className="text-ink-3" aria-hidden />}>
          <ul className="flex flex-col gap-2">
            {inspection.evidence.map((entry, index) => (
              <li key={index} className="flex items-start justify-between gap-3">
                <span className="text-2xs leading-relaxed text-ink-2">{entry.statement}</span>
                <span className={`chip shrink-0 ${statusTone(entry.epistemic_status)}`}>{entry.epistemic_status}</span>
              </li>
            ))}
          </ul>
          <ul className="mt-3 flex flex-col gap-1">
            {inspection.limitations.map((limitation) => (
              <li key={limitation} className="text-2xs leading-relaxed text-ink-3">
                — {limitation}
              </li>
            ))}
          </ul>
        </ChainCard>
      </div>

      {/* WHAT NEXT */}
      <Panel title="05 · WHAT NEXT" subtitle="Process context and advisory action">
        <div className="grid gap-3 px-4 py-4 lg:grid-cols-2">
          <div className="flex flex-col gap-2">
            <p className="label">Process link</p>
            <div className="flex items-start gap-2 border border-line px-3 py-2.5">
              <Link2Off size={13} className="mt-0.5 shrink-0 text-ink-3" aria-hidden />
              <div>
                <p className="text-2xs leading-relaxed text-ink-2">{inspection.process_link.reason}</p>
                {contract && (
                  <p className="mt-1.5 text-2xs text-ink-3">
                    Active process dataset: <span className="text-ink-2">{contract.filename}</span>
                    {candidate?.station ? ` · candidate constraint ${candidate.station}` : ""}
                  </p>
                )}
              </div>
            </div>
            {!contract && (
              <p className="text-2xs text-ink-3">
                Load a process dataset in the CONTROL ROOM to connect inspection findings with root cause, bottleneck and
                economics.
              </p>
            )}
          </div>

          <div className="flex flex-col gap-2">
            <p className="label">Advisory action</p>
            {topRecommendation ? (
              <div className="border border-cyan/40 bg-cyan/5 px-3 py-2.5">
                <p className="flex items-center gap-2 text-xs font-medium text-cyan">
                  {topRecommendation.action_type.replace(/_/g, " ")}
                  <ArrowRight size={11} aria-hidden />
                </p>
                <p className="mt-1 text-xs text-ink">{topRecommendation.title}</p>
                <p className="mt-1 text-2xs text-ink-3">
                  evidence quality: {topRecommendation.evidence_quality.replace(/_/g, " ")} · advisory only
                </p>
              </div>
            ) : (
              <NotAvailable reason="No process recommendations are available yet. Load a dataset and generate recommendations in the CONTROL ROOM." />
            )}
            {topFactor && (
              <p className="text-2xs text-ink-3">
                Top associated process factor: <span className="text-ink-2">{topFactor.factor}</span> (
                {topFactor.association_status.replace(/_/g, " ")})
              </p>
            )}
          </div>
        </div>
      </Panel>

      {/* thresholds */}
      <Panel title="Decision thresholds" subtitle="Configurable PASS / DEFECT / REVIEW gates">
        <div className="grid gap-3 px-4 py-4 sm:grid-cols-2 lg:grid-cols-4">
          <Threshold label="Pass confidence ≥" value={visionStatus?.thresholds?.pass_confidence} />
          <Threshold label="Defect confidence ≥" value={visionStatus?.thresholds?.defect_confidence} />
          <Threshold label="Anomaly review gate" value={visionStatus?.thresholds?.anomaly_review_percentile} />
          <div>
            <p className="label">Test-set outcomes</p>
            <p className="mt-1 font-mono text-xs text-ink-2">
              {visionStatus?.metrics
                ? `PASS ${visionStatus.metrics.decisions.PASS} · DEFECT ${visionStatus.metrics.decisions.DEFECT} · REVIEW ${visionStatus.metrics.decisions.REVIEW}`
                : "—"}
            </p>
          </div>
        </div>
        <div className="grid gap-3 border-t border-line px-4 py-3 sm:grid-cols-3">
          <div>
            <p className="label">False accept rate</p>
            <p className="mono-value text-xs text-ink-2">
              {visionStatus?.metrics?.false_accept_rate !== null && visionStatus?.metrics?.false_accept_rate !== undefined
                ? `${(visionStatus.metrics.false_accept_rate * 100).toFixed(2)}%`
                : "—"}
            </p>
          </div>
          <div>
            <p className="label">False reject rate</p>
            <p className="mono-value text-xs text-ink-2">
              {visionStatus?.metrics?.false_reject_rate !== null && visionStatus?.metrics?.false_reject_rate !== undefined
                ? `${(visionStatus.metrics.false_reject_rate * 100).toFixed(2)}%`
                : "—"}
            </p>
          </div>
          <div>
            <p className="label">Review rate</p>
            <p className="mono-value text-xs text-ink-2">
              {visionStatus?.metrics?.review_rate !== undefined ? `${(visionStatus.metrics.review_rate * 100).toFixed(2)}%` : "—"}
            </p>
          </div>
        </div>
        <p className="border-t border-line px-4 py-2 text-2xs text-ink-3">
          Rates are measured on the held-out test split of the image dataset — not estimated. Thresholds are
          configurable in the backend; changing them changes the trade-off between false accepts, false rejects and
          manual review.
        </p>
      </Panel>
    </div>
  );
}

function ChainCard({
  index,
  title,
  icon,
  children,
}: {
  index: string;
  title: string;
  icon?: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <Panel>
      <div className="flex flex-col gap-2 px-4 py-4">
        <div className="flex items-center gap-2">
          <span className="font-mono text-2xs text-ink-3">{index}</span>
          <p className="text-xs font-semibold uppercase tracking-[0.14em] text-ink-2">{title}</p>
          {icon}
        </div>
        {children}
      </div>
    </Panel>
  );
}

function Threshold({ label, value }: { label: string; value?: number }) {
  return (
    <div>
      <p className="label">{label}</p>
      <p className="mono-value mt-1 text-xs text-ink-2">{value !== undefined ? value.toFixed(2) : "—"}</p>
    </div>
  );
}
