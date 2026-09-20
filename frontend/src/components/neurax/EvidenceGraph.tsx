import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import { useMemo, useState } from "react";

import { EvidenceBadge } from "./EvidenceBadge";

export type GraphNode = {
  id: string;
  label: string;
  kind: "source" | "stage" | "signal" | "decision" | "action";
  epistemic: string;
  detail: string;
  value?: string | null;
  column?: number;
};

export type GraphEdge = {
  from: string;
  to: string;
  label?: string;
  strength?: number | null;
};

const KIND_STYLE: Record<GraphNode["kind"], { border: string; text: string; chip: string }> = {
  source: { border: "border-line-2", text: "text-ink-2", chip: "SOURCE" },
  stage: { border: "border-cyan/40", text: "text-cyan", chip: "STAGE" },
  signal: { border: "border-novel/40", text: "text-novel", chip: "SIGNAL" },
  decision: { border: "border-ok/40", text: "text-ok", chip: "DECISION" },
  action: { border: "border-warn/40", text: "text-warn", chip: "ACTION" },
};

const WIDTH = 1000;
const HEIGHT = 460;
const NODE_W = 176;
const NODE_H = 74;

/**
 * The signature evidence graph: every node is real output from this run,
 * every edge is a recorded relationship, every node carries its epistemic badge.
 */
