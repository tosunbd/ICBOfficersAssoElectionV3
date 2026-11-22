"use client";

import Link from "next/link";
import { useCallback, useState } from "react";
import { api } from "@/lib/api";
import { BALLOT_STATUS_LABEL, errorMessage, formatDateTime, publishedMessage } from "@/lib/format";
import type { Ballot, BallotStatus, DashboardData, SystemStatus } from "@/lib/types";
import { useAuth } from "@/hooks/useAuth";
import { useElection } from "@/hooks/useElection";
import { useLoader } from "@/hooks/useLoader";
import { useToast } from "@/components/ui/Toast";
import { Alert, CardHead, ElectionStatusBadge, EmptyState, Skeleton, Spinner } from "@/components/ui/Basics";
import { StatsGrid } from "@/components/dashboard/ResultsView";
import { Icon, type IconName } from "@/components/ui/Icon";
import { AnimatedNumber, RingGauge } from "@/components/ui/Motion";

const TIMELINE_TONE: Record<BallotStatus, { tone: string; icon: IconName }> = {
  processing: { tone: "", icon: "refresh" },
  processed: { tone: "success", icon: "check" },
  needs_review: { tone: "warning", icon: "alert" },
  reviewed: { tone: "accent", icon: "shield" },
  error: { tone: "error", icon: "xCircle" },
};

function greeting(): string {
  const hour = new Date().getHours();
  return hour < 12 ? "Good morning" : hour < 17 ? "Good afternoon" : "Good evening";
}

