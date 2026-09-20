import { useEffect } from "react";

import { useSession } from "./SessionContext";

/**
 * Global automation loop: while the production stream is running, process the
 * next real frame at the selected speed. The interval is display pacing only -
 * every frame is a real backend inspection. Never fires faster than the backend.
 */
export function useStreamLoop() {
  const { stream, streamBusy, processNextFrame } = useSession();

  useEffect(() => {
    if (!stream?.running || streamBusy) return;
    const speed = stream.speed && stream.speed > 0 ? stream.speed : 1;
    const interval = Math.max(250, 1200 / speed);
    const timer = window.setInterval(() => {
      void processNextFrame();
    }, interval);
    return () => window.clearInterval(timer);
  }, [stream?.running, stream?.speed, streamBusy, processNextFrame]);
}
