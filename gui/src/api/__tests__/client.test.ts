import type { InternalAxiosRequestConfig } from 'axios';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';

import {
  getCoach,
  getComparison,
  getGames,
  getGrades,
  getPatterns,
  getPlayer,
  getPlayers,
  getReplay,
  getReplayReview,
  getTrends,
  getWeaknesses,
  http,
  setGrade,
  tagPlayer,
} from '../client';

// Each request as it would go out, and what the stub answers with
let sent: { method: string; url: string; body: unknown }[] = [];
let answer: unknown = { ok: true };
const realAdapter = http.defaults.adapter;

beforeEach(() => {
  sent = [];
  answer = { ok: true };
  http.defaults.adapter = async (config: InternalAxiosRequestConfig) => {
    sent.push({
      method: (config.method ?? '').toUpperCase(),
      url: http.getUri(config),
      body: config.data === undefined ? undefined : JSON.parse(config.data),
    });
    return { data: answer, status: 200, statusText: 'OK', headers: {}, config };
  };
});

afterEach(() => {
  http.defaults.adapter = realAdapter;
});

describe('the API client', () => {
  it('lists games a page at a time, leaving out the filters you did not set', async () => {
    await getGames({ playlist: undefined, result: 'WIN', limit: 20, offset: 40 });
    expect(sent).toEqual([{ method: 'GET', url: '/api/games?result=WIN&limit=20&offset=40', body: undefined }]);
  });

  it('answers with what the API sent', async () => {
    answer = { items: [], total: 0, limit: 20, offset: 0 };
    expect(await getGames({ limit: 20, offset: 0 })).toEqual(answer);
  });

  it('encodes ids into the path', async () => {
    await getReplay('a/b');
    await getReplayReview('a/b');
    await getPlayer('epic:abc');
    expect(sent.map((request) => request.url)).toEqual([
      '/api/replays/a%2Fb',
      '/api/replays/a%2Fb/review',
      '/api/players/epic%3Aabc',
    ]);
  });

  it('sends tagged=false, which means not tagged', async () => {
    await getPlayers({ tagged: false, min_games: 0, sort: '-games_with_me', limit: 20, offset: 0 });
    expect(sent[0].url).toBe('/api/players?tagged=false&min_games=0&sort=-games_with_me&limit=20&offset=0');
  });

  it('leaves out tagged to show everyone', async () => {
    await getPlayers({ tagged: undefined, min_games: 1, sort: '-games_with_me', limit: 20, offset: 0 });
    expect(sent[0].url).toBe('/api/players?min_games=1&sort=-games_with_me&limit=20&offset=0');
  });

  it('asks the stats views for a playlist and rank only once you pick them', async () => {
    await getCoach({ playlist: undefined, period: '30d' });
    await getTrends({ metric: 'bcpm', period: '7d', playlist: 'DOUBLES' });
    await getComparison({ rank: undefined, period: '30d', playlist: undefined });
    await getWeaknesses({ rank: 'P1', period: '30d', playlist: 'STANDARD' });
    await getPatterns({ period: '30d', playlist: undefined });
    await getGrades();
    expect(sent.map((request) => request.url)).toEqual([
      '/api/coach?period=30d',
      '/api/trends?metric=bcpm&period=7d&playlist=DOUBLES',
      '/api/compare?period=30d',
      '/api/weaknesses?rank=P1&period=30d&playlist=STANDARD',
      '/api/patterns?period=30d',
      '/api/grades',
    ]);
  });

  it('puts a grade on the game it belongs to', async () => {
    await setGrade('abc', { item: 'mistake', t: 309.1, kind: 'last_back_overcommit', grade: 'wrong' });
    expect(sent).toEqual([
      {
        method: 'PUT',
        url: '/api/replays/abc/grades',
        body: { item: 'mistake', t: 309.1, kind: 'last_back_overcommit', grade: 'wrong' },
      },
    ]);
  });

  it('tags a player, and leaves their notes alone unless it sends some', async () => {
    await tagPlayer('xbox:1', { tagged: true });
    await tagPlayer('xbox:1', { tagged: true, notes: 'Rotates well' });
    expect(sent).toEqual([
      { method: 'POST', url: '/api/players/xbox%3A1/tag', body: { tagged: true } },
      { method: 'POST', url: '/api/players/xbox%3A1/tag', body: { tagged: true, notes: 'Rotates well' } },
    ]);
  });
});
