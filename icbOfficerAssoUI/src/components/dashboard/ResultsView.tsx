"use client";

import type { CandidateResult, DashboardStats, PositionResult } from "@/lib/types";
import { Icon, type IconName } from "@/components/ui/Icon";
import { AnimatedNumber, useFlip } from "@/components/ui/Motion";

type Tone = "primary" | "gold" | "success" | "warning" | "muted" | "error";

export function StatCard({ value, label, icon, tone = "primary", suffix, foot, progress, delay = 0 }: {
  value: number; label: string; icon: IconName; tone?: Tone; suffix?: string; foot?: string; progress?: number; delay?: number;
}) {
  return (
    <div className={`stat-card tone-${tone}`} style={{ animationDelay: `${delay}ms` }}>
      <div className="stat-top">
        <span className="stat-label">{label}</span>
        <span className="stat-icon"><Icon name={icon} size={19} /></span>
      </div>
      <AnimatedNumber value={value} suffix={suffix} className="stat-value" />
      {progress !== undefined && <div className="stat-bar"><span style={{ width: `${Math.min(100, progress)}%` }} /></div>}
      {foot && <span className="stat-foot">{foot}</span>}
    </div>
  );
}

export function StatsGrid({ stats, compact }: { stats: DashboardStats; compact?: boolean }) {
  const remaining = Math.max(0, stats.total_voters - stats.counted_ballots);
  return (
    <div className="stats-grid">
      <StatCard value={stats.counted_ballots} label="Ballots counted" icon="vote" tone="primary" foot={`${stats.total_ballots} scanned in total`} delay={0} />
      <StatCard value={stats.total_voters} label="Total voters" icon="users" tone="muted" foot={`${remaining} yet to be counted`} delay={70} />
      <StatCard value={stats.turnout_percentage} suffix="%" label="Turnout" icon="target" tone="gold" progress={stats.turnout_percentage} delay={140} />
      {compact ? (
        <StatCard value={stats.needs_review_ballots} label="Needs review" icon="alert" tone="warning" foot={`${stats.reviewed_ballots} reviewed so far`} delay={210} />
      ) : (
        <StatCard value={stats.pending_ballots + stats.needs_review_ballots} label="Pending / review" icon="clock" tone="warning" delay={210} />
      )}
    </div>
  );
}

function CandidateRow({ candidate, maxVotes, showBengali, crowned }: { candidate: CandidateResult; maxVotes: number; showBengali: boolean; crowned: boolean }) {
  const width = maxVotes > 0 ? (candidate.vote_count / maxVotes) * 100 : 0;
  const primary = showBengali && candidate.name_bn ? candidate.name_bn : candidate.name_en;
  const secondary = showBengali && candidate.name_bn ? candidate.name_en : candidate.name_bn;
  return (
    <div className={`candidate-row ${candidate.is_leading ? "is-leading" : ""}`} data-flip={candidate.candidate_id}>
      <span className={`candidate-rank ${candidate.is_leading ? "rank-leading" : ""}`}>
        {crowned && <Icon name="crown" size={14} className="rank-crown" strokeWidth={2} />}
        {candidate.rank}
      </span>
      <div className="candidate-info">
        <div className="candidate-name">
          <span className="chip-no">{candidate.voter_no}</span>
          <span className={showBengali && candidate.name_bn ? "text-bengali" : ""}>{primary}</span>
        </div>
        {secondary && <div className={`candidate-voter-no ${showBengali ? "" : "text-bengali"}`}>{secondary}</div>}
        <div className="vote-bar-container">
          <div className={`vote-bar ${candidate.is_leading ? "vote-bar-leading" : "vote-bar-trailing"}`} style={{ width: `${Math.max(width, 1.5)}%` }} />
        </div>
      </div>
      <div className="candidate-votes">
        <AnimatedNumber value={candidate.vote_count} className="candidate-vote-count" />
        <div className="candidate-percentage">{candidate.percentage}%</div>
      </div>
    </div>
  );
}

export function PositionCard({ position, maxVotes, delay = 0, showBengali = true }: {
  position: PositionResult; maxVotes: number; delay?: number; showBengali?: boolean;
}) {
  const order = position.candidates.map((c) => c.candidate_id).join(",");
  const flipRef = useFlip<HTMLDivElement>(order);
  const wide = position.candidates.length > 4;
  return (
    <div className={`position-card ${wide ? "is-wide" : ""}`} style={{ animationDelay: `${delay}ms` }}>
      <div className="position-header">
        <div className="flex items-center gap-3">
          <span className="position-number">{String(position.position_order).padStart(2, "0")}</span>
          <div>
            <div className="position-title">{position.name_en}</div>
            {position.name_bn && <div className="position-title-bn">{position.name_bn}</div>}
          </div>
        </div>
        {position.max_selections > 1 && <span className="badge badge-accent"><Icon name="users" />Elect {position.max_selections}</span>}
      </div>
      <div className="position-candidates" ref={flipRef} style={{ position: "relative" }}>
        {position.candidates.map((candidate) => (
          <CandidateRow key={candidate.candidate_id} candidate={candidate} maxVotes={maxVotes} showBengali={showBengali}
            crowned={candidate.is_leading && candidate.rank === 1} />
        ))}
        {position.candidates.length === 0 && <div className="empty-inline"><Icon name="users" size={26} />No candidates.</div>}
      </div>
      <div className="position-foot">
        <span>{position.candidates.length} candidate{position.candidates.length === 1 ? "" : "s"}</span>
        <span>Total votes cast: <strong style={{ color: "var(--color-text-primary)" }}>{position.total_votes_cast}</strong></span>
      </div>
    </div>
  );
}

export function PositionsGrid({ positions, showBengali = true }: { positions: PositionResult[]; showBengali?: boolean }) {
  return (
    <div className="positions-grid">
      {positions.map((position, index) => {
        // bars are scaled per position so every race reads clearly on its own
        const maxVotes = Math.max(1, ...position.candidates.map((c) => c.vote_count));
        return <PositionCard key={position.position_id} position={position} maxVotes={maxVotes} delay={Math.min(index * 50, 500)} showBengali={showBengali} />;
      })}
    </div>
  );
}
