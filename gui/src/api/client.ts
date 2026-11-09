// Calls to the local API, which `rlcoach serve` keeps under /api beside the dashboard.
import axios from 'axios';
import type {
  CoachResponse,
  CompareResponse,
  Game,
  GameResult,
  GradeRequest,
  GradesResponse,
  PaginatedResponse,
  PatternsResponse,
  Player,
  ReplayDetail,
  ReplayReview,
  TagRequest,
  TrendsResponse,
  WeaknessesResponse,
} from '../types/api';

/** The one connection every call goes through. Tests swap its adapter. */
export const http = axios.create({ baseURL: '/api', timeout: 30_000 });

/** A request's query string. axios leaves out the parameters that are undefined. */
type Query = Record<string, string | number | boolean | undefined>;

async function get<T>(path: string, query?: Query): Promise<T> {
  const response = await http.get<T>(path, { params: query });
  return response.data;
}

// Ids hold characters such as the colon in "epic:..." and go into paths encoded
const replayPath = (replayId: string) => `/replays/${encodeURIComponent(replayId)}`;
const playerPath = (playerId: string) => `/players/${encodeURIComponent(playerId)}`;

/** One page of games, of one playlist or result if given. */
type GamesQuery = { playlist?: string; result?: GameResult; limit: number; offset: number };

export const getGames = (query: GamesQuery) => get<PaginatedResponse<Game>>('/games', query);

export const getReplay = (replayId: string) => get<ReplayDetail>(replayPath(replayId));

export const getReplayReview = (replayId: string) => get<ReplayReview>(`${replayPath(replayId)}/review`);

/** Mark one of the review's calls right or wrong, or clear it with a null grade. */
export async function setGrade(replayId: string, request: GradeRequest): Promise<void> {
  await http.put(`${replayPath(replayId)}/grades`, request);
}

export const getGrades = () => get<GradesResponse>('/grades');

// The stats views. A playlist or rank left out means the API's choice: the
// playlist of your latest game, and the rank in your config.
type StatsQuery = { playlist?: string; period?: string };

export const getCoach = (query: StatsQuery) => get<CoachResponse>('/coach', query);

export const getTrends = (query: StatsQuery & { metric: string }) => get<TrendsResponse>('/trends', query);

export const getComparison = (query: StatsQuery & { rank?: string }) => get<CompareResponse>('/compare', query);

export const getWeaknesses = (query: StatsQuery & { rank?: string }) => get<WeaknessesResponse>('/weaknesses', query);

export const getPatterns = (query: StatsQuery) => get<PatternsResponse>('/patterns', query);

type PlayersQuery = { tagged?: boolean; min_games: number; sort: string; limit: number; offset: number };

export const getPlayers = (query: PlayersQuery) => get<PaginatedResponse<Player>>('/players', query);

export const getPlayer = (playerId: string) => get<Player>(playerPath(playerId));

/** Tag or untag someone as your teammate. Notes left out stay as they were. */
export async function tagPlayer(playerId: string, request: TagRequest): Promise<void> {
  await http.post(`${playerPath(playerId)}/tag`, request);
}
