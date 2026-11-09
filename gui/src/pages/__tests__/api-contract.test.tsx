import type { ReactElement } from 'react';
import { QueryClient, QueryClientProvider, type QueryKey } from '@tanstack/react-query';
import { renderToStaticMarkup } from 'react-dom/server';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { describe, expect, it } from 'vitest';

import { Benchmarks } from '../Benchmarks';
import { Coach, GradesTable } from '../Coach';
import { Compare } from '../Compare';
import { GameDetail } from '../GameDetail';
import { GameReviewBody } from '../GameReview';
import { Trends } from '../Trends';
import type {
  CategorySummary,
  CoachResponse,
  CompareResponse,
  KickoffSummary,
  GradesResponse,
  PatternsResponse,
  ReplayDetail,
  ReplayReview,
  TrendsResponse,
  WeaknessesResponse,
} from '../../types/api';

// These payloads mirror real API responses. Pages once rendered against a
// shape the API no longer sent, which type checks alone did not catch.
const LAST_BACK: CategorySummary = {
  category: 'last_back',
  label: 'Last back',
  flags: 4,
  goals_cost: 4,
  games: 10,
  per_game: 0.4,
  latest_per_game: 0.67,
  before_per_game: 0.29,
  sessions: [
    { play_date: '2026-10-31', games: 7, flags: 2 },
    { play_date: '2026-11-05', games: 3, flags: 2 },
  ],
  kinds: { last_back_upfield: 2, last_back_overcommit: 2 },
  top_kind: 'last_back_upfield',
  cue: 'As the last player back, keep the ball in front of you. Go no further than halfway.',
  clean_streak: 2,
};

const GOALKEEPING: CategorySummary = {
  ...LAST_BACK,
  category: 'goalkeeping',
  label: 'Goalkeeping',
  flags: 0,
  goals_cost: 0,
  per_game: 0,
  latest_per_game: 0,
  before_per_game: 0,
  kinds: {},
  top_kind: null,
  cue: null,
  clean_streak: 10,
};

// Shaped like the API's kickoffs section on 41 real games
const KICKOFFS: KickoffSummary = {
  games: 41,
  count: 270,
  double_commits: 19,
  going: {
    count: 97,
    went: 94,
    fakes: 3,
    results: { won: 28, even: 39, lost: 30 },
    flips: { on_time: 61, late: 13, none: 20 },
    by_flip: [
      { flip: 'ON_TIME', count: 61, won: 19, even: 30, lost: 12 },
      { flip: 'LATE', count: 13, won: 3, even: 2, lost: 8 },
      { flip: 'NONE', count: 20, won: 5, even: 6, lost: 9 },
    ],
    speedflips: 0,
    race: { compared: 90, sooner: 16, later: 32, median_gap: 0.007 },
    median_speed: 2010,
    goals_for: 5,
    goals_against: 10,
  },
  support: {
    count: 173,
    results: { won: 60, even: 38, lost: 75 },
    double_commits: 16,
    cheat: 71,
    hold: 84,
    goals_for: 10,
    goals_against: 8,
  },
  sessions: [
    { play_date: '2026-11-05', went: 16, on_time: 11, double_commits: 1 },
    { play_date: '2026-11-06', went: 36, on_time: 18, double_commits: 1 },
  ],
  ladder: [
    {
      key: 'flip_in',
      title: 'Flip into the ball every time',
      level: 'Gold to Platinum',
      measure: 'Kickoffs you went for with a flip into the ball',
      count: 74,
      of: 94,
      value: 0.787,
      target: 0.9,
      why: 'Without a flip your bumper meets their flip.',
      how: "Flip into the ball when you're about two car lengths from it.",
      status: 'focus',
    },
    {
      key: 'on_time',
      title: 'Flip on time',
      level: 'Platinum',
      measure: 'Kickoffs you went for with the flip on time',
      count: 61,
      of: 94,
      value: 0.649,
      target: 0.85,
      why: 'A flip that starts as you reach the ball has no power left for the hit.',
      how: 'Start your flip a moment sooner.',
      status: 'later',
    },
    {
      key: 'one_goes',
      title: 'One goes, the rest support',
      level: 'Platinum to Diamond',
      measure: 'Kickoffs where only one of you went',
      count: 251,
      of: 270,
      value: 0.93,
      target: 0.95,
      why: 'Two cars on the ball leave nobody for where it goes next.',
      how: 'Only one of you goes.',
      status: 'later',
    },
    {
      key: 'speedflip',
      title: 'Learn the speedflip',
      level: 'Diamond to Champion',
      measure: 'Kickoffs you went for with a speedflip',
      count: 0,
      of: 94,
      value: 0,
      target: 0.5,
      why: 'A speedflip is a kickoff where you boost, flip diagonally and cancel the flip straight away.',
      how: 'Learn the motion in Free Play from a speedflip tutorial.',
      status: 'later',
    },
  ],
};

