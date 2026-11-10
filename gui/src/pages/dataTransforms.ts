import type { Placement } from '../types/api';

const RANK_TIERS: Record<string, string> = { G: 'Gold', P: 'Platinum', D: 'Diamond', C: 'Champion' };

/** A rank id as words: "P1" is Platinum 1, "GC" Grand Champion, "below G1" below Gold 1 */
export function rankName(rank: string): string {
  if (rank.startsWith('below ')) return `below ${rankName(rank.slice('below '.length))}`;
  if (rank === 'GC') return 'Grand Champion';
  const tier = RANK_TIERS[rank.charAt(0)];
  return tier ? `${tier} ${rank.slice(1)}` : rank;
}

// The ranks with benchmarks, highest first. RANKS in metrics.py is the source.
export const RANK_OPTIONS = ['GC', 'C3', 'C2', 'C1', 'D3', 'D2', 'D1', 'P3', 'P2', 'P1', 'G3', 'G2', 'G1'].map(
  (r) => ({ value: r, label: rankName(r) }),
);

export const BENCHMARK_HINT = 'Benchmarks cover Doubles and Standard, from Gold 1 to Grand Champion. Duel has none.';

export const BENCHMARK_SOURCE =
  'Benchmarks are ballchasing.com averages. Grand Champion combines every Grand Champion tier.';

// Each stat's plain name, as the stats views show it
export const STAT_NAMES: Record<string, string> = {
  bcpm: 'Boost collected per minute',
  avg_boost: 'Average boost',
  goals: 'Goals',
  assists: 'Assists',
  saves: 'Saves',
  shots: 'Shots',
  time_zero_boost_s: 'Seconds with no boost',
  boost_stolen: "Boost taken from the other team's half",
  epic_saves: 'Epic saves',
  clears: 'Clears from in front of your goal',
  centers: 'Centers',
  aerial_hits: 'Aerial hits',
};

export function statName(metric: string): string {
  return STAT_NAMES[metric] ?? metric;
}

/** A stat's value: whole numbers from 100 up, two decimals under */
export function formatStat(value: number): string {
  return Math.abs(value) >= 100 ? value.toFixed(0) : value.toFixed(2);
}

const games = (count: number) => `${count} ${count === 1 ? 'game' : 'games'}`;

/** Which rank your average reaches, or the span of ranks it could be in */
function levelSentence({ level_low: low, level_high: high, games: count }: Placement): string {
  if (low === null || high === null) return '';
  if (low === high) return low.startsWith('below ') ? `You're ${rankName(low)} level.` : `You're at ${rankName(low)} level.`;
  const from = low.startsWith('below ') ? `from ${rankName(low)} up to` : `between ${rankName(low)} and`;
  return `Somewhere ${from} ${rankName(high)}: ${games(count)} can't place you more closely.`;
}

/** What a placement says about you against the target rank, in a sentence or two */
export function placementSentence(placement: Placement, target: string, minGames: number): string {
  const rank = rankName(target);
  const level = levelSentence(placement);
  switch (placement.verdict) {
    case 'too_few':
      return `${games(placement.games)} is too few to say. It takes ${minGames}.`;
    case 'level':
      // Level with one rank at both ends is the target itself, already named
      if (placement.level_low === placement.level_high) {
        return `About level with ${rank}. The gap is within what chance gives over ${games(placement.games)}.`;
      }
      return `About level with ${rank}. The gap is within what chance gives over ${games(placement.games)}. ${level}`.trim();
    case 'above':
      return `Above ${rank}'s average. ${level}`.trim();
    case 'below':
      return `Below ${rank}'s average. ${level}`.trim();
  }
}

export const BALLCHASING_COUNT_NOTE =
  "The rank's average is Ballchasing's, raised 5% because Ballchasing counts fewer small pads than the game does.";

// The API sends UTC timestamps with no offset, which browsers would read as local.
export function parseUtc(value: string): Date {
  return new Date(/(Z|[+-]\d{2}:\d{2})$/.test(value) ? value : `${value}Z`);
}

// Date-only strings parse as UTC midnight, which lands on the previous day west of UTC.
export function parseLocalDate(value: string): Date {
  return new Date(`${value}T00:00:00`);
}

// Playlists arrive as ids like "STANDARD" or "CASUAL"
export function prettyPlaylist(playlist: string): string {
  return playlist.charAt(0) + playlist.slice(1).toLowerCase();
}

// Game length as m:ss
export function formatDuration(seconds: number): string {
  return `${Math.floor(seconds / 60)}:${String(Math.floor(seconds % 60)).padStart(2, '0')}`;
}
