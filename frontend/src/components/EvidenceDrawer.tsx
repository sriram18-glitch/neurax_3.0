import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import { X } from "lucide-react";
import type { ReactNode } from "react";

import { statusIcon, statusTone } from "./ui/Primitives";

export interface EvidenceItem {
  statement: string;
  detail: string;
  source_artifact: string;
  epistemic_status: string;
  value?: number | string | null;
}

export function EvidenceDrawer({
  open,
  title,
  subtitle,
  items,
  limitations,
  onClose,
  footer,
}: {
  open: boolean;
  title: string;
  subtitle?: string;
  items: EvidenceItem[];
  limitations?: string[];
  onClose: () => void;
  footer?: ReactNode;
}) {
  const reduceMotion = useReducedMotion();
  return (
    <AnimatePresence>
      {open && (
        <motion.aside
          key="evidence-drawer"
          initial={reduceMotion ? false : { x: "100%" }}
          animate={{ x: 0 }}
          exit={reduceMotion ? { opacity: 0 } : { x: "100%" }}
          transition={{ duration: 0.25, ease: [0.22, 1, 0.36, 1] }}
          className="fixed inset-y-0 right-0 z-40 flex w-full max-w-md flex-col border-l border-line-2 bg-bg-2/95 backdrop-blur-xl"
          role="dialog"
          aria-label={`Evidence: ${title}`}
        >
          <header className="flex items-start justify-between gap-4 border-b border-line px-5 py-4">
            <div>
              <p className="label">Evidence</p>
              <h2 className="mt-1 text-sm font-semibold text-ink">{title}</h2>
              {subtitle && <p className="mt-1 text-2xs text-ink-3">{subtitle}</p>}
            </div>
            <button type="button" className="btn-ghost !px-2 !py-1" onClick={onClose} aria-label="Close evidence panel">
              <X size={13} aria-hidden />
            </button>
          </header>

          <div className="min-h-0 flex-1 overflow-y-auto px-5 py-4">
            <ul className="flex flex-col gap-4">
              {items.map((item, index) => (
                <li key={`${item.source_artifact}-${index}`} className="border border-line bg-panel/50 px-3.5 py-3">
                  <div className="flex items-center justify-between gap-2">
                    <span className="label">{item.source_artifact}</span>
                    <span className={`chip ${statusTone(item.epistemic_status)}`}>
                      {statusIcon(item.epistemic_status)}
                      {item.epistemic_status}
                    </span>
                  </div>
                  <p className="mt-2 text-xs leading-relaxed text-ink">{item.statement}</p>
                  <p className="mt-1.5 text-2xs leading-relaxed text-ink-2">{item.detail}</p>
                  {item.value !== undefined && item.value !== null && (
                    <p className="mt-2 font-mono text-2xs text-cyan">
                      {typeof item.value === "number" ? item.value.toFixed(4) : item.value}
                    </p>
                  )}
                </li>
              ))}
              {items.length === 0 && (
                <li className="border border-line bg-panel/50 px-3.5 py-3 text-xs text-ink-3">
                  No evidence entries are available for this stage yet.
                </li>
              )}
            </ul>

            {limitations && limitations.length > 0 && (
              <div className="mt-5">
                <p className="label mb-2">Limitations</p>
                <ul className="flex flex-col gap-1.5">
                  {limitations.map((limitation) => (
                    <li key={limitation} className="flex gap-2 text-2xs leading-relaxed text-ink-2">
                      <span className="text-ink-3">—</span>
                      {limitation}
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>

          {footer && <footer className="border-t border-line px-5 py-3">{footer}</footer>}
        </motion.aside>
      )}
    </AnimatePresence>
  );
}
