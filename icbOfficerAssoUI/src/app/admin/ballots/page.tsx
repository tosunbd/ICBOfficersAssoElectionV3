"use client";

import Link from "next/link";
import { useCallback, useState } from "react";
import { api } from "@/lib/api";
import { errorMessage, formatDateTime } from "@/lib/format";
import type { Ballot, BallotStatus } from "@/lib/types";
import { useAuth } from "@/hooks/useAuth";
import { useElection } from "@/hooks/useElection";
import { useLoader } from "@/hooks/useLoader";
import { useToast } from "@/components/ui/Toast";
import { BallotUploader } from "@/components/admin/BallotUploader";
import { Alert, BallotStatusBadge, CardHead, EmptyState, PageHeader } from "@/components/ui/Basics";
import { Icon } from "@/components/ui/Icon";
import { ConfirmDialog } from "@/components/ui/Modal";

const FILTERS: Array<{ value: BallotStatus | ""; label: string; color?: string }> = [
  { value: "", label: "All" },
  { value: "needs_review", label: "Needs review", color: "var(--color-warning)" },
  { value: "processed", label: "Processed", color: "var(--color-success)" },
  { value: "reviewed", label: "Reviewed", color: "var(--color-primary-300)" },
  { value: "error", label: "Errors", color: "var(--color-error)" },
];
const PER_PAGE = 25;

