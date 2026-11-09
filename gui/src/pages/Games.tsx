import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import { getGames } from '../api/client';
import { NoGamesEmpty, PAGE_SIZE, PageHeader, PagedList, ResultMark, SelectField } from '../components';
import type { Game, GameResult } from '../types/api';
import { prettyMap } from './coachTransforms';
import { formatDuration, parseUtc, prettyPlaylist } from './dataTransforms';

// An empty value shows them all
const PLAYLIST_FILTERS = [
  { value: '', label: 'All playlists' },
  { value: 'STANDARD', label: 'Standard' },
  { value: 'DOUBLES', label: 'Doubles' },
  { value: 'DUEL', label: 'Duel' },
];

const RESULT_FILTERS: { value: GameResult | ''; label: string }[] = [
  { value: '', label: 'All results' },
  { value: 'WIN', label: 'Wins' },
  { value: 'LOSS', label: 'Losses' },
  { value: 'DRAW', label: 'Draws' },
];

/** Every game you've loaded, newest first, a page at a time. */
export function Games() {
  const [playlist, setPlaylist] = useState('');
  const [result, setResult] = useState<GameResult | ''>('');
  const [offset, setOffset] = useState(0);

  const games = useQuery({
    queryKey: ['games', playlist, result, offset],
    queryFn: () =>
      getGames({ playlist: playlist || undefined, result: result || undefined, limit: PAGE_SIZE, offset }),
  });

  return (
    <div>
      <PageHeader title="Games" note={games.data ? `${games.data.total} games loaded` : 'Every replay you have loaded'}>
        <SelectField
          label="Playlist"
          value={playlist}
          options={PLAYLIST_FILTERS}
          onChange={(value) => {
            setPlaylist(value);
            setOffset(0);
          }}
        />
        <SelectField
          label="Result"
          value={result}
          options={RESULT_FILTERS}
          onChange={(value) => {
            setResult(value);
            setOffset(0);
          }}
        />
      </PageHeader>

      <PagedList
        list={games.data}
        loading={games.isLoading}
        failed={!!games.error}
        failure="Your games didn't load. Check that the server is running."
        empty={<NoGamesEmpty />}
        offset={offset}
        onOffset={setOffset}
      >
        {(items) => <GamesTable games={items} />}
      </PagedList>
    </div>
  );
}

function GamesTable({ games }: { games: Game[] }) {
  return (
    <table className="w-full min-w-[40rem]">
      <thead>
        <tr className="border-b border-[var(--color-border)]">
          <th className="th text-left pl-5">Result</th>
          <th className="th text-left">Map</th>
          <th className="th text-left">Played</th>
          <th className="th text-left">Playlist</th>
          <th className="th text-right pr-5">Length</th>
        </tr>
      </thead>
      <tbody>
        {games.map((game) => (
          <GameRow key={game.replay_id} game={game} />
        ))}
      </tbody>
    </table>
  );
}

function GameRow({ game }: { game: Game }) {
  const played = parseUtc(game.played_at_utc);
  return (
    <tr className="border-b last:border-b-0 border-[var(--color-border)] hover:bg-[var(--color-bg-tertiary)]">
      <td className="px-3 pl-5 py-3">
        <ResultMark result={game.result} score={`${game.my_score}–${game.opponent_score}`} />
      </td>
      <td className="px-3 py-3">
        <Link to={`/games/${encodeURIComponent(game.replay_id)}`} className="link">
          {prettyMap(game.map)}
        </Link>
      </td>
      <td className="px-3 py-3">
        {played.toLocaleDateString()}
        <span className="ml-2 text-[13px] text-[var(--color-text-muted)]">
          {played.toLocaleTimeString(undefined, { hour: 'numeric', minute: '2-digit' })}
        </span>
      </td>
      <td className="px-3 py-3">{prettyPlaylist(game.playlist)}</td>
      <td className="px-3 pr-5 py-3 text-right text-[var(--color-text-muted)]">{formatDuration(game.duration_seconds)}</td>
    </tr>
  );
}
