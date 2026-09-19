import type { EvidenceItem } from "./EvidenceDrawer";

/** Shared evidence-drawer callback used across views. */
export interface OpenEvidence {
  (title: string, subtitle: string, items: EvidenceItem[], limitations?: string[]): void;
}
