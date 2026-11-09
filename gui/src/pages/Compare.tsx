import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Bar, BarChart, CartesianGrid, Cell, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { getComparison } from '../api/client';
import { Card, ErrorState, NoDataEmpty, PageHeader, PlaylistSelect, SelectField, SkeletonChart } from '../components';
import type { Comparison } from '../types/api';
import { PERIOD_OPTIONS } from './coachTransforms';
import { BENCHMARK_HINT, BENCHMARK_SOURCE, RANK_OPTIONS, gapBars, isOnTarget, signedPct, type GapBar } from './dataTransforms';
import { AXIS_PROPS, TOOLTIP_PROPS } from './chartStyle';

/** Your averages against a rank's median: a bar chart of the gaps, then the numbers. */
export function Compare() {
  // Rank and playlist stay unset until you pick them, so the API opens on your config's rank and latest playlist
  const [pickedRank, setRank] = useState<string>();
  const [period, setPeriod] = useState('30d');
  const [playlist, setPlaylist] = useState<string>();

  const comparison = useQuery({
    queryKey: ['compare', pickedRank, period, playlist],
    queryFn: () => getComparison({ rank: pickedRank, period, playlist }),
  });

  if (comparison.error) {
    return <ErrorState message="The comparison didn't load. Check that the server is running." />;
  }

  const data = comparison.data;
  const loading = comparison.isLoading;
  const rank = pickedRank ?? data?.target_rank ?? '';
  const shownPlaylist = playlist ?? data?.playlist;
  const bars = gapBars(data?.comparisons ?? []);
  const noGames = (
    <NoDataEmpty
      message={`No ${shownPlaylist ?? ''} games in this period`}
      description="Try a longer period or another playlist."
    />
  );

  let chart;
  if (loading) chart = <SkeletonChart />;
  else if (data?.game_count === 0) chart = noGames;
  else if (bars.length === 0)
    chart = <NoDataEmpty message={`No ${rank} benchmarks for ${shownPlaylist}`} description={BENCHMARK_HINT} />;
  else chart = <GapChart bars={bars} />;

  let table;
  if (loading) table = <div className="p-5 text-[var(--color-text-muted)]">Loading…</div>;
  else if (data?.comparisons.length === 0) table = noGames;
  else table = <GapTable rank={rank} comparisons={data?.comparisons ?? []} />;

  return (
    <div>
      <PageHeader
        title="Compare"
        note={
          <>
            Your averages against a rank's median{data ? `, from ${data.game_count} games` : ''}.
            <span className="block text-[13px] mt-1">{BENCHMARK_SOURCE}</span>
          </>
        }
      >
        <SelectField label="Rank" value={rank} options={RANK_OPTIONS} onChange={setRank} />
        <SelectField label="Period" value={period} options={PERIOD_OPTIONS} onChange={setPeriod} />
        <PlaylistSelect value={shownPlaylist} onChange={setPlaylist} />
      </PageHeader>

      <div className="space-y-6">
        <Card className="p-4 sm:p-6">
          <h2 className="type-display text-[19px]">Gap to {rank || 'your rank'}</h2>
          <p className="text-[13px] text-[var(--color-text-muted)] mt-1 mb-5">
            Teal bars are on the right side of the median, red bars are short of it.
          </p>
          {chart}
        </Card>

        <Card className="overflow-x-auto">{table}</Card>
      </div>
    </div>
  );
}

/** One bar per stat, out from zero: teal on the good side of the median, red short of it */
function GapChart({ bars }: { bars: GapBar[] }) {
  return (
    <div style={{ height: Math.max(200, bars.length * 44 + 40) }}>
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={bars} layout="vertical" margin={{ top: 0, right: 16, bottom: 0, left: 0 }}>
          <CartesianGrid horizontal={false} stroke="var(--color-border)" />
          <XAxis type="number" {...AXIS_PROPS} tickFormatter={(v) => `${v > 0 ? '+' : ''}${v}%`} />
          <YAxis type="category" dataKey="metric" {...AXIS_PROPS} width={88} />
          <ReferenceLine x={0} stroke="var(--color-text-muted)" />
          <Tooltip
            {...TOOLTIP_PROPS}
            cursor={{ fill: 'var(--color-bg-tertiary)' }}
            formatter={(value) => [signedPct(Number(value) || 0), 'Against the median']}
          />
          <Bar dataKey="difference" barSize={18} radius={4}>
            {bars.map((bar) => (
              <Cell key={bar.metric} fill={bar.onTarget ? 'var(--chart-good)' : 'var(--chart-bad)'} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

function GapTable({ rank, comparisons }: { rank: string; comparisons: Comparison[] }) {
  return (
    <table className="w-full min-w-[32rem]">
      <thead>
        <tr className="border-b border-[var(--color-border)]">
          <th className="th text-left pl-5">Stat</th>
          <th className="th text-right">You</th>
          <th className="th text-right">{rank} median</th>
          <th className="th text-right pr-5">Difference</th>
        </tr>
      </thead>
      <tbody>
        {comparisons.map((c) => (
          <tr key={c.metric} className="border-b last:border-b-0 border-[var(--color-border)]">
            <td className="px-3 pl-5 py-3 font-semibold">{c.metric.toUpperCase()}</td>
            <td className="px-3 py-3 text-right">{c.my_value.toFixed(2)}</td>
            <td className="px-3 py-3 text-right text-[var(--color-text-muted)]">{c.target_median?.toFixed(2) ?? '–'}</td>
            <td className="px-3 pr-5 py-3 text-right font-semibold">
              {c.difference_pct === null ? '–' : <Gap pct={c.difference_pct} onTarget={isOnTarget(c.difference_pct, c.direction)} />}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function Gap({ pct, onTarget }: { pct: number; onTarget: boolean }) {
  return (
    <span className={onTarget ? 'text-[var(--color-success)]' : 'text-[var(--color-error)]'}>{signedPct(pct)}</span>
  );
}
