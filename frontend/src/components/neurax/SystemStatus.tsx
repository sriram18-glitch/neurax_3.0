import { motion } from "framer-motion";

import { AnimatedNumber } from "./Motion";

export type CapabilityNode = {
  id: string;
  label: string;
  status: "operational" | "available" | "not_available" | "standby";
  detail: string;
  metric?: { value: number | null; digits?: number; suffix?: string; label: string } | null;
};

const DOT: Record<CapabilityNode["status"], string> = {
  operational: "bg-ok",
  available: "bg-cyan",
  standby: "bg-warn",
  not_available: "bg-idle",
};

const WORD: Record<CapabilityNode["status"], string> = {
  operational: "operational",
  available: "available",
  standby: "standby",
  not_available: "not available",
};

/** Live capability rail — each node reports its real state, never a claim. */
export function SystemStatus({ nodes }: { nodes: CapabilityNode[] }) {
  return (
    <ul className="grid gap-px bg-line/40 sm:grid-cols-2 lg:grid-cols-3">
      {nodes.map((node, index) => (
        <motion.li
          key={node.id}
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ duration: 0.35, delay: index * 0.05 }}
          className="flex flex-col gap-2 bg-panel/70 px-4 py-3.5"
        >
          <div className="flex items-center justify-between gap-2">
            <span className="truncate text-2xs font-semibold uppercase tracking-[0.12em] text-ink-2">{node.label}</span>
            <span className="flex items-center gap-1.5">
              <span className={`h-1.5 w-1.5 ${DOT[node.status]} ${node.status === "operational" ? "pulse-ring" : ""}`} aria-hidden />
              <span className="font-mono text-[9px] uppercase tracking-[0.1em] text-ink-3">{WORD[node.status]}</span>
            </span>
          </div>
          <p className="text-2xs leading-relaxed text-ink-3">{node.detail}</p>
          {node.metric && (
            <p className="mt-auto flex items-baseline gap-2">
              <AnimatedNumber
                value={node.metric.value}
                digits={node.metric.digits ?? 0}
                suffix={node.metric.suffix}
                className="text-lg text-ink"
              />
              <span className="text-2xs uppercase tracking-[0.08em] text-ink-3">{node.metric.label}</span>
            </p>
          )}
        </motion.li>
      ))}
    </ul>
  );
}
