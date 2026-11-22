"use client";

import { useEffect } from "react";

/**
 * Runs `load` when it changes (normally: on mount and when its inputs change)
 * and, optionally, again every `intervalMs` milliseconds.
 *
 * `load` should be a `useCallback` that fetches data and stores it with
 * setState.  Keeping this in one hook avoids repeating the interval logic on
 * every admin page.
 */
export function useLoader(load: () => Promise<void> | void, intervalMs?: number) {
  useEffect(() => {
    void load();
    if (!intervalMs) return;
    const timer = setInterval(() => void load(), intervalMs);
    return () => clearInterval(timer);
  }, [load, intervalMs]);
}
