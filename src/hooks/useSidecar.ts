import { useState, useEffect } from "react";
import { sidecarApi } from "../services/sidecarApi";

const MAX_ATTEMPTS = 20;
const INITIAL_DELAY = 300;
const MAX_DELAY = 5000;

export function useSidecar() {
  const [isReady, setIsReady] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function init() {
      let delay = INITIAL_DELAY;
      for (let attempt = 0; attempt < MAX_ATTEMPTS; attempt++) {
        if (cancelled) return;
        try {
          if (!sidecarApi["baseUrl"]) {
            await sidecarApi.initialize();
          }
          const health = await sidecarApi.healthCheck();
          if (health.status === "ok") {
            if (!cancelled) setIsReady(true);
            return;
          }
        } catch {
          // Sidecar not ready yet
        }
        await new Promise((resolve) => setTimeout(resolve, delay));
        delay = Math.min(delay * 2, MAX_DELAY);
      }
      if (!cancelled) {
        setError("Sidecar failed to start");
      }
    }

    init();
    return () => {
      cancelled = true;
    };
  }, []);

  return { isReady, error };
}
