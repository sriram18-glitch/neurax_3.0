import { motion, useReducedMotion } from "framer-motion";

import type { FlowGraph } from "../types/api";
import type { Tone } from "./ui/Primitives";

const NODE_TONES: Record<Tone, { ring: string; fill: string; text: string }> = {
  ok: { ring: "rgba(67, 209, 122, 0.6)", fill: "rgba(67, 209, 122, 0.12)", text: "#43d17a" },
  warn: { ring: "rgba(240, 180, 41, 0.6)", fill: "rgba(240, 180, 41, 0.12)", text: "#f0b429" },
  bad: { ring: "rgba(239, 95, 107, 0.65)", fill: "rgba(239, 95, 107, 0.14)", text: "#ef5f6b" },
  novel: { ring: "rgba(167, 139, 250, 0.6)", fill: "rgba(167, 139, 250, 0.12)", text: "#a78bfa" },
  cyan: { ring: "rgba(56, 214, 224, 0.6)", fill: "rgba(56, 214, 224, 0.12)", text: "#38d6e0" },
  idle: { ring: "rgba(100, 116, 139, 0.5)", fill: "rgba(100, 116, 139, 0.10)", text: "#94a3b8" },
};

export interface FlowNodeState {
  station: string;
  tone: Tone;
  label: string;
  score: number | null;
  evidenceQuality?: string;
}

/**
 * Plant flow visualisation rendered as an animated SVG - no heavy 3D dependency.
 * Node order, tones and metrics all come from the backend flow graph.
 */
export function PlantFlow({
  graph,
  nodeStates,
  onSelect,
  selected,
}: {
  graph: FlowGraph | null;
  nodeStates: FlowNodeState[];
  onSelect: (station: string) => void;
  selected: string | null;
}) {
  const reduceMotion = useReducedMotion();
  const states = new Map(nodeStates.map((state) => [state.station, state]));

  if (!graph || graph.nodes.length === 0) {
    return (
      <div className="flex h-full items-center justify-center px-6 py-12">
        <p className="max-w-sm text-center text-xs leading-relaxed text-ink-3">
          Flow ordering is not available for this dataset. Station metrics exist, but no defensible
          upstream/downstream sequence could be established.
        </p>
      </div>
    );
  }

  const ordered = [...graph.nodes].sort((a, b) => (a.position ?? 0) - (b.position ?? 0));
  const width = 260;
  const height = 88;
  const gap = 34;
  const totalWidth = ordered.length * width + (ordered.length - 1) * gap;

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="min-h-0 flex-1 overflow-x-auto">
        <svg
          viewBox={`0 0 ${totalWidth} ${height + 20}`}
          className="h-full min-h-[180px] w-full"
          role="img"
          aria-label="Plant process flow with station states"
        >
          <defs>
            <marker id="flow-arrow" viewBox="0 0 8 8" refX="7" refY="4" markerWidth="7" markerHeight="7" orient="auto">
              <path d="M0,0 L8,4 L0,8 z" fill="rgba(148,163,184,0.45)" />
            </marker>
            <linearGradient id="flow-edge" x1="0" y1="0" x2="1" y2="0">
              <stop offset="0%" stopColor="rgba(56,214,224,0.10)" />
              <stop offset="100%" stopColor="rgba(56,214,224,0.55)" />
            </linearGradient>
          </defs>

          {ordered.slice(0, -1).map((node, index) => {
            const next = ordered[index + 1];
            const x1 = index * (width + gap) + width;
            const x2 = (index + 1) * (width + gap);
            const y = height / 2 + 10;
            return (
              <g key={`edge-${node.station}-${next.station}`}>
                <line x1={x1} y1={y} x2={x2 - 8} y2={y} stroke="rgba(148,163,184,0.3)" strokeWidth={1.5} markerEnd="url(#flow-arrow)" />
                {!reduceMotion && (
                  <motion.circle
                    r={3}
                    fill="#38d6e0"
                    initial={{ cx: x1, cy: y, opacity: 0 }}
                    animate={{ cx: [x1, x2 - 8], opacity: [0, 1, 0] }}
                    transition={{ duration: 2.2, repeat: Infinity, delay: index * 0.35, ease: "linear" }}
                  />
                )}
              </g>
            );
          })}

          {ordered.map((node, index) => {
            const state = states.get(node.station);
            const tone: Tone = state?.tone ?? "idle";
            const palette = NODE_TONES[tone];
            const x = index * (width + gap);
            const isSelected = selected === node.station;
            return (
              <g
                key={node.station}
                transform={`translate(${x}, 10)`}
                onClick={() => onSelect(node.station)}
                className="cursor-pointer"
                role="button"
                tabIndex={0}
                aria-label={`${node.station}: ${state?.label ?? "no data"}`}
                onKeyDown={(event) => {
                  if (event.key === "Enter" || event.key === " ") onSelect(node.station);
                }}
              >
                <rect
                  width={width}
                  height={height}
                  fill={palette.fill}
                  stroke={isSelected ? "#38d6e0" : palette.ring}
                  strokeWidth={isSelected ? 2 : 1}
                />
                <text x={16} y={26} fill={palette.text} fontSize={13} fontFamily="var(--font-sans)" fontWeight={600}>
                  {node.station}
                </text>
                <text x={16} y={44} fill="rgba(232,237,244,0.55)" fontSize={9.5} letterSpacing={1.2} fontFamily="var(--font-mono)">
                  {state?.label ?? "NO ANALYSIS"}
                </text>
                {state?.score !== null && state?.score !== undefined && (
                  <text x={16} y={66} fill="rgba(232,237,244,0.85)" fontSize={12} fontFamily="var(--font-mono)">
                    {state.score.toFixed(1)}
                  </text>
                )}
                {state?.evidenceQuality && (
                  <text x={width - 16} y={66} textAnchor="end" fill="rgba(232,237,244,0.4)" fontSize={8.5} letterSpacing={1} fontFamily="var(--font-mono)">
                    {state.evidenceQuality.replace("_EVIDENCE", "")}
                  </text>
                )}
              </g>
            );
          })}
        </svg>
      </div>
      {graph.status !== "SUPPORTED" && (
        <p className="border-t border-line px-4 py-2 text-2xs text-ink-3">{graph.reason ?? "Flow graph partially supported."}</p>
      )}
    </div>
  );
}
