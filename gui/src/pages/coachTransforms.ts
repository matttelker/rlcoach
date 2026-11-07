import type { CategorySummary, GradeRequest, ReplayReview, ReviewMistake, RuleGrades } from '../types/api';
import { parseLocalDate } from './dataTransforms';

export const PERIOD_OPTIONS = [
  { value: '7d', label: 'Last 7 days' },
  { value: '30d', label: 'Last 30 days' },
  { value: '90d', label: 'Last 90 days' },
  { value: 'all', label: 'All time' },
];

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
