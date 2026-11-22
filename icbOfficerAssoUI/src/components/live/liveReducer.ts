import type { DashboardData, LiveBallotEvent } from "@/lib/types";

/**
 * Playback state of the public live screen.
 *
 * Every counted ballot arrives as an event that carries the totals *after*
 * that ballot.  Events are queued and shown one at a time for
 * `display_seconds`; the totals on screen always match the ballot being
 * shown, so the audience sees the sum grow one ballot at a time.
 *
 * Every ballot gets its WHOLE time on stage (scan, close-up, totals): `shown`
 * turns true only when its countdown has run out, and the next ballot in the
 * queue is taken only then.  Nothing cuts a ballot short, not a long queue and
 * not the start of the replay; the finished ballot stays on stage until the
 * next one arrives.
 *
 * The screen shows the summary only (scanning is internal): the totals of a
 * ballot land the moment it takes its turn, and stay for its hold (2 seconds
 * by default) before the next ballot's totals replace them.
 *
 * After Publish the server replays the count from the first ballot, paced
 * one ballot per `display_seconds` (events carry `replay`).  When it starts,
 * ballots still waiting in the queue are dropped (the replay shows them all
 * again); only the committee's "skip" ends a ballot early.
 */
export interface LiveState {
  results: DashboardData | null;
  queue: LiveBallotEvent[];
  current: LiveBallotEvent | null;
  remaining: number;      // seconds left for the current ballot
  holdTotal: number;      // seconds the current ballot is shown in total
  idle: boolean;          // countdown finished, waiting for the next ballot
  shown: boolean;         // the ballot on stage has had its whole time (scan + close-up + totals)
  pending: DashboardData | null;  // latest totals received while a ballot is shown
  staged: DashboardData | null;   // totals of the ballot on stage, applied when it has been read
  paused: boolean;
  countingPaused: boolean;  // PAUSE pressed: the ballot on stage stays, its countdown stops
  lastBallotAt: Date | null;
}

export type LiveAction =
  | { type: "results"; data: DashboardData }
  | { type: "ballot"; event: LiveBallotEvent }
  | { type: "latest"; event: LiveBallotEvent }
  | { type: "tick" }
  | { type: "paused" }
  | { type: "counting"; paused: boolean };

/** Share of the hold after which totals that were kept back are applied. */
export const TOUR_END = 0.78;

/** True once the ballot on stage has been read through (its totals are due). */
function readThrough(holdTotal: number, remaining: number): boolean {
  return holdTotal <= 0 || (holdTotal - remaining) / holdTotal >= TOUR_END;
}

export const initialLiveState: LiveState = {
  results: null, queue: [], current: null, remaining: 0, holdTotal: 0,
  idle: true, shown: false, pending: null, staged: null, paused: false, countingPaused: false, lastBallotAt: null,
};

function show(state: LiveState, event: LiveBallotEvent, queue: LiveBallotEvent[]): LiveState {
  const hold = Math.max(1, event.display_seconds || 2);
  // summary screen: the ballot itself is not shown, so its totals land at once and then
  // stay for `hold` seconds before the next ballot's totals replace them
  return {
    ...state, queue, current: event, results: event.results, staged: null,
    remaining: hold, holdTotal: hold, idle: false, shown: false, pending: null, paused: false, lastBallotAt: new Date(),
  };
}

export function liveReducer(state: LiveState, action: LiveAction): LiveState {
  switch (action.type) {
    case "results": {
      const countingPaused = Boolean(action.data.counting_paused);
      if (countingPaused !== state.countingPaused) state = { ...state, countingPaused };
      if (state.current?.replay && !state.idle && !action.data.replay) {
        // the replay is over on the server.  When this screen is on (or still has in its queue)
        // the replay's last ballot it simply ended: that ballot keeps its time.  Otherwise the
        // committee skipped it: straight to the real totals.
        const last = state.queue.length > 0 ? state.queue[state.queue.length - 1] : state.current;
        const ended = Boolean(last.replay && last.replay.position >= last.replay.total);
        if (!ended) {
          return { ...state, results: action.data, queue: [], idle: true, shown: true, remaining: 0, pending: null, staged: null, paused: false };
        }
      }
      if (state.current && !state.idle) return { ...state, pending: action.data, paused: false };
      return { ...state, results: action.data, paused: false };
    }

    case "ballot": {
      // the replay that follows Publish starts now: it shows every ballot again, so the
      // ones still waiting are dropped; the ballot on stage finishes first
      const before = state.queue.length > 0 ? state.queue[state.queue.length - 1] : state.current;
      const replayStarts = action.event.replay && (action.event.replay.position === 1 || !before?.replay);
      const queue = replayStarts ? [action.event] : [...state.queue, action.event];
      // a ballot nobody can see (the board is hidden while results are unpublished) has nothing to finish
      const onScreen = Boolean(state.results?.results_visible);
      if (state.current && !state.shown && !state.idle && onScreen) return { ...state, queue, paused: false };
      const [next, ...rest] = queue;
      return show(state, next, rest);
    }

    case "latest":
      // a screen opened mid-count shows the last ballot (already counted) instead of a blank stage;
      // its totals are older than the ones just loaded, so they are not applied
      if (state.current) return state;
      return { ...state, current: action.event, remaining: 0, holdTotal: 0, idle: true, shown: true };

    case "tick": {
      if (!state.current || state.idle || state.countingPaused) return state;
      if (state.remaining > 1) {
        const remaining = state.remaining - 1;
        if (state.staged && readThrough(state.holdTotal, remaining)) {
          return { ...state, remaining, results: state.staged, staged: null };
        }
        return { ...state, remaining };
      }
      if (state.queue.length > 0) {
        const [next, ...rest] = state.queue;
        return show(state, next, rest);
      }
      // fully shown: it stays on stage as the last counted ballot until the next one arrives
      return { ...state, remaining: 0, idle: true, shown: true, results: state.pending ?? state.staged ?? state.results, pending: null, staged: null };
    }

    case "paused":
      return { ...state, paused: true };

    case "counting":
      return { ...state, countingPaused: action.paused };

    default:
      return state;
  }
}
