import { useEffect, useRef, useCallback } from "react";

const IDLE_EVENTS = ["mousemove", "keydown", "mousedown", "touchstart", "scroll"] as const;
const WARN_BEFORE_MS = 60_000; // warn 1 minute before logout

/**
 * Auto-signs user out after `timeoutMs` of inactivity.
 * Calls `onWarn` 1 minute before logout, and `onLogout` when time expires.
 * Only active when `enabled` is true (i.e. web/auth mode).
 */
export function useIdleTimeout({
  timeoutMs = 30 * 60_000, // default 30 minutes
  enabled = false,
  onWarn,
  onLogout,
}: {
  timeoutMs?: number;
  enabled: boolean;
  onWarn?: () => void;
  onLogout: () => void;
}) {
  const timerRef = useRef<ReturnType<typeof setTimeout>>();
  const warnTimerRef = useRef<ReturnType<typeof setTimeout>>();

  const resetTimers = useCallback(() => {
    if (timerRef.current) clearTimeout(timerRef.current);
    if (warnTimerRef.current) clearTimeout(warnTimerRef.current);

    warnTimerRef.current = setTimeout(() => {
      onWarn?.();
    }, timeoutMs - WARN_BEFORE_MS);

    timerRef.current = setTimeout(() => {
      onLogout();
    }, timeoutMs);
  }, [timeoutMs, onWarn, onLogout]);

  useEffect(() => {
    if (!enabled) return;

    resetTimers();

    const handler = () => resetTimers();
    for (const event of IDLE_EVENTS) {
      window.addEventListener(event, handler, { passive: true });
    }

    return () => {
      for (const event of IDLE_EVENTS) {
        window.removeEventListener(event, handler);
      }
      if (timerRef.current) clearTimeout(timerRef.current);
      if (warnTimerRef.current) clearTimeout(warnTimerRef.current);
    };
  }, [enabled, resetTimers]);
}
