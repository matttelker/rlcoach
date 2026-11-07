import { useState } from 'react';
import { Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { getCoach, getGrades } from '../api/client';
import {
  Card,
  CardContent,
  SkeletonCard,
  ErrorState,
  NoGamesEmpty,
  PlaylistSelect,
} from '../components';
import type { CategorySummary, CoachResponse, CoachSession, Highlight, RuleGrades } from '../types/api';
import {
  PERIOD_OPTIONS,
  categoryTrend,
  formatRate,
  gradeAccuracy,
  headline,
  kindLabel,
  prettyMap,
  sessionTitle,
} from './coachTransforms';

// A replay lands about 30 seconds after a match ends, so check that often
// while the page is on screen. Coming back to the page also checks.
const REFRESH_MS = 30_000;

const SELECT_CLASS =
  'bg-[var(--color-bg-tertiary)] border border-[var(--color-border)] rounded px-3 py-2 text-sm text-[var(--color-text)]';

export function Coach() {
  // Left unset, the API picks the playlist of your latest game.
  const [playlist, setPlaylist] = useState<string>();
  const [period, setPeriod] = useState('30d');

  const { data, isLoading, error } = useQuery({
    queryKey: ['coach', playlist, period],
    queryFn: () => getCoach({ playlist, period }),
    refetchInterval: REFRESH_MS,
  });

  return (
    <div className="space-y-8 max-w-5xl">
      <div className="flex flex-wrap items-end gap-4">
        <div className="mr-auto">
          <h1 className="text-2xl font-bold text-[var(--color-text)]">Coach</h1>
          <p className="text-sm text-[var(--color-text-muted)]">What to work on next, and what's going well</p>
        </div>
        <PlaylistSelect value={playlist ?? data?.playlist} onChange={setPlaylist} />
        <div>
          <label className="block text-xs text-[var(--color-text-muted)] mb-1">Period</label>
          <select value={period} onChange={(e) => setPeriod(e.target.value)} className={SELECT_CLASS}>
            {PERIOD_OPTIONS.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {opt.label}
              </option>
            ))}
          </select>
        </div>
      </div>

      {error ? (
        <ErrorState message="Couldn't load your coaching summary. Is the API running the latest code?" />
      ) : isLoading || !data ? (
        <div className="space-y-6">
          <SkeletonCard />
          <SkeletonCard />
        </div>
      ) : (
        <CoachBody data={data} />
      )}

      <CallGrades />
    </div>
  );
}

/** How your right and wrong grades on the review's calls add up, per rule. */
function CallGrades() {
  const { data } = useQuery({ queryKey: ['grades'], queryFn: getGrades, retry: false });
  // Nothing graded yet, or an older API without grades
  if (!data || data.rules.length === 0) return null;
  return (
    <section>
      <SectionTitle
        title="How its calls hold up"
        note="Your right and wrong marks on game pages, across every game you've graded"
      />
      <GradesTable rules={data.rules} />
    </section>
  );
}

