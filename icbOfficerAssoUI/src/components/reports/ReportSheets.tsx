import { Fragment, useMemo, type ReactNode } from "react";
import type { ElectionReport, ReportPosition } from "@/lib/types";
import { withBase } from "@/lib/basePath";

/**
 * The printable result sheets (Admin -> Reports): 1 summary and 2 tally here,
 * 3 panel votes and 4 null votes in PanelNullSheets.tsx.  Plain black-on-white
 * "paper" markup styled by reports.css: the same component is the on-screen
 * preview and, rendered into the print root, the PDF.
 */

export type ReportKind = "summary" | "tally" | "panel" | "null";

export const REPORT_TITLES: Record<ReportKind, { en: string; bn: string }> = {
  summary: { en: "Result Summary", bn: "ফলাফল সারসংক্ষেপ" },
  tally: { en: "Ballot-wise Vote Tally", bn: "ব্যালট-ভিত্তিক ভোট গণনা" },
  panel: { en: "Panel Votes", bn: "প্যানেল ভোট" },
  null: { en: "Null Votes", bn: "বাতিল ভোট" },
};

/** API timestamps are naive UTC. */
export function reportDate(value: string): Date {
  return new Date(/[zZ]|[+-]\d\d:\d\d$/.test(value) ? value : `${value}Z`);
}

function formatStamp(value: string): string {
  return reportDate(value).toLocaleString("en-GB", {
    day: "numeric", month: "long", year: "numeric", hour: "numeric", minute: "2-digit", hour12: true,
  });
}

const isFinal = (report: ElectionReport) => report.status === "completed";

/* ------------------------------------------------------- letterhead */

export function SheetHeader({ report, kind, extra }: { report: ElectionReport; kind: ReportKind; extra?: ReactNode }) {
  const title = REPORT_TITLES[kind];
  return (
    <header className="rpt-head">
      <div className="rpt-letterhead">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img className="rpt-logo" src={withBase("/icb-logo.png")} alt="" />
        <div className="rpt-org">
          <div className="rpt-org-bn rpt-bn">আইসিবি কর্মকর্তা সমিতি</div>
          <div className="rpt-org-en">ICB Officers&apos; Association</div>
          <div className="rpt-election">
            {report.title_bn && <span className="rpt-bn">{report.title_bn}</span>}
            <span>{report.title}</span>
          </div>
        </div>
        <div className={`rpt-stamp ${isFinal(report) ? "is-final" : ""}`}>
          {isFinal(report) ? "Final" : "Provisional"}
          <small>{isFinal(report) ? "counting completed" : "counting in progress"}</small>
        </div>
      </div>
      <div className="rpt-title-band">
        <h1>{title.en} <span className="rpt-bn">· {title.bn}</span></h1>
        <div className="rpt-meta">
          <span>Election year <b>{report.year}</b></span>
          <span>Prepared <b>{formatStamp(report.generated_at)}</b></span>
          {extra}
        </div>
      </div>
    </header>
  );
}

/* ------------------------------------------------- signatures */

export function Signatures({ signatories, statement, compact }: { signatories: string[]; statement: ReactNode; compact?: boolean }) {
  return (
    <section className={`rpt-sign ${compact ? "is-compact" : ""}`}>
      <p className="rpt-certify">{statement}</p>
      <div className="rpt-sign-row" style={{ gridTemplateColumns: `repeat(${Math.max(1, signatories.length)}, 1fr)` }}>
        {signatories.map((role, index) => (
          <div className="rpt-sign-box" key={index}>
            <div className="rpt-sign-line" />
            <div className="rpt-sign-role">{role || "\u00a0"}</div>
            <div className="rpt-sign-field">Name:</div>
            <div className="rpt-sign-field">Date:</div>
          </div>
        ))}
      </div>
    </section>
  );
}

/* ------------------------------------------------ 1. result summary */

export function PostName({ p }: { p: ReportPosition }) {
  return (
    <>
      {p.name_bn && <span className="rpt-bn">{p.name_bn}</span>}
      <span className="rpt-post-en">{p.name_en}</span>
    </>
  );
}

