/**
 * API client.
 *
 * Base URL resolution (in order):
 *   1. NEXT_PUBLIC_API_URL baked in at build time (e.g. http://192.168.1.10:8000)
 *   2. Served under a base path (NEXT_PUBLIC_BASE_PATH, e.g. "/election"
 *      behind IIS): the page's own origin + base path, so the API is reached
 *      as http://<server-ip>/election/api/... through the same port 80.
 *   3. In the browser: same host as the page, port 8000  ->  works for
 *      "http://localhost:3000" on a PC and "http://<server-ip>:3000" on the LAN
 *      without rebuilding.
 *   4. http://localhost:8000
 */

import type {
  ActiveElection, AuditLogEntry, Ballot, BallotDetail, BallotList, BallotReviewRequest,
  Candidate, DashboardData, Election, ElectionDetail, FolderListing,
  DatabaseInfo, ElectionReport, LiveBallotEvent, LoginResponse, Position,
  ProcessFolderResponse, ReplayStatus, SystemStatus,
} from "./types";
import { BASE_PATH } from "./basePath";

export function getApiBaseUrl(): string {
  const configured = process.env.NEXT_PUBLIC_API_URL;
  if (configured) return configured.replace(/\/$/, "");
  if (typeof window !== "undefined") {
    if (BASE_PATH) return `${window.location.origin}${BASE_PATH}`;
    return `${window.location.protocol}//${window.location.hostname}:8000`;
  }
  return "http://localhost:8000";
}

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

let unauthorizedHandler: (() => void) | null = null;
/** Called whenever the API answers 401 (token expired) – wired by AuthProvider. */
export function onUnauthorized(handler: (() => void) | null) {
  unauthorizedHandler = handler;
}

interface RequestOptions extends RequestInit {
  token?: string | null;
}

async function parseError(response: Response, fallback: string): Promise<ApiError> {
  let message = fallback;
  try {
    const body = await response.json();
    if (typeof body.detail === "string") message = body.detail;
    else if (Array.isArray(body.detail)) message = body.detail.map((d: { msg: string }) => d.msg).join(", ");
  } catch {
    /* non-JSON error body */
  }
  if (response.status === 401) unauthorizedHandler?.();
  return new ApiError(response.status, message);
}

