import { existsSync, readFileSync } from "node:fs";
import path from "node:path";
import type { NextConfig } from "next";

// "/election" -> the whole UI lives under http://<host>/election/... (see
// src/lib/basePath.ts and deploy/iis/web.config).  Empty = served from "/".
// Next only reads .env files from this folder, so the value is taken from the
// project's root .env when it is not set in the environment; `next build`,
// `next start` and `next dev` must all agree on it.
function rootEnv(name: string): string | undefined {
  const file = path.join(__dirname, "..", ".env");
  if (!existsSync(file)) return undefined;
  const line = readFileSync(file, "utf8").split(/\r?\n/).find((l) => l.startsWith(`${name}=`));
  return line?.slice(name.length + 1).replace(/\s+#.*$/, "").trim();
}

process.env.NEXT_PUBLIC_BASE_PATH ??= rootEnv("NEXT_PUBLIC_BASE_PATH") ?? "";
const basePath = process.env.NEXT_PUBLIC_BASE_PATH.replace(/\/+$/, "");

const nextConfig: NextConfig = {
  output: "standalone",
  basePath,
  // gzip holds back the live screen's event stream when /api is proxied
  // through Next (UI opened on :3000); on a LAN the saving is negligible.
  compress: false,
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: `${process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"}/api/:path*`,
      },
    ];
  },
};

export default nextConfig;
