import { RefreshCw, Sparkles } from "lucide-react";

import { useSession } from "../session/SessionContext";
import type { Recommendation } from "../types/api";
import { NotAvailable, Panel, statusIcon, statusTone } from "./ui/Primitives";

export function RecommendationPanel({ onInspect }: { onInspect: (recommendation: Recommendation) => void }) {
  const { recommendations, recommendationRun, generateRecommendations, busy } = useSession();
  const entries = recommendationRun?.recommendations ?? [];
  const registry = recommendations?.recommendations ?? [];

  return (
    <Panel
      title="Advisory recommendations"
      subtitle={recommendationRun ? `engine v${recommendationRun.engine_version} · ${recommendationRun.total_duration_s}s` : "Deterministic rule engine"}
      actions={
        <button type="button" className="btn-primary" onClick={() => void generateRecommendations()} disabled={Boolean(busy)}>
          {busy?.includes("recommendations") ? (
            <RefreshCw size={11} className="animate-spin" aria-hidden />
          ) : (
            <Sparkles size={11} aria-hidden />
          )}
          Generate
        </button>
      }
    >
      {entries.length === 0 && registry.length === 0 ? (
        <div className="px-4 py-4">
          <NotAvailable reason="No recommendations have been generated for this dataset yet. Generate to run the deterministic rule engine on current artifacts." />
        </div>
      ) : (
        <div className="max-h-[520px] overflow-y-auto">
          {(entries.length ? entries : registry).map((entry, index) => {
            const full = entries.length ? (entry as Recommendation) : null;
            const key = full?.recommendation_id ?? (entry as { recommendation_id: string }).recommendation_id;
            const title = full?.title ?? (entry as { title: string }).title;
            const actionType = full?.action_type ?? (entry as { action_type: string }).action_type;
            const quality = full?.evidence_quality ?? (entry as { evidence_quality: string }).evidence_quality;
            const station = full?.station ?? (entry as { station: string | null }).station;
            const priority = full?.priority ?? (entry as { priority: number | null }).priority;
            const why = full?.why;
            const dataRequirement = full?.data_requirement ?? false;
            return (
              <button
                key={key}
                type="button"
                onClick={() => full && onInspect(full)}
                className={`flex w-full flex-col gap-2 border-b border-line px-4 py-4 text-left transition-colors hover:bg-panel-2/50 ${
                  index === 0 ? "bg-cyan/[0.03]" : ""
                }`}
              >
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-mono text-2xs text-ink-3">#{full?.rank ?? index + 1}</span>
                  <span className={`chip ${dataRequirement ? "border-novel/40 text-novel" : "border-cyan/40 text-cyan"}`}>
                    {actionType.replace(/_/g, " ")}
                  </span>
                  <span className={`chip ${statusTone(quality)}`}>
                    {statusIcon(quality)}
                    {quality.replace(/_/g, " ")}
                  </span>
                  {station && <span className="chip border-line text-ink-2">{station}</span>}
                  {priority !== null && <span className="ml-auto font-mono text-2xs text-ink-3">priority {priority}</span>}
                </div>
                <p className="text-sm font-medium text-ink">{title}</p>
                {why && <p className="text-xs leading-relaxed text-ink-2">{why}</p>}
                {full && (
                  <span className="mt-1 flex flex-wrap gap-x-4 gap-y-1 text-2xs text-ink-3">
                    <span>{full.evidence.length} evidence item(s)</span>
                    <span>{full.source_artifacts.join(" · ")}</span>
                    {full.simulated_effect && <span className="text-novel">includes SIMULATED effect</span>}
                  </span>
                )}
              </button>
            );
          })}
          <p className="px-4 py-2 text-2xs text-ink-3">
            Recommendations are advisory decision support. They never control machinery and are not guaranteed outcomes.
          </p>
        </div>
      )}
    </Panel>
  );
}
