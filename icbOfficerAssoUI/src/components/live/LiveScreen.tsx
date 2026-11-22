"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useReducer, useRef, useState, type ReactNode } from "react";
import { api } from "@/lib/api";
import type { ActiveElection, DashboardData, LiveBallotEvent, PositionResult, ReplayProgress } from "@/lib/types";
import { useSSE } from "@/hooks/useSSE";
import { initialLiveState, liveReducer } from "./liveReducer";
import { ThemeToggle } from "@/components/ui/ThemeToggle";
import { Logo } from "@/components/ui/Logo";
import { Icon } from "@/components/ui/Icon";
import { AnimatedNumber, RingGauge, prefersReducedMotion, useClock, useFlip } from "@/components/ui/Motion";
import { CountingControl } from "./CountingControl";

export { Logo };

const CREDIT = "Designed and developed by Taufiqul Islam";

/* ------------------------------------------------------------------ */
/*  Public live screen — designed for a projector / large TV           */
/*                                                                      */
/*   ┌──────────────────────── header ────────────────────────┐        */
/*   │          standings of every post (whole screen)           │     */
/*   └──────────────────────── footer ────────────────────────┘        */
/*                                                                      */
/*  Summary only: the ballots are scanned and read internally.  Neither */
/*  the scan nor the marks of a single ballot are shown; the totals of  */
/*  every candidate move after each ballot that has been read.          */
/* ------------------------------------------------------------------ */

export function LiveScreen() {
  const [election, setElection] = useState<ActiveElection | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [state, dispatch] = useReducer(liveReducer, initialLiveState);

  useEffect(() => {
    api.dashboard.active()
      .then((active) => {
        setElection(active);
        return api.dashboard.results(active.id).then((data) => dispatch({ type: "results", data }));
      })
      .catch(() => setError("The election has not been set up yet."));
  }, []);

  // START after a PAUSE: open a fresh stream and reload the totals, so this screen is
  // in step again without a page refresh (the stream also sends any ballot it missed)
  const [resyncKey, setResyncKey] = useState(0);
  const wasPaused = useRef(false);
  useEffect(() => {
    const resumed = wasPaused.current && !state.countingPaused;
    wasPaused.current = state.countingPaused;
    if (!resumed || !election) return;
    setResyncKey((key) => key + 1);
    api.dashboard.results(election.id).then((data) => dispatch({ type: "results", data })).catch(() => undefined);
  }, [state.countingPaused, election]);

  const { isConnected } = useSSE(election?.id ?? null, {
    onUpdate: useCallback((data: DashboardData) => dispatch({ type: "results", data }), []),
    onBallot: useCallback((event: LiveBallotEvent) => dispatch({ type: "ballot", event }), []),
    onPaused: useCallback(() => dispatch({ type: "paused" }), []),
    resyncKey,
  });

  // one-second heartbeat drives the countdown; it starts afresh with every ballot,
  // so each one gets its whole first second
  const onStage = state.current ? `${state.current.ballot_id}-${state.current.kind}-${state.lastBallotAt?.getTime() ?? 0}` : "";
  useEffect(() => {
    const timer = setInterval(() => dispatch({ type: "tick" }), 1000);
    return () => clearInterval(timer);
  }, [onStage]);

  const results = state.results;
  const control = election && (
    <CountingControl
      electionId={election.id}
      paused={state.countingPaused}
      onChanged={(paused) => dispatch({ type: "counting", paused })}
    />
  );

  if (error) return <HoldScreen title="ICB Officers' Association" subtitle="আইসিবি কর্মকর্তা সমিতি" message={error} />;
  if (!results) return <HoldScreen title="ICB Officers' Association" subtitle="আইসিবি কর্মকর্তা সমিতি" message="Connecting to the counting system…" spinner />;
  if (!results.results_visible) {
    return (
      <HoldScreen
        title={results.election_title}
        subtitle={results.election_title_bn}
        message={state.countingPaused
          ? "Counting is paused by the election commission. It will start again shortly."
          : "Counting is in progress. Results will be published by the election committee."}
        stats={results}
        control={control}
      />
    );
  }

  // after Publish the count is replayed from the first ballot; "final" waits for it to finish
  const replay = results.replay ?? null;
  const final = results.election_status === "completed" && !replay;

  return (
    <div className={`live live-summary ${final ? "is-final" : ""} ${state.countingPaused ? "is-count-paused" : ""}`}>
      <LiveHeader results={results} connected={isConnected} paused={state.paused} countingPaused={state.countingPaused} final={final} replay={replay} control={control} />
      <ResultsBoard positions={results.positions} current={state.current} active={!state.idle} final={final} />
      <LiveFooter results={results} lastBallotAt={state.lastBallotAt} queued={state.queue.length} replay={replay} />
      {state.countingPaused && !final && (
        <div className="live-count-paused" role="status">
          <span className="live-count-paused-icon"><Icon name="pause" size={30} strokeWidth={2.4} /></span>
          <div>
            <strong className="text-bengali">ভোট গণনা সাময়িকভাবে স্থগিত</strong>
            <span>Counting paused by the election commission · it will start again shortly</span>
          </div>
        </div>
      )}
      {state.paused && !state.countingPaused && (
        <div className="live-pause-banner">
          <Icon name="pause" size={16} /> Live updates paused by the election committee
        </div>
      )}
      {final && <Confetti />}
    </div>
  );
}

