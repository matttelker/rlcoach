import type {
  CategorySummary,
  FlipTiming,
  GradeRequest,
  KickoffResult,
  LadderStatus,
  LadderStep,
  ReplayReview,
  ReviewKickoff,
  ReviewMistake,
  RuleGrades,
} from '../types/api';
import { parseLocalDate } from './dataTransforms';

export const PERIOD_OPTIONS = [
  { value: '7d', label: 'Last 7 days' },
  { value: '30d', label: 'Last 30 days' },
  { value: '90d', label: 'Last 90 days' },
  { value: 'all', label: 'All time' },
];

// The Coach page can also show Doubles and Standard together
export const COACH_PLAYLISTS = [
  { value: 'STANDARD', label: 'Standard' },
  { value: 'DOUBLES', label: 'Doubles' },
  { value: 'DOUBLES,STANDARD', label: 'Doubles and Standard' },
  { value: 'DUEL', label: 'Duel' },
];

export function isMixedPlaylist(playlist: string): boolean {
  return playlist.includes(',');
}

const TEAM_SIZES: Record<string, string> = { DUEL: '1v1', DOUBLES: '2v2', STANDARD: '3v3' };

export function teamSizeLabel(playlist: string): string {
  return TEAM_SIZES[playlist] ?? playlist;
}

export const REGULATION_SECONDS = 300;

// Map names arrive as internal ids like "UtopiaStadium_Dusk_P".
export function prettyMap(name: string): string {
  return name
    .replace(/_P$/, '')
    .replace(/_/g, ' ')
    .replace(/([a-z])([A-Z])/g, '$1 $2');
}

function localIsoDate(date: Date): string {
  const y = date.getFullYear();
  const m = String(date.getMonth() + 1).padStart(2, '0');
  const d = String(date.getDate()).padStart(2, '0');
  return `${y}-${m}-${d}`;
}

export function sessionTitle(playDate: string, now: Date = new Date()): string {
  if (playDate === localIsoDate(now)) return 'Today';
  const yesterday = new Date(now);
  yesterday.setDate(now.getDate() - 1);
  if (playDate === localIsoDate(yesterday)) return 'Yesterday';
  return parseLocalDate(playDate).toLocaleDateString(undefined, {
    weekday: 'long',
    month: 'short',
    day: 'numeric',
  });
}

export function formatRate(value: number | null): string {
  if (value === null) return '–';
  return value === 0 ? '0' : value.toFixed(1);
}

export type Trend = 'worse' | 'better' | 'same' | 'new';

// Fewer flags per game is better. Small wobbles read as "same".
export function categoryTrend(category: CategorySummary): Trend {
  const { before_per_game: before, latest_per_game: latest } = category;
  if (before === null || latest === null) return 'new';
  if (latest - before >= 0.2) return 'worse';
  if (before - latest >= 0.2) return 'better';
  return 'same';
}

export function kindLabel(kind: string): string {
  const text = kind.replace(/_/g, ' ');
  return text.charAt(0).toUpperCase() + text.slice(1);
}

export function headline(target: CategorySummary): string {
  const games = `${target.games} game${target.games === 1 ? '' : 's'}`;
  if (target.goals_cost > 0) {
    const goals = `${target.goals_cost} goal${target.goals_cost === 1 ? '' : 's'}`;
    return `Cost you ${goals} in ${games}`;
  }
  return `${target.flags} flagged in ${games}`;
}

export function groupByCategory(mistakes: ReviewMistake[]) {
  const groups = new Map<string, { label: string; items: ReviewMistake[]; goals: number }>();
  for (const m of mistakes) {
    const group = groups.get(m.category) ?? { label: m.category_label, items: [], goals: 0 };
    group.items.push(m);
    if (m.cost_goal) group.goals += 1;
    groups.set(m.category, group);
  }
  // Groups that cost goals first, then the bigger ones
  return [...groups.entries()]
    .map(([category, group]) => ({ category, ...group }))
    .sort((a, b) => b.goals - a.goals || b.items.length - a.items.length);
}

