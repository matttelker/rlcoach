import type { Comparison } from '../types/api';

// The ranks with benchmarks, highest first. RANKS in metrics.py is the source.
export const RANK_OPTIONS = ['GC', 'C3', 'C2', 'C1', 'D3', 'D2', 'D1', 'P3', 'P2', 'P1', 'G3', 'G2', 'G1'].map(
  (r) => ({ value: r, label: r }),
);

export const BENCHMARK_HINT = 'Benchmarks cover Doubles and Standard, from G1 to GC. Duel has none.';

export const BENCHMARK_SOURCE =
  'Benchmarks are ballchasing.com averages. GC combines every Grand Champion tier.';

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

/** A percentage with its sign, such as +4.0% or -21.1% */
export const signedPct = (value: number) => `${value > 0 ? '+' : ''}${value.toFixed(1)}%`;

/** One bar of Compare's chart: how far a stat sits from the rank's median, in percent */
export interface GapBar {
  metric: string;
  difference: number;
  onTarget: boolean;
  myValue: number;
  targetMedian: number;
}

/** The bars for the stats that have a median to compare with. The rest have no gap to draw. */
export function gapBars(comparisons: Comparison[]): GapBar[] {
  const bars: GapBar[] = [];
  for (const { metric, my_value, target_median, difference_pct, direction } of comparisons) {
    if (target_median === null || difference_pct === null) continue;
    bars.push({
      metric: metric.toUpperCase(),
      difference: difference_pct,
      onTarget: isOnTarget(difference_pct, direction),
      myValue: my_value,
      targetMedian: target_median,
    });
  }
  return bars;
}

// Playlists arrive as ids like "STANDARD"
export function prettyPlaylist(playlist: string): string {
  return playlist.charAt(0) + playlist.slice(1).toLowerCase();
}

// Game length as m:ss
export function formatDuration(seconds: number): string {
  return `${Math.floor(seconds / 60)}:${String(Math.floor(seconds % 60)).padStart(2, '0')}`;
}
