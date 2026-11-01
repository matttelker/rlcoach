import type { ReactElement } from 'react';
import { QueryClient, QueryClientProvider, type QueryKey } from '@tanstack/react-query';
import { renderToStaticMarkup } from 'react-dom/server';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { describe, expect, it } from 'vitest';

import { Dashboard } from '../Dashboard';
import { GameDetail } from '../GameDetail';
import type { DashboardResponse, ReplayDetail } from '../../types/api';

// These payloads mirror real API responses. Both pages once rendered against a
// shape the API no longer sent, which type checks alone did not catch.
const DASHBOARD: DashboardResponse = {
  today: { games_played: 0, wins: 0, losses: 0, draws: 0, win_rate: null },
  quick_stats: { avg_goals: 1.6, avg_saves: 1.5, avg_assists: 0.6, avg_bcpm: 412.4 },
  recent_games: [
    {
      replay_id: 'abc',
      played_at_utc: '2026-11-01T03:56:53',
      playlist: 'STANDARD',
      result: 'WIN',
      my_score: 6,
      opponent_score: 3,
      map: 'Stadium_Foggy_P',
    },
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

function renderWithCache(queryKey: QueryKey, data: unknown, url: string, element: ReactElement) {
  const client = new QueryClient();
  client.setQueryData(queryKey, data);

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

describe('Dashboard', () => {
  const html = renderWithCache(['dashboard'], DASHBOARD, '/', <Dashboard />);

  it('renders no placeholder text when no games were played today', () => {
    expect(html).not.toContain('NaN');
    expect(html).not.toContain('undefined');
  });

  it('shows the boost average and recent games', () => {
    expect(html).toContain('412');
    expect(html).toContain('6 - 3');
  });
});

describe('GameDetail', () => {
  const html = renderWithCache(['replay', 'abc'], REPLAY, '/games/abc', <GameDetail />);

  it('renders both teams by player name', () => {
    expect(html).toContain('midnightmelker');
    expect(html).toContain('Opponent');
  });

  it('marks you on the orange team too', () => {
    expect(html).toContain('You');
  });
});
