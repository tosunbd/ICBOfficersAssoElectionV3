"use client";

import Link from "next/link";
import { useState } from "react";
import { api } from "@/lib/api";
import { errorMessage } from "@/lib/format";
import type { Election } from "@/lib/types";
import { useAuth } from "@/hooks/useAuth";
import { useElection } from "@/hooks/useElection";
import { useToast } from "@/components/ui/Toast";
import { CardHead, EmptyState } from "@/components/ui/Basics";
import { Icon } from "@/components/ui/Icon";
import { DEFAULT_COUNCIL_NO, bengaliOrdinal, buildTitleBn, buildTitleEn, englishOrdinal, parseCouncilNo, toBengaliDigits } from "@/lib/electionTitle";

/** Settings card: the council number, year and voters that make up the election title
 *  shown on the admin overview and the public live screen. */
export function ElectionTitleCard() {
  const { election } = useElection();
  return (
    <div className="card card-gold mb-6" id="title">
      <CardHead icon="landmark" title="Election title" subtitle="Shown on the admin overview and the public live screen" gold />
      {election
        ? <TitleForm key={election.id} election={election} />
        : <EmptyState icon="landmark" title="No election yet"><Link className="link-btn" href="/admin/elections">Create the election</Link> first.</EmptyState>}
    </div>
  );
}

function TitleForm({ election }: { election: Election }) {
  const { token } = useAuth();
  const { refresh } = useElection();
  const toast = useToast();
  const [councilNo, setCouncilNo] = useState(() => parseCouncilNo(election.title_bn, election.title) ?? DEFAULT_COUNCIL_NO);
  const [year, setYear] = useState(election.year);
  const [voters, setVoters] = useState(election.total_voters);
  const [busy, setBusy] = useState(false);

  const valid = councilNo >= 1 && year >= 1900 && year <= 2100 && voters >= 1;
  const titleBn = buildTitleBn(Math.max(1, councilNo || 1), year || new Date().getFullYear());
  const titleEn = buildTitleEn(Math.max(1, councilNo || 1), year || new Date().getFullYear());
  const dirty = titleBn !== election.title_bn || titleEn !== election.title || voters !== election.total_voters || year !== election.year;

  const save = async () => {
    if (!token || !valid) return;
    setBusy(true);
    try {
      await api.elections.update(token, election.id, { title: titleEn, title_bn: titleBn, year, total_voters: voters });
      await refresh();
      toast.success("Election title saved — the overview and live screen now show it");
    } catch (err) {
      toast.error(errorMessage(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="flex flex-col gap-4">
      <div className="form-grid form-grid-3">
        <div className="input-group"><label className="input-label" htmlFor="st-council">Council no.</label>
          <div className="input-wrap"><Icon name="hash" size={16} />
            <input id="st-council" className="input" type="number" min={1} value={councilNo}
              onChange={(e) => setCouncilNo(Math.max(0, Number(e.target.value)))} /></div>
          <span className="input-hint">{councilNo >= 1 ? `${englishOrdinal(councilNo)} · ${bengaliOrdinal(councilNo)}` : "At least 1"}</span></div>
        <div className="input-group"><label className="input-label" htmlFor="st-year">Year</label>
          <div className="input-wrap"><Icon name="clock" size={16} />
            <input id="st-year" className="input" type="number" min={1900} max={2100} value={year}
              onChange={(e) => setYear(Number(e.target.value))} /></div>
          <span className="input-hint text-bengali">{toBengaliDigits(year)}</span></div>
        <div className="input-group"><label className="input-label" htmlFor="st-voters">Total voters</label>
          <div className="input-wrap"><Icon name="users" size={16} />
            <input id="st-voters" className="input" type="number" min={1} value={voters}
              onChange={(e) => setVoters(Number(e.target.value))} /></div>
          <span className="input-hint">Used for the turnout figure</span></div>
      </div>

      <div className="title-preview">
        <div className="title-preview-label"><Icon name="sparkles" size={13} /> {dirty ? "New title" : "Current title"}</div>
        <div className="title-preview-bn">{titleBn}</div>
        <div className="title-preview-en">{titleEn}</div>
      </div>

      <div className="flex items-center gap-3" style={{ justifyContent: "flex-end", flexWrap: "wrap" }}>
        {dirty && election.title_bn && (
          <span className="text-faint text-small">Now stored: <span className="text-bengali">{election.title_bn}</span></span>
        )}
        <button className="btn btn-primary" onClick={save} disabled={busy || !valid || !dirty}>
          {busy ? <><span className="btn-spinner" /> Saving…</> : <><Icon name="save" size={16} /> {dirty ? "Save title" : "Saved"}</>}
        </button>
      </div>
    </div>
  );
}
