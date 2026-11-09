import type { ReactElement } from 'react';
import { QueryClient, QueryClientProvider, type QueryKey } from '@tanstack/react-query';
import { renderToStaticMarkup } from 'react-dom/server';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { describe, expect, it } from 'vitest';

import { Games } from '../Games';
import { PlayerDetail } from '../PlayerDetail';
import { Players } from '../Players';
import type { Game, PaginatedResponse, Player } from '../../types/api';

// The pages as they first open: no filters, page 1
function render(cache: [QueryKey, unknown][], url: string, path: string, element: ReactElement) {
  const client = new QueryClient();
  for (const [key, data] of cache) client.setQueryData(key, data);
  return renderToStaticMarkup(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[url]}>
        <Routes>
          <Route path={path} element={element} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

const page = <T,>(items: T[], total = items.length): PaginatedResponse<T> => ({ items, total, limit: 20, offset: 0 });

// From GET /api/games
const GAME: Game = {
  replay_id: 'ad19e4',
  played_at_utc: '2026-11-07T07:19:21',
  play_date: '2026-11-07',
  playlist: 'STANDARD',
  result: 'LOSS',
  my_score: 0,
  opponent_score: 2,
  map: 'TrainStation_Night_P',
  duration_seconds: 342.4,
};

// From GET /api/players
const TEAMMATE: Player = {
  player_id: 'xbox:2533274833789272',
  display_name: 'LlamaTaboot8416',
  platform: 'xbox',
  is_me: false,
  is_tagged_teammate: true,
  teammate_notes: 'Rotates well',
  games_with_me: 12,
  first_seen_utc: '2026-10-30T20:01:00',
  last_seen_utc: '2026-11-07T07:19:21',
};

const STRANGER: Player = {
  ...TEAMMATE,
  player_id: 'steam:1',
  display_name: 'Stranger',
  platform: null,
  is_tagged_teammate: false,
  teammate_notes: null,
  games_with_me: 1,
  first_seen_utc: null,
  last_seen_utc: null,
};

describe('Games', () => {
  const games = (list: PaginatedResponse<Game>) => render([[['games', '', '', 0], list]], '/', '/', <Games />);

  it('lists each game with its score, map, playlist and length', () => {
    const html = games(page([GAME]));
    expect(html).toContain('1 games loaded');
    expect(html).toMatch(/0–2/);
    expect(html).toContain('href="/games/ad19e4"');
    expect(html).toContain('Train Station Night');
    expect(html).toContain('>Standard<');
    expect(html).toContain('5:42');
  });

  it('pages a long list', () => {
    expect(games(page([GAME], 42))).toMatch(/Page (<!-- -->)?1(<!-- -->)? of (<!-- -->)?3/);
  });

  it('says how to get games in when there are none', () => {
    expect(games(page([]))).toContain('No games yet');
  });

  it('shows placeholders until the list arrives', () => {
    const html = render([], '/', '/', <Games />);
    expect(html).toContain('Every replay you have loaded');
    expect(html).toContain('animate-pulse');
  });
});

describe('Players', () => {
  const players = (list: PaginatedResponse<Player>) =>
    render([[['players', '', 1, 0], list]], '/', '/', <Players />);

  it('links each player by an encoded id, with the star pressed for a tagged teammate', () => {
    const html = players(page([TEAMMATE, STRANGER]));
    expect(html).toContain('href="/players/xbox%3A2533274833789272"');
    expect(html).toContain('aria-pressed="true" aria-label="Tag LlamaTaboot8416 as a teammate"');
    expect(html).toContain('aria-pressed="false" aria-label="Tag Stranger as a teammate"');
    expect(html).toContain('Rotates well');
  });

  it('fills in a player it knows little about', () => {
    const html = players(page([STRANGER]));
    expect(html).toContain('Unknown platform');
    expect(html).toContain('>–<');
  });

  it('opens on everyone with at least one game', () => {
    const html = players(page([TEAMMATE]));
    expect(html).toContain('<option value="" selected="">Everyone</option>');
    expect(html).toContain('value="1"');
  });

  it('says what to change when nobody matches', () => {
    expect(players(page([]))).toContain('Lower the game count or show everyone.');
  });
});

describe('PlayerDetail', () => {
  const detail = (player: Player) =>
    render(
      [[['player', player.player_id], player]],
      `/players/${encodeURIComponent(player.player_id)}`,
      '/players/:playerId',
      <PlayerDetail />,
    );

  it('shows a tagged teammate with your notes', () => {
    const html = detail(TEAMMATE);
    expect(html).toContain('LlamaTaboot8416');
    expect(html).toContain('aria-pressed="true"');
    expect(html).toContain('Tagged as teammate');
    expect(html).toContain('Rotates well');
    expect(html).toContain('Edit notes');
    expect(html).toContain('href="/players"');
  });

  it('offers to tag someone new, and says what it does not know', () => {
    const html = detail(STRANGER);
    expect(html).toContain('Tag as teammate');
    expect(html).toContain('No notes yet.');
    expect(html).toContain('Unknown platform');
    expect(html).toContain('>Unknown<');
  });
});
