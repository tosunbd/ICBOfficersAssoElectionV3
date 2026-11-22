import { useMemo } from "react";
import type { ElectionReport, ReportPosition } from "@/lib/types";
import { Figure, PostName, SheetHeader, Signatures, ballotLabel } from "./ReportSheets";

/**
 * Report 3 (Panel Votes) and report 4 (Null Votes) of Admin -> Reports.
 * Same "paper" markup as ReportSheets.tsx, styled by reports.css.
 */

export type Panel = "left" | "right";
export const PANEL_LABELS: Record<Panel, string> = { left: "Panel Left", right: "Panel Right" };

function CandidateName({ c }: { c: { name_en: string; name_bn: string | null } }) {
  return (
    <>
      {c.name_bn && <span className="rpt-bn">{c.name_bn}</span>}
      <span className={c.name_bn ? "rpt-name-en-inline" : ""}>{c.name_en}</span>
    </>
  );
}

const postNo = (p: ReportPosition) => String(p.position_order).padStart(2, "0");
const plural = (n: number, one: string, many = `${one}s`) => `${n} ${n === 1 ? one : many}`;

/* ---------------------------------------------------- 3. panel votes */

/** The candidates printed on one side of the ballot paper, post by post, and the panel's figures. */
export function panelFigures(report: ElectionReport, panel: Panel) {
  const posts = report.positions
    .map((p) => ({
      position: p,
      candidates: p.candidates
        .filter((c) => c.panel === panel)
        .sort((a, b) => a.display_order - b.display_order || a.candidate_id - b.candidate_id),
    }))
    .filter((g) => g.candidates.length > 0);
  const members = posts.flatMap((g) => g.candidates);
  const ids = new Set(members.map((c) => c.candidate_id));
  const votes = members.reduce((sum, c) => sum + c.votes, 0);
  let full = 0;
  let only = 0;
  report.ballots.forEach((b) => {
    const forPanel = b.candidate_ids.filter((id) => ids.has(id)).length;
    if (ids.size > 0 && forPanel === ids.size) full += 1;                // a vote for every candidate of the panel
    if (forPanel > 0 && forPanel === b.candidate_ids.length) only += 1;  // every counted vote of the ballot is for the panel
  });
  return { posts, members, votes, full, only, elected: members.filter((c) => c.outcome === "elected").length };
}

export function PanelReport({ report, panel, signatories }: { report: ElectionReport; panel: Panel; signatories: string[] }) {
  const own = useMemo(() => panelFigures(report, panel), [report, panel]);
  const otherPanel: Panel = panel === "left" ? "right" : "left";
  const other = useMemo(() => panelFigures(report, otherPanel), [report, otherPanel]);
  const share = report.total_votes ? (own.votes / report.total_votes) * 100 : 0;

  return (
    <article className="rpt-sheet rpt-panel">
      <SheetHeader report={report} kind="panel"
        extra={<span><b>{PANEL_LABELS[panel]}</b> · candidates printed on the {panel} side of the ballot paper</span>} />

      <section className="rpt-figures">
        <Figure label="Panel candidates" value={own.members.length} />
        <Figure label="Ballots counted" value={report.ballots.length} />
        <Figure label="Panel votes" value={own.votes} />
        <Figure label="Share of valid votes" value={`${share.toFixed(2)}%`} />
        <Figure label="Elected" value={own.elected} />
        <Figure label="Full-panel ballots" value={own.full} />
        <Figure label="Panel-only ballots" value={own.only} />
      </section>

      {own.members.length === 0 ? (
        <p className="rpt-note is-warn">No candidate is printed on the {panel} side of the ballot paper for this election.</p>
      ) : (
        <>
          <h2 className="rpt-h2">Votes of {PANEL_LABELS[panel]}</h2>
          <table className="rpt-table rpt-all rpt-panel-table">
            <colgroup>
              <col style={{ width: "6%" }} /><col style={{ width: "23%" }} /><col style={{ width: "8%" }} /><col />
              <col style={{ width: "8%" }} /><col style={{ width: "10%" }} /><col style={{ width: "7%" }} /><col style={{ width: "10%" }} />
            </colgroup>
            <thead>
              <tr>
                <th className="num">Post</th><th>Post name</th><th className="num">Voter No.</th><th>Candidate</th>
                <th className="num">Votes</th><th className="num">% of ballots</th><th className="num">Rank</th><th className="num">Result</th>
              </tr>
            </thead>
            {own.posts.map(({ position: p, candidates }) => (
              <tbody key={p.position_id} className="rpt-all-post">
                {candidates.map((c, i) => (
                  <tr key={c.candidate_id} className={c.outcome ? `is-${c.outcome}` : ""}>
                    {i === 0 && (
                      <>
                        <td className="num rpt-post-no" rowSpan={candidates.length}>{postNo(p)}</td>
                        <td rowSpan={candidates.length} className="rpt-all-postname"><PostName p={p} /></td>
                      </>
                    )}
                    <td className="num mono">{c.voter_no}</td>
                    <td className="rpt-all-name"><CandidateName c={c} /></td>
                    <td className="num mono strong">{c.votes}</td>
                    <td className="num mono">{c.percentage.toFixed(2)}</td>
                    <td className="num">{c.rank}</td>
                    <td className="num rpt-result">{c.outcome === "elected" ? "ELECTED" : c.outcome === "tie" ? "TIE" : ""}</td>
                  </tr>
                ))}
              </tbody>
            ))}
            <tfoot>
              <tr className="rpt-total-row">
                <td colSpan={4}>Total votes of {PANEL_LABELS[panel]}</td>
                <td className="num mono">{own.votes}</td>
                <td colSpan={3} className="num">{share.toFixed(2)}% of valid votes · {own.elected} elected</td>
              </tr>
            </tfoot>
          </table>
          <p className="rpt-note">
            {PANEL_LABELS[panel]}: {plural(own.votes, "vote")} for {plural(own.members.length, "candidate")}, {own.elected} elected.
            {" "}{PANEL_LABELS[otherPanel]}: {plural(other.votes, "vote")} for {plural(other.members.length, "candidate")}, {other.elected} elected.
            {" "}% of ballots: share of the {report.ballots.length} counted ballots.
            {" "}Full-panel ballot: a vote for every candidate of the panel. Panel-only ballot: every counted vote of the ballot is for this panel.
          </p>
        </>
      )}

      <Signatures signatories={signatories}
        statement={<>We certify that the <b>{own.members.length}</b> candidates of {PANEL_LABELS[panel]} received <b>{own.votes}</b> of
          the <b>{report.total_votes}</b> valid votes counted from <b>{report.ballots.length}</b> ballot papers.</>} />
    </article>
  );
}

