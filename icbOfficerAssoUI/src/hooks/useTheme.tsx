"use client";

import { createContext, useCallback, useContext, useMemo, useSyncExternalStore, type ReactNode } from "react";

export type Theme = "dark" | "light";

export const THEME_STORAGE_KEY = "icb-theme";

/**
 * Runs before React hydrates (inlined in the root layout) so the first paint
 * already has the right theme and there is no flash of the wrong colours.
 * Order of precedence: saved choice → OS preference → dark.
 */
export const THEME_INIT_SCRIPT = `(function(){try{var k="${THEME_STORAGE_KEY}";var s=localStorage.getItem(k);var t=(s==="light"||s==="dark")?s:(window.matchMedia&&window.matchMedia("(prefers-color-scheme: light)").matches?"light":"dark");document.documentElement.setAttribute("data-theme",t);}catch(e){document.documentElement.setAttribute("data-theme","dark");}})();`;

interface ThemeContextValue {
  theme: Theme;
  setTheme: (theme: Theme) => void;
  toggleTheme: () => void;
}

const ThemeContext = createContext<ThemeContextValue | null>(null);

/* ---- the <html data-theme> attribute is the single source of truth ---- */

function readDomTheme(): Theme {
  return document.documentElement.getAttribute("data-theme") === "light" ? "light" : "dark";
}

function getServerSnapshot(): Theme {
  return "dark";
}

function applyTheme(theme: Theme) {
  document.documentElement.setAttribute("data-theme", theme);
}

function readSavedTheme(): Theme | null {
  try {
    const saved = localStorage.getItem(THEME_STORAGE_KEY);
    return saved === "light" || saved === "dark" ? saved : null;
  } catch {
    return null;
  }
}

/** Notifies React when the attribute changes, and follows the OS while no explicit choice is saved. */
function subscribe(onChange: () => void): () => void {
  const observer = new MutationObserver(onChange);
  observer.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });

  const media = window.matchMedia ? window.matchMedia("(prefers-color-scheme: light)") : null;
  const onMedia = (event: MediaQueryListEvent) => {
    if (readSavedTheme()) return;
    applyTheme(event.matches ? "light" : "dark");
  };
  media?.addEventListener("change", onMedia);

  return () => {
    observer.disconnect();
    media?.removeEventListener("change", onMedia);
  };
}

export function ThemeProvider({ children }: { children: ReactNode }) {
  const theme = useSyncExternalStore(subscribe, readDomTheme, getServerSnapshot);

  const setTheme = useCallback((next: Theme) => {
    applyTheme(next);
    try { localStorage.setItem(THEME_STORAGE_KEY, next); } catch { /* storage unavailable */ }
  }, []);

  const toggleTheme = useCallback(() => {
    setTheme(readDomTheme() === "dark" ? "light" : "dark");
  }, [setTheme]);

  const value = useMemo<ThemeContextValue>(() => ({ theme, setTheme, toggleTheme }), [theme, setTheme, toggleTheme]);

  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}

export function useTheme(): ThemeContextValue {
  const context = useContext(ThemeContext);
  if (!context) throw new Error("useTheme must be used within a ThemeProvider");
  return context;
}
