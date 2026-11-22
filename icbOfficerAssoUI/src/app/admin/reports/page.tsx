"use client";

import "../../reports.css";
import { useCallback, useMemo, useState, useSyncExternalStore } from "react";
import { createPortal } from "react-dom";
import { api } from "@/lib/api";
import { errorMessage } from "@/lib/format";
import type { ElectionReport } from "@/lib/types";
import { useAuth } from "@/hooks/useAuth";
import { useElection } from "@/hooks/useElection";
import { useLoader } from "@/hooks/useLoader";
import { useToast } from "@/components/ui/Toast";
import { CardHead, EmptyState, PageHeader, Skeleton } from "@/components/ui/Basics";
import { Icon } from "@/components/ui/Icon";
import {
  REPORT_TITLES, SummaryReport, TallyReport, ballotLabel, remark, reportDate, tallyColumns, type ReportKind,
} from "@/components/reports/ReportSheets";
import { NullReport, PANEL_LABELS, PanelReport, type Panel } from "@/components/reports/PanelNullSheets";

const SIGNATORIES_KEY = "icb-report-signatories";
const DEFAULT_SIGNATORIES = ["Member, Election Commission", "Member, Election Commission", "Chief Election Commissioner"];

/** Default PDF file name of every sheet. */
const FILE_NAMES: Record<ReportKind, string> = { summary: "Result-Summary", tally: "Ballot-Tally", panel: "Panel-Votes", null: "Null-Votes" };

/** Paper for the wide tally; the other sheets are always A4 portrait. */
const PAPERS = {
  "A4 landscape": "A4 landscape",
  "A3 landscape": "A3 landscape",
  "Legal landscape": "legal landscape",
} as const;
type Paper = keyof typeof PAPERS;

// signature titles are remembered in this browser (localStorage)
const signListeners = new Set<() => void>();
const subscribeSigns = (listener: () => void) => { signListeners.add(listener); return () => { signListeners.delete(listener); }; };
const readSigns = () => localStorage.getItem(SIGNATORIES_KEY);
function parseSigns(raw: string | null): string[] {
  try {
    const saved = JSON.parse(raw ?? "null");
    if (Array.isArray(saved) && saved.length && saved.every((v) => typeof v === "string")) return saved;
  } catch { /* fall back to the defaults */ }
  return DEFAULT_SIGNATORIES;
}
const noopSubscribe = () => () => {};