export function EvidenceGraph({
  nodes,
  edges,
  caption,
}: {
  nodes: GraphNode[];
  edges: GraphEdge[];
  caption?: string;
}) {
  const reduceMotion = useReducedMotion();
  const [selected, setSelected] = useState<GraphNode | null>(null);
  const [hovered, setHovered] = useState<string | null>(null);

  const layout = useMemo(() => {
    const columns = new Map<number, GraphNode[]>();
    nodes.forEach((node) => {
      const column = node.column ?? 0;
      columns.set(column, [...(columns.get(column) ?? []), node]);
    });
    const maxColumn = Math.max(...columns.keys(), 0);
    const positions = new Map<string, { x: number; y: number }>();
    columns.forEach((columnNodes, column) => {
      const x = maxColumn === 0 ? WIDTH / 2 - NODE_W / 2 : 30 + (column / maxColumn) * (WIDTH - NODE_W - 60);
      columnNodes.forEach((node, index) => {
        const slot = (index + 0.5) / columnNodes.length;
        const y = 40 + slot * (HEIGHT - NODE_H - 80);
        positions.set(node.id, { x, y });
      });
    });
    return { positions, maxColumn };
  }, [nodes]);

  const activeIds = useMemo(() => {
    if (!hovered) return null;
    const ids = new Set<string>([hovered]);
    edges.forEach((edge) => {
      if (edge.from === hovered) ids.add(edge.to);
      if (edge.to === hovered) ids.add(edge.from);
    });
    return ids;
  }, [hovered, edges]);

  return (
    <div className="relative">
      <div className="relative w-full overflow-hidden" style={{ aspectRatio: `${WIDTH} / ${HEIGHT}` }}>
        <svg
          viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
          className="absolute inset-0 h-full w-full"
          role="img"
          aria-label="Evidence graph of this decision"
        >
          {edges.map((edge, index) => {
            const from = layout.positions.get(edge.from);
            const to = layout.positions.get(edge.to);
            if (!from || !to) return null;
            const x1 = from.x + NODE_W;
            const y1 = from.y + NODE_H / 2;
            const x2 = to.x;
            const y2 = to.y + NODE_H / 2;
            const mid = (x1 + x2) / 2;
            const path = `M ${x1} ${y1} C ${mid} ${y1}, ${mid} ${y2}, ${x2} ${y2}`;
            const active = !activeIds || (activeIds.has(edge.from) && activeIds.has(edge.to));
            const strength = edge.strength ?? 0.5;
            return (
              <g key={`${edge.from}-${edge.to}-${index}`} opacity={active ? 1 : 0.18}>
                <motion.path
                  d={path}
                  fill="none"
                  stroke="rgb(var(--cyan) / 0.55)"
                  strokeWidth={1 + strength * 2}
                  strokeDasharray={4}
                  initial={reduceMotion ? false : { pathLength: 0, opacity: 0 }}
                  animate={{ pathLength: 1, opacity: 1 }}
                  transition={{ duration: 0.6, delay: 0.15 + index * 0.08, ease: [0.22, 1, 0.36, 1] }}
                />
                {edge.label && (
                  <motion.text
                    x={mid}
                    y={(y1 + y2) / 2 - 6}
                    textAnchor="middle"
                    fill="#5f7085"
                    fontSize={9}
                    fontFamily="var(--font-mono)"
                    initial={reduceMotion ? false : { opacity: 0 }}
                    animate={{ opacity: 1 }}
                    transition={{ delay: 0.5 + index * 0.08 }}
                  >
                    {edge.label}
                  </motion.text>
                )}
              </g>
            );
          })}
        </svg>

        {nodes.map((node, index) => {
          const position = layout.positions.get(node.id);
          if (!position) return null;
          const style = KIND_STYLE[node.kind];
          const active = !activeIds || activeIds.has(node.id);
          return (
            <motion.button
              key={node.id}
              type="button"
              onMouseEnter={() => setHovered(node.id)}
              onMouseLeave={() => setHovered(null)}
              onClick={() => setSelected(node)}
              className={`absolute flex flex-col items-start gap-1 border bg-bg-2/90 px-2.5 py-2 text-left backdrop-blur transition-all duration-200 hover:bg-panel-2/90 ${style.border} ${
                selected?.id === node.id ? "ring-1 ring-cyan/60" : ""
              }`}
              style={{
                left: `${(position.x / WIDTH) * 100}%`,
                top: `${(position.y / HEIGHT) * 100}%`,
                width: `${(NODE_W / WIDTH) * 100}%`,
                height: `${(NODE_H / HEIGHT) * 100}%`,
                opacity: active ? 1 : 0.25,
              }}
              initial={reduceMotion ? false : { opacity: 0, y: 8 }}
              animate={{ opacity: active ? 1 : 0.25, y: 0 }}
              transition={{ duration: 0.4, delay: 0.1 + index * 0.07 }}
            >
              <span className="flex w-full items-center justify-between gap-2">
                <span className={`font-mono text-[8px] uppercase tracking-[0.14em] ${style.text}`}>{style.chip}</span>
                {node.value && <span className="truncate font-mono text-[9px] text-ink-3">{node.value}</span>}
              </span>
              <span className="w-full truncate text-2xs font-medium text-ink">{node.label}</span>
              <span className="w-full truncate text-[9px] text-ink-3">{node.detail}</span>
            </motion.button>
          );
        })}
      </div>

      <div className="border-t border-line/60">
        <AnimatePresence mode="wait" initial={false}>
          {selected ? (
            <motion.div
              key={selected.id}
              initial={reduceMotion ? false : { opacity: 0, y: 4 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.2 }}
              className="flex flex-col gap-1.5 px-4 py-3"
            >
              <div className="flex flex-wrap items-center gap-2">
                <span className="font-mono text-2xs uppercase tracking-[0.1em] text-ink">{selected.label}</span>
                <EvidenceBadge status={selected.epistemic} />
                {selected.value && <span className="font-mono text-2xs text-ink-2">{selected.value}</span>}
              </div>
              <p className="text-2xs leading-relaxed text-ink-2">{selected.detail}</p>
            </motion.div>
          ) : (
            <motion.p
              key="hint"
              initial={reduceMotion ? false : { opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              className="px-4 py-3 text-2xs text-ink-3"
            >
              {caption ?? "Select any node to inspect its evidence. Hover to trace its connections."}
            </motion.p>
          )}
        </AnimatePresence>
      </div>
    </div>
  );
}
