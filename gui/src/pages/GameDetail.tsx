import { useParams, Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { getReplay } from '../api/client';
import { Card, SectionTitle, SkeletonCard, ErrorState } from '../components';
import type { PlayerStats } from '../types/api';
import { formatDuration, parseUtc, prettyPlaylist } from './dataTransforms';
import { GameReview } from './GameReview';
import { prettyMap } from './coachTransforms';

const RESULT_WORD: Record<string, { word: string; color: string }> = {
  WIN: { word: 'Win', color: 'text-[var(--color-success)]' },
  LOSS: { word: 'Loss', color: 'text-[var(--color-error)]' },
  DRAW: { word: 'Draw', color: 'text-[var(--color-warning)]' },
};

export function GameDetail() {
  const { replayId } = useParams<{ replayId: string }>();

  const { data, isLoading, error } = useQuery({
    queryKey: ['replay', replayId],
    queryFn: () => getReplay(replayId!),
    enabled: !!replayId,
  });

  if (error) {
    return <ErrorState message="This replay didn't load. Check that the server is running." />;
  }

  if (isLoading) {
    return (
      <div className="space-y-6">
        <SkeletonCard />
        <SkeletonCard />
      </div>
    );
  }

  if (!data) {
    return <ErrorState message="There's no replay with this id. It may have been removed." />;
  }

  const result = RESULT_WORD[data.result] ?? RESULT_WORD.DRAW;
  const played = parseUtc(data.played_at_utc);

  return (
    <div className="space-y-12">
      <header>
        <Link
          to="/games"
          className="inline-flex items-center gap-1 text-[14px] text-[var(--color-text-muted)] hover:text-[var(--color-text)]"
        >
          <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" aria-hidden="true">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
          </svg>
          Games
        </Link>
        <div className="flex flex-wrap items-end gap-x-6 gap-y-2 mt-4">
          <h1 className="type-score text-[76px] sm:text-[96px] leading-[0.85]">
            <span className="sr-only">{result.word}, </span>
            {data.my_score}–{data.opponent_score}
          </h1>
          <div className="pb-1">
            <div className={`type-display text-[26px] ${result.color}`} aria-hidden="true">
              {result.word}
            </div>
            <p className="text-[var(--color-text-muted)] mt-1">
              {prettyMap(data.map)}, {played.toLocaleDateString(undefined, { weekday: 'long', month: 'short', day: 'numeric' })}{' '}
              at {played.toLocaleTimeString(undefined, { hour: 'numeric', minute: '2-digit' })}
            </p>
          </div>
        </div>
      </header>

      <GameReview replayId={data.replay_id} />

      <section>
        <SectionTitle title="Match info" />
        <dl className="flex flex-wrap gap-x-10 gap-y-3 mb-5">
          <Fact label="Playlist" value={prettyPlaylist(data.playlist)} />
          <Fact label="Map" value={prettyMap(data.map)} />
          <Fact label="Length" value={formatDuration(data.duration_seconds)} />
          <Fact label="Final score" value={`${data.my_score}–${data.opponent_score}`} />
        </dl>
        <div className="grid md:grid-cols-2 gap-6">
          <TeamTable name="Blue team" color="var(--color-team-blue)" players={data.player_stats.filter((p) => p.team === 'BLUE')} />
          <TeamTable
            name="Orange team"
            color="var(--color-team-orange)"
            players={data.player_stats.filter((p) => p.team === 'ORANGE')}
          />
        </div>
      </section>
    </div>
  );
}

function Fact({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="text-[13px] text-[var(--color-text-muted)]">{label}</dt>
      <dd className="font-semibold mt-0.5">{value}</dd>
    </div>
  );
}

const STAT_COLUMNS = [
  { key: 'goals', short: 'G', long: 'Goals' },
  { key: 'assists', short: 'A', long: 'Assists' },
  { key: 'saves', short: 'Sv', long: 'Saves' },
  { key: 'shots', short: 'Sh', long: 'Shots' },
] as const;

function TeamTable({ name, color, players }: { name: string; color: string; players: PlayerStats[] }) {
  return (
    <Card className="overflow-hidden">
      <div className="h-1" style={{ background: color }} />
      <h3 className="type-display text-[17px] px-5 pt-4 pb-2">{name}</h3>
      <table className="w-full">
        <thead>
          <tr className="border-b border-[var(--color-border)]">
            <th className="th text-left pl-5">Player</th>
            {STAT_COLUMNS.map((col) => (
              <th key={col.key} className="th text-right w-12 last:pr-5">
                <abbr title={col.long} className="no-underline">
                  {col.short}
                </abbr>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {players.map((player) => (
            <tr key={player.player_id} className="border-b last:border-b-0 border-[var(--color-border)]">
              <td className="px-3 pl-5 py-3">
                <span className="inline-flex items-center gap-2">
                  <span className={player.is_me ? 'font-semibold' : ''}>{player.display_name}</span>
                  {player.is_me && (
                    <span className="text-[12px] font-semibold px-1.5 py-px rounded-sm bg-[var(--color-primary)] text-[var(--color-on-primary)]">
                      You
                    </span>
                  )}
                </span>
              </td>
              {STAT_COLUMNS.map((col) => (
                <td key={col.key} className="px-3 py-3 text-right last:pr-5">
                  {player[col.key]}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </Card>
  );
}
