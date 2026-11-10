import { describe, expect, it } from 'vitest';

import {
  formatDuration,
  formatStat,
  parseLocalDate,
  parseUtc,
  placementSentence,
  prettyPlaylist,
  rankName,
  statName,
} from '../dataTransforms';
import type { Placement } from '../../types/api';

const placement = (overrides: Partial<Placement>): Placement => ({
  metric: 'saves',
  games: 31,
  my_value: 1.1,
  target_average: 1.4,
  gap: -0.3,
  margin: 0.2,
  verdict: 'below',
  level_low: 'G1',
  level_high: 'G1',
  scaled: false,
  ...overrides,
});

describe('rankName', () => {
  it('writes rank ids as words', () => {
    expect(rankName('P1')).toBe('Platinum 1');
    expect(rankName('G3')).toBe('Gold 3');
    expect(rankName('D2')).toBe('Diamond 2');
    expect(rankName('C3')).toBe('Champion 3');
  });

  it('tells Grand Champion from Gold', () => {
    expect(rankName('GC')).toBe('Grand Champion');
  });

  it('writes under the ladder as below Gold 1', () => {
    expect(rankName('below G1')).toBe('below Gold 1');
  });
});

describe('placementSentence', () => {
  it('names the rank you reach when you are below the target', () => {
    expect(placementSentence(placement({}), 'P1', 10)).toBe("Below Platinum 1's average. You're at Gold 1 level.");
  });

  it('names the rank you reach when you are above it', () => {
    const above = placement({ verdict: 'above', gap: 0.5, level_low: 'P3', level_high: 'P3' });
    expect(placementSentence(above, 'P1', 10)).toBe("Above Platinum 1's average. You're at Platinum 3 level.");
  });

  it('says below Gold 1 level under the ladder', () => {
    const under = placement({ level_low: 'below G1', level_high: 'below G1' });
    expect(placementSentence(under, 'P1', 10)).toBe("Below Platinum 1's average. You're below Gold 1 level.");
  });

  it('says a gap within the margin is chance', () => {
    const level = placement({ verdict: 'level', level_low: 'P1', level_high: 'P1' });
    expect(placementSentence(level, 'P1', 10)).toBe(
      'About level with Platinum 1. The gap is within what chance gives over 31 games.',
    );
  });

  it('gives a span of ranks when the margin covers several', () => {
    const span = placement({ verdict: 'level', level_low: 'G3', level_high: 'GC' });
    expect(placementSentence(span, 'P1', 10)).toContain(
      "Somewhere between Gold 3 and Grand Champion: 31 games can't place you more closely.",
    );
  });

  it('reads a span that starts under the ladder', () => {
    const span = placement({ level_low: 'below G1', level_high: 'G2' });
    expect(placementSentence(span, 'P1', 10)).toContain('Somewhere from below Gold 1 up to Gold 2:');
  });

  it('says nothing about the rank with too few games', () => {
    const few = placement({ verdict: 'too_few', games: 4, margin: null, level_low: null, level_high: null });
    expect(placementSentence(few, 'P1', 10)).toBe('4 games is too few to say. It takes 10.');
    expect(placementSentence({ ...few, games: 1 }, 'P1', 10)).toBe('1 game is too few to say. It takes 10.');
  });
});

describe('stat labels', () => {
  it('calls bcpm boost collected, not used', () => {
    expect(statName('bcpm')).toBe('Boost collected per minute');
  });

  it('falls back to the id for a stat with no name', () => {
    expect(statName('new_stat')).toBe('new_stat');
  });

  it('rounds big values to whole numbers and keeps two decimals on small ones', () => {
    expect(formatStat(196.66)).toBe('197');
    expect(formatStat(1.3)).toBe('1.30');
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
    expect(prettyPlaylist('CASUAL')).toBe('Casual');
  });

  it('writes game length as minutes and padded seconds', () => {
    expect(formatDuration(458.4)).toBe('7:38');
    expect(formatDuration(305)).toBe('5:05');
  });
});
