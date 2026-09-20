import { CheckCircle2, Gauge, GitBranch, Image as ImageIcon, Search, ScanSearch, ShieldCheck, Wrench, ClipboardList } from "lucide-react";

/**
 * Feature coverage map for the eight judging criteria. This is not a scoring
 * system — it maps each criterion to where its evidence lives in the product.
 */
export function EvaluationCoverage() {
  const items = [
    { icon: ScanSearch, label: "Detection & Classification", where: "Inspection · Classification panel + batch quality" },
    { icon: ImageIcon, label: "Localization", where: "Inspection · model-derived region + heatmap" },
    { icon: ShieldCheck, label: "Robustness", where: "Inspection · known-distribution novelty gauge" },
    { icon: Gauge, label: "False Accept / Reject", where: "Inspection · Decision quality (measured test split)" },
    { icon: GitBranch, label: "Root Cause", where: "Process Intelligence · stage 02 association graph" },
    { icon: Search, label: "Confidence & Explainability", where: "Every result · calibrated confidence + evidence drawer" },
    { icon: Wrench, label: "Technical Reliability", where: "Evidence drawer · model, calibration, thresholds" },
    { icon: ClipboardList, label: "UI / Visualization", where: "Command Center · industrial control room" },
  ];
  return (
    <ul className="grid gap-px bg-line/40 sm:grid-cols-2 lg:grid-cols-4">
      {items.map(({ icon: Icon, label, where }) => (
        <li key={label} className="flex flex-col gap-1 bg-panel/70 px-4 py-3">
          <span className="flex items-center gap-2">
            <CheckCircle2 size={11} className="text-ok" aria-hidden />
            <Icon size={11} className="text-cyan" aria-hidden />
            <span className="text-2xs font-semibold uppercase tracking-[0.1em] text-ink-2">{label}</span>
          </span>
          <span className="text-[9px] leading-relaxed text-ink-3">{where}</span>
        </li>
      ))}
    </ul>
  );
}

/** The core automation principle: automate the certain, escalate the uncertain. */
export function AutomationPrinciple() {
  return (
    <div className="grid gap-px bg-line/40 sm:grid-cols-2">
      <div className="flex items-start gap-3 bg-ok/5 px-4 py-3">
        <span className="mt-1.5 h-1.5 w-1.5 shrink-0 bg-ok" aria-hidden />
        <div>
          <p className="font-mono text-2xs uppercase tracking-[0.14em] text-ok">Automate the certain</p>
          <p className="mt-0.5 text-2xs leading-relaxed text-ink-3">
            High calibrated confidence, familiar samples and consistent signals → automatic PASS / DEFECT decisions.
          </p>
        </div>
      </div>
      <div className="flex items-start gap-3 bg-warn/5 px-4 py-3">
        <span className="mt-1.5 h-1.5 w-1.5 shrink-0 bg-warn" aria-hidden />
        <div>
          <p className="font-mono text-2xs uppercase tracking-[0.14em] text-warn">Escalate the uncertain</p>
          <p className="mt-0.5 text-2xs leading-relaxed text-ink-3">
            Low confidence, novel or anomalous samples → REVIEW and the human review queue. The AI decision is preserved
            next to the human decision.
          </p>
        </div>
      </div>
    </div>
  );
}