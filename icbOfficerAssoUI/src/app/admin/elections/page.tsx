"use client";

import { useCallback, useState } from "react";
import { api } from "@/lib/api";
import { errorMessage } from "@/lib/format";
import type { ElectionDetail, ElectionStatus, Position } from "@/lib/types";
import { useAuth } from "@/hooks/useAuth";
import { useElection } from "@/hooks/useElection";
import { useLoader } from "@/hooks/useLoader";
import { useToast } from "@/components/ui/Toast";
import { ConfirmDialog, Modal } from "@/components/ui/Modal";
import { CardHead, ElectionStatusBadge, EmptyState, PageHeader } from "@/components/ui/Basics";
import { Icon } from "@/components/ui/Icon";
import { DEFAULT_COUNCIL_NO, bengaliOrdinal, buildTitleBn, buildTitleEn, englishOrdinal, parseCouncilNo, toBengaliDigits } from "@/lib/electionTitle";

const THIS_YEAR = new Date().getFullYear();
const EMPTY_FORM = { council_no: DEFAULT_COUNCIL_NO, title: buildTitleEn(DEFAULT_COUNCIL_NO, THIS_YEAR), year: THIS_YEAR, description: "", total_voters: 1000, ballot_display_seconds: 2 };
const MIN_SECONDS = 1;
const MAX_SECONDS = 600;
type ElectionFormValue = typeof EMPTY_FORM;

/** API payload: the Bengali title is always generated from the council number and year. */
function toPayload(form: ElectionFormValue) {
  return {
    title: form.title.trim() || buildTitleEn(form.council_no, form.year),
    title_bn: buildTitleBn(form.council_no, form.year),
    year: form.year,
    description: form.description || null,
    total_voters: form.total_voters,
    ballot_display_seconds: form.ballot_display_seconds,
  };
}
const EMPTY_POSITION = { position_order: 1, name_en: "", name_bn: "", max_selections: 1 };

const STEPS: Array<{ status: ElectionStatus; title: string; desc: string }> = [
  { status: "draft", title: "Draft", desc: "Setting up positions and candidates" },
  { status: "active", title: "Active", desc: "Ballots are scanned and counted automatically" },
  { status: "completed", title: "Completed", desc: "Counting finished, results final" },
];

