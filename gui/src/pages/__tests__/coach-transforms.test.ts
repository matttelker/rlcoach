import { describe, expect, it } from 'vitest';

import type { CategorySummary, ReplayReview, ReviewMistake } from '../../types/api';
import {
  applyGrade,
  categoryTrend,
  gradeAccuracy,
  groupByCategory,
  headline,
  prettyMap,
  sessionTitle,
  timelineX,
} from '../coachTransforms';

const category = (before: number | null, latest: number | null): CategorySummary => ({
  category: 'rotation',
  label: 'Rotation',
  flags: 5,
  goals_cost: 0,
  games: 10,
  per_game: 0.5,
  latest_per_game: latest,
  before_per_game: before,
  sessions: [],
  kinds: {},
  top_kind: null,
  cue: null,
  clean_streak: 0,
});

const mistake = (category: string, cost_goal: boolean): ReviewMistake => ({
  kind: 'k',
  label: 'K',
  category,
  category_label: category,
  t: 1,
  seconds_left: 1,
  clock: '0:01',
  score: '0-0',
  duration: 0,
  what: '',
  instead: '',
  outcome: '',
  cost_goal,
  grade: null,
});

describe('categoryTrend', () => {
  it('calls more flags per game worse and fewer better', () => {
    expect(categoryTrend(category(0.3, 1.0))).toBe('worse');
    expect(categoryTrend(category(1.3, 0.5))).toBe('better');
    expect(categoryTrend(category(0.4, 0.5))).toBe('same');
  });

  it('has no trend with only one session', () => {
    expect(categoryTrend(category(null, 0.5))).toBe('new');
  });
});

describe('headline', () => {
  it('leads with goals when the habit cost any', () => {
    expect(headline({ ...category(0, 0), goals_cost: 1, games: 1 })).toBe('Cost you 1 goal in 1 game');
    expect(headline(category(0, 0))).toBe('5 flagged in 10 games');
  });
});

describe('groupByCategory', () => {
  it('puts the categories that cost goals first', () => {
    const groups = groupByCategory([
      mistake('clearing', false),
      mistake('clearing', false),
      mistake('last_back', true),
    ]);
    expect(groups.map((g) => g.category)).toEqual(['last_back', 'clearing']);
    expect(groups[0].goals).toBe(1);
  });
});

describe('grades', () => {
  const review: ReplayReview = {
    replay_id: 'abc',
    status: 'ok',
    error: null,
    clears: 0,
    clears_given_back: 0,
    mistakes: [mistake('clearing', false), { ...mistake('clearing', false), t: 2 }],
    goals: [],
  };

  it('sets the grade on the one call you pressed', () => {
    const graded = applyGrade(review, { item: 'mistake', kind: 'k', t: 2, grade: 'wrong' });
    expect(graded.mistakes.map((m) => m.grade)).toEqual([null, 'wrong']);
    expect(review.mistakes[1].grade).toBeNull();
  });

  it('turns a tally into a right percentage', () => {
    const rule = { item: 'mistake' as const, kind: 'k', label: 'K' };
    expect(gradeAccuracy({ ...rule, right: 1, wrong: 2 })).toBe(33);
    expect(gradeAccuracy({ ...rule, right: 0, wrong: 0 })).toBeNull();
  });
});

describe('timelineX', () => {
  it('runs from kickoff at 5:00 to the end of regulation', () => {
    expect(timelineX(300, 0, 1000)).toBe(0);
    expect(timelineX(150, 0, 1000)).toBe(500);
    expect(timelineX(0, 0, 1000)).toBe(1000);
  });

  it('makes room for overtime', () => {
    expect(timelineX(0, 100, 800)).toBe(600);
    expect(timelineX(-100, 100, 800)).toBe(800);
  });
});

describe('labels', () => {
  it('reads map ids as names', () => {
    expect(prettyMap('UtopiaStadium_Dusk_P')).toBe('Utopia Stadium Dusk');
    expect(prettyMap('Stadium_P')).toBe('Stadium');
  });

  it('names recent sessions by day', () => {
    const now = new Date(2026, 10, 5, 21, 0);
    expect(sessionTitle('2026-11-05', now)).toBe('Today');
    expect(sessionTitle('2026-11-04', now)).toBe('Yesterday');
    expect(sessionTitle('2026-10-31', now)).toContain('Oct');
  });
});
