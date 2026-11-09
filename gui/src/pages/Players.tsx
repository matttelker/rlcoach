import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import { getPlayers } from '../api/client';
import { NoDataEmpty, PAGE_SIZE, PageHeader, PagedList, SelectField } from '../components';
import type { Player } from '../types/api';
import { parseUtc } from './dataTransforms';
import { useTagPlayer } from './useTagPlayer';

type Show = '' | 'tagged' | 'untagged';

const SHOW_OPTIONS: { value: Show; label: string }[] = [
  { value: '', label: 'Everyone' },
  { value: 'tagged', label: 'Teammates you tagged' },
  { value: 'untagged', label: 'Not tagged' },
];

/** Everyone you've shared a match with, with the teammates you tagged and your notes on them. */
export function Players() {
  const [show, setShow] = useState<Show>('');
  const [minGames, setMinGames] = useState(1);
  const [offset, setOffset] = useState(0);
  const tag = useTagPlayer();

  const players = useQuery({
    queryKey: ['players', show, minGames, offset],
    queryFn: () =>
      getPlayers({
        tagged: show === '' ? undefined : show === 'tagged',
        min_games: minGames,
        sort: '-games_with_me',
        limit: PAGE_SIZE,
        offset,
      }),
  });

  return (
    <div>
      <PageHeader title="Players" note="Everyone you've shared a match with, most games first">
        <SelectField
          label="Show"
          value={show}
          options={SHOW_OPTIONS}
          onChange={(value) => {
            setShow(value);
            setOffset(0);
          }}
        />
        <label>
          <span className="field-label">At least this many games</span>
          <input
            type="number"
            min={0}
            value={minGames}
            onChange={(e) => {
              // An emptied or unreadable box counts as no minimum
              setMinGames(Number.parseInt(e.target.value, 10) || 0);
              setOffset(0);
            }}
            className="field w-24"
          />
        </label>
      </PageHeader>

      <PagedList
        list={players.data}
        loading={players.isLoading}
        failed={!!players.error}
        failure="Players didn't load. Check that the server is running."
        empty={<NoDataEmpty message="No players match" description="Lower the game count or show everyone." />}
        offset={offset}
        onOffset={setOffset}
      >
        {(items) => (
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
              {items.map((player) => (
                <PlayerRow
                  key={player.player_id}
                  player={player}
                  // One change at a time: every star waits while one is saving
                  saving={tag.isPending}
                  onToggle={() => tag.mutate({ playerId: player.player_id, tagged: !player.is_tagged_teammate })}
                />
              ))}
            </tbody>
          </table>
        )}
      </PagedList>
    </div>
  );
}

function PlayerRow({ player, saving, onToggle }: { player: Player; saving: boolean; onToggle: () => void }) {
  return (
    <tr className="border-b last:border-b-0 border-[var(--color-border)]">
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
        <TagToggle tagged={player.is_tagged_teammate} name={player.display_name} disabled={saving} onToggle={onToggle} />
      </td>
      <td className="px-3 pr-5 py-3 text-[14px] text-[var(--color-text-muted)] max-w-56 truncate">
        {player.teammate_notes || '–'}
      </td>
    </tr>
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