export default function OverviewPage() {
  const { token, username } = useAuth();
  const { election, elections, loading, patch } = useElection();
  const toast = useToast();
  const [data, setData] = useState<DashboardData | null>(null);
  const [system, setSystem] = useState<SystemStatus | null>(null);
  const [recent, setRecent] = useState<Ballot[]>([]);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    if (!token || !election) return;
    try {
      const [results, status, ballots] = await Promise.all([
        api.dashboard.results(election.id, token),
        api.admin.system(token),
        api.ballots.list(token, election.id, 1, 8),
      ]);
      setData(results);
      setSystem(status);
      setRecent(ballots.ballots);
    } catch (err) {
      toast.error(errorMessage(err));
    }
  }, [token, election, toast]);

  useLoader(load, 5000);  // keep the overview fresh while scanning

  const scanFolder = async () => {
    if (!token || !election) return;
    setBusy(true);
    try {
      const summary = await api.ballots.scanFolder(token, election.id);
      toast.success(`Scan folder: ${summary.files_processed} processed, ${summary.files_errored} error(s) of ${summary.files_found} file(s)`);
      await load();
    } catch (err) {
      toast.error(errorMessage(err));
    } finally {
      setBusy(false);
    }
  };

  const togglePublish = async () => {
    if (!token || !election) return;
    try {
      const response = await api.admin.publish(token, election.id, !election.dashboard_published);
      patch({ dashboard_published: !election.dashboard_published });
      toast.success(election.dashboard_published ? "Dashboard hidden" : publishedMessage(response.replay));
    } catch (err) {
      toast.error(errorMessage(err));
    }
  };

  const togglePause = async () => {
    if (!token || !election) return;
    try {
      await api.admin.pause(token, election.id, !election.dashboard_paused);
      patch({ dashboard_paused: !election.dashboard_paused });
      toast.success(`Live updates ${election.dashboard_paused ? "resumed" : "paused"}`);
    } catch (err) {
      toast.error(errorMessage(err));
    }
  };

  if (loading) return <Spinner label="Loading…" />;

  if (elections.length === 0 || !election) {
    return (
      <div className="page">
        <div className="page-header"><div><div className="page-eyebrow">Welcome</div><h1>Let&apos;s set up the election</h1><p>Three quick steps and the counting room is ready.</p></div></div>
        <EmptyState icon="landmark" title="No election yet">
          <p>Create one under <Link href="/admin/elections">Elections</Link>, seed the positions, add the candidates, then set it to <strong>active</strong>.</p>
          <Link href="/admin/elections" className="btn btn-accent mt-6"><Icon name="plus" size={16} /> Create the election</Link>
        </EmptyState>
      </div>
    );
  }

  const autoProcessing = system?.auto_process_enabled && system.watcher_running && system.active_election_id === election.id;
  const stats = data?.stats;
  const breakdown = stats ? [
    { label: "Processed", value: stats.processed_ballots, color: "var(--color-success)" },
    { label: "Reviewed", value: stats.reviewed_ballots, color: "var(--color-accent-400)" },
    { label: "Needs review", value: stats.needs_review_ballots, color: "var(--color-warning)" },
    { label: "Errors", value: stats.error_ballots, color: "var(--color-error)" },
    { label: "Pending", value: stats.pending_ballots, color: "var(--color-primary-300)" },
  ] : [];
  const breakdownTotal = Math.max(1, breakdown.reduce((sum, b) => sum + b.value, 0));

  return (
    <div className="page">
      <section className="hero">
        <div>
          <div className="hero-greeting"><Icon name="sparkles" size={15} style={{ color: "var(--color-accent-text)" }} />{greeting()}, {username}</div>
          {election.title_bn ? (
            <>
              <h1 className="hero-title hero-title-main-bn">{election.title_bn}</h1>
              <div className="hero-title-en">{election.title}</div>
            </>
          ) : <h1 className="hero-title">{election.title}</h1>}
          <div className="hero-pills">
            <ElectionStatusBadge status={election.status} />
            <span className="badge badge-muted"><Icon name="landmark" />{election.year}</span>
            <span className="badge badge-muted"><Icon name="users" />{election.total_voters.toLocaleString()} voters</span>
            <span className={`badge ${election.dashboard_published ? "badge-success" : "badge-muted"}`}><Icon name={election.dashboard_published ? "eye" : "eyeOff"} />{election.dashboard_published ? "Results public" : "Results hidden"}</span>
            {data?.replay && <span className="badge badge-warning"><Icon name="activity" />Counting on screen · {data.replay.position} of {data.replay.total}</span>}
          </div>
          <div className="hero-actions">
            <button className="btn btn-primary" onClick={scanFolder} disabled={busy}>
              {busy ? <><span className="btn-spinner" /> Scanning…</> : <><Icon name="folderScan" size={17} /> Scan folder now</>}
            </button>
            <button className={`btn ${election.dashboard_published ? "btn-danger-ghost" : "btn-accent"}`} onClick={togglePublish}>
              <Icon name={election.dashboard_published ? "lock" : "broadcast"} size={16} />
              {election.dashboard_published ? "Hide results" : "Publish results"}
            </button>
            <button className="btn btn-ghost" onClick={togglePause}>
              <Icon name={election.dashboard_paused ? "play" : "pause"} size={15} />
              {election.dashboard_paused ? "Resume live updates" : "Pause live updates"}
            </button>
          </div>
        </div>
        <RingGauge value={stats?.turnout_percentage ?? 0} size={196} stroke={14}>
          <div className="hero-gauge-value"><AnimatedNumber value={stats?.turnout_percentage ?? 0} suffix="%" /></div>
          <div className="hero-gauge-label">Turnout</div>
          <div className="hero-gauge-sub">{stats ? `${stats.counted_ballots} of ${stats.total_voters}` : "—"}</div>
        </RingGauge>
      </section>

      {election.status !== "active" && (
        <Alert type="warning">
          This election is <strong>{election.status}</strong>. Files dropped in the Scanned folder are only processed
          automatically for the <strong>active</strong> election. Change the status under <Link href="/admin/elections">Elections</Link>.
        </Alert>
      )}
      {system && !system.auto_process_enabled && (
        <Alert type="info">Automatic processing is disabled (AUTO_PROCESS_ENABLED=false). Use “Scan folder now” or upload files.</Alert>
      )}
      {system?.last_error && <Alert type="error">Last processing error: {system.last_error}</Alert>}

      <div className="mb-6">
        {stats ? <StatsGrid stats={stats} compact /> : (
          <div className="stats-grid">{[0, 1, 2, 3].map((i) => <Skeleton key={i} height={128} style={{ borderRadius: 18 }} />)}</div>
        )}
      </div>

      <div className="overview-grid">
        <div className="card">
          <CardHead icon="server" title="Automatic processing" subtitle="Folder watcher & ballot reader" />
          {system ? (
            <>
              <div className="health">
                <span className={`health-orb ${autoProcessing ? "ok" : "warn"}`}><Icon name={autoProcessing ? "activity" : "pause"} size={20} strokeWidth={2.2} /></span>
                <div>
                  <div className="health-title">{autoProcessing ? "Watching the Scanned folder" : "Not processing for this election"}</div>
                  <div className="health-sub">{system.os_events_active ? "OS file notifications + polling" : "Polling only"}</div>
                </div>
              </div>
              <div className="mini-stats">
                <div className="mini-stat"><strong><AnimatedNumber value={system.files_waiting} /></strong><span>Files waiting</span></div>
                <div className="mini-stat"><strong><AnimatedNumber value={system.queue_size} /></strong><span>In queue</span></div>
                <div className="mini-stat"><strong><AnimatedNumber value={system.files_processed_since_start} /></strong><span>Processed</span></div>
              </div>
              {stats && (
                <>
                  <div className="meter" aria-label="Ballot status breakdown">
                    {breakdown.filter((b) => b.value > 0).map((b) => (
                      <span key={b.label} style={{ width: `${(b.value / breakdownTotal) * 100}%`, background: b.color }} title={`${b.label}: ${b.value}`} />
                    ))}
                  </div>
                  <div className="meter-legend">
                    {breakdown.map((b) => <span key={b.label}><i style={{ background: b.color }} />{b.label}<strong>{b.value}</strong></span>)}
                  </div>
                </>
              )}
              <div className="info-list mt-6">
                {[
                  { label: "Scanned folder", value: system.scanned_folder, icon: "folderScan" as IconName },
                  { label: "Completed folder", value: system.completed_folder, icon: "checkCircle" as IconName },
                  { label: "Failed folder", value: system.failed_folder, icon: "xCircle" as IconName },
                ].map((row) => (
                  <div className="info-row" key={row.label}>
                    <span className="info-row-icon"><Icon name={row.icon} size={16} /></span>
                    <div style={{ minWidth: 0 }}><div className="info-row-label">{row.label}</div><div className="info-row-value"><code>{row.value}</code></div></div>
                  </div>
                ))}
                <Link href="/admin/settings#folders" className="btn btn-ghost btn-sm" style={{ alignSelf: "flex-start" }}><Icon name="folderScan" size={14} /> Change folders</Link>
              </div>
            </>
          ) : <Spinner />}
        </div>

        <div className="card">
          <CardHead icon="activity" title="Recent ballots" subtitle="Refreshes every 5 seconds" gold>
            <Link href="/admin/ballots" className="btn btn-ghost btn-sm">View all <Icon name="arrowRight" size={14} /></Link>
          </CardHead>
          {recent.length === 0 ? (
            <div className="empty-inline"><Icon name="inbox" size={30} />No ballots processed yet.<br />Scanned ballots will stream in here.</div>
          ) : (
            <ul className="timeline stagger">
              {recent.map((b) => {
                const look = TIMELINE_TONE[b.status] ?? TIMELINE_TONE.processing;
                return (
                  <li key={b.id}>
                    <Link href={`/admin/ballots/${b.id}`} className="timeline-item" style={{ color: "inherit" }}>
                      <span className={`timeline-dot ${look.tone}`}><Icon name={look.icon} size={16} strokeWidth={2.2} /></span>
                      <div className="timeline-body">
                        <div className="timeline-title">
                          Ballot #{b.id}
                          {b.ballot_paper_no && <span className="chip-no">{b.ballot_paper_no}</span>}
                          <span className="text-faint text-xs" style={{ fontWeight: 600 }}>{BALLOT_STATUS_LABEL[b.status]}</span>
                        </div>
                        <div className="timeline-meta" title={b.pdf_filename}>{b.pdf_filename}{b.page_number > 1 ? ` · p${b.page_number}` : ""} · {formatDateTime(b.processed_at ?? b.scanned_at)}</div>
                      </div>
                      <div className="timeline-right"><strong>{b.total_votes_extracted}</strong>votes</div>
                    </Link>
                  </li>
                );
              })}
            </ul>
          )}
        </div>
      </div>
    </div>
  );
}
