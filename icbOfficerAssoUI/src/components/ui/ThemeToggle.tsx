"use client";

import { useTheme } from "@/hooks/useTheme";
import { Icon } from "./Icon";

/**
 * Dark / light switch: a small sky with the sun (light) or moon (dark)
 * sliding across it.  `compact` drops the text label for tight spaces.
 */
export function ThemeToggle({ compact = false, className = "" }: { compact?: boolean; className?: string }) {
  const { theme, toggleTheme } = useTheme();
  const isDark = theme === "dark";
  const label = isDark ? "Switch to light mode" : "Switch to dark mode";

  return (
    <button
      type="button"
      className={`theme-toggle ${compact ? "is-compact" : ""} ${className}`.trim()}
      onClick={toggleTheme}
      aria-label={label}
      title={label}
      aria-pressed={isDark}
    >
      <span className="theme-toggle-track" aria-hidden="true">
        <span className="theme-toggle-thumb"><Icon name={isDark ? "moon" : "sun"} strokeWidth={2.4} /></span>
      </span>
      {!compact && <span>{isDark ? "Dark" : "Light"}</span>}
    </button>
  );
}
