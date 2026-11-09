import { describe, expect, it } from 'vitest';

import {
  formatDuration,
  gapBars,
  isOnTarget,
  parseLocalDate,
  parseUtc,
  prettyPlaylist,
  signedPct,
} from '../dataTransforms';
import type { Comparison } from '../../types/api';

const comparison = (overrides: Partial<Comparison>): Comparison => ({
  metric: 'bcpm',
  my_value: 206.69,
  target_median: 261.9,
  difference: -55.21,
  difference_pct: -21.1,
  direction: 'higher',
  ...overrides,
});

describe('gapBars', () => {
  it('draws a bar for each stat with a median, named in capitals', () => {
    expect(gapBars([comparison({})])).toEqual([
      { metric: 'BCPM', difference: -21.1, onTarget: false, myValue: 206.69, targetMedian: 261.9 },
    ]);
  });

  it('leaves out a stat with no median rather than drawing it at zero', () => {
    const noMedian = comparison({ metric: 'epic_saves', target_median: null, difference: null, difference_pct: null });
    expect(gapBars([noMedian, comparison({ metric: 'goals', difference_pct: 20 })]).map((bar) => bar.metric)).toEqual([
      'GOALS',
    ]);
  });

  it('keeps a stat that sits exactly on the median', () => {
    expect(gapBars([comparison({ difference: 0, difference_pct: 0 })])).toHaveLength(1);
  });

  it('marks the bar on target by which way is better for the stat', () => {
    const [lowBoost] = gapBars([comparison({ metric: 'avg_boost', difference_pct: -14.3, direction: 'lower' })]);
    expect(lowBoost.onTarget).toBe(true);
  });

  it('has nothing to draw without comparisons', () => {
    expect(gapBars([])).toEqual([]);
  });
});

describe('isOnTarget', () => {
  it('counts under the median as good for a stat where lower is better', () => {
    expect(isOnTarget(-10, 'lower')).toBe(true);
    expect(isOnTarget(10, 'lower')).toBe(false);
  });

  it('counts over the median as good for a stat where higher is better', () => {
    expect(isOnTarget(10, 'higher')).toBe(true);
    expect(isOnTarget(-10, 'higher')).toBe(false);
  });

  it('counts the median itself as on target either way', () => {
    expect(isOnTarget(0, 'higher')).toBe(true);
    expect(isOnTarget(0, 'lower')).toBe(true);
  });
});

describe('signedPct', () => {
  it('writes a gain with a plus sign and one decimal', () => {
    expect(signedPct(4)).toBe('+4.0%');
  });

  it('writes a shortfall with its minus sign', () => {
    expect(signedPct(-21.14)).toBe('-21.1%');
  });

  it('writes no sign on zero', () => {
    expect(signedPct(0)).toBe('0.0%');
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