export function SummaryReport({ report, signatories }: { report: ElectionReport; signatories: string[] }) {
  const { stats } = report;
  const ties = report.positions.filter((p) => p.candidates.some((c) => c.outcome === "tie"));
  const turnout = report.total_voters ? (stats.counted_ballots / report.total_voters) * 100 : 0;

  return (
    <article className="rpt-sheet rpt-summary">
      <SheetHeader report={report} kind="summary" />

      <section className="rpt-figures">
        <Figure label="Registered voters" value={report.total_voters} />
        <Figure label="Ballots counted" value={stats.counted_ballots} />
        <Figure label="Manual files" value={report.manual_ballots} />
        <Figure label="Turnout" value={`${turnout.toFixed(2)}%`} />
        <Figure label="Valid votes" value={report.total_votes} />
      </section>
      {stats.error_ballots > 0 && (
        <p className="rpt-note is-warn">
          {stats.error_ballots} scanned file{stats.error_ballots === 1 ? " is" : "s are"} not read yet and not in these totals.
          {" "}Open {stats.error_ballots === 1 ? "it" : "them"} under Ballots, tick the candidates marked on the paper and save: {stats.error_ballots === 1 ? "it becomes a manual file" : "they become manual files"} and count.
        </p>
      )}
      {stats.needs_review_ballots > 0 && (
        <p className="rpt-note is-warn">
          {stats.needs_review_ballots} ballot{stats.needs_review_ballots === 1 ? " is" : "s are"} still marked &ldquo;needs review&rdquo;.
          {" "}They are included in these totals; check them under Ballots before signing.
        </p>
      )}

      <h2 className="rpt-h2">A. Elected candidates</h2>
      <table className="rpt-table rpt-winners">
        <colgroup><col style={{ width: "7%" }} /><col style={{ width: "33%" }} /><col style={{ width: "6%" }} /><col style={{ width: "8%" }} /><col /><col style={{ width: "7%" }} /><col style={{ width: "6%" }} /></colgroup>
        <thead>
          <tr><th className="num">Post</th><th>Post name</th><th className="num">Seats</th><th className="num">Voter No.</th><th>Elected candidate</th><th className="num">Votes</th><th className="num">Lead</th></tr>
        </thead>
        <tbody>
          {report.positions.map((p) => {
            const elected = p.candidates.filter((c) => c.outcome === "elected");
            const tied = p.candidates.filter((c) => c.outcome === "tie");
            const firstLoser = p.candidates.find((c) => !c.outcome);
            const rows = elected.length + (tied.length ? 1 : 0) || 1;
            return (
              <Fragment key={p.position_id}>
                {elected.map((c, i) => (
                  <tr key={c.candidate_id} className={i === 0 ? "rpt-group-start" : ""}>
                    {i === 0 && <><td className="num rpt-post-no" rowSpan={rows}>{String(p.position_order).padStart(2, "0")}</td><td rowSpan={rows}><PostName p={p} /></td><td className="num" rowSpan={rows}>{p.max_selections}</td></>}
                    <td className="num mono">{c.voter_no}</td>
                    <td><div className="rpt-winner-name"><span className="rpt-tick">✓</span><span>{c.name_bn && <span className="rpt-bn">{c.name_bn}</span>}<span className={c.name_bn ? "rpt-name-en-inline" : ""}>{c.name_en}</span></span></div></td>
                    <td className="num mono strong">{c.votes}</td>
                    <td className="num mono">{firstLoser ? `+${c.votes - firstLoser.votes}` : "—"}</td>
                  </tr>
                ))}
                {tied.length > 0 && (
                  <tr className={elected.length === 0 ? "rpt-group-start" : ""}>
                    {elected.length === 0 && <><td className="num rpt-post-no" rowSpan={rows}>{String(p.position_order).padStart(2, "0")}</td><td rowSpan={rows}><PostName p={p} /></td><td className="num" rowSpan={rows}>{p.max_selections}</td></>}
                    <td className="num mono">{tied.map((c) => c.voter_no).join(", ")}</td>
                    <td className="rpt-tie" colSpan={3}>
                      Tie on {tied[0].votes} vote{tied[0].votes === 1 ? "" : "s"} between {tied.map((c) => c.name_bn ?? c.name_en).join(" and ")}
                      {" "}for {elected.length ? "the last seat" : p.max_selections > 1 ? `${p.max_selections - elected.length} seats` : "the seat"}: to be decided by the Election Commission
                    </td>
                  </tr>
                )}
                {elected.length === 0 && tied.length === 0 && (
                  <tr className="rpt-group-start">
                    <td className="num rpt-post-no">{String(p.position_order).padStart(2, "0")}</td><td><PostName p={p} /></td><td className="num">{p.max_selections}</td>
                    <td className="rpt-muted" colSpan={4}>No votes counted for this post</td>
                  </tr>
                )}
              </Fragment>
            );
          })}
        </tbody>
      </table>

      <Signatures
        signatories={signatories}
        statement={<>We certify that the results above were counted from <b>{stats.counted_ballots}</b> ballot papers
          {report.manual_ballots > 0 ? <> ({report.manual_ballots} of them entered or corrected manually by the Election Commission)</> : null}
          {" "}of <b>{report.total_voters}</b> registered voters.
          {" "}The votes of every candidate are given in the annex.</>}
      />

      <section className="rpt-annex">
        <h2 className="rpt-h2">Annex · B. Votes received by every candidate</h2>
        <table className="rpt-table rpt-all">
          <colgroup><col style={{ width: "6%" }} /><col style={{ width: "19%" }} /><col style={{ width: "6%" }} /><col style={{ width: "8%" }} /><col /><col style={{ width: "7%" }} /><col style={{ width: "9%" }} /><col style={{ width: "10%" }} /></colgroup>
          <thead>
            <tr><th className="num">Post</th><th>Post name</th><th className="num">Rank</th><th className="num">Voter No.</th><th>Candidate</th><th className="num">Votes</th><th className="num">% of ballots</th><th className="num">Result</th></tr>
          </thead>
          {report.positions.map((p) => (
            <tbody key={p.position_id} className="rpt-all-post">
              {p.candidates.map((c, i) => (
                <tr key={c.candidate_id} className={c.outcome ? `is-${c.outcome}` : ""}>
                  {i === 0 && (
                    <>
                      <td className="num rpt-post-no" rowSpan={p.candidates.length}>{String(p.position_order).padStart(2, "0")}</td>
                      <td rowSpan={p.candidates.length} className="rpt-all-postname">
                        <PostName p={p} />
                        <span className="rpt-post-seats-inline">{p.max_selections > 1 ? `${p.max_selections} seats` : "1 seat"} · {p.total_votes} votes</span>
                      </td>
                    </>
                  )}
                  <td className="num">{c.rank}</td>
                  <td className="num mono">{c.voter_no}</td>
                  <td className="rpt-all-name">{c.name_bn && <span className="rpt-bn">{c.name_bn}</span>}<span className={c.name_bn ? "rpt-name-en-inline" : ""}>{c.name_en}</span></td>
                  <td className="num mono strong">{c.votes}</td>
                  <td className="num mono">{c.percentage.toFixed(2)}</td>
                  <td className="num rpt-result">{c.outcome === "elected" ? "ELECTED" : c.outcome === "tie" ? "TIE" : ""}</td>
                </tr>
              ))}
            </tbody>
          ))}
        </table>
        {ties.length > 0 && <p className="rpt-note">TIE: equal votes for the last seat of a post; the Election Commission decides as per the constitution.</p>}
        <Signatures compact signatories={signatories}
          statement={<>Annex to the Result Summary: votes received by each of the {report.positions.reduce((n, p) => n + p.candidates.length, 0)} candidates.</>} />
      </section>
    </article>
  );
}

