import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { CartesianGrid, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { getTrends } from '../api/client';
import { Card, ErrorState, NoDataEmpty, PageHeader, PlaylistSelect, SelectField, SkeletonChart } from '../components';
import { PERIOD_OPTIONS } from './coachTransforms';
import { parseLocalDate } from './dataTransforms';
import { AXIS_PROPS, TOOLTIP_PROPS } from './chartStyle';

// The stats you can follow, each one the API keeps per game
const STATS = [
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

/** One stat of yours day by day, against your rank's median. */
export function Trends() {
  const [metric, setMetric] = useState('bcpm');
  const [period, setPeriod] = useState('30d');
  // Unset until you pick one, so the API opens on the playlist of your latest game
  const [playlist, setPlaylist] = useState<string>();
  const [showMedian, setShowMedian] = useState(true);

  const trend = useQuery({
    queryKey: ['trends', metric, period, playlist],
    queryFn: () => getTrends({ metric, period, playlist }),
  });

  const rank = trend.data?.rank ?? 'rank';
  const label = STATS.find((stat) => stat.value === metric)?.label;
  // A median of 0 is still a median to draw
  const median = showMedian ? (trend.data?.rank_median ?? null) : null;
  const days = (trend.data?.values ?? []).map(({ date, value }) => ({
    date: parseLocalDate(date).toLocaleDateString('en-US', { month: 'short', day: 'numeric' }),
    value,
  }));

  let chart;
  if (trend.error) {
    chart = <ErrorState message="Trends didn't load. Check that the server is running." />;
  } else if (trend.isLoading) {
    chart = <SkeletonChart />;
  } else if (days.length === 0) {
    chart = <NoDataEmpty message="No games in this period" description="Try a longer period or another playlist." />;
  } else {
    chart = (
      <div className="h-80">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={days} margin={{ top: 8, right: 16, bottom: 0, left: -8 }}>
            <CartesianGrid vertical={false} stroke="var(--color-border)" />
            <XAxis dataKey="date" {...AXIS_PROPS} />
            <YAxis {...AXIS_PROPS} />
            <Tooltip {...TOOLTIP_PROPS} />
            {median !== null && (
              <ReferenceLine
                y={median}
                ifOverflow="extendDomain"
                stroke="var(--color-text-muted)"
                strokeDasharray="4 4"
                label={{ value: `${rank} median`, position: 'insideTopRight', fill: 'var(--color-text-muted)', fontSize: 13 }}
              />
            )}
            <Line
              type="monotone"
              dataKey="value"
              name={label}
              stroke="var(--chart-ink)"
              strokeWidth={2}
              dot={{ r: 3, fill: 'var(--chart-ink)', strokeWidth: 0 }}
              activeDot={{ r: 5, stroke: 'var(--color-bg-secondary)', strokeWidth: 2 }}
            />
          </LineChart>
        </ResponsiveContainer>
      </div>
    );
  }

  return (
    <div>
      <PageHeader title="Trends" note="How one stat moves from day to day">
        <SelectField label="Stat" value={metric} options={STATS} onChange={setMetric} />
        <SelectField label="Period" value={period} options={PERIOD_OPTIONS} onChange={setPeriod} />
        <PlaylistSelect value={playlist ?? trend.data?.playlist} onChange={setPlaylist} />
        <label className="flex items-center gap-2 h-[38px] text-[14px]">
          <input
            type="checkbox"
            className="w-4 h-4 accent-[var(--color-primary)]"
            checked={showMedian}
            onChange={(e) => setShowMedian(e.target.checked)}
          />
          Show the {rank} median
        </label>
      </PageHeader>

      <Card className="p-4 sm:p-6">
        <h2 className="type-display text-[19px] mb-5">{label}, by day</h2>
        {chart}
      </Card>
    </div>
  );
}
