import { AlertTriangle } from "lucide-react";

/** Honest empty/gap state. Explains what is missing and what unlocks it. */
export function DataGap({
  title,
  reason,
  action,
  tone = "idle",
}: {
  title: string;
  reason: string;
  action?: React.ReactNode;
  tone?: "idle" | "warn" | "bad";
}) {
  const border = tone === "bad" ? "border-bad/40" : tone === "warn" ? "border-warn/40" : "border-line/60";
  const text = tone === "bad" ? "text-bad" : tone === "warn" ? "text-warn" : "text-ink-3";
  return (
    <div className={`flex flex-col gap-1.5 border border-dashed ${border} px-4 py-3`}>
      <p className={`flex items-center gap-2 text-2xs font-semibold uppercase tracking-[0.12em] ${text}`}>
        <AlertTriangle size={11} aria-hidden />
        {title}
      </p>
      <p className="text-2xs leading-relaxed text-ink-3">{reason}</p>
      {action && <div className="mt-1">{action}</div>}
    </div>
  );
}