const COACH: CoachResponse = {
  playlist: 'STANDARD',
  period: '30d',
  rank: 'P1',
  game_count: 11,
  reviewed_count: 10,
  session: {
    play_date: '2026-11-05',
    wins: 2,
    losses: 1,
    draws: 0,
    games: [
      {
        replay_id: 'abc',
        playlist: 'STANDARD',
        played_at_utc: '2026-11-05T23:59:02',
        result: 'WIN',
        my_score: 5,
        opponent_score: 4,
        map: 'Stadium_P',
        goals: 3,
        assists: 1,
        saves: 0,
        shots: 4,
        reviewed: true,
        flags: 4,
        goals_on_me: 2,
      },
      {
        replay_id: 'def',
        playlist: 'STANDARD',
        played_at_utc: '2026-11-06T00:21:26',
        result: 'LOSS',
        my_score: 3,
        opponent_score: 4,
        map: 'UtopiaStadium_Dusk_P',
        goals: 2,
        assists: 1,
        saves: 2,
        shots: 3,
        reviewed: false,
        flags: null,
        goals_on_me: null,
      },
    ],
  },
  targets: [LAST_BACK],
  categories: [LAST_BACK, GOALKEEPING],
  highlights: [
    {
      kind: 'winner',
      title: 'Scored the winner',
      detail: '5–4 on Stadium, with 1:09 left',
      replay_id: 'abc',
    },
  ],
  kickoffs: KICKOFFS,
};

const REVIEW: ReplayReview = {
  replay_id: 'abc',
  status: 'ok',
  error: null,
  clears: 3,
  clears_given_back: 1,
  mistakes: [
    {
      kind: 'last_back_overcommit',
      label: 'Last back overcommit',
      category: 'last_back',
      category_label: 'Last back',
      t: 309.1,
      seconds_left: 107,
      clock: '1:47',
      score: '4-2',
      duration: 0,
      what: "You were your team's last player back and went out at the ball.",
      instead: 'When teammates are already challenging, stay in goal.',
      outcome: 'You conceded right after.',
      cost_goal: true,
      grade: 'wrong',
    },
  ],
  goals: [
    {
      t: 99.2,
      seconds_left: 225,
      clock: '3:45',
      score: '1-0',
      ours: true,
      scorer: 'You',
      by_me: true,
      assist_by_me: false,
      winner: false,
      equalizer: false,
      on_me: null,
      summary: null,
      lines: [],
      grade: null,
    },
    {
      t: 309.4,
      seconds_left: 106,
      clock: '1:46',
      score: '4-2',
      ours: false,
      scorer: 'hezekkia',
      by_me: false,
      assist_by_me: false,
      winner: false,
      equalizer: false,
      on_me: true,
      summary: 'You were the last one back.',
      lines: ['You were beaten by the shot (12 boost)'],
      grade: null,
    },
  ],
  kickoffs: [
    {
      t: 4.1,
      seconds_left: 300,
      clock: '5:00',
      score: '0-0',
      phase: 'INITIAL',
      role: 'GO',
      spot: 'DIAGONAL',
      approach: 'STANDARD_BOOST',
      flip: 'NONE',
      flip_lead: null,
      result: 'LOST',
      first_touch: 'opponent',
      race_gap: 0.04,
      speed_at_contact: 1980,
      boost_used: 33,
      double_commit: false,
      goal_after: 'against',
      goal_after_s: 4.4,
    },
    {
      t: 110.3,
      seconds_left: 210,
      clock: '3:30',
      score: '1-0',
      phase: 'INITIAL',
      role: 'BACK',
      spot: 'BACK',
      approach: 'STANDARD_FRONTFLIP',
      flip: 'ON_TIME',
      flip_lead: 0.12,
      result: 'WON',
      first_touch: 'you',
      race_gap: null,
      speed_at_contact: 2200,
      boost_used: 30,
      double_commit: true,
      goal_after: null,
      goal_after_s: null,
    },
  ],
};

