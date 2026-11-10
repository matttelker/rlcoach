import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { getComparison, getPatterns } from '../api/client';
import { Card, ErrorState, NoDataEmpty, PageHeader, PlaylistSelect, SelectField, SkeletonCard } from '../components';
import type { CompareResponse, ContextStat, Pattern, PatternsResponse, Placement } from '../types/api';
import { PERIOD_OPTIONS } from './coachTransforms';
import {
  BALLCHASING_COUNT_NOTE,
  BENCHMARK_HINT,
  BENCHMARK_SOURCE,
  RANK_OPTIONS,
  formatStat,
  placementSentence,
  prettyPlaylist,
  rankName,
  statName,
} from './dataTransforms';

const VERDICT_MARK: Record<Placement['verdict'], string> = {
  above: 'var(--chart-good)',
  below: 'var(--chart-bad)',
  level: 'var(--color-text-muted)',
  too_few: 'var(--color-border)',
};

/** Where your stats sit among the ranks, and which ones move with your wins. */
export function Compare() {
  // Rank and playlist stay unset until you pick them, so the API opens on your config's rank and latest playlist
  const [pickedRank, setRank] = useState<string>();
  const [period, setPeriod] = useState('30d');
  const [playlist, setPlaylist] = useState<string>();

  const comparison = useQuery({
    queryKey: ['compare', pickedRank, period, playlist],
    queryFn: () => getComparison({ rank: pickedRank, period, playlist }),
  });
  const patterns = useQuery({
    queryKey: ['patterns', period, playlist],
    queryFn: () => getPatterns({ period, playlist }),
  });

  if (comparison.error || patterns.error) {
    return <ErrorState message="The comparison didn't load. Check that the server is running." />;
  }

  const data = comparison.data;
  const rank = pickedRank ?? data?.target_rank ?? '';
  const shownPlaylist = playlist ?? data?.playlist;

  return (
    <div>
      <PageHeader
        title="Compare"
        note={
          <>
            Your averages against {rank ? rankName(rank) : 'a rank'}
            {data ? `, from ${data.game_count} games` : ''}.
            <span className="block text-[13px] mt-1">{BENCHMARK_SOURCE}</span>
          </>
        }
      >
        <SelectField label="Rank" value={rank} options={RANK_OPTIONS} onChange={setRank} />
        <SelectField label="Period" value={period} options={PERIOD_OPTIONS} onChange={setPeriod} />
        <PlaylistSelect value={shownPlaylist} onChange={setPlaylist} />
      </PageHeader>

      <div className="space-y-6">
        <RankCard loading={comparison.isLoading} data={data} rank={rank} />
        <WinsAgainstLosses loading={patterns.isLoading} data={patterns.data} />
      </div>
    </div>
  );
}

function RankCard({ loading, data, rank }: { loading: boolean; data: CompareResponse | undefined; rank: string }) {
  let body;
  if (loading || !data) {
    body = <SkeletonCard />;
  } else if (data.game_count === 0) {
    body = (
      <NoDataEmpty
        message={`No ${prettyPlaylist(data.playlist)} games in this period`}
        description="Try a longer period or another playlist."
      />
    );
  } else if (data.placements.length === 0 && data.context.length === 0) {
    body = (
      <NoDataEmpty
        message={`No ${rankName(rank)} benchmarks for ${prettyPlaylist(data.playlist)}`}
        description={BENCHMARK_HINT}
      />
    );
  } else {
    body = (
      <>
        <ul className="divide-y divide-[var(--color-border)]">
          {data.placements.map((placement) => (
            <PlacementRow key={placement.metric} placement={placement} rank={rank} minGames={data.min_games} />
          ))}
        </ul>
        {data.context.length > 0 && <ContextTable rank={rank} stats={data.context} />}
      </>
    );
  }
  return (
    <Card className="p-5">
      <h2 className="type-display text-[19px] mb-4">Against {rank ? rankName(rank) : 'your rank'}</h2>
      {body}
    </Card>
  );
}

