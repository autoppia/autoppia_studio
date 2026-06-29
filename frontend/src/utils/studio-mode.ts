import { useEffect, useState } from "react";

/**
 * Studio operates in two experience modes:
 *
 *  - "normal": guided, non-technical experience centered on company onboarding.
 *    Raw factory internals (trajectories, tool schemas, runtime traces,
 *    executor blueprints, capability graphs, …) stay hidden.
 *  - "dev": exposes the detailed factory objects for builders who need to debug.
 *
 * The mode is a single global preference persisted in localStorage and shared
 * across the app via the `automata-mode-changed` event (mirroring the existing
 * `automata-company-changed` pattern).
 */
export type StudioMode = "normal" | "dev";

const STORAGE_KEY = "automata_studio_mode";
const EVENT_NAME = "automata-mode-changed";

export function getStudioMode(): StudioMode {
  try {
    return localStorage.getItem(STORAGE_KEY) === "dev" ? "dev" : "normal";
  } catch {
    return "normal";
  }
}

export function setStudioMode(mode: StudioMode): void {
  try {
    localStorage.setItem(STORAGE_KEY, mode);
  } catch {
    /* ignore storage errors */
  }
  window.dispatchEvent(new CustomEvent(EVENT_NAME, { detail: { mode } }));
}

/**
 * React hook returning the current studio mode and keeping the component in
 * sync when the mode changes anywhere in the app.
 */
export function useStudioMode(): StudioMode {
  const [mode, setMode] = useState<StudioMode>(getStudioMode);

  useEffect(() => {
    const handler = (event: Event) => {
      const next = (event as CustomEvent).detail?.mode as StudioMode | undefined;
      setMode(next === "dev" ? "dev" : next === "normal" ? "normal" : getStudioMode());
    };
    window.addEventListener(EVENT_NAME, handler);
    return () => window.removeEventListener(EVENT_NAME, handler);
  }, []);

  return mode;
}
