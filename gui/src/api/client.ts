import axios from 'axios';
import type {
  Game,
  ReplayDetail,
  ReplayFull,
  TrendsResponse,
  Benchmark,
  CompareResponse,
  PatternsResponse,
  WeaknessesResponse,
  Player,
  PaginatedResponse,
  TagRequest,
  GameResult,
  CoachResponse,
  ReplayReview,
  GradeRequest,
  GradesResponse,
} from '../types/api';

const api = axios.create({
  baseURL: '/api',
  timeout: 30000,
});

// Games
interface ListParams {
  limit?: number;
  offset?: number;
  sort?: string;
}

export interface GamesParams extends ListParams {
  playlist?: string;
  result?: GameResult;
  date_from?: string;
  date_to?: string;
}

export async function getGames(params: GamesParams = {}): Promise<PaginatedResponse<Game>> {
  const { data } = await api.get<PaginatedResponse<Game>>('/games', { params });
  return data;
}

export async function getReplay(replayId: string): Promise<ReplayDetail> {
  const { data } = await api.get<ReplayDetail>(`/replays/${encodeURIComponent(replayId)}`);
  return data;
}

export async function getReplayFull(replayId: string): Promise<ReplayFull> {
  const { data } = await api.get<ReplayFull>(`/replays/${encodeURIComponent(replayId)}/full`);
  return data;
}

// Analysis
export interface TrendsParams {
  metric: string;
  period?: string;
  playlist?: string;
}

export async function getTrends(params: TrendsParams): Promise<TrendsResponse> {
  const { data } = await api.get<TrendsResponse>('/trends', { params });
  return data;
}

export interface BenchmarksParams {
  metric?: string;
  playlist?: string;
  rank?: string;
}

export async function getBenchmarks(params: BenchmarksParams = {}): Promise<{ items: Benchmark[] }> {
  const { data } = await api.get<{ items: Benchmark[] }>('/benchmarks', { params });
  return data;
}

export interface CompareParams {
  rank: string;
  playlist?: string;
  period?: string;
}

export async function getComparison(params: CompareParams): Promise<CompareResponse> {
  const { data } = await api.get<CompareResponse>('/compare', { params });
  return data;
}

export interface PatternsParams {
  playlist?: string;
  period?: string;
  min_games?: number;
}

export async function getPatterns(params: PatternsParams = {}): Promise<PatternsResponse> {
  const { data } = await api.get<PatternsResponse>('/patterns', { params });
  return data;
}

export type WeaknessesParams = Partial<CompareParams>;

export async function getWeaknesses(params: WeaknessesParams = {}): Promise<WeaknessesResponse> {
  const { data } = await api.get<WeaknessesResponse>('/weaknesses', { params });
  return data;
}

// Coaching
export interface CoachParams {
  playlist?: string;
  period?: string;
}

export async function getCoach(params: CoachParams = {}): Promise<CoachResponse> {
  const { data } = await api.get<CoachResponse>('/coach', { params });
  return data;
}

export async function getReplayReview(replayId: string): Promise<ReplayReview> {
  const { data } = await api.get<ReplayReview>(`/replays/${encodeURIComponent(replayId)}/review`);
  return data;
}

export async function setGrade(replayId: string, request: GradeRequest): Promise<void> {
  await api.put(`/replays/${encodeURIComponent(replayId)}/grades`, request);
}

export async function getGrades(): Promise<GradesResponse> {
  const { data } = await api.get<GradesResponse>('/grades');
  return data;
}

// Players
export interface PlayersParams extends ListParams {
  tagged?: boolean;
  min_games?: number;
}

export async function getPlayers(params: PlayersParams = {}): Promise<PaginatedResponse<Player>> {
  const { data } = await api.get<PaginatedResponse<Player>>('/players', { params });
  return data;
}

export async function getPlayer(playerId: string): Promise<Player> {
  const { data } = await api.get<Player>(`/players/${encodeURIComponent(playerId)}`);
  return data;
}

export async function tagPlayer(playerId: string, request: TagRequest): Promise<Player> {
  const { data } = await api.post<Player>(`/players/${encodeURIComponent(playerId)}/tag`, request);
  return data;
}

export default api;