/** One stat that rises with rank: you, the rank's average, and what the gap means */
function PlacementRow({ placement, rank, minGames }: { placement: Placement; rank: string; minGames: number }) {
  return (
    <li className="grid grid-cols-[4px_minmax(0,1fr)] gap-x-4 py-3">
      <span className="rounded-full" style={{ background: VERDICT_MARK[placement.verdict] }} aria-hidden="true" />
      <div>
        <div className="font-semibold">{statName(placement.metric)}</div>
        <div className="text-[14px] mt-0.5">
          You {formatStat(placement.my_value)}, {rankName(rank)} average {formatStat(placement.target_average)}
        </div>
        <div className="text-[14px] mt-0.5">{placementSentence(placement, rank, minGames)}</div>
        {placement.scaled && (
          <div className="text-[13px] text-[var(--color-text-muted)] mt-0.5">
            {BALLCHASING_COUNT_NOTE}
          </div>
        )}
      </div>
    </li>
  );
}

/** Benchmarked stats that don't separate ranks, shown plainly beside the rank's average */
function ContextTable({ rank, stats }: { rank: string; stats: ContextStat[] }) {
  return (
    <div className="mt-6">
      <h3 className="font-semibold">Other stats</h3>
      <p className="text-[13px] text-[var(--color-text-muted)] mt-1 mb-3">
        These barely change from rank to rank, so they say little about your rank.
      </p>
      <table className="w-full">
        <thead>
          <tr className="border-b border-[var(--color-border)]">
            <th className="th text-left">Stat</th>
            <th className="th text-right">You</th>
            <th className="th text-right">{rankName(rank)} average</th>
          </tr>
        </thead>
        <tbody>
          {stats.map((stat) => (
            <tr key={stat.metric} className="border-b last:border-b-0 border-[var(--color-border)]">
              <td className="px-3 py-2">{statName(stat.metric)}</td>
              <td className="px-3 py-2 text-right">{formatStat(stat.my_value)}</td>
              <td className="px-3 py-2 text-right text-[var(--color-text-muted)]">{formatStat(stat.target_average)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function WinsAgainstLosses({ loading, data }: { loading: boolean; data: PatternsResponse | undefined }) {
  let body;
  if (loading) {
    body = <SkeletonCard />;
  } else if (data?.patterns.length === 0) {
    body = (
      <NoDataEmpty
        message="Not enough games yet"
        description={`Needs at least ${data.min_games} wins and ${data.min_games} losses in ${prettyPlaylist(data.playlist)}.`}
      />
    );
  } else {
    body = (
      <ul className="divide-y divide-[var(--color-border)]">
        {data?.patterns.map((pattern) => (
          <PatternRow key={pattern.metric} pattern={pattern} />
        ))}
      </ul>
    );
  }
  return (
    <Card className="p-5">
      <h2 className="type-display text-[19px]">Wins against losses</h2>
      {data && (
        <p className="text-[13px] text-[var(--color-text-muted)] mt-1">
          From {data.win_count} wins and {data.loss_count} losses
        </p>
      )}
      <div className="mt-4">{body}</div>
    </Card>
  );
}

/** A stat with its average in wins and in losses. Green when more of it goes with winning. */
function PatternRow({ pattern }: { pattern: Pattern }) {
  const helps = pattern.direction === 'higher_in_wins';
  return (
    <li className="flex items-center justify-between gap-4 py-3">
      <div>
        <div className="font-semibold">{pattern.metric.toUpperCase()}</div>
        <div className="text-[14px] text-[var(--color-text-muted)]">
          {pattern.win_avg.toFixed(2)} in wins, {pattern.loss_avg.toFixed(2)} in losses
        </div>
      </div>
      <div className="text-right">
        <div className={`type-score text-[26px] ${helps ? 'text-[var(--color-success)]' : 'text-[var(--color-error)]'}`}>
          {helps ? '+' : ''}
          {pattern.delta.toFixed(2)}
        </div>
        <div className="text-[13px] text-[var(--color-text-muted)]">Effect size {pattern.effect_size.toFixed(2)}</div>
      </div>
    </li>
  );
}