export function GradesTable({ rules }: { rules: RuleGrades[] }) {
  return (
    <Card>
      <table className="w-full text-sm">
        <thead>
          <tr className="text-xs text-[var(--color-text-muted)] border-b border-[var(--color-border)]">
            <th className="text-left font-medium p-3">Call</th>
            <th className="text-right font-medium p-3 w-20">Right</th>
            <th className="text-right font-medium p-3 w-20">Wrong</th>
            <th className="text-right font-medium p-3 w-24">Right %</th>
          </tr>
        </thead>
        <tbody>
          {rules.map((rule) => {
            const accuracy = gradeAccuracy(rule);
            return (
              <tr key={`${rule.item}-${rule.kind}`} className="border-b last:border-b-0 border-[var(--color-border)]">
                <td className="p-3">
                  {rule.label}
                  <span className="ml-2 text-xs text-[var(--color-text-muted)]">
                    {rule.item === 'goal' ? 'goal verdict' : 'flagged moment'}
                  </span>
                </td>
                <td className="p-3 text-right text-[var(--color-success)]">{rule.right}</td>
                <td className="p-3 text-right text-[var(--color-error)]">{rule.wrong}</td>
                <td className={`p-3 text-right ${accuracy !== null && accuracy < 50 ? 'text-[var(--color-error)]' : ''}`}>
                  {accuracy === null ? '–' : `${accuracy}%`}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </Card>
  );
}

export function CoachBody({ data }: { data: CoachResponse }) {
  if (data.game_count === 0) {
    return (
      <Card>
        <NoGamesEmpty />
      </Card>
    );
  }

  const unreviewed = data.game_count - data.reviewed_count;

  return (
    <div className="space-y-8">
      {unreviewed > 0 && (
        <p className="text-sm text-[var(--color-warning)]">
          {unreviewed} of {data.game_count} games have no mistake review yet. Run{' '}
          <code className="px-1 rounded bg-[var(--color-bg-tertiary)]">uv run rlcoach reviews</code> to add them.
        </p>
      )}

      {data.session && <SessionBlock session={data.session} />}

      <section>
        <SectionTitle title="Training targets" note="Ranked by goals they cost you, then how often they happen" />
        {data.targets.length === 0 ? (
          <Card>
            <CardContent className="text-sm text-[var(--color-text-muted)]">
              No mistakes flagged in these games. Keep it up.
            </CardContent>
          </Card>
        ) : (
          <div className="grid gap-4 md:grid-cols-3">
            {data.targets.map((target, index) => (
              <TargetCard key={target.category} target={target} rank={index + 1} />
            ))}
          </div>
        )}
      </section>

      <section>
        <SectionTitle
          title="Mistakes by category"
          note={`${data.reviewed_count} reviewed games, your latest session against the ones before`}
        />
        <CategoryTable categories={data.categories} />
      </section>

      <section>
        <SectionTitle title="Strengths and highlights" />
        {data.highlights.length === 0 ? (
          <Card>
            <CardContent className="text-sm text-[var(--color-text-muted)]">
              Nothing to call out yet. Highlights come from winners, clean games and habits you've fixed.
            </CardContent>
          </Card>
        ) : (
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {data.highlights.map((h, i) => (
              <HighlightCard key={`${h.kind}-${i}`} highlight={h} />
            ))}
          </div>
        )}
      </section>
    </div>
  );
}

function SectionTitle({ title, note }: { title: string; note?: string }) {
  return (
    <div className="flex flex-wrap items-baseline gap-x-3 mb-3">
      <h2 className="text-lg font-semibold text-[var(--color-text)]">{title}</h2>
      {note && <span className="text-xs text-[var(--color-text-muted)]">{note}</span>}
    </div>
  );
}

function resultPill(result: string | null, score: string) {
  const style =
    result === 'WIN'
      ? 'bg-[var(--color-success)]/15 text-[var(--color-success)]'
      : result === 'LOSS'
        ? 'bg-[var(--color-error)]/15 text-[var(--color-error)]'
        : 'bg-[var(--color-warning)]/15 text-[var(--color-warning)]';
  const letter = result === 'WIN' ? 'W' : result === 'LOSS' ? 'L' : 'D';
  return (
    <span className={`inline-block w-16 text-center text-xs font-semibold rounded px-2 py-1 ${style}`}>
      {letter} {score}
    </span>
  );
}

function SessionBlock({ session }: { session: CoachSession }) {
  const record = `${session.wins}–${session.losses}${session.draws ? `–${session.draws}` : ''}`;
  return (
    <section>
      <SectionTitle title={sessionTitle(session.play_date)} note={`${session.games.length} games`} />
      <Card>
        <div className="grid md:grid-cols-[140px_1fr]">
          <div className="p-4 border-b md:border-b-0 md:border-r border-[var(--color-border)]">
            <div className="text-xs text-[var(--color-text-muted)]">Record</div>
            <div className="text-3xl font-bold">{record}</div>
          </div>
          <ul>
            {session.games.map((g) => (
              <li key={g.replay_id} className="border-b last:border-b-0 border-[var(--color-border)]">
                <Link
                  to={`/games/${g.replay_id}`}
                  className="flex flex-wrap items-center gap-x-4 gap-y-1 px-4 py-3 hover:bg-[var(--color-bg-tertiary)]/50"
                >
                  {resultPill(g.result, `${g.my_score}–${g.opponent_score}`)}
                  <span className="text-sm w-36 truncate">{prettyMap(g.map)}</span>
                  <span className="text-sm text-[var(--color-text-muted)]">
                    {g.goals ?? 0} G · {g.assists ?? 0} A · {g.saves ?? 0} Sv
                  </span>
                  <span className="ml-auto text-sm">
                    {!g.reviewed ? (
                      <span className="text-[var(--color-text-muted)]">Not reviewed</span>
                    ) : g.goals_on_me ? (
                      <span className="text-[var(--color-error)]">
                        {g.goals_on_me} goal{g.goals_on_me === 1 ? '' : 's'} on you
                      </span>
                    ) : (
                      <span className="text-[var(--color-text-muted)]">0 goals on you</span>
                    )}
                    {g.reviewed && (
                      <span className="text-[var(--color-text-muted)]"> · {g.flags} flagged</span>
                    )}
                  </span>
                </Link>
              </li>
            ))}
          </ul>
        </div>
      </Card>
    </section>
  );
}

function TrendText({ category }: { category: CategorySummary }) {
  const trend = categoryTrend(category);
  if (trend === 'new') {
    return <span>{formatRate(category.per_game)} a game</span>;
  }
  const color =
    trend === 'worse'
      ? 'text-[var(--color-error)]'
      : trend === 'better'
        ? 'text-[var(--color-success)]'
        : 'text-[var(--color-text-muted)]';
  const arrow = trend === 'worse' ? '↑' : trend === 'better' ? '↓' : '→';
  return (
    <span className={color}>
      {formatRate(category.before_per_game)} → {formatRate(category.latest_per_game)} a game {arrow}
    </span>
  );
}

function TargetCard({ target, rank }: { target: CategorySummary; rank: number }) {
  const first = rank === 1;
  return (
    <Card className={first ? 'border-2 border-[var(--color-primary)]' : ''}>
      <CardContent className="space-y-2">
        <div className={`text-xs font-semibold ${first ? 'text-[var(--color-primary)]' : 'text-[var(--color-text-muted)]'}`}>
          {rank} · {target.label}
        </div>
        <div className="text-base font-semibold">{headline(target)}</div>
        <div className="text-xs">
          <TrendText category={target} />
        </div>
        {target.cue && <p className="text-sm leading-relaxed pt-1">{target.cue}</p>}
        <div className="flex flex-wrap gap-1.5 pt-1">
          {Object.entries(target.kinds).map(([kind, count]) => (
            <span
              key={kind}
              className="text-xs px-2 py-0.5 rounded bg-[var(--color-bg-tertiary)] text-[var(--color-text-muted)]"
            >
              {kindLabel(kind)} ×{count}
            </span>
          ))}
        </div>
      </CardContent>
    </Card>
  );
}

function CategoryTable({ categories }: { categories: CategorySummary[] }) {
  const most = Math.max(1, ...categories.map((c) => c.flags));
  return (
    <Card>
      <table className="w-full text-sm">
        <thead>
          <tr className="text-xs text-[var(--color-text-muted)] border-b border-[var(--color-border)]">
            <th className="text-left font-medium p-3 w-32">Category</th>
            <th className="text-left font-medium p-3">Flagged</th>
            <th className="text-right font-medium p-3 w-24">Goals cost</th>
            <th className="text-right font-medium p-3 w-52">Before → latest session</th>
          </tr>
        </thead>
        <tbody>
          {categories.map((c) => (
            <tr key={c.category} className="border-b last:border-b-0 border-[var(--color-border)]">
              <td className="p-3">{c.label}</td>
              <td className="p-3">
                <div className="flex items-center gap-2">
                  <div className="flex-1 max-w-64 h-2 rounded bg-[var(--color-bg-tertiary)]">
                    <div
                      className={`h-2 rounded ${c.goals_cost ? 'bg-[var(--color-error)]' : 'bg-[var(--color-text-muted)]'}`}
                      style={{ width: `${(c.flags / most) * 100}%` }}
                    />
                  </div>
                  <span className="w-6 text-right">{c.flags}</span>
                </div>
              </td>
              <td className="p-3 text-right">{c.goals_cost || '–'}</td>
              <td className="p-3 text-right">
                <TrendText category={c} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </Card>
  );
}

function HighlightCard({ highlight }: { highlight: Highlight }) {
  const body = (
    <div className="h-full rounded-lg border border-[var(--color-success)]/40 bg-[var(--color-success)]/10 px-4 py-3">
      <div className="text-sm font-semibold text-[var(--color-success)]">{highlight.title}</div>
      <div className="text-sm text-[var(--color-text)] mt-1">{highlight.detail}</div>
    </div>
  );
  return highlight.replay_id ? (
    <Link to={`/games/${highlight.replay_id}`} className="block hover:opacity-90">
      {body}
    </Link>
  ) : (
    body
  );
}
