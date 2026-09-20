import { ScanSearch, Search, Share2, TrendingDown, FlaskConical, ListChecks, Gauge } from "lucide-react";

const ITEMS = [
  { icon: ScanSearch, label: "DETECT", text: "AI sees the defect — calibrated classification on real model output." },
  { icon: Search, label: "EXPLAIN", text: "AI exposes the evidence — every result carries its epistemic status." },
  { icon: Share2, label: "CORRELATE", text: "AI connects inspection to process data when a valid join exists — and says so when it does not." },
  { icon: TrendingDown, label: "INVESTIGATE", text: "AI identifies statistical root-cause candidates, never claimed causes." },
  { icon: Gauge, label: "CONSTRAIN", text: "AI identifies production bottlenecks as evidence-based hypotheses." },
  { icon: FlaskConical, label: "SIMULATE", text: "AI evaluates assumption-based what-if scenarios, labelled as simulations." },
  { icon: ListChecks, label: "RECOMMEND", text: "AI generates evidence-linked advisory actions — humans decide." },
];

/** The NEURAX difference: static product copy, no results. */
export function NeuraxDifference() {
  return (
    <div className="flex flex-col">
      <ul className="grid gap-px bg-line/40 sm:grid-cols-2 lg:grid-cols-4 xl:grid-cols-7">
        {ITEMS.map(({ icon: Icon, label, text }) => (
          <li key={label} className="flex flex-col gap-1.5 bg-panel/70 px-4 py-3">
            <span className="flex items-center gap-2">
              <Icon size={12} className="text-cyan" aria-hidden />
              <span className="font-mono text-2xs uppercase tracking-[0.14em] text-cyan">{label}</span>
            </span>
            <span className="text-[9px] leading-relaxed text-ink-3">{text}</span>
          </li>
        ))}
      </ul>
      <p className="border-t border-line/60 px-4 py-2 text-center font-mono text-2xs uppercase tracking-[0.3em] text-ink-2">
        From detection to decision.
      </p>
    </div>
  );
}