/* ------------------------------------------------------------ header */

function LiveHeader({ results, connected, paused, countingPaused, final, replay, control }: {
  results: DashboardData; connected: boolean; paused: boolean; countingPaused: boolean; final: boolean;
  replay: ReplayProgress | null; control: ReactNode;
}) {
  const clock = useClock();
  const [fullscreen, setFullscreen] = useState(false);

  useEffect(() => {
    const onChange = () => setFullscreen(Boolean(document.fullscreenElement));
    document.addEventListener("fullscreenchange", onChange);
    return () => document.removeEventListener("fullscreenchange", onChange);
  }, []);

  const toggleFullscreen = () => {
    if (document.fullscreenElement) document.exitFullscreen().catch(() => undefined);
    else document.documentElement.requestFullscreen().catch(() => undefined);
  };

  const { stats } = results;
  return (
    <header className="live-header">
      <div className="live-brand">
        <Logo size={76} halo />
        <div style={{ minWidth: 0 }}>
          <div className="live-org">ICB Officers&apos; Association <span className="text-bengali">· আইসিবি কর্মকর্তা সমিতি</span></div>
          {results.election_title_bn ? (
            <>
              <h1 className="live-title live-title-main text-bengali"><span className="text-gold">{results.election_title_bn}</span></h1>
              <div className="live-title-sub">{results.election_title}</div>
            </>
          ) : (
            <h1 className="live-title"><span className="text-gold">{results.election_title}</span></h1>
          )}
        </div>
      </div>

      <div className="live-header-right">
        <div className="live-kpi">
          <AnimatedNumber value={stats.counted_ballots} className="live-kpi-value" />
          <div className="live-kpi-label">Ballots counted</div>
        </div>
        <div className="live-kpi live-kpi-ring">
          <RingGauge value={stats.turnout_percentage} size={84} stroke={8}>
            <AnimatedNumber value={stats.turnout_percentage} suffix="%" className="live-ring-value" />
          </RingGauge>
          <div className="live-kpi-label">Turnout of {stats.total_voters}</div>
        </div>
        <div className="live-status">
          {final ? (
            <span className="live-indicator live-final"><Icon name="crown" size={14} strokeWidth={2.2} />FINAL RESULT</span>
          ) : paused || countingPaused ? (
            <span className="live-indicator live-paused"><span className="live-dot" />PAUSED</span>
          ) : replay ? (
            <span className="live-indicator live-final" title="The count is shown from the first ballot">
              <span className="live-dot live-dot-gold" />COUNTING {replay.position > 0 ? `${replay.position} / ${replay.total}` : ""}
            </span>
          ) : connected ? (
            <span className="live-indicator"><span className="live-dot" />LIVE</span>
          ) : (
            <span className="live-indicator live-offline"><span className="live-dot" />RECONNECTING</span>
          )}
          <div className="live-clock">{clock}</div>
          <div className="live-controls">
            {!final && control}
            <ThemeToggle compact />
            {!fullscreen && (
              <>
                <button className="live-fullscreen" onClick={toggleFullscreen} title="Full screen"><Icon name="maximize" size={13} /> Full screen</button>
                <Link href="/admin/login" className="live-fullscreen" title="Election committee login"><Icon name="key" size={13} /> Admin</Link>
              </>
            )}
          </div>
        </div>
      </div>
    </header>
  );
}

/* ------------------------------------------------ standings summary */