/* ----------------------------------------------------- 4. null votes */

export function NullReport({ report, signatories }: { report: ElectionReport; signatories: string[] }) {
  const data = useMemo(() => {
    const byId = new Map(report.positions.flatMap((p) => p.candidates.map((c) => [c.candidate_id, { c, p }] as const)));
    const rows = report.ballots.flatMap((b) => b.void.map((mark) => ({ ballot: b, mark, found: byId.get(mark.candidate_id) })));
    const reasons = new Map<string, { marks: number; ballots: Set<number> }>();
    rows.forEach(({ ballot, mark }) => {
      const entry = reasons.get(mark.reason) ?? { marks: 0, ballots: new Set<number>() };
      entry.marks += 1;
      entry.ballots.add(ballot.ballot_id);
      reasons.set(mark.reason, entry);
    });
    const posts = report.positions.map((p) => {
      const ids = new Set(p.candidates.map((c) => c.candidate_id));
      const nulls = rows.filter((r) => r.mark.position_id === p.position_id).length;
      // left blank: the voter put no mark at all for this post
      const blank = report.ballots.filter((b) =>
        !b.candidate_ids.some((id) => ids.has(id)) && !b.void.some((v) => v.position_id === p.position_id)).length;
      return { p, nulls, blank };
    });
    return {
      rows,
      posts,
      reasons: [...reasons.entries()].sort((a, b) => b[1].marks - a[1].marks),
      ballots: report.ballots.filter((b) => b.void.length > 0).length,
      blank: posts.reduce((sum, g) => sum + g.blank, 0),
    };
  }, [report]);
  const unread = report.unread_files;
  const nulls = data.rows.length;

  return (
    <article className="rpt-sheet rpt-null">
      <SheetHeader report={report} kind="null" extra={<span>every vote that is <b>not counted</b>, with the reason</span>} />

      <section className="rpt-figures">
        <Figure label="Ballots counted" value={report.ballots.length} />
        <Figure label="Valid votes" value={report.total_votes} />
        <Figure label="Null votes" value={nulls} />
        <Figure label="Ballots with null votes" value={data.ballots} />
        <Figure label="Posts left blank" value={data.blank} />
        <Figure label="Files not read" value={unread.length} />
      </section>

      <h2 className="rpt-h2">A. Null votes by reason</h2>
      <table className="rpt-table rpt-null-table">
        <colgroup><col /><col style={{ width: "14%" }} /><col style={{ width: "14%" }} /></colgroup>
        <thead><tr><th>Reason the vote is not counted</th><th className="num">Null votes</th><th className="num">Ballots</th></tr></thead>
        <tbody>
          {data.reasons.map(([reason, entry]) => (
            <tr key={reason}><td>{reason}</td><td className="num mono strong">{entry.marks}</td><td className="num mono">{entry.ballots.size}</td></tr>
          ))}
          {data.reasons.length === 0 && (
            <tr><td colSpan={3} className="rpt-muted">No null votes: every mark found on the counted ballots is counted.</td></tr>
          )}
        </tbody>
        {data.reasons.length > 0 && (
          <tfoot><tr className="rpt-total-row"><td>Total</td><td className="num mono">{nulls}</td><td className="num mono">{data.ballots}</td></tr></tfoot>
        )}
      </table>

      <h2 className="rpt-h2">B. Post by post</h2>
      <table className="rpt-table rpt-null-table">
        <colgroup>
          <col style={{ width: "7%" }} /><col /><col style={{ width: "9%" }} /><col style={{ width: "13%" }} />
          <col style={{ width: "13%" }} /><col style={{ width: "18%" }} />
        </colgroup>
        <thead>
          <tr>
            <th className="num">Post</th><th>Post name</th><th className="num">Seats</th><th className="num">Valid votes</th>
            <th className="num">Null votes</th><th className="num">Left blank (ballots)</th>
          </tr>
        </thead>
        <tbody>
          {data.posts.map(({ p, nulls: postNulls, blank }) => (
            <tr key={p.position_id}>
              <td className="num rpt-post-no">{postNo(p)}</td><td><PostName p={p} /></td><td className="num">{p.max_selections}</td>
              <td className="num mono">{p.total_votes}</td><td className="num mono strong">{postNulls}</td><td className="num mono">{blank}</td>
            </tr>
          ))}
        </tbody>
        <tfoot>
          <tr className="rpt-total-row">
            <td colSpan={3}>Total</td><td className="num mono">{report.total_votes}</td><td className="num mono">{nulls}</td><td className="num mono">{data.blank}</td>
          </tr>
        </tfoot>
      </table>

      <h2 className="rpt-h2">C. Every null vote</h2>
      <table className="rpt-table rpt-null-table rpt-null-list">
        <colgroup>
          <col style={{ width: "6%" }} /><col style={{ width: "10%" }} /><col style={{ width: "19%" }} /><col style={{ width: "9%" }} />
          <col style={{ width: "24%" }} /><col />
        </colgroup>
        <thead>
          <tr><th className="num">Sl.</th><th className="num">Ballot No.</th><th>Post</th><th className="num">Voter No.</th><th>Candidate marked</th><th>Reason</th></tr>
        </thead>
        <tbody>
          {data.rows.map(({ ballot, mark, found }, index) => (
            <tr key={`${ballot.ballot_id}-${mark.candidate_id}-${index}`}>
              <td className="num">{index + 1}</td>
              <td className="num mono strong">{ballotLabel(ballot)}</td>
              <td>{found ? <span className={found.p.name_bn ? "rpt-bn" : ""}>{found.p.name_bn ?? found.p.name_en}</span> : "—"}</td>
              <td className="num mono">{found?.c.voter_no ?? "—"}</td>
              <td>{found ? <span className={found.c.name_bn ? "rpt-bn" : ""}>{found.c.name_bn ?? found.c.name_en}</span> : "—"}</td>
              <td className="rpt-null-reason">{mark.reason}</td>
            </tr>
          ))}
          {nulls === 0 && <tr><td colSpan={6} className="rpt-muted">No null votes.</td></tr>}
        </tbody>
      </table>

      <h2 className="rpt-h2">D. Scanned files not read</h2>
      <table className="rpt-table rpt-null-table rpt-null-list">
        <colgroup><col style={{ width: "6%" }} /><col style={{ width: "34%" }} /><col style={{ width: "8%" }} /><col /></colgroup>
        <thead><tr><th className="num">Sl.</th><th>File</th><th className="num">Page</th><th>Reason</th></tr></thead>
        <tbody>
          {unread.map((f, index) => (
            <tr key={f.ballot_id}>
              <td className="num">{index + 1}</td><td className="mono">{f.pdf_filename}</td><td className="num">{f.page_number}</td>
              <td className="rpt-null-reason">{f.reason}</td>
            </tr>
          ))}
          {unread.length === 0 && <tr><td colSpan={4} className="rpt-muted">Every scanned file was read.</td></tr>}
        </tbody>
      </table>
      <p className="rpt-note">
        Null vote: a mark found on a counted ballot that is not added to any candidate (ballot rules ক/খ/গ, or not counted by the Election Commission on the review screen).
        {" "}Left blank: ballots with no mark at all for that post.
        {" "}A file not read counts for nobody until its votes are entered under Ballots; it then becomes a manual file.
      </p>

      <Signatures signatories={signatories}
        statement={<>We certify that <b>{nulls}</b> vote{nulls === 1 ? "" : "s"} on <b>{data.ballots}</b> of the <b>{report.ballots.length}</b> counted
          ballot papers {nulls === 1 ? "was" : "were"} not counted for the reasons listed above
          {unread.length > 0 ? <>, and that <b>{unread.length}</b> scanned file{unread.length === 1 ? " is" : "s are"} not read</> : null}.</>} />
    </article>
  );
}