export default function ElectionsPage() {
  const { token } = useAuth();
  const { elections, election, refresh, selectElection, patch } = useElection();
  const toast = useToast();

  const [detail, setDetail] = useState<ElectionDetail | null>(null);
  const [form, setForm] = useState(EMPTY_FORM);
  const [showCreate, setShowCreate] = useState(false);
  const [editing, setEditing] = useState(false);
  const [editForm, setEditForm] = useState(EMPTY_FORM);
  const [positionForm, setPositionForm] = useState(EMPTY_POSITION);
  const [editPosition, setEditPosition] = useState<Position | null>(null);
  const [confirm, setConfirm] = useState<{ title: string; message: string; danger?: boolean; action: () => Promise<void> } | null>(null);
  const [busy, setBusy] = useState(false);

  const loadDetail = useCallback(async () => {
    if (!election) { setDetail(null); return; }
    try {
      setDetail(await api.elections.get(election.id));
    } catch (err) {
      toast.error(errorMessage(err));
    }
  }, [election, toast]);

  useLoader(loadDetail);

  const run = async (action: () => Promise<void>, success?: string) => {
    setBusy(true);
    try {
      await action();
      if (success) toast.success(success);
    } catch (err) {
      toast.error(errorMessage(err));
    } finally {
      setBusy(false);
      setConfirm(null);
    }
  };

  const createElection = () => run(async () => {
    if (!token) return;
    const created = await api.elections.create(token, toPayload(form));
    await refresh();
    selectElection(created.id);
    setShowCreate(false);
    setForm(EMPTY_FORM);
  }, "Election created");

  const saveElection = () => run(async () => {
    if (!token || !election) return;
    await api.elections.update(token, election.id, toPayload(editForm));
    await refresh();
    setEditing(false);
  }, "Election updated");

  const setStatus = (status: ElectionStatus) => run(async () => {
    if (!token || !election) return;
    await api.admin.setStatus(token, election.id, status);
    patch({ status });
    await refresh();
  }, `Election is now ${status}`);

  const seed = (withCandidates: boolean) => run(async () => {
    if (!token || !election) return;
    await api.elections.seedPositions(token, election.id, withCandidates);
    await loadDetail();
  }, withCandidates ? "13 positions and 30 template candidates created" : "13 positions created");

  const addPosition = () => run(async () => {
    if (!token || !election) return;
    await api.elections.addPosition(token, election.id, { ...positionForm, name_bn: positionForm.name_bn || null });
    setPositionForm({ ...EMPTY_POSITION, position_order: (detail?.positions.length ?? 0) + 2 });
    await loadDetail();
  }, "Position added");

  const savePosition = () => run(async () => {
    if (!token || !election || !editPosition) return;
    await api.elections.updatePosition(token, election.id, editPosition.id, {
      position_order: editPosition.position_order, name_en: editPosition.name_en,
      name_bn: editPosition.name_bn || null, max_selections: editPosition.max_selections,
    });
    setEditPosition(null);
    await loadDetail();
  }, "Position updated");

  const currentStep = election ? STEPS.findIndex((s) => s.status === election.status) : -1;

  return (
    <div className="page">
      <PageHeader
        eyebrow="Election"
        title="Elections"
        subtitle="Create the election, define its positions, then set it active to start counting"
        actions={<button className="btn btn-accent" onClick={() => setShowCreate(true)}><Icon name="plus" size={16} /> New election</button>}
      />

      {elections.length === 0 && (
        <EmptyState icon="landmark" title="No election exists yet">
          <p>Create one to begin — you can seed the 13 ICB positions in one click afterwards.</p>
          <button className="btn btn-primary mt-6" onClick={() => setShowCreate(true)}><Icon name="plus" size={16} /> Create election</button>
        </EmptyState>
      )}

      {election && (
        <>
          <div className="card card-gold mb-6">
            <div className="card-head">
              <div className="card-title">
                <span className="card-title-icon gold"><Icon name="landmark" size={18} /></span>
                <div>
                  <div className="flex items-center gap-2 flex-wrap"><span className="display" style={{ fontSize: "1.35rem" }}>{election.title}</span> <ElectionStatusBadge status={election.status} /></div>
                  {election.title_bn && <div className="card-subtitle text-bengali">{election.title_bn}</div>}
                </div>
              </div>
              <div className="flex gap-2 flex-wrap">
                <button className="btn btn-ghost btn-sm" onClick={() => {
                  setEditForm({
                    council_no: parseCouncilNo(election.title_bn, election.title) ?? DEFAULT_COUNCIL_NO, title: election.title,
                    year: election.year, description: election.description ?? "", total_voters: election.total_voters,
                    ballot_display_seconds: election.ballot_display_seconds,
                  });
                  setEditing(true);
                }}><Icon name="edit" size={14} /> Edit</button>
                <button className="btn btn-danger-ghost btn-sm" onClick={() => setConfirm({
                  title: "Delete election", danger: true,
                  message: `Delete "${election.title}" with all its positions, candidates, ballots and votes? This cannot be undone.`,
                  action: async () => { if (!token) return; await api.elections.remove(token, election.id); await refresh(); },
                })}><Icon name="trash" size={14} /> Delete</button>
              </div>
            </div>

            <div className="mini-stats">
              <div className="mini-stat"><strong className="text-bengali">{(() => { const n = parseCouncilNo(election.title_bn, election.title); return n ? bengaliOrdinal(n) : "—"; })()}</strong><span>Council</span></div>
              <div className="mini-stat"><strong>{election.year}</strong><span>Year</span></div>
              <div className="mini-stat"><strong>{election.total_voters.toLocaleString()}</strong><span>Total voters</span></div>
              <div className="mini-stat"><strong>{election.ballot_display_seconds} s</strong><span>Between live updates</span></div>
              <div className="mini-stat"><strong>{detail?.positions.length ?? "—"}</strong><span>Positions</span></div>
            </div>
            {election.description && <p className="text-muted text-small mb-4">{election.description}</p>}

            <div className="section-title" style={{ marginTop: 8 }}>Election status</div>
            <div className="stepper">
              {STEPS.map((step, index) => {
                const isCurrent = election.status === step.status;
                return (
                  <button key={step.status} className={`step ${isCurrent ? "current" : index < currentStep ? "done" : ""}`}
                    disabled={busy || isCurrent}
                    onClick={() => step.status === "active"
                      ? setConfirm({ title: "Activate election", message: "Scanned files will be counted into this election. Any other active election becomes completed. Continue?", action: () => setStatus(step.status) })
                      : setStatus(step.status)}>
                    <span className="step-index">{index < currentStep ? <Icon name="check" size={15} strokeWidth={2.6} /> : index + 1}</span>
                    <span>
                      <div className="step-title">{step.title}{isCurrent && <span className="text-faint text-xs" style={{ fontWeight: 600 }}> · current</span>}</div>
                      <div className="step-desc">{step.desc}</div>
                    </span>
                  </button>
                );
              })}
            </div>
          </div>

          <div className="card">
            <CardHead icon="overview" title={`Positions (${detail?.positions.length ?? 0})`} subtitle="Must match the printed ballot from top to bottom">
              {detail && detail.positions.length === 0 && (
                <>
                  <button className="btn btn-accent btn-sm" disabled={busy} onClick={() => seed(false)}><Icon name="sprout" size={15} /> Seed the 13 ICB positions</button>
                  <button className="btn btn-ghost btn-sm" disabled={busy} onClick={() => seed(true)}>Seed with template candidates (rehearsal)</button>
                </>
              )}
            </CardHead>

            {detail && detail.positions.length > 0 && (
              <div className="position-chip-list mb-6 stagger">
                {detail.positions.map((p) => (
                  <div key={p.id} className="position-chip">
                    <span className="position-number">{String(p.position_order).padStart(2, "0")}</span>
                    <div className="position-chip-body">
                      <div className="position-chip-name">{p.name_en}</div>
                      <div className="position-chip-bn">{p.name_bn ?? "—"}{p.max_selections > 1 ? ` · elect ${p.max_selections}` : ""}</div>
                    </div>
                    <div className="position-chip-actions">
                      <button className="btn btn-ghost btn-sm btn-icon" onClick={() => setEditPosition({ ...p })} aria-label="Edit" title="Edit"><Icon name="edit" size={14} /></button>
                      <button className="btn btn-danger-ghost btn-sm btn-icon" aria-label="Delete" title="Delete" onClick={() => setConfirm({
                        title: "Delete position", danger: true,
                        message: `Delete "${p.name_en}" and its candidates?`,
                        action: async () => { if (!token) return; await api.elections.removePosition(token, election.id, p.id); await loadDetail(); },
                      })}><Icon name="trash" size={14} /></button>
                    </div>
                  </div>
                ))}
              </div>
            )}

            <div className="section-title">Add a position</div>
            <div className="form-grid form-grid-4">
              <div className="input-group"><label className="input-label">Order</label>
                <input className="input" type="number" min={1} value={positionForm.position_order} onChange={(e) => setPositionForm({ ...positionForm, position_order: Number(e.target.value) })} /></div>
              <div className="input-group"><label className="input-label">Name (English)</label>
                <input className="input" value={positionForm.name_en} onChange={(e) => setPositionForm({ ...positionForm, name_en: e.target.value })} /></div>
              <div className="input-group"><label className="input-label">Name (Bengali)</label>
                <input className="input text-bengali" value={positionForm.name_bn} onChange={(e) => setPositionForm({ ...positionForm, name_bn: e.target.value })} /></div>
              <div className="input-group"><label className="input-label">Seats to elect</label>
                <input className="input" type="number" min={1} value={positionForm.max_selections} onChange={(e) => setPositionForm({ ...positionForm, max_selections: Number(e.target.value) })} /></div>
            </div>
            <div className="flex items-center gap-4 mt-4 flex-wrap">
              <button className="btn btn-primary" disabled={busy || !positionForm.name_en} onClick={addPosition}><Icon name="plus" size={16} /> Add position</button>
              <span className="text-faint text-small">Candidates of each position are printed two per row.</span>
            </div>
          </div>
        </>
      )}

      {/* Create */}
      <Modal open={showCreate} title="New election" onClose={() => setShowCreate(false)} footer={
        <><button className="btn btn-ghost" onClick={() => setShowCreate(false)}>Cancel</button>
          <button className="btn btn-primary" disabled={busy || !validForm(form)} onClick={createElection}><Icon name="sparkles" size={15} /> Create</button></>
      }>
        <ElectionForm value={form} onChange={setForm} />
      </Modal>

      {/* Edit */}
      <Modal open={editing} title="Edit election" onClose={() => setEditing(false)} footer={
        <><button className="btn btn-ghost" onClick={() => setEditing(false)}>Cancel</button>
          <button className="btn btn-primary" disabled={busy || !validForm(editForm)} onClick={saveElection}><Icon name="save" size={15} /> Save</button></>
      }>
        <ElectionForm value={editForm} onChange={setEditForm} />
      </Modal>

      {/* Edit position */}
      <Modal open={Boolean(editPosition)} title="Edit position" onClose={() => setEditPosition(null)} footer={
        <><button className="btn btn-ghost" onClick={() => setEditPosition(null)}>Cancel</button>
          <button className="btn btn-primary" disabled={busy} onClick={savePosition}><Icon name="save" size={15} /> Save</button></>
      }>
        {editPosition && (
          <div className="form-grid">
            <div className="input-group"><label className="input-label">Order</label>
              <input className="input" type="number" min={1} value={editPosition.position_order} onChange={(e) => setEditPosition({ ...editPosition, position_order: Number(e.target.value) })} /></div>
            <div className="input-group"><label className="input-label">Seats to elect</label>
              <input className="input" type="number" min={1} value={editPosition.max_selections} onChange={(e) => setEditPosition({ ...editPosition, max_selections: Number(e.target.value) })} /></div>
            <div className="input-group"><label className="input-label">Name (English)</label>
              <input className="input" value={editPosition.name_en} onChange={(e) => setEditPosition({ ...editPosition, name_en: e.target.value })} /></div>
            <div className="input-group"><label className="input-label">Name (Bengali)</label>
              <input className="input text-bengali" value={editPosition.name_bn ?? ""} onChange={(e) => setEditPosition({ ...editPosition, name_bn: e.target.value })} /></div>
          </div>
        )}
      </Modal>

      <ConfirmDialog open={Boolean(confirm)} title={confirm?.title ?? ""} message={confirm?.message ?? ""} danger={confirm?.danger} busy={busy}
        onConfirm={() => confirm && run(confirm.action)} onCancel={() => setConfirm(null)} />
    </div>
  );
}

