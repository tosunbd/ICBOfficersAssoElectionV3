"use client";

import { useEffect, useId, useLayoutEffect, useRef, useState, type ReactNode } from "react";

/* ------------------------------------------------------------------ */
/*  Small motion primitives shared by the live screen and admin pages  */
/* ------------------------------------------------------------------ */

export function prefersReducedMotion(): boolean {
  return typeof window !== "undefined" && window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
}

const easeOutExpo = (t: number) => (t === 1 ? 1 : 1 - Math.pow(2, -10 * t));

/**
 * A number that glides to its new value instead of jumping.  Counts up from
 * zero on first mount so a freshly opened screen "fills in" gracefully.
 */
export function AnimatedNumber({ value, duration = 1100, decimals, suffix = "", className }: {
  value: number; duration?: number; decimals?: number; suffix?: string; className?: string;
}) {
  const places = decimals ?? (Number.isInteger(value) ? 0 : 1);
  const [shown, setShown] = useState(0);
  const from = useRef(0);
  const frame = useRef(0);

  useEffect(() => {
    const start = from.current;
    if (prefersReducedMotion() || start === value) {
      from.current = value;
      frame.current = requestAnimationFrame(() => setShown(value));
      return () => cancelAnimationFrame(frame.current);
    }
    const began = performance.now();
    const step = (now: number) => {
      const t = Math.min(1, (now - began) / duration);
      const current = start + (value - start) * easeOutExpo(t);
      from.current = current;
      setShown(current);
      if (t < 1) frame.current = requestAnimationFrame(step);
    };
    frame.current = requestAnimationFrame(step);
    return () => cancelAnimationFrame(frame.current);
  }, [value, duration]);

  return <span className={className}>{shown.toLocaleString("en-US", { minimumFractionDigits: places, maximumFractionDigits: places })}{suffix}</span>;
}

/** Circular progress ring with a gold → teal gradient stroke. */
export function RingGauge({ value, size = 120, stroke = 10, children, tone = "gold", className = "" }: {
  value: number; size?: number; stroke?: number; children?: ReactNode; tone?: "gold" | "teal" | "success"; className?: string;
}) {
  const id = useId().replace(/:/g, "");
  const radius = (size - stroke) / 2;
  const circumference = 2 * Math.PI * radius;
  const pct = Math.max(0, Math.min(100, value));
  const offset = circumference * (1 - pct / 100);
  return (
    <div className={`ring-gauge ring-${tone} ${className}`.trim()} style={{ width: size, height: size }}>
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} aria-hidden="true">
        <defs>
          <linearGradient id={`rg-${id}`} x1="0" y1="0" x2="1" y2="1">
            <stop offset="0%" className="ring-stop-a" />
            <stop offset="100%" className="ring-stop-b" />
          </linearGradient>
        </defs>
        <circle cx={size / 2} cy={size / 2} r={radius} className="ring-track" strokeWidth={stroke} fill="none" />
        <circle
          cx={size / 2} cy={size / 2} r={radius} fill="none" strokeWidth={stroke} strokeLinecap="round"
          stroke={`url(#rg-${id})`} className="ring-value"
          strokeDasharray={circumference} strokeDashoffset={offset}
          transform={`rotate(-90 ${size / 2} ${size / 2})`}
        />
      </svg>
      <div className="ring-center">{children}</div>
    </div>
  );
}

/**
 * FLIP re-ordering: children marked `data-flip="<key>"` glide from their old
 * slot to the new one whenever `dep` changes (e.g. a candidate overtakes
 * another).  Items that moved up get a brief `is-rising` highlight.
 */
export function useFlip<T extends HTMLElement>(dep: unknown) {
  const ref = useRef<T>(null);
  const slots = useRef(new Map<string, { x: number; y: number }>());

  useLayoutEffect(() => {
    const root = ref.current;
    if (!root) return;
    const reduce = prefersReducedMotion();
    const next = new Map<string, { x: number; y: number }>();
    root.querySelectorAll<HTMLElement>("[data-flip]").forEach((node) => {
      const key = node.dataset.flip as string;
      const slot = { x: node.offsetLeft, y: node.offsetTop };
      next.set(key, slot);
      const previous = slots.current.get(key);
      if (!previous || reduce) return;
      const dx = previous.x - slot.x;
      const dy = previous.y - slot.y;
      if (Math.abs(dx) < 1 && Math.abs(dy) < 1) return;
      node.animate(
        [{ transform: `translate(${dx}px, ${dy}px)` }, { transform: "translate(0, 0)" }],
        { duration: 850, easing: "cubic-bezier(0.22, 1, 0.36, 1)" },
      );
      if (dy > 0) {
        node.classList.remove("is-rising");
        void node.offsetWidth;  // restart the highlight animation
        node.classList.add("is-rising");
        window.setTimeout(() => node.classList.remove("is-rising"), 2200);
      }
    });
    slots.current = next;
  }, [dep]);

  return ref;
}

/** Ambient animated backdrop: drifting aurora light and faint star dust. */
export function Aurora() {
  return (
    <div className="aurora" aria-hidden="true">
      <span className="aurora-orb aurora-orb-1" />
      <span className="aurora-orb aurora-orb-2" />
      <span className="aurora-orb aurora-orb-3" />
      <span className="aurora-grid" />
      <span className="aurora-dust" />
    </div>
  );
}

/** Wall clock that re-renders every second (client only). */
export function useClock(options: Intl.DateTimeFormatOptions = { hour: "2-digit", minute: "2-digit", second: "2-digit" }) {
  const [now, setNow] = useState<Date | null>(null);
  useEffect(() => {
    const update = () => setNow(new Date());
    update();
    const timer = setInterval(update, 1000);
    return () => clearInterval(timer);
  }, []);
  return now ? now.toLocaleTimeString([], options) : "";
}