export function Figure({ label, value }: { label: string; value: ReactNode }) {
  return <div className="rpt-figure"><b>{value}</b><span>{label}</span></div>;
}

/* --------------------------------------------- 2. ballot-wise tally */

/** Every candidate in ballot order, grouped by post: the tally's columns. */
export function tallyColumns(report: ElectionReport) {
  const groups = report.positions.map((p) => ({
    position: p,
    candidates: [...p.candidates].sort((a, b) => a.display_order - b.display_order || a.candidate_id - b.candidate_id),
  }));
  return { groups, columns: groups.flatMap((g) => g.candidates) };
}

export function ballotLabel(ballot: { ballot_paper_no: string | null; serial: number }): string {
  return ballot.ballot_paper_no ?? String(ballot.serial);
}

/** Remarks column: "Manual" = selections saved by the Election Commission (counted like any other ballot). */
export function remark(status: string): string {
  if (status === "reviewed") return "Manual";
  if (status === "needs_review") return "Review";
  return "";
}

export function TallyReport({ report, signatories, highlight, onHighlight }: {
  report: ElectionReport; signatories: string[];
  highlight?: number | null; onHighlight?: (candidateId: number | null) => void;
}) {
  const { groups, columns } = useMemo(() => tallyColumns(report), [report]);
  const totals = useMemo(() => {
    const sums = new Map<number, number>();
    report.ballots.forEach((b) => b.candidate_ids.forEach((id) => sums.set(id, (sums.get(id) ?? 0) + 1)));
    return sums;
  }, [report]);
  const elected = useMemo(() => new Map(report.positions.flatMap((p) => p.candidates.map((c) => [c.candidate_id, c.outcome] as const))), [report]);
  const grandTotal = report.ballots.reduce((sum, b) => sum + b.candidate_ids.length, 0);
  const hl = (id: number) => (highlight === id ? "is-hl" : "");

  return (
    <article className="rpt-sheet rpt-tally-sheet">
      <SheetHeader report={report} kind="tally" extra={<span>1 = vote counted · 0 = no vote · <b>{report.ballots.length}</b> ballots × <b>{columns.length}</b> candidates</span>} />

      <table className="rpt-tally" onMouseLeave={() => onHighlight?.(null)}>
        {/* fixed widths: every candidate column the same, whatever the post names */}
        <colgroup>
          <col className="rpt-col-sl" /><col className="rpt-col-no" />
          {columns.map((c) => <col key={c.candidate_id} className="rpt-col-cand" />)}
          <col className="rpt-col-total" /><col className="rpt-col-remark" />
        </colgroup>
        <thead>
          <tr className="rpt-tally-posts">
            <th rowSpan={2} className="rpt-tally-sl">Sl.</th>
            <th rowSpan={2} className="rpt-tally-no">Ballot<br />No.</th>
            {groups.map((g) => (
              <th key={g.position.position_id} colSpan={g.candidates.length} className="rpt-tally-post" title={g.position.name_en}>
                <span className="rpt-tally-post-no">{String(g.position.position_order).padStart(2, "0")}</span>
                <span className="rpt-tally-post-name">{g.position.name_bn ?? g.position.name_en}</span>
              </th>
            ))}
            <th rowSpan={2} className="rpt-tally-total">Votes</th>
            <th rowSpan={2} className="rpt-tally-remark">Remarks</th>
          </tr>
          <tr className="rpt-tally-cands">
            {groups.map((g) => g.candidates.map((c, i) => (
              <th key={c.candidate_id} className={`rpt-tally-cand ${i === 0 ? "grp" : ""} ${hl(c.candidate_id)}`} onMouseEnter={() => onHighlight?.(c.candidate_id)} title={`${c.voter_no} · ${c.name_en}`}>
                <span className="rpt-tally-cname">{c.name_bn ?? c.name_en}</span>
                <span className="rpt-tally-vno">{c.voter_no}</span>
              </th>
            )))}
          </tr>
        </thead>
        <tbody>
          {report.ballots.map((b) => {
            const marks = new Set(b.candidate_ids);
            return (
              <tr key={b.ballot_id} className={b.status === "reviewed" ? "is-manual" : ""}>
                <td className="rpt-tally-sl">{b.serial}</td>
                <td className="rpt-tally-no">{ballotLabel(b)}</td>
                {groups.map((g) => g.candidates.map((c, i) => (
                  <td key={c.candidate_id} className={`${marks.has(c.candidate_id) ? "one" : "zero"} ${i === 0 ? "grp" : ""} ${hl(c.candidate_id)}`} onMouseEnter={() => onHighlight?.(c.candidate_id)}>
                    {marks.has(c.candidate_id) ? 1 : 0}
                  </td>
                )))}
                <td className="rpt-tally-total">{b.candidate_ids.length}</td>
                <td className="rpt-tally-remark">{remark(b.status)}</td>
              </tr>
            );
          })}
          {report.ballots.length === 0 && (
            <tr><td colSpan={columns.length + 4} className="rpt-muted rpt-tally-empty">No ballots have been counted yet.</td></tr>
          )}
          <tr className="rpt-tally-sum">
            <td colSpan={2}>Total</td>
            {groups.map((g) => g.candidates.map((c, i) => (
              <td key={c.candidate_id} className={`${i === 0 ? "grp" : ""} ${elected.get(c.candidate_id) ? `is-${elected.get(c.candidate_id)}` : ""} ${hl(c.candidate_id)}`}>
                {totals.get(c.candidate_id) ?? 0}
              </td>
            )))}
            <td className="rpt-tally-total">{grandTotal}</td>
            <td />
          </tr>
        </tbody>
      </table>
      <p className="rpt-note">
        Dark totals are the elected candidates (yellow, underlined: tie for the last seat). Each candidate&apos;s total equals the votes in the Result Summary.
        {report.manual_ballots > 0 && ` Manual: the ${report.manual_ballots} ballot${report.manual_ballots === 1 ? "" : "s"} whose selections the Election Commission entered or corrected; they count in the totals.`}
        {report.void_marks > 0 && ` ${report.void_marks} mark${report.void_marks === 1 ? " was" : "s were"} not counted under the ballot rules (ক/খ/গ) and show as 0.`}
      </p>

      <Signatures
        signatories={signatories}
        statement={<>We certify that this tally lists every one of the <b>{report.ballots.length}</b> counted ballot papers and the
          {" "}<b>{grandTotal}</b> valid votes read from them.</>}
      />
    </article>
  );
}
