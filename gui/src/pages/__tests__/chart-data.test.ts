import { describe, expect, it } from 'vitest';

import {
  buildCompareChartData,
  buildGamesParams,
  formatDuration,
  hasBenchmarkValue,
  isOnTarget,
  parseLocalDate,
  parseUtc,
  prettyPlaylist,
} from '../dataTransforms';
import type { Comparison } from '../../types/api';

describe('Trends benchmark handling', () => {
  it('treats zero-valued benchmarks as present', () => {
    expect(hasBenchmarkValue(0)).toBe(true);
    expect(hasBenchmarkValue(null)).toBe(false);
    expect(hasBenchmarkValue(undefined)).toBe(false);
  });
});

describe('Compare chart data', () => {
  it('does not coerce unavailable percentage differences into zero bars', () => {
    const comparisons: Comparison[] = [
      {
        metric: 'bcpm',
        my_value: 0,
        target_median: 50,
        difference: null,
        difference_pct: null,
        direction: 'higher',
      },
      {
        metric: 'goals',
        my_value: 2,
        target_median: 1,
        difference: 1,
        difference_pct: 100,
        direction: 'higher',
      },
    ];

    expect(buildCompareChartData(comparisons)).toEqual([
      {
        metric: 'GOALS',
        difference: 100,
        onTarget: true,
        myValue: 2,
        targetMedian: 1,
      },
    ]);
  });

  it('treats being under target as good for lower-is-better metrics', () => {
    expect(isOnTarget(-10, 'lower')).toBe(true);
    expect(isOnTarget(10, 'lower')).toBe(false);
    expect(isOnTarget(10, 'higher')).toBe(true);
    expect(isOnTarget(-10, 'higher')).toBe(false);
  });
});

describe('Date parsing', () => {
  it('reads offset-less API timestamps as UTC', () => {
    expect(parseUtc('2026-11-01T03:56:53').toISOString()).toBe('2026-11-01T03:56:53.000Z');
  });

  it('keeps timestamps that already carry an offset', () => {
    expect(parseUtc('2026-11-01T03:56:53Z').toISOString()).toBe('2026-11-01T03:56:53.000Z');
    expect(parseUtc('2026-11-01T03:56:53+01:00').toISOString()).toBe('2026-11-01T02:56:53.000Z');
  });

  it('keeps a play date on its own calendar day in any timezone', () => {
    expect(parseLocalDate('2026-10-31').getDate()).toBe(31);
  });
});

describe('Games query params', () => {
  it('omits the result param when All Results is selected', () => {
    expect(
      buildGamesParams({
        playlist: '',
        result: '',
        limit: 20,
        offset: 0,
      }),
    ).toEqual({
      playlist: undefined,
      result: undefined,
      limit: 20,
      offset: 0,
    });
  });
});

describe('labels', () => {
  it('writes playlist ids as words', () => {
    expect(prettyPlaylist('STANDARD')).toBe('Standard');
    expect(prettyPlaylist('DUEL')).toBe('Duel');
  });

  it('writes game length as minutes and padded seconds', () => {
    expect(formatDuration(458.4)).toBe('7:38');
    expect(formatDuration(305)).toBe('5:05');
  });
});
