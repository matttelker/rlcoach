import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import { getPlayers, tagPlayer } from '../api/client';
import { Card, SkeletonTable, ErrorState, NoDataEmpty, PageHeader, Pagination, SelectField } from '../components';
import { parseUtc } from './dataTransforms';

const TAG_FILTERS = [
  { value: '', label: 'Everyone' },
  { value: 'true', label: 'Teammates you tagged' },
  { value: 'false', label: 'Not tagged' },
];

export function Players() {
  const queryClient = useQueryClient();
  const [filters, setFilters] = useState({
    tagged: undefined as boolean | undefined,
    minGames: 1,
    limit: 20,
    offset: 0,
  });

  const { data, isLoading, error } = useQuery({
    queryKey: ['players', filters],
    queryFn: () =>
      getPlayers({
        tagged: filters.tagged,
        min_games: filters.minGames,
        limit: filters.limit,
        offset: filters.offset,
        sort: '-games_with_me',
      }),
  });

  const tagMutation = useMutation({
    mutationFn: ({ playerId, tagged }: { playerId: string; tagged: boolean }) => tagPlayer(playerId, { tagged }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['players'] });
    },
  });

  const totalPages = data ? Math.ceil(data.total / filters.limit) : 0;
  const currentPage = Math.floor(filters.offset / filters.limit) + 1;

  return (
    <div>
      <PageHeader title="Players" note="Everyone you've shared a match with, most games first">
        <SelectField
          label="Show"
          value={filters.tagged === undefined ? '' : String(filters.tagged)}
          options={TAG_FILTERS}
          onChange={(value) =>
            setFilters({ ...filters, tagged: value === '' ? undefined : value === 'true', offset: 0 })
          }
        />
        <label>
          <span className="field-label">At least this many games</span>
          <input
            type="number"
            value={filters.minGames}
            onChange={(e) => setFilters({ ...filters, minGames: parseInt(e.target.value) || 0, offset: 0 })}
            min={0}
            className="field w-24"
          />
        </label>
      </PageHeader>

      <Card className="overflow-x-auto">
        {error ? (
          <ErrorState message="Players didn't load. Check that the server is running." />
        ) : isLoading ? (
          <div className="p-4">
            <SkeletonTable rows={10} />
          </div>
        ) : data?.items.length === 0 ? (
          <NoDataEmpty message="No players match" description="Lower the game count or show everyone." />
        ) : (
          <>
            <table className="w-full min-w-[36rem]">
              <thead>
                <tr className="border-b border-[var(--color-border)]">
                  <th className="th text-left pl-5">Player</th>
                  <th className="th text-right">Games together</th>
                  <th className="th text-left">Last seen</th>
                  <th className="th text-center">Teammate</th>
                  <th className="th text-left pr-5">Notes</th>
                </tr>
              </thead>
              <tbody>
                {data?.items.map((player) => (
                  <tr key={player.player_id} className="border-b last:border-b-0 border-[var(--color-border)]">
                    <td className="px-3 pl-5 py-3">
                      <Link to={`/players/${encodeURIComponent(player.player_id)}`} className="link">
                        {player.display_name}
                      </Link>
                      <div className="text-[13px] text-[var(--color-text-muted)]">{player.platform || 'Unknown platform'}</div>
                    </td>
                    <td className="px-3 py-3 text-right">{player.games_with_me}</td>
                    <td className="px-3 py-3 text-[var(--color-text-muted)]">
                      {player.last_seen_utc ? parseUtc(player.last_seen_utc).toLocaleDateString() : '–'}
                    </td>
                    <td className="px-3 py-3 text-center">
                      <TagToggle
                        tagged={player.is_tagged_teammate}
                        name={player.display_name}
                        disabled={tagMutation.isPending}
                        onToggle={() =>
                          tagMutation.mutate({ playerId: player.player_id, tagged: !player.is_tagged_teammate })
                        }
                      />
                    </td>
                    <td className="px-3 pr-5 py-3 text-[14px] text-[var(--color-text-muted)] max-w-56 truncate">
                      {player.teammate_notes || '–'}
                    </td>
                  </tr>
                ))}
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

function TagToggle({
  tagged,
  name,
  disabled,
  onToggle,
}: {
  tagged: boolean;
  name: string;
  disabled?: boolean;
  onToggle: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onToggle}
      disabled={disabled}
      aria-pressed={tagged}
      aria-label={`Tag ${name} as a teammate`}
      className={`w-8 h-8 rounded-full inline-grid place-items-center border transition-colors ${
        tagged
          ? 'bg-[var(--color-primary)] border-[var(--color-primary)] text-[var(--color-on-primary)]'
          : 'border-[var(--color-border)] text-[var(--color-text-muted)] hover:text-[var(--color-text)] hover:border-[var(--color-text-muted)]'
      }`}
    >
      <svg viewBox="0 0 20 20" className="w-4 h-4" aria-hidden="true">
        <path
          d="M10 2.5l2.3 4.7 5.2.8-3.8 3.6.9 5.1L10 14.3l-4.6 2.4.9-5.1-3.8-3.6 5.2-.8z"
          fill={tagged ? 'currentColor' : 'none'}
          stroke="currentColor"
          strokeWidth={1.5}
          strokeLinejoin="round"
        />
      </svg>
    </button>
  );
}
