import { describe, expect, it } from 'vitest';

import type { CategorySummary, LadderStep, ReplayReview, ReviewMistake } from '../../types/api';
import {
  applyGrade,
  approachLabel,
  categoryTrend,
  flipText,
  focusStep,
  goalAfterText,
  gradeAccuracy,
  groupByCategory,
  headline,
  isMixedPlaylist,
  kickoffSeat,
  percent,
  prettyMap,
  sessionTitle,
  shareOf,
  teamSizeLabel,
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

  it('names modes by team size', () => {
    expect(teamSizeLabel('DOUBLES')).toBe('2v2');
    expect(teamSizeLabel('STANDARD')).toBe('3v3');
    expect(teamSizeLabel('EXTRA_MODE')).toBe('EXTRA_MODE');
  });

  it('tells a combined playlist from a single one', () => {
    expect(isMixedPlaylist('DOUBLES,STANDARD')).toBe(true);
    expect(isMixedPlaylist('DOUBLES')).toBe(false);
  });

  it('names recent sessions by day', () => {
    const now = new Date(2026, 10, 5, 21, 0);
    expect(sessionTitle('2026-11-05', now)).toBe('Today');
    expect(sessionTitle('2026-11-04', now)).toBe('Yesterday');
    expect(sessionTitle('2026-10-31', now)).toContain('Oct');
  });
});

describe('kickoff labels', () => {
  it('names each approach in words', () => {
    expect(approachLabel('SPEEDFLIP')).toBe('Speedflip');
    expect(approachLabel('STANDARD_BOOST')).toBe('Boosted in');
    expect(approachLabel('SUPPORT_CHEAT')).toBe('Cheated up');
    expect(approachLabel('SOMETHING_NEW')).toBe('Something new');
  });

  it('says whether you went or supported, and from where', () => {
    expect(kickoffSeat({ role: 'GO', spot: 'DIAGONAL' })).toBe('You went from the diagonal');
    expect(kickoffSeat({ role: 'BACK', spot: 'OFF_CENTRE' })).toBe('Support from the off-centre');
    expect(kickoffSeat({ role: 'WING', spot: null })).toBe('Support');
  });

  it('times the flip into the ball against the contact', () => {
    expect(flipText('ON_TIME', 0.12)).toBe('Flip on time, 0.12 s before contact');
    expect(flipText('LATE', -0.08)).toBe('Flip late, 0.08 s after contact');
    expect(flipText('NONE', null)).toBe('No flip into the ball');
    expect(flipText(null, null)).toBe('');
  });

  it('names the goal that followed', () => {
    expect(goalAfterText({ goal_after: 'against', goal_after_s: 4.4 })).toBe('They scored 4 s later');
    expect(goalAfterText({ goal_after: 'for', goal_after_s: 7 })).toBe('Your team scored 7 s later');
    expect(goalAfterText({ goal_after: null, goal_after_s: null })).toBe('');
  });

  it('writes shares as whole percents, with a dash for nothing', () => {
    expect(percent(0.787)).toBe('79%');
    expect(percent(null)).toBe('–');
    expect(shareOf(12, 61)).toBe('20%');
    expect(shareOf(0, 0)).toBe('–');
  });

  it('finds the step to work on', () => {
    const step = (key: string, status: LadderStep['status']): LadderStep => ({
      key,
      title: key,
      level: '',
      measure: '',
      count: 0,
      of: 0,
      value: null,
      target: 0.9,
      why: '',
      how: '',
      status,
    });
    expect(focusStep([step('a', 'solid'), step('b', 'focus'), step('c', 'later')])?.key).toBe('b');
    expect(focusStep([step('a', 'solid'), step('b', 'unknown')])).toBeUndefined();
  });
});
