"use client";

import Link from "next/link";
import { useCallback, useState } from "react";
import { api } from "@/lib/api";
import { errorMessage, publishedMessage } from "@/lib/format";
import type { DashboardData } from "@/lib/types";
import { useAuth } from "@/hooks/useAuth";
import { useElection } from "@/hooks/useElection";
import { useSSE } from "@/hooks/useSSE";
import { useLoader } from "@/hooks/useLoader";
import { useToast } from "@/components/ui/Toast";
import { ConfirmDialog } from "@/components/ui/Modal";
import { CardHead, EmptyState, PageHeader, Skeleton, Switch } from "@/components/ui/Basics";
import { PositionsGrid, StatsGrid } from "@/components/dashboard/ResultsView";
import { Icon } from "@/components/ui/Icon";

export default function ResultsPage() {
  const { token } = useAuth();
  const { election, patch } = useElection();
  const toast = useToast();
  const [data, setData] = useState<DashboardData | null>(null);
  const [confirmRecount, setConfirmRecount] = useState(false);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    if (!token || !election) return;
    try {
      setData(await api.dashboard.results(election.id, token));
    } catch (err) {
      toast.error(errorMessage(err));
    }
  }, [token, election, toast]);

  useLoader(load);

  // Live refresh: the public stream tells us when something changed; admins
  // always re-fetch with their token so unpublished numbers are visible.
  const { isConnected } = useSSE(election?.id ?? null, { onUpdate: () => load(), onPaused: () => load() });

  const togglePublish = async () => {
    if (!token || !election) return;
    try {
      const response = await api.admin.publish(token, election.id, !election.dashboard_published);
      patch({ dashboard_published: !election.dashboard_published });
      toast.success(election.dashboard_published ? "Results hidden from the public dashboard" : publishedMessage(response.replay));
      await load();
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

  const replayAgain = async () => {
    if (!token || !election) return;
    try {
      await api.admin.replay(token, election.id);
      toast.success("The live screen is counting again from the first ballot");
      await load();
    } catch (err) {
      toast.error(errorMessage(err));
    }
  };

  const skipReplay = async () => {
    if (!token || !election) return;
    try {
      await api.admin.skipReplay(token, election.id);
      toast.success("Replay skipped: the live screen shows the totals");
      await load();
    } catch (err) {
      toast.error(errorMessage(err));
    }
  };

  const replay = data?.replay ?? null;

  const recount = async () => {
    if (!token || !election) return;
    setBusy(true);
    try {
      await api.admin.recount(token, election.id);
      toast.success("Recount finished");
      await load();
    } catch (err) {
      toast.error(errorMessage(err));
    } finally {
      setBusy(false);
      setConfirmRecount(false);
    }
  };

  const exportCsv = () => {
    if (!data) return;
    const rows = [["Position order", "Position", "Rank", "Voter no", "Candidate", "Candidate (BN)", "Votes", "Percent", "Leading"]];
    data.positions.forEach((p) => p.candidates.forEach((c) => rows.push([
      String(p.position_order), p.name_en, String(c.rank), c.voter_no, c.name_en, c.name_bn ?? "", String(c.vote_count), String(c.percentage), c.is_leading ? "yes" : "no",
    ])));
    const csv = rows.map((r) => r.map((v) => `"${v.replace(/"/g, '""')}"`).join(",")).join("\n");
    const url = URL.createObjectURL(new Blob(["﻿" + csv], { type: "text/csv;charset=utf-8" }));
    const a = document.createElement("a");
    a.href = url;
    a.download = `results-${data.election_year}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  };

  if (!election) return <EmptyState icon="landmark" title="Create an election first" />;

  return (
    <div className="page">
      <PageHeader eyebrow="Command" title="Results & controls" subtitle="What the public dashboard shows, and the switches that control it"
        actions={
          <>
            <Link href="/dashboard" target="_blank" className="btn btn-ghost"><Icon name="external" size={15} /> View live screen</Link>
            <button className="btn btn-primary" onClick={exportCsv} disabled={!data}><Icon name="download" size={16} /> Export CSV</button>
          </>
        } />

      <div className="card card-gold mb-6">
        <CardHead icon="broadcast" title="Public dashboard controls" subtitle="Changes reach every open live screen instantly" gold>
          <span className={`badge badge-dot ${isConnected ? "badge-success pulse" : "badge-warning"}`}>{isConnected ? "Stream connected" : "Reconnecting"}</span>
        </CardHead>
        <div className="controls-grid">
          <div className="control-row">
            <Switch gold checked={election.dashboard_published} onChange={togglePublish}
              label={election.dashboard_published ? "Results are published" : "Results are hidden"}
              description={election.dashboard_published ? "The public screen shows the live tally" : "Publishing counts every ballot again on the public screen, from the first"} />
          </div>
          {election.dashboard_published && (
            <div className="control-row">
              <span className="card-title-icon"><Icon name={replay ? "activity" : "play"} size={18} /></span>
              <div className="flex-1">
                <div style={{ fontWeight: 600, fontSize: "0.9rem" }}>
                  {replay ? `Counting on screen: ballot ${replay.position} of ${replay.total}` : "Ballot-by-ballot count"}
                </div>
                <div className="text-small text-muted">
                  {replay ? "The live screen shows each ballot in turn, totals growing from zero" : "Show the whole count again from the first ballot"}
                </div>
              </div>
              {replay
                ? <button className="btn btn-ghost btn-sm" onClick={skipReplay}><Icon name="arrowRight" size={14} /> Skip to totals</button>
                : <button className="btn btn-ghost btn-sm" onClick={replayAgain}><Icon name="refresh" size={14} /> Count again</button>}
            </div>
          )}
          <div className="control-row">
            <Switch checked={!election.dashboard_paused} onChange={togglePause}
              label={election.dashboard_paused ? "Live updates paused" : "Live updates on"}
              description={election.dashboard_paused ? "Screens keep the last totals" : "Each counted ballot is shown as it arrives"} />
          </div>
          <div className="control-row">
            <span className="card-title-icon"><Icon name="calculator" size={18} /></span>
            <div className="flex-1">
              <div style={{ fontWeight: 600, fontSize: "0.9rem" }}>Recount from records</div>
              <div className="text-small text-muted">Rebuild totals from stored votes</div>
            </div>
            <button className="btn btn-ghost btn-sm" onClick={() => setConfirmRecount(true)}><Icon name="refresh" size={14} /> Recount</button>
          </div>
        </div>
      </div>

      {!data ? (
        <div className="stats-grid mb-6">{[0, 1, 2, 3].map((i) => <Skeleton key={i} height={128} style={{ borderRadius: 18 }} />)}</div>
      ) : (
        <>
          <div className="mb-6"><StatsGrid stats={data.stats} compact /></div>
          <div className="section-title">Standings by position</div>
          <PositionsGrid positions={data.positions} />
        </>
      )}

      <ConfirmDialog open={confirmRecount} title="Recount" busy={busy}
        message="Rebuild every candidate's total from the stored vote records. Safe to run at any time."
        confirmLabel="Recount" onConfirm={recount} onCancel={() => setConfirmRecount(false)} />
    </div>
  );
}
