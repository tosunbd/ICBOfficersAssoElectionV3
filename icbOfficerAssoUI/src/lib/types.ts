/**
 * TypeScript mirrors of the backend Pydantic schemas (icbOfficerAssoAPI/app/schemas).
 * Keep these in sync when the API changes.
 */

export type ElectionStatus = "draft" | "active" | "completed";
export type BallotStatus = "processing" | "processed" | "needs_review" | "reviewed" | "error";

export interface Election {
  id: number;
  title: string;
  title_bn: string | null;
  year: number;
  description: string | null;
  status: ElectionStatus;
  dashboard_published: boolean;
  dashboard_paused: boolean;
  /** PAUSE pressed on the live screen: no ballot is read until START. */
  counting_paused?: boolean;
  total_voters: number;
  /** Seconds the public screen shows each ballot (live count and the replay after Publish). */
  ballot_display_seconds: number;
  created_at: string;
  updated_at: string;
}

export interface Position {
  id: number;
  election_id: number;
  position_order: number;
  name_en: string;
  name_bn: string | null;
  max_selections: number;
  created_at: string;
}

export interface ElectionDetail extends Election {
  positions: Position[];
}

export interface Candidate {
  id: number;
  position_id: number;
  election_id: number;
  voter_no: string;
  name_en: string;
  name_bn: string | null;
  display_order: number;
  vote_count: number;
  created_at: string;
}

export interface Vote {
  id: number;
  ballot_id: number;
  candidate_id: number;
  position_id: number;
  is_valid: boolean;
  invalid_reason: string | null;
  confidence_score: number;
  created_at: string;
}

export interface Ballot {
  id: number;
  election_id: number;
  ballot_paper_no: string | null;
  pdf_filename: string;
  page_number: number;
  source: "watcher" | "upload" | "manual";
  status: BallotStatus;
  error_message: string | null;
  ocr_warnings: string[];
  boxes_detected: number;
  boxes_expected: number;
  total_votes_extracted: number;
  is_valid: boolean;
  printed_paper_no?: string | null;
  has_preview: boolean;
  scanned_at: string;
  processed_at: string | null;
  reviewed_at: string | null;
}

export interface BallotDetail extends Ballot {
  votes: Vote[];
}

export interface BallotList {
  ballots: Ballot[];
  total: number;
  page: number;
  per_page: number;
}

export interface VoteCorrection {
  candidate_id: number;
  position_id: number;
  is_valid: boolean;
}

export interface BallotReviewRequest {
  ballot_paper_no?: string | null;
  votes: VoteCorrection[];
}

export interface ProcessFolderResponse {
  files_found: number;
  files_processed: number;
  files_errored: number;
  details: Array<{
    filename: string;
    status: string;
    ballot_ids: number[];
    votes_extracted: number;
    error: string | null;
  }>;
}

export interface CandidateResult {
  candidate_id: number;
  voter_no: string;
  name_en: string;
  name_bn: string | null;
  vote_count: number;
  percentage: number;
  rank: number;
  is_leading: boolean;
}

export interface PositionResult {
  position_id: number;
  position_order: number;
  name_en: string;
  name_bn: string | null;
  max_selections: number;
  total_votes_cast: number;
  candidates: CandidateResult[];
}

export interface DashboardStats {
  total_ballots: number;
  counted_ballots: number;
  processed_ballots: number;
  needs_review_ballots: number;
  reviewed_ballots: number;
  error_ballots: number;
  pending_ballots: number;
  total_voters: number;
  turnout_percentage: number;
}

export interface DashboardData {
  election_id: number;
  election_title: string;
  election_title_bn: string | null;
  election_year: number;
  election_status: ElectionStatus;
  dashboard_published: boolean;
  dashboard_paused: boolean;
  /** PAUSE pressed on the live screen: no ballot is read until START. */
  counting_paused?: boolean;
  results_visible: boolean;
  stats: DashboardStats;
  positions: PositionResult[];
  /** Set while the count is replayed ballot by ballot after Publish. */
  replay?: ReplayProgress | null;
}

/** Ballot `position` of `total` in the replay that follows Publish. */
export interface ReplayProgress {
  position: number;
  total: number;
}

export interface ReplayStatus {
  running: boolean;
  shown: number;
  total: number;
  seconds: number;
}