function validForm(form: ElectionFormValue): boolean {
  return form.council_no >= 1 && form.year >= 1900 && form.total_voters >= 1
    && form.ballot_display_seconds >= MIN_SECONDS && form.ballot_display_seconds <= MAX_SECONDS;
}

function ElectionForm({ value, onChange }: { value: ElectionFormValue; onChange: (v: ElectionFormValue) => void }) {
  // Keep the English title in step with the inputs until the admin types their own.
  const setNumbers = (changes: Partial<ElectionFormValue>) => {
    const next = { ...value, ...changes };
    const wasAuto = !value.title.trim() || value.title === buildTitleEn(value.council_no, value.year);
    onChange(wasAuto ? { ...next, title: buildTitleEn(next.council_no, next.year) } : next);
  };
  const autoTitle = buildTitleEn(value.council_no, value.year);

  return (
    <div className="flex flex-col gap-4">
      <div className="form-grid form-grid-3">
        <div className="input-group"><label className="input-label" htmlFor="ef-council">Council no.</label>
          <div className="input-wrap"><Icon name="hash" size={16} />
            <input id="ef-council" className="input" type="number" min={1} value={value.council_no}
              onChange={(e) => setNumbers({ council_no: Math.max(0, Number(e.target.value)) })} /></div>
          <span className="input-hint">{value.council_no >= 1 ? `${englishOrdinal(value.council_no)} · ${bengaliOrdinal(value.council_no)}` : "At least 1"}</span></div>
        <div className="input-group"><label className="input-label" htmlFor="ef-year">Year</label>
          <div className="input-wrap"><Icon name="clock" size={16} />
            <input id="ef-year" className="input" type="number" min={1900} value={value.year}
              onChange={(e) => setNumbers({ year: Number(e.target.value) })} /></div>
          <span className="input-hint text-bengali">{toBengaliDigits(value.year)}</span></div>
        <div className="input-group"><label className="input-label" htmlFor="ef-voters">Total voters</label>
          <div className="input-wrap"><Icon name="users" size={16} />
            <input id="ef-voters" className="input" type="number" min={1} value={value.total_voters}
              onChange={(e) => onChange({ ...value, total_voters: Number(e.target.value) })} /></div>
          <span className="input-hint">Used for the turnout figure</span></div>
      </div>

      <div className="input-group"><label className="input-label" htmlFor="ef-seconds">Seconds between updates on the live screen</label>
        <div className="input-wrap"><Icon name="clock" size={16} />
          <input id="ef-seconds" className="input" type="number" min={MIN_SECONDS} max={MAX_SECONDS} value={value.ballot_display_seconds}
            onChange={(e) => onChange({ ...value, ballot_display_seconds: Number(e.target.value) })} /></div>
        <span className="input-hint">
          {value.ballot_display_seconds >= MIN_SECONDS && value.ballot_display_seconds <= MAX_SECONDS
            ? `The totals on the public screen move one ballot every ${value.ballot_display_seconds} s, while counting and in the count shown after Publish. A change applies from the next ballot.`
            : `Between ${MIN_SECONDS} and ${MAX_SECONDS} seconds`}
        </span></div>

      <div className="title-preview">
        <div className="title-preview-label"><Icon name="sparkles" size={13} /> Title on the ballot screen</div>
        <div className="title-preview-bn">{buildTitleBn(Math.max(1, value.council_no || 1), value.year || THIS_YEAR)}</div>
        <div className="title-preview-en">{value.title || autoTitle}</div>
      </div>

      <div className="input-group"><label className="input-label" htmlFor="ef-title">Title (English)</label>
        <div className="input-wrap">
          <Icon name="landmark" size={16} />
          <input id="ef-title" className="input" value={value.title} placeholder={autoTitle} style={{ paddingRight: 110 }}
            onChange={(e) => onChange({ ...value, title: e.target.value })} />
          {value.title !== autoTitle && (
            <button type="button" className="input-affix" onClick={() => onChange({ ...value, title: autoTitle })}><Icon name="undo" size={13} /> Standard</button>
          )}
        </div>
        <span className="input-hint">The Bengali title is generated from the council number and year.</span></div>
      <div className="input-group"><label className="input-label" htmlFor="ef-desc">Description (optional)</label>
        <input id="ef-desc" className="input" value={value.description} onChange={(e) => onChange({ ...value, description: e.target.value })} /></div>
    </div>
  );
}
