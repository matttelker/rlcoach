import { useState } from 'react';
import { Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { getCoach, getGrades } from '../api/client';
import {
  Card,
  SkeletonCard,
  ErrorState,
  NoGamesEmpty,
  PageHeader,
  ResultMark,
  SectionTitle,
  SelectField,
} from '../components';
import type { CategorySummary, CoachResponse, CoachSession, Highlight, RuleGrades } from '../types/api';
import {
  COACH_PLAYLISTS,
  PERIOD_OPTIONS,
  categoryTrend,
  formatRate,
  gradeAccuracy,
  headline,
  kindLabel,
  prettyMap,
  isMixedPlaylist,
  sessionTitle,
  teamSizeLabel,
} from './coachTransforms';

// A replay lands about 30 seconds after a match ends, so check that often
// while the page is on screen. Coming back to the page also checks.
const REFRESH_MS = 30_000;

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
    <div className="space-y-14">
      <div>
        <PageHeader title="Coach" note="What to work on next, and what's going well">
          <SelectField
            label="Playlist"
            value={playlist ?? data?.playlist ?? ''}
            options={COACH_PLAYLISTS}
            onChange={setPlaylist}
          />
          <SelectField label="Period" value={period} options={PERIOD_OPTIONS} onChange={setPeriod} />
        </PageHeader>

        {error ? (
          <Card>
            <ErrorState message="Couldn't load your coaching summary. Is the server running the latest code?" />
          </Card>
        ) : isLoading || !data ? (
          <div className="space-y-6">
            <SkeletonCard />
            <SkeletonCard />
          </div>
        ) : (
          <CoachBody data={data} />
        )}
      </div>

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
    <Card className="overflow-x-auto">
      <table className="w-full min-w-[30rem]">
        <thead>
          <tr className="border-b border-[var(--color-border)]">
            <th className="th text-left pl-5">Call</th>
            <th className="th text-right w-20">Right</th>
            <th className="th text-right w-20">Wrong</th>
            <th className="th text-right w-24 pr-5">Right %</th>
          </tr>
        </thead>
        <tbody>
          {rules.map((rule) => {
            const accuracy = gradeAccuracy(rule);
            return (
              <tr key={`${rule.item}-${rule.kind}`} className="border-b last:border-b-0 border-[var(--color-border)]">
                <td className="px-3 pl-5 py-3">
                  {rule.label}
                  <span className="ml-2 text-[13px] text-[var(--color-text-muted)]">
                    {rule.item === 'goal' ? 'goal verdict' : 'flagged moment'}
                  </span>
                </td>
                <td className="px-3 py-3 text-right text-[var(--color-success)]">{rule.right}</td>
                <td className="px-3 py-3 text-right text-[var(--color-error)]">{rule.wrong}</td>
                <td
                  className={`px-3 pr-5 py-3 text-right font-semibold ${
                    accuracy !== null && accuracy < 50 ? 'text-[var(--color-error)]' : ''
                  }`}
                >
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
  const [first, ...rest] = data.targets;
  const mixed = isMixedPlaylist(data.playlist);

  return (
    <div className="space-y-14">
      <section>
        <SectionTitle title="Training targets" note="Ranked by goals they cost you, then how often they happen" />
        {unreviewed > 0 && (
          <p className="mb-4 text-[14px] text-[var(--color-warning)]">
            {unreviewed} of {data.game_count} games have no mistake review yet. Run{' '}
            <code className="px-1 rounded bg-[var(--color-bg-tertiary)]">uv run rlcoach reviews</code> to add them.
          </p>
        )}
        {!first ? (
          <Card className="p-5 text-[var(--color-text-muted)]">No mistakes flagged in these games. Keep it up.</Card>
        ) : (
          <>
            <Prescription target={first} />
            {rest.length > 0 && <RunnersUp targets={rest} />}
          </>
        )}
      </section>

      {data.session && <SessionBlock session={data.session} mixed={mixed} />}

      <section>
        <SectionTitle
          title="Mistakes by category"
          note={
            `${data.reviewed_count} reviewed games, your latest session against the ones before` +
            (mixed ? '. With Doubles and Standard together, a change can come from which mode you played' : '')
          }
        />
        <CategoryTable categories={data.categories} />
      </section>

      <section>
        <SectionTitle title="Strengths and highlights" />
        {data.highlights.length === 0 ? (
          <Card className="p-5 text-[var(--color-text-muted)]">
            Nothing to call out yet. Highlights come from winners, clean games and habits you've fixed.
          </Card>
        ) : (
          <ul className="grid gap-x-6 sm:grid-cols-2 lg:grid-cols-3 rounded-md border border-[var(--color-border)] bg-[var(--color-bg-secondary)] p-2">
            {data.highlights.map((h, i) => (
              <li key={`${h.kind}-${i}`}>
                <HighlightItem highlight={h} />
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}

/** The one thing to work on, written up like a prescription. */
function Prescription({ target }: { target: CategorySummary }) {
  return (
    <article className="rounded-md border border-[var(--color-border)] bg-[var(--color-bg-secondary)] overflow-hidden">
      <div className={target.cue ? 'grid md:grid-cols-[minmax(0,5fr)_minmax(0,6fr)]' : ''}>
        <div className="p-5 sm:p-7">
          <div className="flex items-baseline gap-3">
            <span className="type-score text-[44px] text-[var(--color-error)]">
              <span className="sr-only">Rank </span>1
            </span>
            <span className="text-[17px] font-semibold">{target.label}</span>
          </div>
          <p className="type-display text-[28px] sm:text-[34px] mt-4">{headline(target)}</p>
          <p className="mt-3 text-[14px]">
            <TrendText category={target} />
          </p>
          <KindChips kinds={target.kinds} />
        </div>
        {target.cue && (
          <div className="relative p-5 sm:p-7 border-t md:border-t-0 md:border-l border-[var(--color-border)] bg-[var(--strip-paper)]">
            <RxMark />
            <p className="mt-3 text-[19px] sm:text-[21px] leading-[1.55] max-w-[34em]">{target.cue}</p>
          </div>
        )}
      </div>
    </article>
  );
}

function RxMark() {
  return (
    <span className="type-display text-[22px] text-[var(--color-error)]" title="What to practise">
      R<span className="text-[15px] align-[-0.15em]">x</span>
      <span className="sr-only"> What to practise</span>
    </span>
  );
}

function RunnersUp({ targets }: { targets: CategorySummary[] }) {
  return (
    <ol className="mt-3 rounded-md border border-[var(--color-border)] bg-[var(--color-bg-secondary)] divide-y divide-[var(--color-border)]">
      {targets.map((target, index) => (
        <li key={target.category} className="grid grid-cols-[2.25rem_minmax(0,1fr)] gap-x-3 p-5">
          <span className="type-score text-[30px] text-[var(--color-text-muted)]">
            <span className="sr-only">Rank </span>
            {index + 2}
          </span>
          <div className="grid md:grid-cols-[minmax(0,17rem)_minmax(0,1fr)] gap-x-8 gap-y-2">
            <div>
              <div className="font-semibold">{target.label}</div>
              <div className="type-display text-[17px] mt-1">{headline(target)}</div>
              <div className="text-[13px] mt-1.5">
                <TrendText category={target} />
              </div>
            </div>
            <div>
              {target.cue && <p className="text-[var(--color-text-muted)] max-w-[60ch]">{target.cue}</p>}
              <KindChips kinds={target.kinds} />
            </div>
          </div>
        </li>
      ))}
    </ol>
  );
}

function KindChips({ kinds }: { kinds: Record<string, number> }) {
  const entries = Object.entries(kinds);
  if (entries.length === 0) return null;
  return (
    <ul className="flex flex-wrap gap-1.5 mt-4">
      {entries.map(([kind, count]) => (
        <li key={kind} className="text-[13px] px-2 py-0.5 rounded bg-[var(--color-bg-tertiary)]">
          {kindLabel(kind)} ×{count}
        </li>
      ))}
    </ul>
  );
}

function SessionBlock({ session, mixed }: { session: CoachSession; mixed: boolean }) {
  const record = `${session.wins}–${session.losses}${session.draws ? `–${session.draws}` : ''}`;
  return (
    <section>
      <SectionTitle title={sessionTitle(session.play_date)} note={`${session.games.length} games`} />
      <Card className="grid md:grid-cols-[11rem_minmax(0,1fr)]">
        <div className="px-5 py-4 md:py-5 border-b md:border-b-0 md:border-r border-[var(--color-border)] flex md:block items-baseline gap-4">
          <div className="text-[13px] text-[var(--color-text-muted)]">Record</div>
          <div className="type-score text-[48px] md:text-[64px] md:mt-2">{record}</div>
        </div>
        <ul>
          {session.games.map((g) => (
            <li key={g.replay_id} className="border-b last:border-b-0 border-[var(--color-border)]">
              <Link
                to={`/games/${g.replay_id}`}
                className="grid grid-cols-[5.5rem_minmax(0,1fr)] sm:grid-cols-[5.5rem_minmax(0,10rem)_minmax(0,1fr)_auto] items-center gap-x-4 gap-y-1 px-5 py-3 hover:bg-[var(--color-bg-tertiary)]"
              >
                <ResultMark result={g.result} score={`${g.my_score}–${g.opponent_score}`} />
                <span className="font-semibold truncate">
                  {prettyMap(g.map)}
                  {mixed && (
                    <span className="ml-2 text-[13px] font-normal text-[var(--color-text-muted)]">
                      {teamSizeLabel(g.playlist)}
                    </span>
                  )}
                </span>
                <span className="col-start-2 sm:col-start-auto flex gap-3 text-[14px] text-[var(--color-text-muted)]">
                  <span title="Goals">
                    <span className="text-[var(--color-text)]">{g.goals ?? 0}</span> G
                  </span>
                  <span title="Assists">
                    <span className="text-[var(--color-text)]">{g.assists ?? 0}</span> A
                  </span>
                  <span title="Saves">
                    <span className="text-[var(--color-text)]">{g.saves ?? 0}</span> Sv
                  </span>
                </span>
                <span className="col-start-2 sm:col-start-auto flex gap-3 text-[14px] sm:justify-end">
                  {!g.reviewed ? (
                    <span className="text-[var(--color-text-muted)]">Not reviewed</span>
                  ) : (
                    <>
                      <span className={g.goals_on_me ? 'text-[var(--color-error)] font-semibold' : 'text-[var(--color-text-muted)]'}>
                        {g.goals_on_me ?? 0} goal{g.goals_on_me === 1 ? '' : 's'} on you
                      </span>
                      <span className="text-[var(--color-text-muted)]">{g.flags} flagged</span>
                    </>
                  )}
                </span>
              </Link>
            </li>
          ))}
        </ul>
      </Card>
    </section>
  );
}

function TrendText({ category }: { category: CategorySummary }) {
  const trend = categoryTrend(category);
  if (trend === 'new') {
    return <span className="text-[var(--color-text-muted)]">{formatRate(category.per_game)} a game</span>;
  }
  const color =
    trend === 'worse'
      ? 'text-[var(--color-error)]'
      : trend === 'better'
        ? 'text-[var(--color-success)]'
        : 'text-[var(--color-text-muted)]';
  const word = trend === 'worse' ? 'up' : trend === 'better' ? 'down' : 'steady';
  return (
    <span className={color}>
      {formatRate(category.before_per_game)} → {formatRate(category.latest_per_game)} a game, {word}
    </span>
  );
}

function CategoryTable({ categories }: { categories: CategorySummary[] }) {
  const most = Math.max(1, ...categories.map((c) => c.flags));
  return (
    <Card className="overflow-x-auto">
      <table className="w-full min-w-[38rem]">
        <thead>
          <tr className="border-b border-[var(--color-border)]">
            <th className="th text-left pl-5 w-36">Category</th>
            <th className="th text-left">Flagged</th>
            <th className="th text-right w-28">Goals cost</th>
            <th className="th text-right w-60 pr-5">Before → latest session</th>
          </tr>
        </thead>
        <tbody>
          {categories.map((c) => (
            <tr key={c.category} className="border-b last:border-b-0 border-[var(--color-border)]">
              <td className="px-3 pl-5 py-3 font-semibold">{c.label}</td>
              <td className="px-3 py-3">
                <div className="flex items-center gap-3">
                  <div className="flex-1 max-w-64">
                    <div
                      className="h-2 rounded-r"
                      style={{
                        width: `${(c.flags / most) * 100}%`,
                        background: c.goals_cost ? 'var(--chart-bad)' : 'var(--color-text-muted)',
                      }}
                    />
                  </div>
                  <span className="w-6 text-right">{c.flags}</span>
                </div>
              </td>
              <td className={`px-3 py-3 text-right ${c.goals_cost ? 'text-[var(--color-error)] font-semibold' : ''}`}>
                {c.goals_cost || '–'}
              </td>
              <td className="px-3 pr-5 py-3 text-right text-[14px]">
                <TrendText category={c} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </Card>
  );
}

function HighlightItem({ highlight }: { highlight: Highlight }) {
  const body = (
    <div className="flex gap-3 rounded p-3 h-full">
      <svg viewBox="0 0 12 12" className="w-3 h-3 mt-1.5 shrink-0" aria-hidden="true">
        <path d="M6 1v10M1 6h10" stroke="var(--chart-good)" strokeWidth={2.5} strokeLinecap="round" />
      </svg>
      <div>
        <div className="font-semibold">{highlight.title}</div>
        <div className="text-[14px] text-[var(--color-text-muted)] mt-0.5">{highlight.detail}</div>
      </div>
    </div>
  );
  return highlight.replay_id ? (
    <Link to={`/games/${highlight.replay_id}`} className="block rounded hover:bg-[var(--color-bg-tertiary)]">
      {body}
    </Link>
  ) : (
    body
  );
}