export interface ActiveElection {
  id: number;
  title: string;
  title_bn: string | null;
  year: number;
  status: ElectionStatus;
  dashboard_published: boolean;
  dashboard_paused: boolean;
  /** PAUSE pressed on the live screen: no ballot is read until START. */
  counting_paused?: boolean;
  live_display_seconds: number;
}

export interface LiveVote {
  position_id: number;
  position_order: number;
  position_name_en: string;
  position_name_bn: string | null;
  candidate_id: number;
  voter_no: string;
  candidate_name_en: string;
  candidate_name_bn: string | null;
  is_valid: boolean;
  invalid_reason: string | null;
  confidence: number;
}

/** One counted ballot, pushed to the public live screen. */
export interface LiveBallotEvent {
  ballot_id: number;
  election_id: number;
  sequence_no: number;
  ballot_paper_no: string | null;
  pdf_filename: string;
  page_number: number;
  status: BallotStatus;
  /** counted | reread (read again) | reviewed (corrected by the committee) | unreadable */
  kind: "counted" | "reread" | "reviewed" | "unreadable";
  error_message: string | null;
  is_valid: boolean;
  has_preview: boolean;
  votes: LiveVote[];
  display_seconds: number;
  results: DashboardData;
  /** Set when this ballot is shown by the replay that follows Publish. */
  replay?: ReplayProgress | null;
}

export interface AuditLogEntry {
  id: number;
  admin_user_id: number | null;
  username: string | null;
  action: string;
  details: string | null;
  created_at: string | null;
}

export interface SystemStatus {
  auto_process_enabled: boolean;
  watcher_running: boolean;
  os_events_active: boolean;
  queue_size: number;
  files_waiting: number;
  files_processed_since_start: number;
  last_error: string | null;
  active_election_id: number | null;
  scanned_folder: string;
  completed_folder: string;
  failed_folder: string;
  ocr_dpi: number;
  mark_threshold: number;
}

export interface LoginResponse {
  access_token: string;
  token_type: string;
  username: string;
  role: string;
}

export interface FolderEntry {
  name: string;
  path: string;
}

/** One level of the server's folder tree (admin folder picker). */
export interface FolderListing {
  path: string;            // "" = list of drives
  parent: string | null;   // null at the top, "" = back to the drive list
  folders: FolderEntry[];
  shortcuts: FolderEntry[];
}

export interface DatabaseFile {
  year: number;
  file_name: string;
  size_bytes: number;
  modified_at: string;
  current: boolean;
}

/** The database file in use (one per election year) and the others next to it. */
export interface DatabaseInfo {
  year: number;
  per_year: boolean;
  file_name: string | null;
  path: string | null;
  size_bytes: number | null;
  files: DatabaseFile[];
}

/* ------------------------------------------------ Admin -> Reports */

export interface ReportCandidate {
  candidate_id: number;
  voter_no: string;
  name_en: string;
  name_bn: string | null;
  display_order: number;
  panel: "left" | "right" | "";    // side of the ballot paper the name is printed on
  votes: number;
  percentage: number;
  rank: number;
  outcome: "elected" | "tie" | "";
}

export interface ReportPosition {
  position_id: number;
  position_order: number;
  name_en: string;
  name_bn: string | null;
  max_selections: number;
  total_votes: number;
  candidates: ReportCandidate[];   // by votes, highest first
}

/** A mark found on a ballot that is not counted (Null Votes report). */
export interface ReportVoidMark {
  candidate_id: number;
  position_id: number;
  reason: string;
}

/** A scanned file that could not be read: none of its votes are counted yet. */
export interface ReportUnreadFile {
  ballot_id: number;
  pdf_filename: string;
  page_number: number;
  reason: string;
}

export interface ReportBallot {
  ballot_id: number;
  serial: number;
  ballot_paper_no: string | null;
  pdf_filename: string;
  page_number: number;
  status: string;
  is_valid: boolean;
  candidate_ids: number[];         // the 1s of this row
  void_marks: number;
  void: ReportVoidMark[];
}

export interface ElectionReport {
  election_id: number;
  title: string;
  title_bn: string | null;
  year: number;
  status: string;
  total_voters: number;
  generated_at: string;
  stats: DashboardStats;
  manual_ballots: number;  // selections saved by the Election Commission (reviewed)
  total_votes: number;
  void_marks: number;
  positions: ReportPosition[];
  ballots: ReportBallot[];
  unread_files: ReportUnreadFile[];
}
