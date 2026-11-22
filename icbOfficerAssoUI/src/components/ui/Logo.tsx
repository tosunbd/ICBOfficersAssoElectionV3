import { withBase } from "@/lib/basePath";

/**
 * ICB seal in a gold-foil medallion.  `halo` adds the slowly turning light
 * ring used on ceremonial screens (live board, login, hold screens).
 */
export function Logo({ size = 80, soft = false, halo = false }: { size?: number; soft?: boolean; halo?: boolean }) {
  return (
    <div className={`medallion ${soft ? "is-soft" : ""} ${halo ? "has-halo" : ""}`} style={{ width: size, height: size }}>
      {halo && <span className="medallion-halo" aria-hidden="true" />}
      <span className="medallion-rim">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img src={withBase("/icb-logo.png")} alt="Investment Corporation of Bangladesh" width={size} height={size} />
      </span>
    </div>
  );
}