// The review with one call's grade set, before the server answers
export function applyGrade(review: ReplayReview, request: GradeRequest): ReplayReview {
  if (request.item === 'mistake') {
    return {
      ...review,
      mistakes: review.mistakes.map((m) =>
        m.kind === request.kind && m.t === request.t ? { ...m, grade: request.grade } : m,
      ),
    };
  }
  return {
    ...review,
    goals: review.goals.map((g) => (!g.ours && g.t === request.t ? { ...g, grade: request.grade } : g)),
  };
}

// Share of graded calls you marked right, as a whole percent
export function gradeAccuracy(rule: RuleGrades): number | null {
  const total = rule.right + rule.wrong;
  return total === 0 ? null : Math.round((100 * rule.right) / total);
}

// Position on a 5:00 → 0:00 axis that stretches to fit any overtime.
export function timelineX(secondsLeft: number, overtimeSeconds: number, width: number): number {
  const total = REGULATION_SECONDS + overtimeSeconds;
  const elapsed = REGULATION_SECONDS - secondsLeft;
  return Math.min(Math.max(elapsed / total, 0), 1) * width;
}

// Kickoffs

const APPROACHES: Record<string, string> = {
  SPEEDFLIP: 'Speedflip',
  STANDARD_FRONTFLIP: 'Front flip',
  STANDARD_DIAGONAL: 'Diagonal flip',
  STANDARD_BOOST: 'Boosted in',
  STANDARD: 'Drove in',
  FAKE_HALFFLIP: 'Faked, half-flip',
  FAKE_STATIONARY: 'Faked, stayed put',
  FAKE_AGGRESSIVE: 'Faked, drove off',
  SUPPORT_CHEAT: 'Cheated up',
  SUPPORT_HOLD: 'Held back',
  UNKNOWN: "Didn't move",
};

export function approachLabel(approach: string): string {
  return APPROACHES[approach] ?? kindLabel(approach.toLowerCase());
}

const SPOTS: Record<string, string> = { DIAGONAL: 'diagonal', OFF_CENTRE: 'off-centre', BACK: 'back' };

/** "You went from the diagonal" or "Support from the back" */
export function kickoffSeat(kickoff: Pick<ReviewKickoff, 'role' | 'spot'>): string {
  const spot = kickoff.spot ? SPOTS[kickoff.spot] ?? kickoff.spot.toLowerCase() : null;
  const from = spot ? ` from the ${spot}` : '';
  return kickoff.role === 'GO' ? `You went${from}` : `Support${from}`;
}

export function flipText(flip: FlipTiming | null, lead: number | null): string {
  if (flip === 'ON_TIME') return lead === null ? 'Flip on time' : `Flip on time, ${lead.toFixed(2)} s before contact`;
  if (flip === 'LATE') return lead === null ? 'Flip late' : `Flip late, ${(-lead).toFixed(2)} s after contact`;
  if (flip === 'NONE') return 'No flip into the ball';
  return '';
}

export const RESULT_LABELS: Record<KickoffResult, string> = {
  WON: 'Went your way',
  EVEN: 'Even',
  LOST: 'Came back at you',
};

export function goalAfterText(kickoff: Pick<ReviewKickoff, 'goal_after' | 'goal_after_s'>): string {
  if (!kickoff.goal_after) return '';
  const when = kickoff.goal_after_s === null ? '' : ` ${Math.round(kickoff.goal_after_s)} s later`;
  return kickoff.goal_after === 'for' ? `Your team scored${when}` : `They scored${when}`;
}

/** A share of 0 to 1 as a whole percent, or a dash */
export function percent(value: number | null): string {
  return value === null ? '–' : `${Math.round(value * 100)}%`;
}

/** Whole percent of a count, or a dash when there's nothing to divide */
export function shareOf(part: number, whole: number): string {
  return whole === 0 ? '–' : `${Math.round((100 * part) / whole)}%`;
}

export const STEP_STATUS: Record<LadderStatus, string> = {
  solid: 'Solid',
  focus: 'Work on this now',
  later: 'Later',
  unknown: 'Not enough kickoffs yet',
};

/** The step to work on: the focus, or nothing when every judged step is solid. */
export function focusStep(ladder: LadderStep[]): LadderStep | undefined {
  return ladder.find((step) => step.status === 'focus');
}
