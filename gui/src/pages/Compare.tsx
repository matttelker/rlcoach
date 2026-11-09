import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Cell, ReferenceLine } from 'recharts';
import { getComparison } from '../api/client';
import { Card, SkeletonChart, ErrorState, NoDataEmpty, PageHeader, PlaylistSelect, SelectField } from '../components';
import { PERIOD_OPTIONS } from './coachTransforms';
import { BENCHMARK_HINT, BENCHMARK_SOURCE, RANK_OPTIONS, buildCompareChartData, isOnTarget } from './dataTransforms';
import { AXIS_PROPS, TOOLTIP_PROPS } from './chartStyle';

const signed = (value: number) => `${value > 0 ? '+' : ''}${value.toFixed(1)}%`;

export function Compare() {
  const [pickedRank, setRank] = useState<string>();
  const [period, setPeriod] = useState('30d');
  const [playlist, setPlaylist] = useState<string>();

  const { data, isLoading, error } = useQuery({
    queryKey: ['compare', pickedRank, period, playlist],
    queryFn: () => getComparison({ rank: pickedRank, period, playlist }),
  });
  const rank = pickedRank ?? data?.target_rank ?? '';

  const chartData = buildCompareChartData(data?.comparisons);
  const activePlaylist = playlist ?? data?.playlist;
  const noGames = (
    <NoDataEmpty
      message={`No ${activePlaylist ?? ''} games in this period`}
      description="Try a longer period or another playlist."
    />
  );

  if (error) {
    return <ErrorState message="The comparison didn't load. Check that the server is running." />;
  }

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
        <PlaylistSelect value={activePlaylist} onChange={setPlaylist} />
      </PageHeader>

      <div className="space-y-6">
        <Card className="p-4 sm:p-6">
          <h2 className="type-display text-[19px]">Gap to {rank || 'your rank'}</h2>
          <p className="text-[13px] text-[var(--color-text-muted)] mt-1 mb-5">
            Teal bars are on the right side of the median, red bars are short of it.
          </p>
          {isLoading ? (
            <SkeletonChart />
          ) : data?.game_count === 0 ? (
            noGames
          ) : chartData.length === 0 ? (
            <NoDataEmpty message={`No ${rank} benchmarks for ${activePlaylist}`} description={BENCHMARK_HINT} />
          ) : (
            <div style={{ height: Math.max(200, chartData.length * 44 + 40) }}>
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={chartData} layout="vertical" margin={{ top: 0, right: 16, bottom: 0, left: 0 }}>
                  <CartesianGrid horizontal={false} stroke="var(--color-border)" />
                  <XAxis type="number" {...AXIS_PROPS} tickFormatter={(v) => `${v > 0 ? '+' : ''}${v}%`} />
                  <YAxis type="category" dataKey="metric" {...AXIS_PROPS} width={88} />
                  <ReferenceLine x={0} stroke="var(--color-text-muted)" />
                  <Tooltip
                    {...TOOLTIP_PROPS}
                    cursor={{ fill: 'var(--color-bg-tertiary)' }}
                    formatter={(value) => [signed(Number(value) || 0), 'Against the median']}
                  />
                  <Bar dataKey="difference" barSize={18} radius={4}>
                    {chartData.map((entry) => (
                      <Cell key={entry.metric} fill={entry.onTarget ? 'var(--chart-good)' : 'var(--chart-bad)'} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>
          )}
        </Card>

        <Card className="overflow-x-auto">
          {isLoading ? (
            <div className="p-5 text-[var(--color-text-muted)]">Loading…</div>
          ) : data?.comparisons.length === 0 ? (
            noGames
          ) : (
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
                {data?.comparisons.map((c) => (
                  <tr key={c.metric} className="border-b last:border-b-0 border-[var(--color-border)]">
                    <td className="px-3 pl-5 py-3 font-semibold">{c.metric.toUpperCase()}</td>
                    <td className="px-3 py-3 text-right">{c.my_value.toFixed(2)}</td>
                    <td className="px-3 py-3 text-right text-[var(--color-text-muted)]">
                      {c.target_median?.toFixed(2) ?? '–'}
                    </td>
                    <td className="px-3 pr-5 py-3 text-right font-semibold">
                      {c.difference_pct !== null ? (
                        <span
                          className={
                            isOnTarget(c.difference_pct, c.direction)
                              ? 'text-[var(--color-success)]'
                              : 'text-[var(--color-error)]'
                          }
                        >
                          {signed(c.difference_pct)}
                        </span>
                      ) : (
                        '–'
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </Card>
      </div>
    </div>
  );
}