export async function apiFetch<T>(endpoint: string, options: RequestOptions = {}): Promise<T> {
  const { token, headers, ...rest } = options;
  const finalHeaders: Record<string, string> = { ...(headers as Record<string, string>) };
  if (rest.body && !(rest.body instanceof FormData)) finalHeaders["Content-Type"] = "application/json";
  if (token) finalHeaders["Authorization"] = `Bearer ${token}`;

  const response = await fetch(`${getApiBaseUrl()}${endpoint}`, { ...rest, headers: finalHeaders });
  if (!response.ok) throw await parseError(response, `Request failed (HTTP ${response.status})`);
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

export async function apiBlob(endpoint: string, token: string): Promise<Blob> {
  const response = await fetch(`${getApiBaseUrl()}${endpoint}`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!response.ok) throw await parseError(response, `Request failed (HTTP ${response.status})`);
  return response.blob();
}

const json = (body: unknown) => JSON.stringify(body);

/** Typed wrappers for every backend endpoint, grouped like the routers. */
export const api = {
  auth: {
    login: (username: string, password: string) =>
      apiFetch<LoginResponse>("/api/auth/login", { method: "POST", body: json({ username, password }) }),
    changePassword: (token: string, current_password: string, new_password: string) =>
      apiFetch<{ status: string }>("/api/auth/change-password", {
        method: "PUT", token, body: json({ current_password, new_password }),
      }),
  },

  elections: {
    list: () => apiFetch<Election[]>("/api/elections"),
    get: (id: number) => apiFetch<ElectionDetail>(`/api/elections/${id}`),
    create: (token: string, data: Partial<Election>) =>
      apiFetch<Election>("/api/elections", { method: "POST", token, body: json(data) }),
    update: (token: string, id: number, data: Partial<Election>) =>
      apiFetch<Election>(`/api/elections/${id}`, { method: "PUT", token, body: json(data) }),
    remove: (token: string, id: number) =>
      apiFetch<void>(`/api/elections/${id}`, { method: "DELETE", token }),
    seedPositions: (token: string, id: number, withTemplateCandidates: boolean) =>
      apiFetch<ElectionDetail>(
        `/api/elections/${id}/seed-positions?with_template_candidates=${withTemplateCandidates}`,
        { method: "POST", token },
      ),
    addPosition: (token: string, id: number, data: Partial<Position>) =>
      apiFetch<Position>(`/api/elections/${id}/positions`, { method: "POST", token, body: json(data) }),
    updatePosition: (token: string, id: number, positionId: number, data: Partial<Position>) =>
      apiFetch<Position>(`/api/elections/${id}/positions/${positionId}`, { method: "PUT", token, body: json(data) }),
    removePosition: (token: string, id: number, positionId: number) =>
      apiFetch<void>(`/api/elections/${id}/positions/${positionId}`, { method: "DELETE", token }),
  },

  candidates: {
    list: (electionId: number) => apiFetch<Candidate[]>(`/api/candidates/election/${electionId}`),
    create: (token: string, data: Partial<Candidate>) =>
      apiFetch<Candidate>("/api/candidates", { method: "POST", token, body: json(data) }),
    update: (token: string, id: number, data: Partial<Candidate>) =>
      apiFetch<Candidate>(`/api/candidates/${id}`, { method: "PUT", token, body: json(data) }),
    remove: (token: string, id: number) =>
      apiFetch<void>(`/api/candidates/${id}`, { method: "DELETE", token }),
    /** Load candidates from a CSV (voter_no, post_no, name_en, name_bn). */
    importCsv: (token: string, electionId: number, file: File, replace: boolean) => {
      const form = new FormData();
      form.append("file", file);
      return apiFetch<Candidate[]>(`/api/candidates/import?election_id=${electionId}&replace=${replace}`, {
        method: "POST", token, body: form,
      });
    },
  },

  ballots: {
    list: (token: string, electionId: number, page = 1, perPage = 25, status?: string) =>
      apiFetch<BallotList>(
        `/api/ballots?election_id=${electionId}&page=${page}&per_page=${perPage}` +
          (status ? `&status_filter=${status}` : ""),
        { token },
      ),
    get: (token: string, id: number) => apiFetch<BallotDetail>(`/api/ballots/${id}`, { token }),
    preview: (token: string, id: number) => apiBlob(`/api/ballots/${id}/preview`, token),
    upload: (token: string, electionId: number, files: File[]) => {
      const form = new FormData();
      files.forEach((file) => form.append("files", file));
      return apiFetch<Ballot[]>(`/api/ballots/upload?election_id=${electionId}`, {
        method: "POST", token, body: form,
      });
    },
    scanFolder: (token: string, electionId: number) =>
      apiFetch<ProcessFolderResponse>(`/api/ballots/scan-folder?election_id=${electionId}`, {
        method: "POST", token,
      }),
    review: (token: string, id: number, data: BallotReviewRequest) =>
      apiFetch<BallotDetail>(`/api/ballots/${id}/review`, { method: "PUT", token, body: json(data) }),
    reprocess: (token: string, id: number) =>
      apiFetch<BallotDetail>(`/api/ballots/${id}/reprocess`, { method: "POST", token }),
    remove: (token: string, id: number) =>
      apiFetch<void>(`/api/ballots/${id}`, { method: "DELETE", token }),
    /** Delete the given ballots, or every ballot of an election matching the filter. */
    bulkRemove: (token: string, data: { ballot_ids?: number[]; election_id?: number; status_filter?: string | null; all_matching?: boolean }) =>
      apiFetch<{ deleted: number }>("/api/ballots/bulk-delete", { method: "POST", token, body: json(data) }),
  },

  reports: {
    /** Result summary + ballot-by-ballot tally (admin only). */
    get: (token: string, electionId: number) => apiFetch<ElectionReport>(`/api/reports/${electionId}`, { token }),
  },

  dashboard: {
    active: () => apiFetch<ActiveElection>("/api/dashboard/active"),
    results: (electionId: number, token?: string | null) =>
      apiFetch<DashboardData>(`/api/dashboard/results/${electionId}`, { token }),
    latest: (electionId: number) => apiFetch<LiveBallotEvent | null>(`/api/dashboard/latest/${electionId}`),
    /**
     * Live stream URLs, best first.  Behind a base path (IIS on port 80) the
     * stream goes straight to the API on :8000, because the IIS proxy holds
     * the event stream back; the proxied URL is the fallback.
     */
    streamUrls: (electionId: number): string[] => {
      const path = `/api/dashboard/stream/${electionId}`;
      const proxied = `${getApiBaseUrl()}${path}`;
      if (!BASE_PATH || process.env.NEXT_PUBLIC_API_URL || typeof window === "undefined") return [proxied];
      return [`${window.location.protocol}//${window.location.hostname}:8000${path}`, proxied];
    },
    publicPreviewUrl: (ballotId: number) => `${getApiBaseUrl()}/api/dashboard/ballots/${ballotId}/preview`,
  },

  admin: {
    publish: (token: string, electionId: number, publish: boolean) =>
      apiFetch<{ status: string; replay: ReplayStatus }>(`/api/admin/dashboard/${electionId}/publish?publish=${publish}`, {
        method: "PUT", token,
      }),
    /** Show the count again on the live screen, from the first ballot. */
    replay: (token: string, electionId: number) =>
      apiFetch<ReplayStatus>(`/api/admin/dashboard/${electionId}/replay`, { method: "POST", token }),
    /** End the replay; the live screen jumps to the totals. */
    skipReplay: (token: string, electionId: number) =>
      apiFetch<ReplayStatus>(`/api/admin/dashboard/${electionId}/replay`, { method: "DELETE", token }),
    pause: (token: string, electionId: number, pause: boolean) =>
      apiFetch<{ status: string }>(`/api/admin/dashboard/${electionId}/pause?pause=${pause}`, {
        method: "PUT", token,
      }),
    /** PAUSE / START the count: while paused no ballot is read. */
    pauseCounting: (token: string, electionId: number, pause: boolean) =>
      apiFetch<{ status: string }>(`/api/admin/counting/${electionId}/pause?pause=${pause}`, {
        method: "PUT", token,
      }),
    setStatus: (token: string, electionId: number, status: string) =>
      apiFetch<{ status: string }>(`/api/admin/election/${electionId}/status?new_status=${status}`, {
        method: "PUT", token,
      }),
    recount: (token: string, electionId: number) =>
      apiFetch<{ status: string }>(`/api/admin/election/${electionId}/recount`, { method: "POST", token }),
    auditLog: (token: string, limit = 100) =>
      apiFetch<AuditLogEntry[]>(`/api/admin/audit-log?limit=${limit}`, { token }),
    system: (token: string) => apiFetch<SystemStatus>("/api/admin/system", { token }),
    browseFolders: (token: string, path?: string) =>
      apiFetch<FolderListing>(`/api/admin/fs/browse${path ? `?path=${encodeURIComponent(path)}` : ""}`, { token }),
    updateFolders: (token: string, data: { scanned_folder?: string; completed_folder?: string; failed_folder?: string }) =>
      apiFetch<SystemStatus>("/api/admin/folders", { method: "PUT", token, body: json(data) }),
    database: (token: string) => apiFetch<DatabaseInfo>("/api/admin/database", { token }),
    setDatabaseYear: (token: string, year: number) =>
      apiFetch<DatabaseInfo>("/api/admin/database", { method: "PUT", token, body: json({ year }) }),
  },
};
