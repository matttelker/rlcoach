import { describe, expect, it } from 'vitest';

import type { CategorySummary, LadderStep, ReplayReview, ReviewMistake, SituationSummary } from '../../types/api';
import {
  applyGrade,
  approachLabel,
  categoryTrend,
  costNote,
  costText,
  flipText,
  focusStep,
  goalAfterText,
  gradeAccuracy,
  groupByCategory,
  isMixedPlaylist,
  kickoffSeat,
  percent,
  prettyMap,
  riskText,
  sessionTitle,
  situationText,
  shareOf,
  teamSizeLabel,
  timelineX,
  trendText,
} from '../coachTransforms';

const category = (earlier: number | null, recent: number | null, trendGames = 10): CategorySummary => ({
  category: 'rotation',
  label: 'Rotation',
  flags: 5,
  goals_cost: 0,
  games: 20,
  per_game: 0.5,
  recent_per_game: recent,
  earlier_per_game: earlier,
  trend_games: trendGames,
  cost_per_game: 0,
  cost_measured: false,
  situations: [],
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

describe('trendText', () => {
  it('compares your last games with as many before them', () => {
    expect(trendText(category(1.4, 0.5))).toBe('0.5 a game over your last 10 games, 1.4 over the 10 before');
    expect(trendText(category(1.4, 0.5, 6))).toBe('0.5 a game over your last 6 games, 1.4 over the 6 before');
  });

  it('has no trend when there are too few games', () => {
    expect(trendText(category(null, null, 0))).toBeNull();
    expect(categoryTrend(category(null, null, 0))).toBe('new');
  });
});

// The real row the API sent for shots at your goal on 41 games
const SHOTS: SituationSummary = {
  kind: 'shot_last_back',
  what: 'shots at your goal with you last back',
  bad_label: 'out of position',
  count: 106,
  bad: 19,
  bad_share: 0.179,
  others_bad_share: 0.124,
  conceded_after_bad: 9,
  extra_risk: 0.2269,
  proven: true,
  goals_per_game: 0.105,
};

describe('costText', () => {
  it('says a measured cost as one goal every so many games', () => {
    expect(costText({ cost_per_game: 0.2 })).toBe('Costs you about 1 goal every 5 games');
    expect(costText({ cost_per_game: 0.105 })).toBe('Costs you about 1 goal every 10 games');
    expect(costNote({ cost_per_game: 0.2, cost_measured: true })).toContain('Measured from how often a goal followed');
  });

  it('says a cost of a goal or more a game in goals a game', () => {
    expect(costText({ cost_per_game: 0.9 })).toBe('Costs you about 1 goal a game');
    expect(costText({ cost_per_game: 1.46 })).toBe('Costs you about 1.5 goals a game');
  });

  it('says an unmeasured cost is an estimate', () => {
    expect(costText({ cost_per_game: 0.05 })).toBe('Costs you about 1 goal every 20 games');
    expect(costNote({ cost_per_game: 0.05, cost_measured: false })).toBe('Estimated from the goals it led to.');
  });

  it('never divides by a zero or tiny cost', () => {
    expect(costText({ cost_per_game: 0 })).toBe('Costs you no goals that can be measured yet');
    expect(costText({ cost_per_game: 0.001 })).toBe('Costs you less than 1 goal every 50 games');
    expect(costNote({ cost_per_game: 0, cost_measured: false })).toBeNull();
  });
});

describe('situationText', () => {
  it('puts your rate beside the players you meet, and the goals that followed', () => {
    expect(situationText(SHOTS)).toBe(
      'Shots at your goal with you last back: 19 of 106 out of position (18%). Players in your games: 12%. ' +
        'A goal against followed 9 of your 19.',
    );
    expect(riskText(SHOTS)).toBe('When that happens, a goal against follows 23 points more often.');
  });

  it('says when there is too little data to measure the risk', () => {
    const few = { ...SHOTS, extra_risk: null, goals_per_game: null };
    expect(riskText(few)).toBe('Too few of these yet to say how much more often a goal follows.');
  });

  it('never claims a negative risk', () => {
    expect(riskText({ ...SHOTS, extra_risk: -0.03 })).toBe('A goal against follows no more often when that happens.');
  });

  it('handles a choice that never came up', () => {
    const none = { ...SHOTS, count: 0, bad: 0, bad_share: null, others_bad_share: null, conceded_after_bad: 0 };
    expect(situationText(none)).toBe('No shots at your goal with you last back in these games yet.');
    expect(riskText(none)).toBeNull();
  });

  it('leaves out the other players when there are none to compare', () => {
    const text = situationText({ ...SHOTS, others_bad_share: null, bad: 0, bad_share: 0 });
    expect(text).toBe('Shots at your goal with you last back: 0 of 106 out of position (0%).');
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

  it('names modes by team size, and casual by name', () => {
    expect(teamSizeLabel('DOUBLES')).toBe('2v2');
    expect(teamSizeLabel('STANDARD')).toBe('3v3');
    expect(teamSizeLabel('CASUAL')).toBe('Casual');
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

describe('riskText for an unproven habit', () => {
  it('says the games have not shown it costs goals', () => {
    expect(riskText({ ...SHOTS, proven: false })).toMatch(/shown this costs goals/);
  });
});
