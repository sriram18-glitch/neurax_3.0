import { useEffect } from "react";

import { useSession } from "./SessionContext";

/**
 * Polls the real batch progress while the backend inspects the validated
 * images. Polling stops as soon as the batch is complete or failed.
 */
export function useBatchPoll(batchId: string | null, interval = 1200) {
  const { batch, refreshBatch } = useSession();

  useEffect(() => {
    if (!batchId) return;
    if (batch?.status !== "inspecting") return;
    const timer = window.setInterval(() => {
      void refreshBatch(batchId);
    }, interval);
    return () => window.clearInterval(timer);
  }, [batchId, batch?.status, interval, refreshBatch]);
}