export default function ReportsPage() {
  const { token } = useAuth();
  const { election } = useElection();
  const toast = useToast();
  const [report, setReport] = useState<ElectionReport | null>(null);
  const [loading, setLoading] = useState(true);
  const [kind, setKind] = useState<ReportKind>("summary");
  const [paper, setPaper] = useState<Paper>("A4 landscape");
  const [panel, setPanel] = useState<Panel>("left");
  const signsRaw = useSyncExternalStore(subscribeSigns, readSigns, () => null);
  const signatories = useMemo(() => parseSigns(signsRaw), [signsRaw]);
  const hydrated = useSyncExternalStore(noopSubscribe, () => true, () => false);
  const [editingSigns, setEditingSigns] = useState(false);
  const [highlight, setHighlight] = useState<number | null>(null);

  const load = useCallback(async () => {
    if (!token || !election) return;
    setLoading(true);
    try {
      setReport(await api.reports.get(token, election.id));
    } catch (err) {
      toast.error(errorMessage(err));
    } finally {
      setLoading(false);
    }
  }, [token, election, toast]);
  useLoader(load);

  const saveSignatories = (next: string[]) => {
    localStorage.setItem(SIGNATORIES_KEY, JSON.stringify(next));
    signListeners.forEach((listener) => listener());
  };

  const fileName = (what: string) => {
    const year = report?.year ?? election?.year ?? "";
    const stamp = report ? reportDate(report.generated_at).toISOString().slice(0, 10) : "";
    return `ICB-Officers-Association-Election-${year}-${what}-${stamp}`;
  };

  const print = async () => {
    await load();  // print the latest figures
    const previous = document.title;
    document.title = fileName(kind === "panel" ? `Panel-${panel === "left" ? "Left" : "Right"}-Votes` : FILE_NAMES[kind]);  // default PDF file name
    const restore = () => { document.title = previous; window.removeEventListener("afterprint", restore); };
    window.addEventListener("afterprint", restore);
    // let React paint the refreshed copy before the print dialog opens
    requestAnimationFrame(() => setTimeout(() => window.print(), 50));
  };

  const exportTallyCsv = () => {
    if (!report) return;
    const { columns } = tallyColumns(report);
    const header = ["Sl", "Ballot No", ...columns.map((c) => `${c.voter_no} ${c.name_en}`), "Votes", "Remarks"];
    const rows = report.ballots.map((b) => {
      const marks = new Set(b.candidate_ids);
      return [String(b.serial), ballotLabel(b), ...columns.map((c) => (marks.has(c.candidate_id) ? "1" : "0")), String(b.candidate_ids.length), remark(b.status)];
    });
    const totals = ["", "Total", ...columns.map((c) => String(report.ballots.filter((b) => b.candidate_ids.includes(c.candidate_id)).length)),
      String(report.ballots.reduce((s, b) => s + b.candidate_ids.length, 0)), ""];
    const csv = [header, ...rows, totals].map((r) => r.map((v) => `"${v.replace(/"/g, '""')}"`).join(",")).join("\r\n");
    const url = URL.createObjectURL(new Blob(["\ufeff" + csv], { type: "text/csv;charset=utf-8" }));
    const a = document.createElement("a");
    a.href = url;
    a.download = `${fileName("Ballot-Tally")}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  };

  if (!election) return <EmptyState icon="landmark" title="Create an election first" />;

  const sheet = report && (
    kind === "summary" ? <SummaryReport report={report} signatories={signatories} />
    : kind === "tally" ? <TallyReport report={report} signatories={signatories} highlight={highlight} onHighlight={setHighlight} />
    : kind === "panel" ? <PanelReport report={report} panel={panel} signatories={signatories} />
    : <NullReport report={report} signatories={signatories} />);
  const pageSize = kind === "tally" ? PAPERS[paper] : "A4 portrait";
  const footerTitle = kind === "panel" ? `${REPORT_TITLES.panel.en} (${PANEL_LABELS[panel]})` : REPORT_TITLES[kind].en;

  return (
    <div className="page">
      {/* paper size and page numbers of the PDF */}
      <style>{`@page { size: ${pageSize}; margin: 12mm 11mm 14mm; @bottom-right { content: "Page " counter(page) " of " counter(pages); font: 8pt sans-serif; color: #555; } @bottom-left { content: "${footerTitle} · ${(report?.title ?? "").replace(/["\\]/g, "")}"; font: 8pt sans-serif; color: #555; }${kind === "tally" ? ' @bottom-center { content: "Initials: ____________   ____________   ____________"; font: 8pt sans-serif; color: #555; }' : ""} }`}</style>

      <PageHeader eyebrow="Command" title="Reports" subtitle="Official result sheets to print, sign and submit"
        actions={
          <>
            <button className="btn btn-ghost" onClick={load} disabled={loading}><Icon name="refresh" size={15} /> Refresh</button>
            {kind === "tally" && <button className="btn btn-ghost" onClick={exportTallyCsv} disabled={!report}><Icon name="download" size={15} /> Excel (CSV)</button>}
            <button className="btn btn-primary" onClick={print} disabled={!report}><Icon name="download" size={16} /> Print / Save as PDF</button>
          </>
        } />

      <div className="card mb-6">
        <CardHead icon="scroll" title="Report" subtitle="Choose the sheet; the preview below is exactly what is printed">
          <div className="segmented" role="tablist">
            {(Object.keys(REPORT_TITLES) as ReportKind[]).map((k, index) => (
              <button key={k} role="tab" aria-selected={kind === k} className={kind === k ? "active" : ""} onClick={() => setKind(k)}>
                {index + 1} · {REPORT_TITLES[k].en}
              </button>
            ))}
          </div>
        </CardHead>
        <div className="rpt-options">
          {kind === "tally" ? (
            <label className="rpt-option">
              <span>Paper</span>
              <select className="input" value={paper} onChange={(e) => setPaper(e.target.value as Paper)}>
                {(Object.keys(PAPERS) as Paper[]).map((p) => <option key={p}>{p}</option>)}
              </select>
              <em>A3 suits many candidates; the column headings repeat on every page.</em>
            </label>
          ) : kind === "panel" ? (
            <label className="rpt-option">
              <span>Panel</span>
              <select className="input" value={panel} onChange={(e) => setPanel(e.target.value as Panel)}>
                {(Object.keys(PANEL_LABELS) as Panel[]).map((p) => <option key={p} value={p}>{PANEL_LABELS[p]}</option>)}
              </select>
              <em>The candidates printed on that side of the ballot paper. A4 portrait.</em>
            </label>
          ) : kind === "null" ? (
            <div className="rpt-option"><span>Paper</span><b>A4 portrait</b><em>Every vote that is not counted, with its reason, and the files not read.</em></div>
          ) : (
            <div className="rpt-option"><span>Paper</span><b>A4 portrait</b><em>Elected candidates first, then the votes of every candidate.</em></div>
          )}
          <div className="rpt-option rpt-option-signs">
            <span>Signatures</span>
            {editingSigns ? (
              <div className="rpt-sign-editor">
                {signatories.map((s, i) => (
                  <div key={i} className="rpt-sign-edit-row">
                    <input className="input" value={s} placeholder="Title, e.g. Chief Election Commissioner"
                      onChange={(e) => saveSignatories(signatories.map((v, j) => (j === i ? e.target.value : v)))} />
                    <button className="btn btn-ghost btn-sm" onClick={() => saveSignatories(signatories.filter((_, j) => j !== i))} disabled={signatories.length <= 1} title="Remove"><Icon name="x" size={14} /></button>
                  </div>
                ))}
                <div className="rpt-sign-edit-actions">
                  <button className="btn btn-ghost btn-sm" onClick={() => saveSignatories([...signatories, ""])} disabled={signatories.length >= 5}><Icon name="plus" size={14} /> Add</button>
                  <button className="btn btn-ghost btn-sm" onClick={() => saveSignatories(DEFAULT_SIGNATORIES)}>Reset</button>
                  <button className="btn btn-accent btn-sm" onClick={() => setEditingSigns(false)}><Icon name="check" size={14} /> Done</button>
                </div>
              </div>
            ) : (
              <>
                <b>{signatories.filter(Boolean).join(" · ") || "—"}</b>
                <button className="link-btn" onClick={() => setEditingSigns(true)}><Icon name="edit" size={13} /> Edit</button>
              </>
            )}
          </div>
        </div>
      </div>

      <div className={`rpt-preview ${kind === "tally" ? "is-wide" : ""}`}>
        {loading && !report ? (
          <div className="rpt-sheet"><Skeleton height={60} /><Skeleton height={400} style={{ marginTop: 16 }} /></div>
        ) : sheet}
      </div>

      {/* the PDF is printed from this copy, outside the admin layout (see reports.css) */}
      {hydrated && sheet && createPortal(<div className="rpt-print-root">{sheet}</div>, document.body)}
    </div>
  );
}