export default function BallotsPage() {
  const { token } = useAuth();
  const { election } = useElection();
  const toast = useToast();
  const [ballots, setBallots] = useState<Ballot[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [filter, setFilter] = useState<BallotStatus | "">("");
  const [busy, setBusy] = useState(false);
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [allMatching, setAllMatching] = useState(false);  // every ballot matching the filter, across pages
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [candidateCount, setCandidateCount] = useState<number | null>(null);

  const load = useCallback(async () => {
    if (!token || !election) return;
    try {
      const data = await api.ballots.list(token, election.id, page, PER_PAGE, filter || undefined);
      setBallots(data.ballots);
      setTotal(data.total);
      setCandidateCount((await api.candidates.list(election.id)).length);
    } catch (err) {
      toast.error(errorMessage(err));
    }
  }, [token, election, page, filter, toast]);

  useLoader(load, 5000);  // keep the list fresh while the scanner is running

  const upload = async (files: File[]) => {
    if (!token || !election) return;
    setBusy(true);
    try {
      const created = await api.ballots.upload(token, election.id, files);
      const review = created.filter((b) => b.status === "needs_review").length;
      const errors = created.filter((b) => b.status === "error").length;
      toast.success(`${created.length} ballot(s) processed${review ? `, ${review} need review` : ""}${errors ? `, ${errors} error(s)` : ""}`);
      setPage(1);
      await load();
    } catch (err) {
      toast.error(errorMessage(err));
    } finally {
      setBusy(false);
    }
  };

  const scanFolder = async () => {
    if (!token || !election) return;
    setBusy(true);
    try {
      const summary = await api.ballots.scanFolder(token, election.id);
      toast.success(`${summary.files_processed} file(s) processed, ${summary.files_errored} error(s)`);
      await load();
    } catch (err) {
      toast.error(errorMessage(err));
    } finally {
      setBusy(false);
    }
  };

  const clearSelection = () => { setSelected(new Set()); setAllMatching(false); };

  const toggleOne = (id: number) => {
    setAllMatching(false);
    setSelected((current) => {
      const next = new Set(current);
      if (next.has(id)) next.delete(id); else next.add(id);
      return next;
    });
  };

  const pageIds = ballots.map((b) => b.id);
  const pageAllSelected = pageIds.length > 0 && pageIds.every((id) => selected.has(id));
  const pageSomeSelected = pageIds.some((id) => selected.has(id));
  const togglePage = () => {
    setAllMatching(false);
    setSelected((current) => {
      const next = new Set(current);
      if (pageAllSelected) pageIds.forEach((id) => next.delete(id)); else pageIds.forEach((id) => next.add(id));
      return next;
    });
  };
  const selectedCount = allMatching ? total : selected.size;

  const deleteSelected = async () => {
    if (!token || !election) return;
    setBusy(true);
    try {
      const result = allMatching
        ? await api.ballots.bulkRemove(token, { election_id: election.id, status_filter: filter || null, all_matching: true })
        : await api.ballots.bulkRemove(token, { ballot_ids: Array.from(selected) });
      toast.success(`${result.deleted} ballot${result.deleted === 1 ? "" : "s"} deleted`);
      clearSelection();
      setPage(1);
      await load();
    } catch (err) {
      toast.error(errorMessage(err));
    } finally {
      setBusy(false);
      setConfirmDelete(false);
    }
  };

  if (!election) return <EmptyState icon="landmark" title="Create an election first" />;
  const pages = Math.max(1, Math.ceil(total / PER_PAGE));
  const first = total === 0 ? 0 : (page - 1) * PER_PAGE + 1;

  return (
    <div className="page">
      <PageHeader eyebrow="Counting" title="Ballots" subtitle="Scanned ballots are processed automatically; upload here for manual runs"
        actions={
          <button className="btn btn-accent" onClick={scanFolder} disabled={busy || candidateCount === 0}>
            {busy ? <><span className="btn-spinner" /> Working…</> : <><Icon name="folderScan" size={17} /> Process Scanned folder now</>}
          </button>
        } />

      {candidateCount === 0 && (
        <Alert type="error">
          This election has <strong>no candidates yet</strong>, so ballots cannot be read. Open{" "}
          <Link href="/admin/candidates">Candidates</Link> and use <strong>Import CSV</strong> (for the test: <code>Sample Ballotscandidates.csv</code>).
          Files in the Scanned folder wait there until then.
        </Alert>
      )}

      {election.status !== "active" && (
        <Alert type="warning">This election is <strong>{election.status}</strong>; uploads still work, but automatic folder processing only targets the active election.</Alert>
      )}

      <div className="card mb-6">
        <CardHead icon="upload" title="Upload scanned ballots" subtitle="Each page is read, checked against the ballot rules and counted" />
        <BallotUploader onUpload={upload} busy={busy} disabled={candidateCount === 0} />
      </div>

      <div className="card">
        <CardHead icon="ballot" title={<>Ballot register <span className="badge badge-muted" style={{ marginLeft: 6 }}>{total}</span></>} gold>
          <div className="segmented" role="tablist">
            {FILTERS.map((f) => (
              <button key={f.value} role="tab" aria-selected={filter === f.value} className={filter === f.value ? "active" : ""}
                onClick={() => { setFilter(f.value); setPage(1); clearSelection(); }}>
                {f.color && <span className="seg-dot" style={{ color: f.color }} />}{f.label}
              </button>
            ))}
          </div>
        </CardHead>

        {pageAllSelected && !allMatching && total > ballots.length && (
          <div className="select-banner">
            All {ballots.length} ballots on this page are selected.
            <button className="link-btn" onClick={() => setAllMatching(true)}>Select all {total} {filter ? "matching " : ""}ballots</button>
          </div>
        )}
        {allMatching && (
          <div className="select-banner is-all">
            All {total} {filter ? "matching " : ""}ballots are selected.
            <button className="link-btn" onClick={clearSelection}>Clear selection</button>
          </div>
        )}
        {ballots.length === 0 ? (
          <div className="empty-inline"><Icon name="inbox" size={32} />No ballots{filter ? " with this status" : " yet"}.</div>
        ) : (
          <div className="table-wrapper">
            <table className="table">
              <thead>
                <tr>
                  <th className="cell-check">
                    <input type="checkbox" className="check" aria-label="Select all ballots on this page" checked={pageAllSelected}
                      ref={(el) => { if (el) el.indeterminate = !pageAllSelected && pageSomeSelected; }} onChange={togglePage} />
                  </th>
                  <th>#</th><th>Paper no.</th><th>File</th><th>Source</th><th>Status</th><th>Boxes</th><th className="num">Votes</th><th>Processed</th><th></th>
                </tr>
              </thead>
              <tbody>
                {ballots.map((b) => (
                  <tr key={b.id} className={`${b.status === "needs_review" ? "row-attention" : ""} ${allMatching || selected.has(b.id) ? "row-selected" : ""}`}>
                    <td className="cell-check">
                      <input type="checkbox" className="check" aria-label={`Select ballot ${b.id}`} checked={allMatching || selected.has(b.id)} onChange={() => toggleOne(b.id)} />
                    </td>
                    <td><Link href={`/admin/ballots/${b.id}`} className="row-link">#{b.id}</Link></td>
                    <td>{b.ballot_paper_no ? <span className="chip-no">{b.ballot_paper_no}</span> : <span className="text-faint">—</span>}</td>
                    <td className="cell-ellipsis" title={b.pdf_filename}>
                      <span className="flex items-center gap-2"><Icon name="file" size={14} className="text-faint" />{b.pdf_filename}{b.page_number > 1 ? <span className="text-faint"> · p{b.page_number}</span> : null}</span>
                    </td>
                    <td><span className="badge badge-muted">{b.source}</span></td>
                    <td>
                      <span className="flex items-center gap-2">
                        <BallotStatusBadge status={b.status} />
                        {b.ocr_warnings.length > 0 && <span title={b.ocr_warnings.join("\n")} className="text-warning" style={{ display: "inline-flex" }}><Icon name="alert" size={15} /></span>}
                      </span>
                    </td>
                    <td>
                      {b.boxes_expected ? (
                        <span className={b.boxes_detected === b.boxes_expected ? "text-success" : "text-warning"} style={{ fontWeight: 700, fontVariantNumeric: "tabular-nums" }}>
                          {b.boxes_detected}/{b.boxes_expected}
                        </span>
                      ) : "—"}
                    </td>
                    <td className="num"><strong>{b.total_votes_extracted}</strong></td>
                    <td className="text-faint text-small" style={{ whiteSpace: "nowrap" }}>{formatDateTime(b.processed_at ?? b.scanned_at)}</td>
                    <td className="cell-actions">
                      <Link href={`/admin/ballots/${b.id}`} className={`btn btn-sm ${b.status === "needs_review" ? "btn-accent" : "btn-ghost"}`}>
                        {b.status === "needs_review" ? <><Icon name="eye" size={14} /> Review</> : <>Open <Icon name="chevronRight" size={14} /></>}
                      </Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {pages > 1 && (
          <div className="pager">
            <button className="btn btn-ghost btn-sm" disabled={page <= 1} onClick={() => setPage(page - 1)}><Icon name="arrowLeft" size={14} /> Previous</button>
            <span className="pager-info">{first}–{Math.min(total, page * PER_PAGE)} of {total} · page {page} of {pages}</span>
            <button className="btn btn-ghost btn-sm" disabled={page >= pages} onClick={() => setPage(page + 1)}>Next <Icon name="arrowRight" size={14} /></button>
          </div>
        )}
      </div>

      {selectedCount > 0 && (
        <div className="action-bar" role="region" aria-label="Selected ballots">
          <span className="action-bar-count"><span className="action-bar-num">{selectedCount}</span> ballot{selectedCount === 1 ? "" : "s"} selected</span>
          <button className="btn btn-ghost btn-sm" onClick={clearSelection}><Icon name="x" size={14} /> Clear</button>
          <button className="btn btn-danger btn-sm" onClick={() => setConfirmDelete(true)} disabled={busy}><Icon name="trash" size={14} /> Delete selected</button>
        </div>
      )}

      <ConfirmDialog open={confirmDelete} danger busy={busy}
        title={`Delete ${selectedCount} ballot${selectedCount === 1 ? "" : "s"}`}
        message={`Delete ${selectedCount === 1 ? "this ballot" : `these ${selectedCount} ballots`} and their votes? Candidate totals are reduced accordingly. The scanned files stay in the Completed folder.`}
        confirmLabel="Delete" onConfirm={deleteSelected} onCancel={() => setConfirmDelete(false)} />
    </div>
  );
}
