import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import { getGames } from '../api/client';
import {
  Card,
  SkeletonTable,
  ErrorState,
  NoGamesEmpty,
  PageHeader,
  Pagination,
  ResultMark,
  SelectField,
} from '../components';
import { prettyMap } from './coachTransforms';
import {
  buildGamesParams,
  formatDuration,
  parseUtc,
  prettyPlaylist,
  type GameFilters,
  type GameResult,
} from './dataTransforms';

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

export function Games() {
  const [filters, setFilters] = useState<GameFilters>({
    playlist: '',
    result: '',
    limit: 20,
    offset: 0,
  });

  const { data, isLoading, error } = useQuery({
    queryKey: ['games', filters],
    queryFn: () => getGames(buildGamesParams(filters)),
  });

  const totalPages = data ? Math.ceil(data.total / filters.limit) : 0;
  const currentPage = Math.floor(filters.offset / filters.limit) + 1;

  return (
    <div>
      <PageHeader title="Games" note={data ? `${data.total} games loaded` : 'Every replay you have loaded'}>
        <SelectField
          label="Playlist"
          value={filters.playlist}
          options={PLAYLIST_FILTERS}
          onChange={(playlist) => setFilters({ ...filters, playlist, offset: 0 })}
        />
        <SelectField
          label="Result"
          value={filters.result}
          options={RESULT_FILTERS}
          onChange={(result) => setFilters({ ...filters, result, offset: 0 })}
        />
      </PageHeader>

      <Card className="overflow-x-auto">
        {error ? (
          <ErrorState message="Your games didn't load. Check that the server is running." />
        ) : isLoading ? (
          <div className="p-4">
            <SkeletonTable rows={10} />
          </div>
        ) : data?.items.length === 0 ? (
          <NoGamesEmpty />
        ) : (
          <>
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
                {data?.items.map((game) => {
                  const played = parseUtc(game.played_at_utc);
                  return (
                    <tr
                      key={game.replay_id}
                      className="border-b last:border-b-0 border-[var(--color-border)] hover:bg-[var(--color-bg-tertiary)]"
                    >
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
                      <td className="px-3 pr-5 py-3 text-right text-[var(--color-text-muted)]">
                        {formatDuration(game.duration_seconds)}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>

            {totalPages > 1 && (
              <Pagination
                currentPage={currentPage}
                totalPages={totalPages}
                previousDisabled={filters.offset === 0}
                nextDisabled={currentPage >= totalPages}
                onPrevious={() => setFilters({ ...filters, offset: filters.offset - filters.limit })}
                onNext={() => setFilters({ ...filters, offset: filters.offset + filters.limit })}
              />
            )}
          </>
        )}
      </Card>
    </div>
  );
}
