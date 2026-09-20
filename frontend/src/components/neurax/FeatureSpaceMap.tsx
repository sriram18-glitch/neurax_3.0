import { motion, useReducedMotion } from "framer-motion";
import { useMemo, useState } from "react";

import { useSession } from "../../session/SessionContext";
import { DataGap } from "./DataGap";
import { EvidenceBadge } from "./EvidenceBadge";

const CLASS_TONES = ["#38d6e0", "#a78bfa", "#f0b429", "#43d17a", "#ef5f6b", "#7dd3fc", "#f472b6", "#94a3b8"];

/**
 * Feature-space scatter of the REAL training embeddings (2-D PCA computed at
 * training time) with the current sample projected into the same space.
 */
export function FeatureSpaceMap() {
  const { featureSpace, inspection } = useSession();
  const [hovered, setHovered] = useState<string | null>(null);
  const reduceMotion = useReducedMotion();

  const layout = useMemo(() => {
    if (!featureSpace || featureSpace.status !== "AVAILABLE") return null;
    const points = Object.entries(featureSpace.clouds).flatMap(([, cloud]) => cloud);
    const point = inspection?.feature_space_point ?? null;
    const all = point ? [...points, point] : points;
    if (all.length === 0) return null;
    const xs = all.map((entry) => entry[0]);
    const ys = all.map((entry) => entry[1]);
    const minX = Math.min(...xs);
    const maxX = Math.max(...xs);
    const minY = Math.min(...ys);
    const maxY = Math.max(...ys);
    const padX = (maxX - minX) * 0.08 || 1;
    const padY = (maxY - minY) * 0.08 || 1;
    return { minX: minX - padX, maxX: maxX + padX, minY: minY - padY, maxY: maxY + padY };
  }, [featureSpace, inspection]);

  if (!featureSpace || featureSpace.status !== "AVAILABLE" || !layout) {
    return (
      <DataGap
        title="Feature space unavailable"
        reason={
          featureSpace?.reason ??
          "The trained artifacts predate the feature-space projection, or no model is trained. Retrain the vision model to generate it."
        }
      />
    );
  }

  const width = 640;
  const height = 320;
  const toX = (value: number) => ((value - layout.minX) / (layout.maxX - layout.minX)) * (width - 40) + 20;
  const toY = (value: number) => height - (((value - layout.minY) / (layout.maxY - layout.minY)) * (height - 40) + 20);
  const point = inspection?.feature_space_point ?? null;
  const predicted = inspection?.prediction.predicted_class ?? null;
  const classes = Object.keys(featureSpace.clouds);

  return (
    <div className="flex flex-col gap-2 px-4 py-3">
      <div className="flex flex-wrap items-center gap-3">
        {classes.map((name, index) => (
          <button
            key={name}
            type="button"
            onMouseEnter={() => setHovered(name)}
            onMouseLeave={() => setHovered(null)}
            className={`flex items-center gap-1.5 text-2xs ${name === predicted ? "text-cyan" : "text-ink-3"}`}
          >
            <span className="h-1.5 w-1.5" style={{ background: CLASS_TONES[index % CLASS_TONES.length] }} aria-hidden />
            {name}
            {featureSpace.counts?.[name] !== undefined && <span className="font-mono text-[9px] text-ink-3">({featureSpace.counts[name]})</span>}
          </button>
        ))}
        <span className="ml-auto">
          <EvidenceBadge status="MODEL-DERIVED" />
        </span>
      </div>

      <div className="border border-line/60 bg-bg-2/40">
        <svg viewBox={`0 0 ${width} ${height}`} className="h-auto w-full" role="img" aria-label="Feature-space projection of training embeddings and the current sample">
          <line x1={20} y1={height - 20} x2={width - 20} y2={height - 20} stroke="rgb(var(--line) / 0.5)" />
          <line x1={20} y1={20} x2={20} y2={height - 20} stroke="rgb(var(--line) / 0.5)" />
          {classes.map((name, index) => {
            const dim = hovered !== null && hovered !== name;
            return (
              <g key={name} opacity={dim ? 0.25 : 0.85}>
                {featureSpace.clouds[name].map(([x, y], pointIndex) => (
                  <circle
                    key={pointIndex}
                    cx={toX(x)}
                    cy={toY(y)}
                    r={2.1}
                    fill={CLASS_TONES[index % CLASS_TONES.length]}
                    opacity={0.75}
                  />
                ))}
              </g>
            );
          })}
          {point && (
            <g>
              <motion.circle
                cx={toX(point[0])}
                cy={toY(point[1])}
                r={7}
                fill="none"
                stroke="#e8edf4"
                strokeWidth={1.5}
                initial={reduceMotion ? false : { r: 2, opacity: 0 }}
                animate={{ r: 7, opacity: 1 }}
                transition={{ duration: 0.6, ease: [0.22, 1, 0.36, 1] }}
              />
              <circle cx={toX(point[0])} cy={toY(point[1])} r={2.6} fill="#e8edf4" />
              <text
                x={toX(point[0]) + 10}
                y={toY(point[1]) - 8}
                fill="#e8edf4"
                fontSize={10}
                fontFamily="var(--font-mono)"
              >
                current
              </text>
            </g>
          )}
        </svg>
      </div>

      <p className="text-2xs leading-relaxed text-ink-3">
        {featureSpace.method} · {featureSpace.components} components explain{" "}
        {((featureSpace.explained_variance_ratio?.reduce((total, value) => total + value, 0) ?? 0) * 100).toFixed(1)}% of the
        training variance · {featureSpace.sampling}. {point ? "The current sample is projected with the same components." : "Run an inspection to project a live sample."}
      </p>
    </div>
  );
}
