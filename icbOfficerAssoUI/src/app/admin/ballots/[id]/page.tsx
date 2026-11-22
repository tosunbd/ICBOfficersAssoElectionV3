"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useState, type MouseEvent } from "react";
import { api, getApiBaseUrl } from "@/lib/api";
import { errorMessage, formatDateTime } from "@/lib/format";
import type { BallotDetail, Candidate, Position } from "@/lib/types";
import { useAuth } from "@/hooks/useAuth";
import { useLoader } from "@/hooks/useLoader";
import { useToast } from "@/components/ui/Toast";
import { ConfirmDialog } from "@/components/ui/Modal";
import { Alert, BallotStatusBadge, CardHead, PageHeader, Spinner } from "@/components/ui/Basics";
import { Icon } from "@/components/ui/Icon";

/**
 * Ballot review: the annotated scan on the left, one checkbox per candidate
 * on the right.  Saving replaces the ballot's votes with the Election
 * Commission's choice (a manual file), also for a file the scanner could not
 * read; it then counts in the totals.  A ballot is never rejected as a whole.
 */
export default function BallotReviewPage() {
  const params = useParams<{ id: string }>();
  const ballotId = Number(params.id);
  const router = useRouter();
  const { token } = useAuth();
  const toast = useToast();

  const [ballot, setBallot] = useState<BallotDetail | null>(null);
  const [positions, setPositions] = useState<Position[]>([]);
  const [candidates, setCandidates] = useState<Candidate[]>([]);
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [paperNo, setPaperNo] = useState("");
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [zoom, setZoom] = useState(false);

  const load = useCallback(async () => {
    if (!token || !ballotId) return;
    try {
      const detail = await api.ballots.get(token, ballotId);
      const [election, list] = await Promise.all([api.elections.get(detail.election_id), api.candidates.list(detail.election_id)]);
      setBallot(detail);
      setPositions(election.positions);
      setCandidates(list);
      setSelected(new Set(detail.votes.filter((v) => v.is_valid).map((v) => v.candidate_id)));
      setPaperNo(detail.ballot_paper_no ?? "");
      if (detail.has_preview) {
        const blob = await api.ballots.preview(token, ballotId);
        setPreviewUrl((old) => { if (old) URL.revokeObjectURL(old); return URL.createObjectURL(blob); });
      }
    } catch (err) {
      toast.error(errorMessage(err));
    }
  }, [token, ballotId, toast]);

  useLoader(load);
  useEffect(() => () => { if (previewUrl) URL.revokeObjectURL(previewUrl); }, [previewUrl]);

  const byPosition = useMemo(() => {
    const map = new Map<number, Candidate[]>();
    candidates.forEach((c) => map.set(c.position_id, [...(map.get(c.position_id) ?? []), c]));
    return map;
  }, [candidates]);

  const detectedByCandidate = useMemo(() => new Map(ballot?.votes.map((v) => [v.candidate_id, v]) ?? []), [ballot]);

  const toggle = (candidate: Candidate, max: number) => {
    setSelected((current) => {
      const next = new Set(current);
      if (next.has(candidate.id)) {
        next.delete(candidate.id);
      } else {
        const chosen = (byPosition.get(candidate.position_id) ?? []).filter((c) => next.has(c.id));
        if (chosen.length >= max) {
          if (max === 1) chosen.forEach((c) => next.delete(c.id));  // radio-like behaviour
          else { toast.error(`Only ${max} selection(s) allowed for this position`); return current; }
        }
        next.add(candidate.id);
      }
      return next;
    });
  };

  const save = async () => {
    if (!token || !ballot) return;
    setBusy(true);
    try {
      const votes = candidates.filter((c) => selected.has(c.id)).map((c) => ({ candidate_id: c.id, position_id: c.position_id, is_valid: true }));
      await api.ballots.review(token, ballot.id, { ballot_paper_no: paperNo.trim() || null, votes });
      toast.success("Saved as a manual file: these votes now count");
      await load();
    } catch (err) {
      toast.error(errorMessage(err));
    } finally {
      setBusy(false);
    }
  };

  const reprocess = async () => {
    if (!token || !ballot) return;
    setBusy(true);
    try {
      await api.ballots.reprocess(token, ballot.id);
      toast.success("Ballot re-read from the scan");
      await load();
    } catch (err) {
      toast.error(errorMessage(err));
    } finally {
      setBusy(false);
    }
  };

  const remove = async () => {
    if (!token || !ballot) return;
    setBusy(true);
    try {
      await api.ballots.remove(token, ballot.id);
      toast.success("Ballot deleted");
      router.push("/admin/ballots");
    } catch (err) {
      toast.error(errorMessage(err));
      setBusy(false);
    }
  };

  if (!ballot) return <Spinner label="Loading ballot…" />;

  const selectedCount = selected.size;
  const openOriginal = async (e: MouseEvent) => {
    e.preventDefault();
    if (!token) return;
    const blob = await (await fetch(`${getApiBaseUrl()}/api/ballots/${ballot.id}/file`, { headers: { Authorization: `Bearer ${token}` } })).blob();
    window.open(URL.createObjectURL(blob), "_blank");
  };

  return (
    <div className="page">
      <PageHeader
        eyebrow="Ballot review"
        title={`Ballot #${ballot.id}`}
        subtitle={`${ballot.pdf_filename}${ballot.page_number > 1 ? ` · page ${ballot.page_number}` : ""} · ${ballot.source} · scanned ${formatDateTime(ballot.scanned_at)}`}
        actions={
          <>
            <Link href="/admin/ballots" className="btn btn-ghost"><Icon name="arrowLeft" size={16} /> Back</Link>
            <a className="btn btn-ghost" href={`${getApiBaseUrl()}/api/ballots/${ballot.id}/file`} target="_blank" rel="noreferrer" onClick={openOriginal}>
              <Icon name="file" size={16} /> Original file
            </a>
            <button className="btn btn-ghost" onClick={reprocess} disabled={busy}><Icon name="rotate" size={16} /> Re-read scan</button>
            <button className="btn btn-danger-ghost" onClick={() => setConfirmDelete(true)} disabled={busy}><Icon name="trash" size={16} /> Delete</button>
          </>
        }
      />

      <div className="flex gap-2 items-center flex-wrap mb-6">
        <BallotStatusBadge status={ballot.status} />
        {ballot.ballot_paper_no && <span className="badge badge-accent"><Icon name="hash" />Paper {ballot.ballot_paper_no}</span>}
        {ballot.boxes_expected > 0 && (
          <span className={`badge ${ballot.boxes_detected === ballot.boxes_expected ? "badge-success" : "badge-warning"}`}>
            <Icon name="target" />{ballot.boxes_detected}/{ballot.boxes_expected} boxes found
          </span>
        )}
        {ballot.printed_paper_no && (
          <span className="badge badge-accent" title="Number printed in the box at the top right of the paper">
            <Icon name="hash" />Printed no {ballot.printed_paper_no}
          </span>
        )}
        <span className="badge badge-primary"><Icon name="vote" />{ballot.total_votes_extracted} counted vote(s)</span>
        {ballot.reviewed_at && <span className="text-faint text-small">Reviewed {formatDateTime(ballot.reviewed_at)}</span>}
      </div>

      {ballot.error_message && <Alert type="error">{ballot.error_message}</Alert>}
      {ballot.votes.some((v) => !v.is_valid) && (
        <Alert type="error">
          <strong>Marks not counted by the ballot rules:</strong>
          <ul>
            {ballot.votes.filter((v) => !v.is_valid).map((v) => {
              const c = candidates.find((x) => x.id === v.candidate_id);
              return <li key={v.id}>{c ? `${c.voter_no} ${c.name_en}` : `candidate ${v.candidate_id}`}: {v.invalid_reason ?? "not counted"}</li>;
            })}
          </ul>
        </Alert>
      )}
      {ballot.ocr_warnings.length > 0 && (
        <Alert type="warning">
          <strong>Why this ballot needs attention:</strong>
          <ul>{ballot.ocr_warnings.map((w, i) => <li key={i}>{w}</li>)}</ul>
        </Alert>
      )}

      <div className="review-layout">
        <div className="card review-scan">
          <CardHead icon="ballot" title="Scanned page" subtitle="Annotated by the ballot reader">
            {previewUrl && (
              <button className="btn btn-ghost btn-sm" onClick={() => setZoom(!zoom)}>
                <Icon name={zoom ? "zoomOut" : "zoomIn"} size={15} /> {zoom ? "Fit to width" : "Zoom in"}
              </button>
            )}
          </CardHead>
          {previewUrl ? (
            <div className={`scan-frame ${zoom ? "zoomed" : ""}`}>
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img src={previewUrl} alt="Scanned ballot with detected marks" />
            </div>
          ) : (
            <div className="empty-inline"><Icon name="file" size={30} />No preview available for this ballot.</div>
          )}
          <div className="scan-legend">
            <span><i style={{ background: "#22c55e" }} />Mark detected</span>
            <span><i style={{ background: "#9ca3af" }} />Empty box</span>
            <span>The number beside a box is the detection confidence.</span>
          </div>
        </div>

        <div className="card review-votes">
          <CardHead icon="vote" title="Votes" subtitle="Tick exactly what the voter marked" gold>
            <span className={`badge ${selectedCount > 0 ? "badge-primary" : "badge-muted"}`}>{selectedCount} selected</span>
          </CardHead>

          <div className="form-grid mb-4">
            <div className="input-group">
              <label className="input-label" htmlFor="paper-no">Ballot paper no.</label>
              <div className="input-wrap">
                <Icon name="hash" size={16} />
                <input id="paper-no" className="input" value={paperNo} onChange={(e) => setPaperNo(e.target.value)} placeholder="from the top-right box" />
              </div>
            </div>
          </div>

          <div className="review-votes-scroll">
            {positions.map((position) => {
              const list = byPosition.get(position.id) ?? [];
              const chosen = list.filter((c) => selected.has(c.id)).length;
              return (
                <div key={position.id} className="review-position">
                  <div className="review-position-head">
                    <span className="review-position-name">
                      <span className="position-number">{String(position.position_order).padStart(2, "0")}</span>
                      {position.name_en}
                    </span>
                    <span className={`badge ${chosen > position.max_selections ? "badge-error" : chosen === 0 ? "badge-muted" : "badge-success"}`}>
                      {chosen}/{position.max_selections}
                    </span>
                  </div>
                  <div className="review-candidates">
                    {list.map((c) => {
                      const detected = detectedByCandidate.get(c.id);
                      return (
                        <label key={c.id} className={`checkbox-row ${selected.has(c.id) ? "checked" : ""}`}>
                          <input type="checkbox" checked={selected.has(c.id)} onChange={() => toggle(c, position.max_selections)} />
                          <span className="chip-no">{c.voter_no}</span>
                          <span>{c.name_bn ? <span className="text-bengali">{c.name_bn}</span> : c.name_en}</span>
                          {detected && (
                            <span className={`detect-tag ${detected.is_valid ? "" : "void"}`} title={detected.invalid_reason ?? "Detected by the scanner"}>
                              <Icon name={detected.is_valid ? "check" : "ban"} size={12} strokeWidth={2.4} />
                              {detected.is_valid ? "" : "void "}{(detected.confidence_score * 100).toFixed(0)}%
                            </span>
                          )}
                        </label>
                      );
                    })}
                  </div>
                </div>
              );
            })}
          </div>

          <div className="review-votes-foot">
            <button className="btn btn-success" onClick={save} disabled={busy}>
              {busy ? <><span className="btn-spinner" /> Saving…</> : <><Icon name="save" size={16} /> Save as manual file</>}
            </button>
            <button className="btn btn-ghost" onClick={load} disabled={busy}><Icon name="undo" size={15} /> Reset changes</button>
          </div>
        </div>
      </div>

      <ConfirmDialog open={confirmDelete} title="Delete ballot" danger busy={busy}
        message="Delete this ballot and its votes? The scanned file stays in the Completed folder."
        onConfirm={remove} onCancel={() => setConfirmDelete(false)} />
    </div>
  );
}
