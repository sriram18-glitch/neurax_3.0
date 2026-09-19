import { AlertTriangle, CheckCircle2, CircleSlash, HelpCircle, Info, MinusCircle } from "lucide-react";
import type { ReactNode } from "react";

export type Tone = "ok" | "warn" | "bad" | "novel" | "cyan" | "idle";

export const toneClasses: Record<Tone, string> = {
  ok: "text-ok border-ok/40 bg-ok/10",
  warn: "text-warn border-warn/40 bg-warn/10",
  bad: "text-bad border-bad/40 bg-bad/10",
  novel: "text-novel border-novel/40 bg-novel/10",
  cyan: "text-cyan border-cyan/40 bg-cyan/10",
  idle: "text-idle border-line text-ink-3",
};

export function StatusChip({ tone, children, icon }: { tone: Tone; children: ReactNode; icon?: ReactNode }) {
  return (
    <span className={`chip ${toneClasses[tone]}`}>
      {icon}
      {children}
    </span>
  );
}

export function statusTone(status: string): Tone {
  const normalized = (status || "").toUpperCase();
  if (["READY", "SUPPORTED", "COMPLETE", "HIGH_EVIDENCE", "CANDIDATE_BOTTLENECK", "CALCULATED", "DRIFT_DETECTED"].includes(normalized)) return "ok";
  if (["REQUIRES_ASSUMPTIONS", "PARTIALLY_SUPPORTED", "MODERATE_EVIDENCE", "POSSIBLE_CONTRIBUTOR", "REVIEW", "LIMITED_EVIDENCE", "NOT_GENERATED"].includes(normalized)) return "warn";
  if (["FAILED", "ERROR", "NOT_SUPPORTED", "INSUFFICIENT_EVIDENCE"].includes(normalized)) return "bad";
  if (["NOVEL", "PROFILED"].includes(normalized)) return "novel";
  return "idle";
}

export function statusIcon(status: string): ReactNode {
  const tone = statusTone(status);
  if (tone === "ok") return <CheckCircle2 size={11} aria-hidden />;
  if (tone === "warn") return <AlertTriangle size={11} aria-hidden />;
  if (tone === "bad") return <CircleSlash size={11} aria-hidden />;
  if (tone === "novel") return <HelpCircle size={11} aria-hidden />;
  return <MinusCircle size={11} aria-hidden />;
}

export function Panel({
  title,
  subtitle,
  actions,
  children,
  className = "",
}: {
  title?: ReactNode;
  subtitle?: ReactNode;
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section className={`panel flex min-h-0 flex-col ${className}`}>
      {(title || actions) && (
        <header className="flex items-center justify-between gap-3 border-b border-line px-4 py-2.5">
          <div className="min-w-0">
            {title && <h2 className="truncate text-xs font-semibold uppercase tracking-[0.14em] text-ink-2">{title}</h2>}
            {subtitle && <p className="mt-0.5 truncate text-2xs text-ink-3">{subtitle}</p>}
          </div>
          {actions && <div className="flex shrink-0 items-center gap-2">{actions}</div>}
        </header>
      )}
      <div className="min-h-0 flex-1">{children}</div>
    </section>
  );
}

export function Metric({
  label,
  value,
  unit,
  tone = "idle",
  unavailableReason,
  hint,
}: {
  label: string;
  value: ReactNode;
  unit?: string;
  tone?: Tone;
  unavailableReason?: string;
  hint?: string;
}) {
  const unavailable = value === null || value === undefined || value === "NOT_AVAILABLE";
  return (
    <div className="flex min-w-0 flex-col gap-1 px-4 py-3" title={hint}>
      <span className="label">{label}</span>
      {unavailable ? (
        <span className="flex items-baseline gap-1.5">
          <span className="mono-value text-sm text-ink-3">NOT AVAILABLE</span>
          {unavailableReason && <span className="truncate text-2xs text-ink-3">{unavailableReason}</span>}
        </span>
      ) : (
        <span className={`mono-value text-lg leading-none ${tone === "idle" ? "text-ink" : `text-${tone}`}`}>
          {value}
          {unit && <span className="ml-1 text-2xs font-normal text-ink-3">{unit}</span>}
        </span>
      )}
    </div>
  );
}

export function NotAvailable({ reason, className = "" }: { reason: string; className?: string }) {
  return (
    <div className={`flex items-start gap-2 border border-line bg-panel-2/40 px-3 py-2.5 ${className}`}>
      <Info size={13} className="mt-0.5 shrink-0 text-ink-3" aria-hidden />
      <div>
        <p className="text-2xs font-semibold uppercase tracking-[0.12em] text-ink-3">NOT AVAILABLE</p>
        <p className="mt-1 text-xs leading-relaxed text-ink-2">{reason}</p>
      </div>
    </div>
  );
}

export function formatNumber(value: number | null | undefined, digits = 2): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  return new Intl.NumberFormat("en-US", { maximumFractionDigits: digits, minimumFractionDigits: 0 }).format(value);
}

export function formatCurrency(value: number | null | undefined, currency: string | null | undefined, digits = 0): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  const formatted = new Intl.NumberFormat("en-US", { maximumFractionDigits: digits }).format(value);
  return currency ? `${currency} ${formatted}` : formatted;
}

export function formatBytes(bytes: number | null | undefined): string {
  if (bytes === null || bytes === undefined) return "—";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}
