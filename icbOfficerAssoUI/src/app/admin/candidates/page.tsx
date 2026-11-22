"use client";

import Link from "next/link";
import { useCallback, useMemo, useRef, useState } from "react";
import { api } from "@/lib/api";
import { errorMessage } from "@/lib/format";
import type { Candidate, Position } from "@/lib/types";
import { useAuth } from "@/hooks/useAuth";
import { useElection } from "@/hooks/useElection";
import { useLoader } from "@/hooks/useLoader";
import { useToast } from "@/components/ui/Toast";
import { ConfirmDialog, Modal } from "@/components/ui/Modal";
import { Alert, CardHead, EmptyState, PageHeader, initials } from "@/components/ui/Basics";
import { Icon } from "@/components/ui/Icon";

const EMPTY = { position_id: 0, voter_no: "", name_en: "", name_bn: "", display_order: 0 };

export default function CandidatesPage() {
  const { token } = useAuth();
  const { election } = useElection();
  const toast = useToast();
  const [positions, setPositions] = useState<Position[]>([]);
  const [candidates, setCandidates] = useState<Candidate[]>([]);
  const [form, setForm] = useState(EMPTY);
  const [editing, setEditing] = useState<Candidate | null>(null);
  const [deleting, setDeleting] = useState<Candidate | null>(null);
  const [busy, setBusy] = useState(false);
  const [importFile, setImportFile] = useState<File | null>(null);
  const [replaceExisting, setReplaceExisting] = useState(false);
  const csvInput = useRef<HTMLInputElement>(null);

  const load = useCallback(async () => {
    if (!election) return;
    try {
      const [detail, list] = await Promise.all([api.elections.get(election.id), api.candidates.list(election.id)]);
      setPositions(detail.positions);
      setCandidates(list);
    } catch (err) {
      toast.error(errorMessage(err));
    }
  }, [election, toast]);

  useLoader(load);

  const byPosition = useMemo(() => {
    const map = new Map<number, Candidate[]>();
    candidates.forEach((c) => map.set(c.position_id, [...(map.get(c.position_id) ?? []), c]));
    return map;
  }, [candidates]);

  const nextOrder = (positionId: number) => byPosition.get(positionId)?.length ?? 0;

  const run = async (action: () => Promise<void>, success: string) => {
    setBusy(true);
    try {
      await action();
      toast.success(success);
      await load();
    } catch (err) {
      toast.error(errorMessage(err));
    } finally {
      setBusy(false);
    }
  };

  const add = () => run(async () => {
    if (!token || !election) return;
    await api.candidates.create(token, {
      election_id: election.id, position_id: form.position_id, voter_no: form.voter_no.trim(),
      name_en: form.name_en.trim(), name_bn: form.name_bn.trim() || null, display_order: nextOrder(form.position_id),
    });
    setForm({ ...EMPTY, position_id: form.position_id });
  }, "Candidate added");

  const save = () => run(async () => {
    if (!token || !editing) return;
    await api.candidates.update(token, editing.id, {
      voter_no: editing.voter_no, name_en: editing.name_en, name_bn: editing.name_bn || null, display_order: editing.display_order,
    });
    setEditing(null);
  }, "Candidate updated");

  const remove = () => run(async () => {
    if (!token || !deleting) return;
    await api.candidates.remove(token, deleting.id);
    setDeleting(null);
  }, "Candidate deleted");

  const importCsv = () => run(async () => {
    if (!token || !election || !importFile) return;
    await api.candidates.importCsv(token, election.id, importFile, replaceExisting);
    setImportFile(null);
  }, "Candidate list imported");

  if (!election) return <EmptyState icon="landmark" title="Create an election first" />;

  return (
    <div className="page">
      <PageHeader eyebrow="Election" title="Candidates"
        subtitle="Enter the candidates exactly in the order they are printed on the ballot"
        actions={<>
          <span className="badge badge-accent badge-lg"><Icon name="users" />{candidates.length} candidates · {positions.length} positions</span>
          <button className="btn btn-ghost" onClick={() => csvInput.current?.click()}><Icon name="upload" size={16} /> Import CSV</button>
          <input ref={csvInput} type="file" accept=".csv,text/csv" style={{ display: "none" }}
            onChange={(e) => { setImportFile(e.target.files?.[0] ?? null); setReplaceExisting(false); e.target.value = ""; }} />
        </>} />

      {positions.length === 0 ? (
        <Alert type="warning">No positions yet. Seed or add positions under <Link href="/admin/elections">Elections</Link> first, or load a candidate list with <strong>Import CSV</strong> (the 13 standard posts are then created automatically).</Alert>
      ) : (
        <div className="card card-gold mb-6">
          <CardHead icon="plus" title="Add a candidate" subtitle="They are appended to the end of the position's ballot order" gold />
          <div className="form-grid form-grid-4">
            <div className="input-group"><label className="input-label">Position</label>
              <select className="input" value={form.position_id} onChange={(e) => setForm({ ...form, position_id: Number(e.target.value) })}>
                <option value={0}>Select…</option>
                {positions.map((p) => <option key={p.id} value={p.id}>{p.position_order}. {p.name_en}</option>)}
              </select></div>
            <div className="input-group"><label className="input-label">Voter / ballot no.</label>
              <div className="input-wrap"><Icon name="hash" size={16} />
                <input className="input" placeholder="101" value={form.voter_no} onChange={(e) => setForm({ ...form, voter_no: e.target.value })} /></div></div>
            <div className="input-group"><label className="input-label">Name (English)</label>
              <input className="input" placeholder="Mr. Candidate" value={form.name_en} onChange={(e) => setForm({ ...form, name_en: e.target.value })} /></div>
            <div className="input-group"><label className="input-label">Name (Bengali)</label>
              <input className="input text-bengali" placeholder="প্রার্থীর নাম" value={form.name_bn} onChange={(e) => setForm({ ...form, name_bn: e.target.value })} /></div>
          </div>
          <button className="btn btn-primary mt-4" disabled={busy || !form.position_id || !form.voter_no || !form.name_en} onClick={add}>
            <Icon name="plus" size={16} /> Add candidate
          </button>
        </div>
      )}

      {positions.map((position) => {
        const list = byPosition.get(position.id) ?? [];
        return (
          <div key={position.id} className="card mb-4">
            <div className="card-head">
              <div className="card-title">
                <span className="position-number">{String(position.position_order).padStart(2, "0")}</span>
                <div>
                  <div>{position.name_en}</div>
                  {position.name_bn && <div className="card-subtitle text-bengali">{position.name_bn}</div>}
                </div>
              </div>
              <div className="flex gap-2">
                <span className="badge badge-muted"><Icon name="users" />{list.length} candidate{list.length === 1 ? "" : "s"}</span>
                <span className="badge badge-accent">Elect {position.max_selections}</span>
              </div>
            </div>
            {list.length === 0 ? <div className="empty-inline"><Icon name="user" size={26} />No candidates yet.</div> : (
              <div className="table-wrapper">
                <table className="table">
                  <thead><tr><th style={{ width: 70 }}>Order</th><th>Candidate</th><th>No.</th><th className="num">Votes</th><th></th></tr></thead>
                  <tbody>
                    {list.map((c, index) => (
                      <tr key={c.id}>
                        <td className="text-faint tabular">{String(index + 1).padStart(2, "0")}</td>
                        <td>
                          <div className="candidate-cell">
                            <span className={`avatar avatar-sm ${index % 2 ? "avatar-teal" : ""}`}>{initials(c.name_en)}</span>
                            <div>
                              <div className="candidate-cell-name">{c.name_en}</div>
                              {c.name_bn && <div className="candidate-cell-bn">{c.name_bn}</div>}
                            </div>
                          </div>
                        </td>
                        <td><span className="chip-no">{c.voter_no}</span></td>
                        <td className="num"><strong>{c.vote_count}</strong></td>
                        <td className="cell-actions">
                          <button className="btn btn-ghost btn-sm" onClick={() => setEditing({ ...c })}><Icon name="edit" size={14} /> Edit</button>
                          <button className="btn btn-danger-ghost btn-sm btn-icon" onClick={() => setDeleting(c)} aria-label="Delete" title="Delete"><Icon name="trash" size={14} /></button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        );
      })}

      <Modal open={Boolean(editing)} title="Edit candidate" onClose={() => setEditing(null)} footer={
        <><button className="btn btn-ghost" onClick={() => setEditing(null)}>Cancel</button>
          <button className="btn btn-primary" disabled={busy} onClick={save}><Icon name="save" size={15} /> Save</button></>
      }>
        {editing && (
          <div className="form-grid">
            <div className="input-group"><label className="input-label">Voter / ballot no.</label>
              <input className="input" value={editing.voter_no} onChange={(e) => setEditing({ ...editing, voter_no: e.target.value })} /></div>
            <div className="input-group"><label className="input-label">Ballot order (0 = first)</label>
              <input className="input" type="number" min={0} value={editing.display_order} onChange={(e) => setEditing({ ...editing, display_order: Number(e.target.value) })} /></div>
            <div className="input-group"><label className="input-label">Name (English)</label>
              <input className="input" value={editing.name_en} onChange={(e) => setEditing({ ...editing, name_en: e.target.value })} /></div>
            <div className="input-group"><label className="input-label">Name (Bengali)</label>
              <input className="input text-bengali" value={editing.name_bn ?? ""} onChange={(e) => setEditing({ ...editing, name_bn: e.target.value })} /></div>
          </div>
        )}
      </Modal>

      <Modal open={Boolean(importFile)} title="Import candidates from CSV" onClose={() => setImportFile(null)} footer={
        <><button className="btn btn-ghost" onClick={() => setImportFile(null)}>Cancel</button>
          <button className="btn btn-primary" disabled={busy} onClick={importCsv}><Icon name="upload" size={15} /> Import</button></>
      }>
        <p className="mb-4"><strong>{importFile?.name}</strong></p>
        <p className="text-faint text-sm mb-4">
          Columns: <code>voter_no</code>, <code>post_no</code> (the post&apos;s serial on the ballot, 1–13), <code>name_en</code>, <code>name_bn</code>.
          Rows must be in the order printed on the ballot. The 13 standard posts are created automatically if the election has none.
        </p>
        {candidates.length > 0 && (
          <label className="flex items-center gap-2">
            <input type="checkbox" checked={replaceExisting} onChange={(e) => setReplaceExisting(e.target.checked)} />
            Replace the {candidates.length} existing candidates (only possible before any ballot is counted)
          </label>
        )}
      </Modal>

      <ConfirmDialog open={Boolean(deleting)} title="Delete candidate" danger busy={busy}
        message={`Delete ${deleting?.voter_no} ${deleting?.name_en}? Existing votes for this candidate are removed too.`}
        onConfirm={remove} onCancel={() => setDeleting(null)} />
    </div>
  );
}
