/**
 * Waiting-state illustration: a ballot paper floats down and slips into an
 * ICB ballot box, over and over, with a glow at the slot and twinkling stars.
 * Pure SVG + CSS (see `.ballot-box` in live.css).
 */
import { withBase } from "@/lib/basePath";

export function BallotBox({ size = 260 }: { size?: number }) {
  return (
    <svg className="ballot-box" width={size} height={size} viewBox="0 0 260 260" role="img" aria-label="Ballot box awaiting the next ballot">
      <defs>
        <linearGradient id="bb-front" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="#1f3170" />
          <stop offset="100%" stopColor="#0c1636" />
        </linearGradient>
        <linearGradient id="bb-lid" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="#34498f" />
          <stop offset="100%" stopColor="#1d2d63" />
        </linearGradient>
        <linearGradient id="bb-gold" x1="0" y1="0" x2="1" y2="0">
          <stop offset="0%" stopColor="#c9971c" />
          <stop offset="50%" stopColor="#fff1b8" />
          <stop offset="100%" stopColor="#c9971c" />
        </linearGradient>
        <radialGradient id="bb-glow">
          <stop offset="0%" stopColor="#ffe89a" stopOpacity="0.95" />
          <stop offset="100%" stopColor="#f5c542" stopOpacity="0" />
        </radialGradient>
        <clipPath id="bb-above-slot"><rect x="0" y="0" width="260" height="113" /></clipPath>
        <clipPath id="bb-seal"><circle cx="130" cy="178" r="30" /></clipPath>
      </defs>

      {/* floor shadow */}
      <ellipse className="bb-shadow" cx="130" cy="240" rx="92" ry="9" fill="#000" opacity="0.35" />

      {/* the paper, clipped so it disappears into the slot */}
      <g clipPath="url(#bb-above-slot)">
        <g className="bb-paper">
          <rect x="100" y="14" width="60" height="78" rx="4" fill="#ffffff" stroke="#e5e7eb" />
          <rect x="108" y="24" width="30" height="3" rx="1.5" fill="#94a3b8" />
          {[36, 48, 60, 72].map((y) => (
            <g key={y}>
              <rect x="108" y={y} width="26" height="3" rx="1.5" fill="#cbd5e1" />
              <rect x="140" y={y - 3} width="10" height="9" rx="1.5" fill="none" stroke="#64748b" strokeWidth="1.2" />
            </g>
          ))}
          <path d="M141.5 46.5 l7 6 M148.5 46.5 l-7 6" stroke="#16a34a" strokeWidth="2" strokeLinecap="round" />
          <path d="M141.5 70.5 l7 6 M148.5 70.5 l-7 6" stroke="#16a34a" strokeWidth="2" strokeLinecap="round" />
        </g>
      </g>

      {/* lid */}
      <path d="M40 104 L220 104 L236 126 L24 126 Z" fill="url(#bb-lid)" />
      <rect x="92" y="109" width="76" height="8" rx="4" fill="#03060e" />
      <ellipse className="bb-slot-glow" cx="130" cy="112" rx="52" ry="12" fill="url(#bb-glow)" />

      {/* front */}
      <rect x="24" y="126" width="212" height="108" rx="10" fill="url(#bb-front)" />
      <rect x="24" y="126" width="212" height="4" fill="url(#bb-gold)" />
      <rect x="24" y="226" width="212" height="3" fill="url(#bb-gold)" opacity="0.6" />
      <circle cx="130" cy="178" r="34" fill="url(#bb-gold)" />
      <circle cx="130" cy="178" r="31" fill="#fff" />
      <image href={withBase("/icb-logo.png")} x="100" y="148" width="60" height="60" clipPath="url(#bb-seal)" />

      {/* stars */}
      {[[36, 50, 0], [222, 64, 0.8], [52, 96, 1.6], [206, 26, 2.2], [20, 170, 1.1], [244, 150, 2.8]].map(([x, y, delay], i) => (
        <path key={i} className="bb-star" style={{ animationDelay: `${delay}s` }}
          d={`M${x} ${y - 6} L${x + 1.6} ${y - 1.6} L${x + 6} ${y} L${x + 1.6} ${y + 1.6} L${x} ${y + 6} L${x - 1.6} ${y + 1.6} L${x - 6} ${y} L${x - 1.6} ${y - 1.6} Z`}
          fill="#ffe89a" />
      ))}
    </svg>
  );
}
