import type { ReactElement } from 'react';
import { QueryClient, QueryClientProvider, type QueryKey } from '@tanstack/react-query';
import { renderToStaticMarkup } from 'react-dom/server';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { describe, expect, it } from 'vitest';

import { Coach, GradesTable } from '../Coach';
import { GameDetail } from '../GameDetail';
import { GameReviewBody } from '../GameReview';
import type {
  CategorySummary,
  CoachResponse,
  GradesResponse,
  ReplayDetail,
  ReplayReview,
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

const COACH: CoachResponse = {
  playlist: 'STANDARD',
  period: '30d',
  rank: 'GC1',
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

  it('leaves out the grades tally until you grade something', () => {
    expect(html).not.toContain('How its calls hold up');
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
