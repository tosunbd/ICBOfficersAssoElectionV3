/**
 * URL prefix the UI is served under, e.g. "/election" when IIS publishes it as
 * http://<server-ip>/election/... (NEXT_PUBLIC_BASE_PATH, baked in at build
 * time).  Empty = served from the root, e.g. http://localhost:3000/.
 *
 * <Link> and router.push() add it on their own; plain <img src>, window.open()
 * and the API base URL go through `withBase()`.
 */
export const BASE_PATH = (process.env.NEXT_PUBLIC_BASE_PATH || "").replace(/\/+$/, "");

export function withBase(path: string): string {
  return `${BASE_PATH}${path}`;
}
