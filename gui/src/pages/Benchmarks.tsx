import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { getWeaknesses, getPatterns } from '../api/client';
import type { Weakness } from '../types/api';
import { Card, SkeletonCard, ErrorState, NoDataEmpty, PageHeader, PlaylistSelect, SelectField } from '../components';
import { BENCHMARK_HINT, BENCHMARK_SOURCE, RANK_OPTIONS } from './dataTransforms';

const SEVERITY_MARK: Record<Weakness['severity'] | 'strength', string> = {
  critical: 'var(--chart-bad)',
  high: 'var(--chart-bad)',
  medium: 'var(--chart-flag)',
  low: 'var(--color-text-muted)',
  neutral: 'var(--color-border)',
  strength: 'var(--chart-good)',
};

export function Benchmarks() {
  const [period] = useState('30d');
  const [pickedRank, setRank] = useState<string>();
  const [playlist, setPlaylist] = useState<string>();

  const { data: weaknessesData, isLoading: weaknessesLoading, error: weaknessesError } = useQuery({
    queryKey: ['weaknesses', period, pickedRank, playlist],
    queryFn: () => getWeaknesses({ period, rank: pickedRank, playlist }),
  });
  const rank = pickedRank ?? weaknessesData?.rank ?? '';

  const { data: patternsData, isLoading: patternsLoading, error: patternsError } = useQuery({
    queryKey: ['patterns', period, playlist],
    queryFn: () => getPatterns({ period, playlist }),
  });

  if (weaknessesError || patternsError) {
    return <ErrorState message="Benchmarks didn't load. Check that the server is running." />;
  }

  const activePlaylist = playlist ?? weaknessesData?.playlist;
  const missingData =
    weaknessesData?.game_count === 0
      ? {
          message: `No ${activePlaylist} games in this period`,
          description: 'Try another playlist.',
        }
      : weaknessesData?.has_benchmarks === false
        ? { message: `No ${rank} benchmarks for ${activePlaylist}`, description: BENCHMARK_HINT }
        : null;

  return (
    <div>
      <PageHeader
        title="Benchmarks"
        note={
          <>
            Your last 30 days against {rank || 'your rank'} players
            {weaknessesData ? `, from ${weaknessesData.game_count} games` : ''}.
            <span className="block text-[13px] mt-1">{BENCHMARK_SOURCE}</span>
          </>
        }
      >
        <SelectField label="Rank" value={rank} options={RANK_OPTIONS} onChange={setRank} />
        <PlaylistSelect value={activePlaylist} onChange={setPlaylist} />
      </PageHeader>

      <div className="space-y-6">
        <div className="grid lg:grid-cols-2 gap-6 items-start">
          <Card className="p-5">
            <h2 className="type-display text-[19px] mb-4">Areas to improve</h2>
            {weaknessesLoading ? (
              <SkeletonCard />
            ) : missingData ? (
              <NoDataEmpty {...missingData} />
            ) : weaknessesData?.weaknesses.length === 0 ? (
              <NoDataEmpty
                message="Nothing below the usual range"
                description={`Your averages sit within the normal ${rank} range.`}
              />
            ) : (
              <ul className="divide-y divide-[var(--color-border)]">
                {weaknessesData?.weaknesses.map((w) => (
                  <MetricRow key={w.metric} item={w} rank={rank} severity={w.severity} />
                ))}
              </ul>
            )}
          </Card>

          <Card className="p-5">
            <h2 className="type-display text-[19px] mb-4">Your strengths</h2>
            {weaknessesLoading ? (
              <SkeletonCard />
            ) : missingData ? (
              <NoDataEmpty {...missingData} />
            ) : weaknessesData?.strengths.length === 0 ? (
              <NoDataEmpty message="No strengths yet" description="Strengths show up once a stat sits clearly above the median." />
            ) : (
              <ul className="divide-y divide-[var(--color-border)]">
                {weaknessesData?.strengths.map((s) => (
                  <MetricRow key={s.metric} item={s} rank={rank} severity="strength" />
                ))}
              </ul>
            )}
          </Card>
        </div>

        <Card className="p-5">
          <h2 className="type-display text-[19px]">Wins against losses</h2>
          {patternsData && (
            <p className="text-[13px] text-[var(--color-text-muted)] mt-1">
              From {patternsData.win_count} wins and {patternsData.loss_count} losses
            </p>
          )}
          <div className="mt-4">
            {patternsLoading ? (
              <SkeletonCard />
            ) : patternsData?.patterns.length === 0 ? (
              <NoDataEmpty
                message="Not enough games yet"
                description={`Needs at least ${patternsData?.min_games} wins and ${patternsData?.min_games} losses in ${patternsData?.playlist}.`}
              />
            ) : (
              <ul className="divide-y divide-[var(--color-border)]">
                {patternsData?.patterns.map((p) => (
                  <li key={p.metric} className="flex items-center justify-between gap-4 py-3">
                    <div>
                      <div className="font-semibold">{p.metric.toUpperCase()}</div>
                      <div className="text-[14px] text-[var(--color-text-muted)]">
                        {p.win_avg.toFixed(2)} in wins, {p.loss_avg.toFixed(2)} in losses
                      </div>
                    </div>
                    <div className="text-right">
                      <div
                        className={`type-score text-[26px] ${
                          p.direction === 'higher_in_wins' ? 'text-[var(--color-success)]' : 'text-[var(--color-error)]'
                        }`}
                      >
                        {p.direction === 'higher_in_wins' ? '+' : ''}
                        {p.delta.toFixed(2)}
                      </div>
                      <div className="text-[13px] text-[var(--color-text-muted)]">Effect size {p.effect_size.toFixed(2)}</div>
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </Card>
      </div>
    </div>
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
