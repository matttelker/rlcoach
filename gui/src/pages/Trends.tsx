import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, ReferenceLine } from 'recharts';
import { getTrends } from '../api/client';
import { Card, SkeletonChart, ErrorState, NoDataEmpty, PageHeader, PlaylistSelect, SelectField } from '../components';
import { PERIOD_OPTIONS } from './coachTransforms';
import { hasBenchmarkValue, parseLocalDate } from './dataTransforms';
import { AXIS_PROPS, TOOLTIP_PROPS } from './chartStyle';

const METRIC_OPTIONS = [
  { value: 'bcpm', label: 'Boost used per minute' },
  { value: 'avg_boost', label: 'Average boost' },
  { value: 'goals', label: 'Goals' },
  { value: 'assists', label: 'Assists' },
  { value: 'saves', label: 'Saves' },
  { value: 'shots', label: 'Shots' },
  { value: 'epic_saves', label: 'Epic saves' },
  { value: 'clears', label: 'Clears from in front of your goal' },
  { value: 'centers', label: 'Centers' },
  { value: 'aerial_hits', label: 'Aerial hits' },
];

export function Trends() {
  const [metric, setMetric] = useState('bcpm');
  const [period, setPeriod] = useState('30d');
  const [playlist, setPlaylist] = useState<string>();
  const [showBenchmark, setShowBenchmark] = useState(true);

  const { data, isLoading, error } = useQuery({
    queryKey: ['trends', metric, period, playlist],
    queryFn: () => getTrends({ metric, period, playlist }),
  });

  const activePlaylist = playlist ?? data?.playlist;
  const rank = data?.rank ?? 'rank';
  const benchmarkValue = data?.rank_median;
  const hasBenchmark = showBenchmark && hasBenchmarkValue(benchmarkValue);

  const chartData =
    data?.values.map((v) => ({
      date: parseLocalDate(v.date).toLocaleDateString('en-US', { month: 'short', day: 'numeric' }),
      value: v.value,
    })) ?? [];

  const selectedMetric = METRIC_OPTIONS.find((m) => m.value === metric);

  return (
    <div>
      <PageHeader title="Trends" note="How one stat moves from day to day">
        <SelectField label="Stat" value={metric} options={METRIC_OPTIONS} onChange={setMetric} />
        <SelectField label="Period" value={period} options={PERIOD_OPTIONS} onChange={setPeriod} />
        <PlaylistSelect value={activePlaylist} onChange={setPlaylist} />
        <label className="flex items-center gap-2 h-[38px] text-[14px]">
          <input
            type="checkbox"
            checked={showBenchmark}
            onChange={(e) => setShowBenchmark(e.target.checked)}
            className="w-4 h-4 accent-[var(--color-primary)]"
          />
          Show the {rank} median
        </label>
      </PageHeader>

      <Card className="p-4 sm:p-6">
        <h2 className="type-display text-[19px] mb-5">{selectedMetric?.label}, by day</h2>
        {error ? (
          <ErrorState message="Trends didn't load. Check that the server is running." />
        ) : isLoading ? (
          <SkeletonChart />
        ) : chartData.length === 0 ? (
          <NoDataEmpty message="No games in this period" description="Try a longer period or another playlist." />
        ) : (
          <div className="h-80">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={chartData} margin={{ top: 8, right: 16, bottom: 0, left: -8 }}>
                <CartesianGrid vertical={false} stroke="var(--color-border)" />
                <XAxis dataKey="date" {...AXIS_PROPS} />
                <YAxis {...AXIS_PROPS} />
                <Tooltip {...TOOLTIP_PROPS} />
                {hasBenchmark && (
                  <ReferenceLine
                    y={benchmarkValue}
                    ifOverflow="extendDomain"
                    stroke="var(--color-text-muted)"
                    strokeDasharray="4 4"
                    label={{
                      value: `${rank} median`,
                      position: 'insideTopRight',
                      fill: 'var(--color-text-muted)',
                      fontSize: 13,
                    }}
                  />
                )}
                <Line
                  type="monotone"
                  dataKey="value"
                  stroke="var(--chart-ink)"
                  strokeWidth={2}
                  dot={{ r: 3, fill: 'var(--chart-ink)', strokeWidth: 0 }}
                  activeDot={{ r: 5, stroke: 'var(--color-bg-secondary)', strokeWidth: 2 }}
                  name={selectedMetric?.label}
                />
              </LineChart>
            </ResponsiveContainer>
          </div>
        )}
      </Card>
    </div>
  );
}