function ResultsBoard({ positions, current, active, final }: { positions: PositionResult[]; current: LiveBallotEvent | null; active: boolean; final: boolean }) {
  const justVoted = useMemo(
    // only a newly counted ballot adds +1; a re-read or correction replaces earlier votes
    () => new Set(active && current?.kind === "counted" ? current.votes.filter((v) => v.is_valid).map((v) => v.candidate_id) : []),
    [current, active],
  );
  const board = useRef<HTMLElement>(null);
  useAutoScroll(board);

  return (
    <main className="live-board" ref={board} aria-label="Standings">
      {positions.map((position, index) => (
        <BoardPosition key={position.position_id} position={position} justVoted={justVoted} final={final} index={index} />
      ))}
    </main>
  );
}

function BoardPosition({ position, justVoted, final, index }: { position: PositionResult; justVoted: Set<number>; final: boolean; index: number }) {
  const order = position.candidates.map((c) => c.candidate_id).join(",");
  const flipRef = useFlip<HTMLDivElement>(order);
  const maxVotes = Math.max(1, ...position.candidates.map((c) => c.vote_count));
  const touched = position.candidates.some((c) => justVoted.has(c.candidate_id));

  return (
    <div className={`live-position ${position.candidates.length > 3 ? "is-tall" : ""} ${touched ? "is-touched" : ""}`} style={{ animationDelay: `${Math.min(index * 45, 600)}ms` }}>
      <div className="live-position-head">
        <span className="live-position-no">{String(position.position_order).padStart(2, "0")}</span>
        <div className="live-position-names">
          {position.name_bn && <div className="text-bengali live-position-bn">{position.name_bn}</div>}
          <div className="live-position-en">{position.name_en}{position.max_selections > 1 ? ` · elect ${position.max_selections}` : ""}</div>
        </div>
        <span className="live-position-total" title="Votes cast for this post">{position.total_votes_cast}</span>
      </div>
      <div className="live-candidates" ref={flipRef}>
        {position.candidates.map((c) => {
          const width = Math.max((c.vote_count / maxVotes) * 100, 2);
          const hit = justVoted.has(c.candidate_id);
          const crowned = c.is_leading && (final || c.rank === 1);
          return (
            <div key={c.candidate_id} data-flip={c.candidate_id} className={`live-candidate ${c.is_leading ? "is-leading" : ""} ${hit ? "is-hit" : ""}`}>
              <span className="live-rank">
                {crowned && <Icon name="crown" size={12} strokeWidth={2.2} className="live-crown" />}
                {c.rank}
              </span>
              <div className="live-candidate-body">
                <div className="live-candidate-name">
                  <span className="live-vote-no">{c.voter_no}</span>
                  <span className={`live-candidate-text ${c.name_bn ? "text-bengali" : ""}`}>{c.name_bn ?? c.name_en}</span>
                  {hit && <span className="live-plus">+1</span>}
                  {final && c.is_leading && <span className="live-elected">Elected</span>}
                </div>
                <div className="live-bar"><div className="live-bar-fill" style={{ width: `${width}%` }} /></div>
              </div>
              <div className="live-count">
                <AnimatedNumber value={c.vote_count} className="live-count-value" />
                <div className="live-count-pct">{c.percentage}%</div>
              </div>
              {hit && <span className="live-sparks" aria-hidden="true"><i /><i /><i /><i /><i /><i /></span>}
            </div>
          );
        })}
      </div>
    </div>
  );
}

/** When there is more than fits, glide the list down (and, unless `once`, back up) slowly. */
function useAutoScroll(
  ref: React.RefObject<HTMLElement | null>,
  resetKey: string = "",
  { pause = 4000, speed = 0.025, once = false }: { pause?: number; speed?: number; once?: boolean } = {},
) {
  useEffect(() => {
    const el = ref.current;
    if (!el || prefersReducedMotion()) return;
    el.scrollTop = 0;
    let direction = 1;
    let pauseUntil = performance.now() + pause;
    let frame = 0;
    let last = performance.now();
    let hovered = false;
    const enter = () => { hovered = true; };
    const leave = () => { hovered = false; };
    el.addEventListener("mouseenter", enter);
    el.addEventListener("mouseleave", leave);
    const step = (now: number) => {
      const dt = now - last;
      last = now;
      const room = el.scrollHeight - el.clientHeight;
      if (room > 4 && !hovered && now > pauseUntil) {
        el.scrollTop += direction * dt * speed;  // 0.025 = ~25 px per second
        if (direction > 0 && el.scrollTop >= room - 1) {
          if (once) { cancelAnimationFrame(frame); return; }  // stay on the last votes
          direction = -1; pauseUntil = now + 4000;
        }
        else if (direction < 0 && el.scrollTop <= 0) { direction = 1; pauseUntil = now + 6000; }
      }
      frame = requestAnimationFrame(step);
    };
    frame = requestAnimationFrame(step);
    return () => {
      cancelAnimationFrame(frame);
      el.removeEventListener("mouseenter", enter);
      el.removeEventListener("mouseleave", leave);
    };
  }, [ref, resetKey, pause, speed, once]);
}

