import type { GamesParams } from '../api/client';
import type { Comparison, GameResult } from '../types/api';

export type { GameResult } from '../types/api';

export type GameFilters = Required<Pick<GamesParams, 'playlist' | 'limit' | 'offset'>> & {
  result: GameResult | '';
};

export const BENCHMARK_HINT =
  'Bundled benchmarks cover C2, C3 and GC1 for Doubles and Standard. Add more with rlcoach benchmarks import.';

export const BENCHMARK_SOURCE =
  'Benchmarks are ballchasing.com averages. GC1 combines every Grand Champion tier.';

// The API sends UTC timestamps with no offset, which browsers would read as local.
export function parseUtc(value: string): Date {
  return new Date(/(Z|[+-]\d{2}:\d{2})$/.test(value) ? value : `${value}Z`);
}

// Date-only strings parse as UTC midnight, which lands on the previous day west of UTC.
export function parseLocalDate(value: string): Date {
  return new Date(`${value}T00:00:00`);
}

export function isOnTarget(differencePct: number, direction: Comparison['direction']): boolean {
  return direction === 'lower' ? differencePct <= 0 : differencePct >= 0;
}

export function hasBenchmarkValue(value: number | null | undefined): value is number {
  return value != null;
}

export function buildCompareChartData(comparisons: Comparison[] = []) {
  return comparisons
    .filter(
      (c): c is Comparison & { target_median: number; difference_pct: number } =>
        c.target_median !== null && c.difference_pct !== null,
    )
    .map((c) => ({
      metric: c.metric.toUpperCase(),
      difference: c.difference_pct,
      onTarget: isOnTarget(c.difference_pct, c.direction),
      myValue: c.my_value,
      targetMedian: c.target_median,
    }));
}

export function buildGamesParams(filters: GameFilters): GamesParams {
  return {
    playlist: filters.playlist || undefined,
    result: filters.result || undefined,
    limit: filters.limit,
    offset: filters.offset,
  };
}
