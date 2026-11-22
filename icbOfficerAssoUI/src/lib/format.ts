import type { BallotStatus, ElectionStatus, ReplayStatus } from "./types";

/** API timestamps are naive UTC; make them explicit before formatting. */
export function formatDateTime(value: string | null | undefined): string {
  if (!value) return "—";
  const iso = /[zZ]|[+-]\d\d:\d\d$/.test(value) ? value : `${value}Z`;
  const date = new Date(iso);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
}

export const BALLOT_STATUS_LABEL: Record<BallotStatus, string> = {
  processing: "Processing",
  processed: "Processed",
  needs_review: "Needs review",
  reviewed: "Reviewed",
  error: "Error",
};

export const BALLOT_STATUS_BADGE: Record<BallotStatus, string> = {
  processing: "badge-info",
  processed: "badge-success",
  needs_review: "badge-warning",
  reviewed: "badge-primary",
  error: "badge-error",
};

export const ELECTION_STATUS_BADGE: Record<ElectionStatus, string> = {
  draft: "badge-info",
  active: "badge-success",
  completed: "badge-accent",
};

export function errorMessage(error: unknown, fallback = "Something went wrong"): string {
  if (error instanceof Error && error.message) return error.message;
  return fallback;
}

/** Toast after Publish: the live screen counts every ballot again, from the first. */
export function publishedMessage(replay: ReplayStatus | undefined): string {
  if (!replay?.running) return "Results published to the public dashboard";
  return `Published: the live screen now counts every ballot from the first, ${replay.seconds} s each`;
}
