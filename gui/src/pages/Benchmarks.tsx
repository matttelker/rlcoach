import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { getPatterns, getWeaknesses } from '../api/client';
import { Card, ErrorState, NoDataEmpty, PageHeader, PlaylistSelect, SelectField, SkeletonCard } from '../components';
import type { Pattern, PatternsResponse, Weakness } from '../types/api';
import { BENCHMARK_HINT, BENCHMARK_SOURCE, RANK_OPTIONS } from './dataTransforms';

// The page always looks at your last 30 days
const PERIOD = '30d';

const SEVERITY_MARK: Record<Weakness['severity'] | 'strength', string> = {
  critical: 'var(--chart-bad)',
  high: 'var(--chart-bad)',
  medium: 'var(--chart-flag)',
  low: 'var(--color-text-muted)',
  neutral: 'var(--color-border)',
  strength: 'var(--chart-good)',
};

/** Where you sit well off a rank's median, and which stats move with your wins. */
export function Benchmarks() {
  // Unset until you pick them, so the API opens on your config's rank and latest playlist
  const [pickedRank, setRank] = useState<string>();
  const [playlist, setPlaylist] = useState<string>();

  const spread = useQuery({
    queryKey: ['weaknesses', PERIOD, pickedRank, playlist],
    queryFn: () => getWeaknesses({ period: PERIOD, rank: pickedRank, playlist }),
  });
  const patterns = useQuery({
    queryKey: ['patterns', PERIOD, playlist],
    queryFn: () => getPatterns({ period: PERIOD, playlist }),
  });

  if (spread.error || patterns.error) {
    return <ErrorState message="Benchmarks didn't load. Check that the server is running." />;
  }

  const data = spread.data;
  const rank = pickedRank ?? data?.rank ?? '';
  const shownPlaylist = playlist ?? data?.playlist;
  // Why neither list can say anything, if it can't
  let nothing: Message | null = null;
  if (data?.game_count === 0) {
    nothing = { message: `No ${shownPlaylist} games in this period`, description: 'Try another playlist.' };
  } else if (data?.has_benchmarks === false) {
    nothing = { message: `No ${rank} benchmarks for ${shownPlaylist}`, description: BENCHMARK_HINT };
  }

  return (
    <div>
      <PageHeader
        title="Benchmarks"
        note={
          <>
            Your last 30 days against {rank || 'your rank'} players
            {data ? `, from ${data.game_count} games` : ''}.
            <span className="block text-[13px] mt-1">{BENCHMARK_SOURCE}</span>
          </>
        }
      >
        <SelectField label="Rank" value={rank} options={RANK_OPTIONS} onChange={setRank} />
        <PlaylistSelect value={shownPlaylist} onChange={setPlaylist} />
      </PageHeader>

      <div className="space-y-6">
        <div className="grid lg:grid-cols-2 gap-6 items-start">
          <Card className="p-5">
            <h2 className="type-display text-[19px] mb-4">Areas to improve</h2>
            <StatList
              loading={spread.isLoading}
              nothing={nothing}
              stats={data?.weaknesses}
              none={{
                message: 'Nothing below the usual range',
                description: `Your averages sit within the normal ${rank} range.`,
              }}
              rank={rank}
            />
          </Card>

          <Card className="p-5">
            <h2 className="type-display text-[19px] mb-4">Your strengths</h2>
            <StatList
              loading={spread.isLoading}
              nothing={nothing}
              stats={data?.strengths}
              none={{
                message: 'No strengths yet',
                description: 'Strengths show up once a stat sits clearly above the median.',
              }}
              rank={rank}
              strengths
            />
          </Card>
        </div>

        <WinsAgainstLosses loading={patterns.isLoading} data={patterns.data} />
      </div>
    </div>
  );
}

/** A heading and a line under it, for a list with nothing in it */
type Message = { message: string; description: string };

function StatList({
  loading,
  nothing,
  stats,
  none,
  rank,
  strengths = false,
}: {
  loading: boolean;
  /** Why there's nothing to compare, which comes before an empty list */
  nothing: Message | null;
  stats: Weakness[] | undefined;
  /** What to say when every stat sits in the usual range */
  none: Message;
  rank: string;
  strengths?: boolean;
}) {
  if (loading) return <SkeletonCard />;
  if (nothing) return <NoDataEmpty {...nothing} />;
  if (stats?.length === 0) return <NoDataEmpty {...none} />;
  return (
    <ul className="divide-y divide-[var(--color-border)]">
      {stats?.map((stat) => (
        <MetricRow key={stat.metric} item={stat} rank={rank} severity={strengths ? 'strength' : stat.severity} />
      ))}
    </ul>
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
        description={`Needs at least ${data.min_games} wins and ${data.min_games} losses in ${data.playlist}.`}
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

function MetricRow({
  item,
  rank,
  severity,
}: {
  item: { metric: string; my_value: number; target_median: number; z_score: number };
  rank: string;
  severity: Weakness['severity'] | 'strength';
}) {
  const side = item.z_score < 0 ? 'below' : 'above';
  return (
    <li className="grid grid-cols-[4px_minmax(0,1fr)] gap-x-4 py-3">
      <span className="rounded-full" style={{ background: SEVERITY_MARK[severity] }} aria-hidden="true" />
      <div>
        <div className="flex items-baseline justify-between gap-3">
          <span className="font-semibold">{item.metric.toUpperCase()}</span>
          <span className="text-[13px] text-[var(--color-text-muted)]">{severity === 'strength' ? 'Strength' : `${severity[0].toUpperCase()}${severity.slice(1)}`}</span>
        </div>
        <div className="text-[14px] mt-0.5">
          You {item.my_value.toFixed(2)}, {rank} median {item.target_median.toFixed(2)}
        </div>
        <div className="text-[13px] text-[var(--color-text-muted)] mt-0.5">
          {Math.abs(item.z_score).toFixed(1)} standard deviations {side} the median
        </div>
      </div>
    </li>
  );
}
