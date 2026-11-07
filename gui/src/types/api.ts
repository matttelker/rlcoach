// API response types for RLCoach

export type GameResult = 'WIN' | 'LOSS' | 'DRAW';

export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  limit: number;
  offset: number;
}

interface ReplaySummary {
  replay_id: string;
  played_at_utc: string;
  playlist: string;
  result: GameResult;
  my_score: number;
  opponent_score: number;
  duration_seconds: number;
}

// Game/Replay types
export interface Game extends ReplaySummary {
  play_date: string;
  map: string;
}

export interface PlayerStats {
  player_id: string;
  display_name: string;
  team: 'BLUE' | 'ORANGE';
  is_me: boolean;
  goals: number;
  assists: number;
  saves: number;
  shots: number;
  bcpm: number | null;
  avg_boost: number | null;
}

export interface ReplayDetail extends ReplaySummary {
  map: string;
  player_stats: PlayerStats[];
}

// Analysis types
export interface TrendValue {
  date: string;
  value: number;
}

export interface TrendsResponse {
  metric: string;
  period: string;
  playlist: string;
  values: TrendValue[];
}

export interface Benchmark {
  metric: string;
  playlist: string;
  rank_tier: string;
  median_value: number;
  p25_value: number;
  p75_value: number;
  elite_threshold: number | null;
  source: string | null;
}

export interface Comparison {
  metric: string;
  my_value: number;
  target_median: number | null;
  difference: number | null;
  difference_pct: number | null;
  direction: 'higher' | 'lower';
}

export interface CompareResponse {
  target_rank: string;
  playlist: string;
  comparisons: Comparison[];
  game_count: number;
}

export interface Pattern {
  metric: string;
  win_avg: number;
  loss_avg: number;
  delta: number;
  effect_size: number;
  direction: 'higher_in_wins' | 'lower_in_wins';
}

export interface PatternsResponse {
  patterns: Pattern[];
  playlist: string;
  win_count: number;
  loss_count: number;
  min_games: number;
}

export interface Weakness {
  metric: string;
  my_value: number;
  target_median: number;
  z_score: number;
  severity: 'critical' | 'high' | 'medium' | 'low' | 'strength' | 'neutral';
}

export interface WeaknessesResponse {
  weaknesses: Weakness[];
  strengths: Weakness[];
  game_count: number;
  playlist: string;
  has_benchmarks: boolean;
}

// Player types
export interface Player {
  player_id: string;
  display_name: string;
  platform: string | null;
  is_me: boolean;
  is_tagged_teammate: boolean;
  teammate_notes: string | null;
  games_with_me: number;
  first_seen_utc: string | null;
  last_seen_utc: string | null;
}

export interface TagRequest {
  tagged?: boolean;
  notes?: string | null;
}

// Coaching types
export interface CategorySession {
  play_date: string;
  games: number;
  flags: number;
}

export interface CategorySummary {
  category: string;
  label: string;
  flags: number;
  goals_cost: number;
  games: number;
  per_game: number | null;
  latest_per_game: number | null;
  before_per_game: number | null;
  sessions: CategorySession[];
  kinds: Record<string, number>;
  top_kind: string | null;
  cue: string | null;
  clean_streak: number;
}

export interface SessionGame {
  replay_id: string;
  playlist: string;
  played_at_utc: string;
  result: GameResult | null;
  my_score: number | null;
  opponent_score: number | null;
  map: string;
  goals: number | null;
  assists: number | null;
  saves: number | null;
  shots: number | null;
  reviewed: boolean;
  flags: number | null;
  goals_on_me: number | null;
}

export interface CoachSession {
  play_date: string;
  wins: number;
  losses: number;
  draws: number;
  games: SessionGame[];
}

export interface Highlight {
  kind: 'winner' | 'equalizer' | 'clean' | 'streak' | 'improving' | 'benchmark';
  title: string;
  detail: string;
  replay_id: string | null;
}

export interface CoachResponse {
  /** One playlist, or several joined by commas such as "DOUBLES,STANDARD" */
  playlist: string;
  period: string;
  rank: string;
  game_count: number;
  reviewed_count: number;
  session: CoachSession | null;
  targets: CategorySummary[];
  categories: CategorySummary[];
  highlights: Highlight[];
}

export interface ReviewMistake {
  kind: string;
  label: string;
  category: string;
  category_label: string;
  t: number;
  seconds_left: number;
  clock: string;
  score: string;
  duration: number;
  what: string;
  instead: string;
  outcome: string;
  cost_goal: boolean;
  grade: Grade | null;
}

export interface ReviewGoal {
  t: number;
  seconds_left: number;
  clock: string;
  score: string;
  ours: boolean;
  scorer: string;
  by_me: boolean;
  assist_by_me: boolean;
  winner: boolean;
  equalizer: boolean;
  on_me: boolean | null;
  summary: string | null;
  lines: string[];
  grade: Grade | null;
}

// Your verdict on one of the review's calls
export type Grade = 'right' | 'wrong';

export interface GradeRequest {
  item: 'mistake' | 'goal';
  t: number;
  kind?: string;
  grade: Grade | null;
}

export interface RuleGrades {
  item: 'mistake' | 'goal';
  kind: string;
  label: string;
  right: number;
  wrong: number;
}

export interface GradesResponse {
  rules: RuleGrades[];
}

export interface ReplayReview {
  replay_id: string;
  status: 'ok' | 'unsupported' | 'error' | 'missing';
  error: string | null;
  clears: number;
  clears_given_back: number;
  mistakes: ReviewMistake[];
  goals: ReviewGoal[];
}
