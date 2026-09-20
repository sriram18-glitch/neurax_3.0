import { useMemo, useState } from "react";

import { EvidenceBadge } from "./EvidenceBadge";

/**
 * Feature-space view of the real 1280-d backbone embedding.
 * Left: the embedding rendered as a value strip (actual numbers).
 * Right: distances from this sample to every known class centroid (actual numbers).
 */
export function FeatureSpace({
  vector,
  dim,
  classDistances,
  predictedClass,
}: {
  vector: number[] | null | undefined;
  dim?: number | null;
  classDistances?: Record<string, number> | null;
  predictedClass?: string | null;
}) {
  const [showAll, setShowAll] = useState(false);
  const strip = useMemo(() => {
    if (!vector || vector.length === 0) return null;
    const values = vector.slice(0, 256);
    const max = Math.max(...values.map((value) => Math.abs(value)), 0.0001);
    return { values, max, total: dim ?? vector.length };
  }, [vector, dim]);

  const distances = useMemo(() => {
    if (!classDistances) return null;
    const entries = Object.entries(classDistances);
    const max = Math.max(...entries.map(([, value]) => value), 0.0001);
    return { entries: entries.sort((a, b) => a[1] - b[1]), max };
  }, [classDistances]);

  return (
    <div className="flex flex-col gap-4 px-4 py-3">
      {strip ? (
        <div>
          <div className="mb-1.5 flex items-center justify-between">
            <span className="label">embedding vector · dim {strip.total}</span>
            <button
              type="button"
              className="text-2xs uppercase tracking-[0.1em] text-ink-3 transition-colors hover:text-cyan"
              onClick={() => setShowAll((current) => !current)}
            >
              {showAll ? "show first 256" : "show all 1280"}
            </button>
          </div>
          <div
            className="flex h-10 items-stretch gap-px overflow-hidden border border-line/60 bg-bg-2/60 p-px"
            role="img"
            aria-label="Embedding value strip"
          >
            {(showAll && vector ? vector : strip.values).map((value, index) => {
              const intensity = Math.min(1, Math.abs(value) / strip.max);
              return (
                <span
                  key={index}
                  className="min-w-px flex-1"
                  style={{
                    background: `rgb(var(--cyan) / ${(0.08 + intensity * 0.85).toFixed(3)})`,
                  }}
                />
              );
            })}
          </div>
          <p className="mt-1.5 text-2xs text-ink-3">
            each bar is one real value from the frozen-backbone output for this image
          </p>
        </div>
      ) : (
        <p className="text-2xs text-ink-3">no embedding available for this inspection</p>
      )}

      {distances ? (
        <div>
          <div className="mb-1.5 flex items-center justify-between">
            <span className="label">distance to known class regions</span>
            <EvidenceBadge status="MODEL-DERIVED" />
          </div>
          <ul className="flex flex-col gap-2">
            {distances.entries.map(([name, value]) => (
              <li key={name} className="flex items-center gap-3">
                <span className={`w-20 shrink-0 truncate font-mono text-2xs uppercase ${name === predictedClass ? "text-cyan" : "text-ink-3"}`}>
                  {name}
                </span>
                <span className="relative h-1.5 flex-1 bg-line/50">
                  <span
                    className={name === predictedClass ? "absolute inset-y-0 left-0 bg-cyan" : "absolute inset-y-0 left-0 bg-idle/60"}
                    style={{ width: `${(value / distances.max) * 100}%` }}
                  />
                </span>
                <span className="w-12 shrink-0 text-right font-mono text-2xs text-ink-3">{value.toFixed(2)}</span>
              </li>
            ))}
          </ul>
          <p className="mt-1.5 text-2xs text-ink-3">
            smaller distance = closer to that class's observed cluster; assigned class highlighted
          </p>
        </div>
      ) : (
        <p className="text-2xs text-ink-3">class-distance reference not available</p>
      )}
    </div>
  );
}