const GRADES: GradesResponse = {
  rules: [
    { item: 'mistake', kind: 'last_back_upfield', label: 'Last back upfield', right: 1, wrong: 3 },
    { item: 'goal', kind: 'goal_on_you', label: 'Goal put on you', right: 2, wrong: 0 },
  ],
};

const REPLAY: ReplayDetail = {
  replay_id: 'abc',
  played_at_utc: '2026-11-01T03:56:53',
  playlist: 'STANDARD',
  result: 'WIN',
  my_score: 6,
  opponent_score: 3,
  duration_seconds: 377.5,
  map: 'Stadium_Foggy_P',
  player_stats: [
    {
      player_id: 'epic:me',
      display_name: 'midnightmelker',
      team: 'ORANGE',
      is_me: true,
      goals: 1,
      assists: 0,
      saves: 1,
      shots: 5,
      bcpm: 412.4,
      avg_boost: 44.2,
    },
    {
      player_id: 'steam:other',
      display_name: 'Opponent',
      team: 'BLUE',
      is_me: false,
      goals: 0,
      assists: 0,
      saves: 2,
      shots: 1,
      bcpm: 300.1,
      avg_boost: 40.0,
    },
  ],
};

function renderWithCache(
  entries: [QueryKey, unknown][],
  url: string,
  element: ReactElement,
) {
  const client = new QueryClient();
  for (const [queryKey, data] of entries) {
    client.setQueryData(queryKey, data);
  }

  return renderToStaticMarkup(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[url]}>
        <Routes>
          <Route path="/" element={element} />
          <Route path="/games/:replayId" element={element} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('Coach', () => {
  const html = renderWithCache([[['coach', undefined, '30d'], COACH]], '/', <Coach />);

  it('renders no placeholder text', () => {
    expect(html).not.toContain('NaN');
    expect(html).not.toContain('undefined');
  });

  it('leads with the target that cost the most goals, and its cue', () => {
    expect(html).toContain('Cost you 4 goals in 10 games');
    expect(html).toContain('keep the ball in front of you');
    expect(html).toContain('Last back upfield ×2');
  });

  it('shows the session and says which games still need a review', () => {
    expect(html).toContain('2 goals on you');
    expect(html).toContain('Not reviewed');
    expect(html).toContain('1 of 11 games have no mistake review yet');
  });

  it('links highlights to their game', () => {
    expect(html).toContain('Scored the winner');
    expect(html).toContain('href="/games/abc"');
  });

  it('leaves out the mode of each game when it shows one playlist', () => {
    expect(html).not.toContain('3v3');
  });

  it('leaves out the grades tally until you grade something', () => {
    expect(html).not.toContain('How its calls hold up');
  });

  it('leads the kickoffs with the step to work on and what to practise', () => {
    expect(html).toContain('Flip into the ball every time');
    expect(html).toContain('Work on this now');
    expect(html).toContain('74 of 94');
    expect(html).toContain('79%, your target 90%');
    expect(html).toContain('two car lengths');
  });

  it('says what a speedflip is, even before it is the step to work on', () => {
    expect(html).toContain('A speedflip is a kickoff');
  });

  it('splits your go kickoffs by how you flipped', () => {
    expect(html).toContain('No flip into the ball');
    expect(html).toContain('There first in 16, second in 32 of 90');
    expect(html).toContain('72 km/h');
  });

  it('shows on-time flips by day', () => {
    expect(html).toContain('Flips on time, by day');
    expect(html).toContain('18 of 36');
  });
});

describe('Coach from an API without kickoffs', () => {
  const older: CoachResponse = { ...COACH, kickoffs: undefined };
  const html = renderWithCache([[['coach', undefined, '30d'], older]], '/', <Coach />);

  it('leaves the kickoffs out', () => {
    expect(html).not.toContain('When you go');
    expect(html).toContain('Training targets');
  });
});


describe('Coach with Doubles and Standard together', () => {
  const mixed: CoachResponse = {
    ...COACH,
    playlist: 'DOUBLES,STANDARD',
    session: {
      ...COACH.session!,
      games: [{ ...COACH.session!.games[0], playlist: 'DOUBLES' }, COACH.session!.games[1]],
    },
  };
  const html = renderWithCache([[['coach', undefined, '30d'], mixed]], '/', <Coach />);

  it('selects the combined option', () => {
    expect(html).toContain('<option value="DOUBLES,STANDARD" selected="">Doubles and Standard</option>');
  });

  it('marks each session game with its mode', () => {
    expect(html).toContain('2v2');
    expect(html).toContain('3v3');
  });

  it('warns that trends can come from the mix of modes', () => {
    expect(html).toContain('a change can come from which mode you played');
  });
});
describe('Coach grades', () => {
  const html = renderWithCache(
    [
      [['coach', undefined, '30d'], COACH],
      [['grades'], GRADES],
    ],
    '/',
    <Coach />,
  );

  it('shows how each rule has held up', () => {
    expect(html).toContain('How its calls hold up');
    expect(html).toContain('Last back upfield');
    expect(html).toContain('25%');
    expect(html).toContain('100%');
  });

  it('says whether a rule flags moments or calls goals', () => {
    const table = renderToStaticMarkup(<GradesTable rules={GRADES.rules} />);
    expect(table).toContain('flagged moment');
    expect(table).toContain('goal verdict');
  });
});

describe('GameReviewBody', () => {
  it('groups flagged moments by category and marks the goals they cost', () => {
    const html = renderToStaticMarkup(<GameReviewBody review={REVIEW} />);
    expect(html).toContain('Last back');
    expect(html).toContain('cost 1 goal');
    expect(html).toContain('1 of 1 on you');
    expect(html).toContain('1 of 3 clears');
  });

  it('shows right and wrong buttons on each call, with your grade pressed', () => {
    const html = renderToStaticMarkup(<GameReviewBody review={REVIEW} onGrade={() => {}} />);
    expect(html).toContain('aria-pressed="true" aria-label="Mark 1:47 Last back overcommit wrong"');
    expect(html).toContain('aria-pressed="false" aria-label="Mark 1:47 Last back overcommit right"');
    // Only the goal against gets buttons, not your own goal
    expect(html).toContain('Mark the verdict on the 1:46 goal right');
    expect(html).not.toContain('3:45 goal');
  });

  it('disables the buttons when there is nowhere to send a grade', () => {
    const html = renderToStaticMarkup(<GameReviewBody review={REVIEW} />);
    expect(html).toContain('disabled=""');
  });

  it('lists every kickoff on the clock with how you played it', () => {
    const html = renderToStaticMarkup(<GameReviewBody review={REVIEW} />);
    expect(html).toContain('You went from the diagonal.');
    expect(html).toContain('Boosted in');
    expect(html).toContain('no flip into the ball');
    expect(html).toContain('Came back at you');
    expect(html).toContain('They scored 4 s later.');
    expect(html).toContain('You and a teammate both went.');
    expect(html).toContain('flip on time, 0.12 s before contact');
  });

  it('explains a missing review instead of showing an empty timeline', () => {
    const html = renderToStaticMarkup(
      <GameReviewBody review={{ ...REVIEW, status: 'missing', mistakes: [], goals: [] }} />,
    );
    expect(html).toContain('rlcoach reviews');
    expect(html).not.toContain('Timeline');
  });
});

describe('GameDetail', () => {
  const html = renderWithCache(
    [
      [['replay', 'abc'], REPLAY],
      [['replay-review', 'abc'], REVIEW],
    ],
    '/games/abc',
    <GameDetail />,
  );

  it('renders both teams by player name', () => {
    expect(html).toContain('midnightmelker');
    expect(html).toContain('Opponent');
  });

  it('marks you on the orange team too', () => {
    expect(html).toContain('You');
  });

  it('puts the review timeline above the box score', () => {
    expect(html.indexOf('Timeline')).toBeGreaterThan(-1);
    expect(html.indexOf('Timeline')).toBeLessThan(html.indexOf('Match info'));
  });
});

// From GET /api/weaknesses and GET /api/patterns on real games
const WEAKNESSES: WeaknessesResponse = {
  game_count: 30,
  has_benchmarks: true,
  playlist: 'STANDARD',
  rank: 'P1',
  strengths: [],
  weaknesses: [
    { metric: 'bcpm', my_value: 206.69, severity: 'critical', target_median: 261.9, z_score: -1.5 },
  ],
};

const PATTERNS: PatternsResponse = {
  loss_count: 12,
  min_games: 5,
  playlist: 'STANDARD',
  win_count: 18,
  patterns: [
    { delta: -1.78, direction: 'lower_in_wins', effect_size: -1.644, loss_avg: 2.17, metric: 'saves', win_avg: 0.39 },
    { delta: 1.75, direction: 'higher_in_wins', effect_size: 1.439, loss_avg: 1.08, metric: 'shots', win_avg: 2.83 },
  ],
};

describe('Benchmarks', () => {
  const html = renderWithCache(
    [
      [['weaknesses', '30d', undefined, undefined], WEAKNESSES],
      [['patterns', '30d', undefined], PATTERNS],
    ],
    '/',
    <Benchmarks />,
  );
  const row = (metric: string) => html.split('<li').find((item) => item.includes(`>${metric}<`)) ?? '';

  it('shows a stat that is higher in wins in green with a plus sign', () => {
    expect(row('SHOTS')).toContain('--color-success');
    expect(row('SHOTS')).toMatch(/\+(<!-- -->)?1\.75/);
  });

  it('shows a stat that is lower in wins in red', () => {
    expect(row('SAVES')).toContain('--color-error');
    expect(row('SAVES')).toContain('-1.78');
    expect(row('SAVES')).not.toContain('+');
  });

  it('compares you with the rank the API chose from your config', () => {
    expect(html).toMatch(/against (<!-- -->)?P1(<!-- -->)? players/);
    expect(row('BCPM')).toMatch(/P1(<!-- -->)? median/);
    expect(html).toContain('<option value="P1" selected="">P1</option>');
  });
});

// From GET /api/compare and GET /api/trends without a rank
const COMPARISON: CompareResponse = {
  target_rank: 'P1',
  playlist: 'STANDARD',
  game_count: 30,
  comparisons: [
    {
      metric: 'bcpm',
      my_value: 206.69,
      target_median: 261.9,
      difference: -55.21,
      difference_pct: -21.1,
      direction: 'higher',
    },
  ],
};

const TRENDS: TrendsResponse = {
  metric: 'bcpm',
  period: '30d',
  playlist: 'STANDARD',
  rank: 'P1',
  rank_median: 261.9,
  values: [{ date: '2026-11-07', value: 206.69 }],
};

describe('Compare', () => {
  const html = renderWithCache([[['compare', undefined, '30d', undefined], COMPARISON]], '/', <Compare />);

  it('opens on the rank the API chose from your config', () => {
    expect(html).toMatch(/Gap to (<!-- -->)?P1/);
    expect(html).toContain('<option value="P1" selected="">P1</option>');
    expect(html).not.toContain('GC1');
  });
});

describe('Trends', () => {
  const html = renderWithCache([[['trends', 'bcpm', '30d', undefined], TRENDS]], '/', <Trends />);

  it('offers the median of the rank in your config', () => {
    expect(html).toMatch(/Show the (<!-- -->)?P1(<!-- -->)? median/);
  });
});