/* ------------------------------------------------------------ footer */

function LiveFooter({ results, lastBallotAt, queued, replay }: {
  results: DashboardData; lastBallotAt: Date | null; queued: number; replay: ReplayProgress | null;
}) {
  const { stats } = results;
  return (
    <footer className="live-footer">
      <div className="live-footer-stats">
        <span><Icon name="vote" size={16} /><AnimatedNumber value={stats.counted_ballots} className="live-footer-num" /> counted</span>
        <span><Icon name="alert" size={16} /><AnimatedNumber value={stats.needs_review_ballots} className="live-footer-num" /> under review</span>
        <span><Icon name="clock" size={16} /><AnimatedNumber value={Math.max(0, stats.total_voters - stats.counted_ballots)} className="live-footer-num" /> remaining of {stats.total_voters}</span>
        {queued > 0 && <span><Icon name="inbox" size={16} /><strong className="live-footer-num">{queued}</strong> in queue</span>}
      </div>
      <div className="live-turnout">
        <div className="live-turnout-bar"><div style={{ width: `${Math.min(100, stats.turnout_percentage)}%` }} /></div>
        <span><strong>{stats.turnout_percentage}%</strong> turnout</span>
      </div>
      <div className="text-muted live-footer-note" title={CREDIT}>
        {replay
          ? (replay.position > 0 ? `Counting from the first ballot · ${replay.position} of ${replay.total}` : "Counting from the first ballot")
          : lastBallotAt ? `Last ballot ${lastBallotAt.toLocaleTimeString()}` : "Awaiting first ballot"}
        {" · "}<span className="live-credit">{CREDIT}</span>
      </div>
    </footer>
  );
}

/* ---------------------------------------------------------- helpers */

/** One-off gold confetti shower for the final result. */
function Confetti() {
  const pieces = useMemo(() => Array.from({ length: 90 }, (_, i) => ({
    left: (i * 37) % 100,
    delay: ((i * 53) % 40) / 10,
    duration: 4 + ((i * 29) % 30) / 10,
    rotate: (i * 71) % 360,
    hue: i % 3,
  })), []);
  return (
    <div className="confetti" aria-hidden="true">
      {pieces.map((p, i) => (
        <i key={i} className={`c${p.hue}`} style={{ left: `${p.left}%`, animationDelay: `${p.delay}s`, animationDuration: `${p.duration}s`, rotate: `${p.rotate}deg` }} />
      ))}
    </div>
  );
}

function HoldScreen({ title, subtitle, message, spinner, stats, control }: {
  title: string; subtitle?: string | null; message: string; spinner?: boolean; stats?: DashboardData; control?: ReactNode;
}) {
  const clock = useClock();
  return (
    <div className="live live-hold">
      <div className="live-hold-controls">
        {control}
        <ThemeToggle compact />
        <Link href="/admin/login" className="live-fullscreen" title="Election committee login"><Icon name="key" size={13} /> Admin</Link>
      </div>
      <div className="live-hold-card">
        <div className="medallion-stage live-hold-stage">
          <span className="orbit" /><span className="orbit orbit-2" /><span className="orbit orbit-3" />
          <Logo size={196} halo />
        </div>
        <div className="live-org" style={{ marginTop: 34 }}>ICB Officers&apos; Association <span className="text-bengali">· আইসিবি কর্মকর্তা সমিতি</span></div>
        <h1 className="live-hold-title"><span className="text-gold">{title}</span></h1>
        {subtitle && <div className="live-title-bn text-bengali" style={{ fontSize: "1.6rem" }}>{subtitle}</div>}
        <p className="live-hold-message">{message}</p>
        {spinner && <div className="spinner" style={{ margin: "24px auto 0" }} />}
        {stats && (
          <div className="live-hold-stats">
            <div><AnimatedNumber value={stats.stats.counted_ballots} className="live-hold-num" /><span>ballots counted</span></div>
            <div className="live-hold-sep" />
            <div><AnimatedNumber value={stats.stats.turnout_percentage} suffix="%" className="live-hold-num" /><span>turnout of {stats.stats.total_voters}</span></div>
          </div>
        )}
        <div className="live-clock" style={{ marginTop: 30 }}>{clock}</div>
        <div className="live-hold-credit">Designed and developed by <strong>Taufiqul Islam</strong></div>
      </div>
    </div>
  );
}
