import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { getReplayReview, setGrade } from '../api/client';
import { Card, CardHeader, CardContent } from '../components';
import type { Grade, GradeRequest, ReplayReview } from '../types/api';
import { REGULATION_SECONDS, applyGrade, groupByCategory, timelineX } from './coachTransforms';

export function GameReview({ replayId }: { replayId: string }) {
  const queryClient = useQueryClient();
  const queryKey = ['replay-review', replayId];
  const { data, error } = useQuery({
    queryKey,
    queryFn: () => getReplayReview(replayId),
    retry: false,
  });
  const grade = useMutation({
    mutationFn: (request: GradeRequest) => setGrade(replayId, request),
    // Show the grade straight away, then reload what the server stored
    onMutate: (request) => {
      queryClient.setQueryData<ReplayReview>(queryKey, (old) => old && applyGrade(old, request));
    },
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey });
      queryClient.invalidateQueries({ queryKey: ['grades'] });
    },
  });

  // An older API has no review endpoint. The rest of the page still works.
  if (error || !data) return null;
  return <GameReviewBody review={data} onGrade={grade.mutate} />;
}

export function GameReviewBody({
  review,
  onGrade,
}: {
  review: ReplayReview;
  onGrade?: (request: GradeRequest) => void;
}) {
  if (review.status !== 'ok') {
    const message =
      review.status === 'missing'
        ? 'This game has no mistake review yet. Run uv run rlcoach reviews to add it.'
        : review.status === 'unsupported'
          ? "Mistake reviews only cover standard arenas, so this game doesn't have one."
          : `The mistake review failed: ${review.error ?? 'unknown error'}`;
    return <Card className="p-5 text-[var(--color-text-muted)]">{message}</Card>;
  }

  const groups = groupByCategory(review.mistakes);
  const against = review.goals.filter((g) => !g.ours);

  return (
    <div className="space-y-6">
      <section aria-labelledby="timeline-title">
        <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1 mb-3">
          <h2 id="timeline-title" className="type-display text-[21px]">
            Timeline
          </h2>
          <span className="text-[13px] text-[var(--color-text-muted)]">
            Goals spike up for your team and down for theirs. Your flagged moments are the small bumps.
          </span>
        </div>
        <Timeline review={review} />
      </section>

      <div className="grid lg:grid-cols-2 gap-6 items-start">
        <Card>
          <CardHeader className="border-b border-[var(--color-border)]">
            <h2 className="type-display text-[19px]">Your flagged moments</h2>
            <p className="text-[13px] text-[var(--color-text-muted)] mt-1">
              {review.mistakes.length} in this game. Mark each one right or wrong as you rewatch.
            </p>
          </CardHeader>
          <CardContent className="space-y-6">
            {groups.length === 0 && <p className="text-[var(--color-text-muted)]">Nothing flagged. Clean game.</p>}
            {groups.map((group) => (
              <div key={group.category}>
                <h3 className="flex items-baseline gap-2 mb-3">
                  <span className="font-semibold">{group.label}</span>
                  {group.goals > 0 && (
                    <span className="text-[13px] font-semibold text-[var(--color-error)]">
                      cost {group.goals} goal{group.goals === 1 ? '' : 's'}
                    </span>
                  )}
                </h3>
                <ul className="space-y-5">
                  {group.items.map((m) => (
                    <li key={`${m.t}-${m.kind}`} className="grid grid-cols-[3.25rem_minmax(0,1fr)] gap-x-3">
                      <span className="type-score text-[20px] pt-0.5">{m.clock}</span>
                      <div className="space-y-1.5 text-[15px]">
                        <p>
                          <span className="font-semibold">{m.label}.</span> {m.what}
                        </p>
                        {m.outcome && (
                          <p className={m.cost_goal ? 'text-[var(--color-error)] font-semibold' : 'text-[var(--color-text-muted)]'}>
                            {m.outcome}
                          </p>
                        )}
                        <p className="text-[var(--color-text-muted)]">
                          <span className="font-semibold text-[var(--color-text)]">Instead:</span> {m.instead}
                        </p>
                        <GradeButtons
                          grade={m.grade}
                          what={`${m.clock} ${m.label}`}
                          onChange={onGrade && ((grade) => onGrade({ item: 'mistake', kind: m.kind, t: m.t, grade }))}
                        />
                      </div>
                    </li>
                  ))}
                </ul>
              </div>
            ))}
            {review.clears > 0 && (
              <p className="text-[13px] text-[var(--color-text-muted)] pt-4 border-t border-[var(--color-border)]">
                {review.clears_given_back} of {review.clears} clears from your half went to an opponent before
                leaving your third.
              </p>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="border-b border-[var(--color-border)]">
            <h2 className="type-display text-[19px]">Goals against</h2>
            <p className="text-[13px] text-[var(--color-text-muted)] mt-1">
              {against.filter((g) => g.on_me).length} of {against.length} on you
            </p>
          </CardHeader>
          <CardContent>
            {against.length === 0 && <p className="text-[var(--color-text-muted)]">Clean sheet.</p>}
            <ul className="space-y-5">
              {against.map((g) => (
                <li key={g.t} className="grid grid-cols-[3.25rem_minmax(0,1fr)] gap-x-3">
                  <span className="type-score text-[20px] pt-0.5">{g.clock}</span>
                  <div className="space-y-1.5 text-[15px]">
                    <p>
                      <span className="font-semibold">{g.scorer}</span>{' '}
                      <span className="text-[var(--color-text-muted)]">({g.score})</span>{' '}
                      <span className={g.on_me ? 'text-[var(--color-error)] font-semibold' : 'text-[var(--color-text-muted)]'}>
                        {g.summary}
                      </span>
                    </p>
                    <ul className="text-[13px] text-[var(--color-text-muted)] space-y-0.5">
                      {g.lines.map((line) => (
                        <li key={line}>{line}</li>
                      ))}
                    </ul>
                    <GradeButtons
                      grade={g.grade}
                      what={`the verdict on the ${g.clock} goal`}
                      onChange={onGrade && ((grade) => onGrade({ item: 'goal', t: g.t, grade }))}
                    />
                  </div>
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

const GRADE_STYLES: Record<Grade, string> = {
  right: 'border-[var(--color-success)] bg-[var(--color-success)] text-[var(--color-on-primary)]',
  wrong: 'border-[var(--color-error)] bg-[var(--color-error)] text-[var(--color-on-primary)]',
};

/** Right and wrong buttons for one call. Pressing the chosen one again clears it. */
function GradeButtons({
  grade,
  what,
  onChange,
}: {
  grade: Grade | null;
  what: string;
  onChange?: (grade: Grade | null) => void;
}) {
  return (
    <div className="flex gap-1.5 pt-1">
      {(['right', 'wrong'] as const).map((value) => {
        const active = grade === value;
        return (
          <button
            key={value}
            type="button"
            aria-pressed={active}
            aria-label={`Mark ${what} ${value}`}
            disabled={!onChange}
            onClick={() => onChange?.(active ? null : value)}
            className={`px-2.5 py-0.5 rounded border text-[13px] font-medium transition-colors disabled:cursor-not-allowed ${
              active
                ? GRADE_STYLES[value]
                : 'border-[var(--color-border)] text-[var(--color-text-muted)] hover:text-[var(--color-text)] hover:border-[var(--color-text-muted)]'
            }`}
          >
            {value === 'right' ? 'Right' : 'Wrong'}
          </button>
        );
      })}
    </div>
  );
}

// The strip is drawn like an ECG: a flat line through the game clock that
// spikes at each goal and bumps at each flagged moment.
const WIDTH = 720;
const HEIGHT = 150;
const PAD = 14;
const BASE = 75;
const SPIKE = 54;

type StripEvent =
  | { x: number; kind: 'goal'; ours: boolean; byMe: boolean; label: string }
  | { x: number; kind: 'flag'; costGoal: boolean; label: string };

/** The trace's path, plus where each bump sits so it can be drawn over in colour. */
function tracePath(events: StripEvent[]) {
  const points: [number, number][] = [[PAD, BASE]];
  const bumps: { d: string; event: StripEvent }[] = [];
  // Events closer than the spike width share the line instead of doubling back
  const to = (x: number, y: number) => {
    const last = points[points.length - 1][0];
    points.push([Math.max(x, last), y]);
  };
  for (const e of events) {
    if (e.kind === 'goal') {
      const dir = e.ours ? -1 : 1;
      to(e.x - 5, BASE);
      to(e.x - 3, BASE - dir * 5);
      to(e.x, BASE + dir * SPIKE);
      to(e.x + 3, BASE - dir * 11);
      to(e.x + 6, BASE);
    } else {
      const h = e.costGoal ? 17 : 9;
      to(e.x - 6, BASE);
      const start = points[points.length - 1][0];
      const end = Math.max(e.x + 6, start + 12);
      const mid = (start + end) / 2;
      const d = `M ${start} ${BASE} Q ${mid} ${BASE - 2 * h} ${end} ${BASE}`;
      bumps.push({ d, event: e });
      // The trace jumps to the end of the bump, which is drawn on its own
      points.push([end, BASE]);
    }
  }
  to(WIDTH - PAD, BASE);
  const d = points.map(([x, y], i) => `${i === 0 ? 'M' : 'L'} ${x.toFixed(1)} ${y}`).join(' ');
  return { d, bumps };
}

function Timeline({ review }: { review: ReplayReview }) {
  const times = [...review.goals.map((g) => g.seconds_left), ...review.mistakes.map((m) => m.seconds_left)];
  const overtime = Math.max(0, -Math.min(0, ...times));
  const x = (seconds: number) => PAD + timelineX(seconds, overtime, WIDTH - 2 * PAD);
  const ticks = [REGULATION_SECONDS, REGULATION_SECONDS / 2, 0];

  const events: StripEvent[] = [
    ...review.goals.map(
      (g): StripEvent => ({
        x: x(g.seconds_left),
        kind: 'goal',
        ours: g.ours,
        byMe: g.by_me,
        label: `${g.clock} ${g.scorer} scored${g.winner ? ', the winner' : ''}`,
      }),
    ),
    ...review.mistakes.map(
      (m): StripEvent => ({ x: x(m.seconds_left), kind: 'flag', costGoal: m.cost_goal, label: `${m.clock} ${m.label}` }),
    ),
  ].sort((a, b) => a.x - b.x);
  const { d, bumps } = tracePath(events);
  const pct = (value: number) => `${(value / WIDTH) * 100}%`;

  return (
    <div className="rounded-md border border-[var(--color-border)] bg-[var(--strip-paper)] overflow-hidden">
      {/* On a phone the strip keeps its height and scrolls sideways, like paper */}
      <div className="overflow-x-auto">
        <div className="min-w-[34rem]">
          <svg
            viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
            className="block w-full h-auto"
            role="img"
            aria-label="Goals and flagged moments on the game clock"
          >
            <defs>
              <pattern id="strip-minor" width="6" height="6" patternUnits="userSpaceOnUse" x="0" y={BASE % 6}>
                <path d="M 6 0 L 0 0 0 6" fill="none" stroke="var(--strip-grid-minor)" strokeWidth={0.75} />
              </pattern>
              <pattern id="strip-major" width="30" height="30" patternUnits="userSpaceOnUse" x={PAD} y={BASE % 30}>
                <rect width="30" height="30" fill="url(#strip-minor)" />
                <path d="M 30 0 L 0 0 0 30" fill="none" stroke="var(--strip-grid-major)" strokeWidth={1} />
              </pattern>
            </defs>
            <rect width={WIDTH} height={HEIGHT} fill="url(#strip-major)" />
            {overtime > 0 && (
              <rect x={x(0)} y={0} width={x(-overtime) - x(0)} height={HEIGHT} fill="var(--chart-flag)" opacity={0.12} />
            )}
            {ticks.map((s) => (
              <line
                key={s}
                x1={x(s)}
                x2={x(s)}
                y1={0}
                y2={HEIGHT}
                stroke="var(--color-text-muted)"
                strokeWidth={1}
                strokeDasharray="2 4"
                opacity={0.6}
              />
            ))}

            <path d={d} fill="none" stroke="var(--chart-ink)" strokeWidth={1.75} strokeLinejoin="round" />

            {bumps.map(({ d: bump, event }, i) => (
              <g key={`b-${i}`}>
                <path
                  d={bump}
                  fill="none"
                  stroke="var(--chart-flag)"
                  strokeWidth={event.kind === 'flag' && event.costGoal ? 3.5 : 2.75}
                  strokeLinecap="round"
                />
                <circle cx={event.x} cy={BASE - 8} r={12} fill="transparent">
                  <title>{event.label}</title>
                </circle>
              </g>
            ))}

            {events.map((e) =>
              e.kind === 'goal' ? (
                <g key={`g-${e.x}-${e.label}`}>
                  {e.byMe && (
                    <circle
                      cx={e.x}
                      cy={BASE + (e.ours ? -SPIKE : SPIKE)}
                      r={10}
                      fill="none"
                      stroke="var(--chart-ink)"
                      strokeWidth={2}
                    />
                  )}
                  <circle
                    cx={e.x}
                    cy={BASE + (e.ours ? -SPIKE : SPIKE)}
                    r={6}
                    fill={e.ours ? 'var(--chart-good)' : 'var(--chart-bad)'}
                    stroke="var(--strip-paper)"
                    strokeWidth={2}
                  />
                  <circle cx={e.x} cy={BASE + (e.ours ? -SPIKE : SPIKE) / 2} r={14} fill="transparent">
                    <title>{e.label}</title>
                  </circle>
                </g>
              ) : null,
            )}
          </svg>

          <div className="relative h-7 border-t border-[var(--strip-grid-major)] text-[13px] text-[var(--color-text-muted)]">
            {ticks.map((s, i) => (
              <span
                key={s}
                className="absolute top-1 type-score text-[15px]"
                style={{
                  left: pct(x(s)),
                  transform: i === 0 ? 'none' : i === ticks.length - 1 && overtime === 0 ? 'translateX(-100%)' : 'translateX(-50%)',
                }}
              >
                {Math.floor(s / 60)}:{String(s % 60).padStart(2, '0')}
              </span>
            ))}
            {overtime > 0 && (
              <span
                className="absolute top-1 type-score text-[15px] text-[var(--color-warning)]"
                style={{ left: pct(x(-overtime)), transform: 'translateX(-100%)' }}
              >
                OT
              </span>
            )}
          </div>
        </div>
      </div>

      <div className="flex flex-wrap gap-x-5 gap-y-1.5 px-4 py-3 border-t border-[var(--color-border)] bg-[var(--color-bg-secondary)] text-[13px] text-[var(--color-text-muted)]">
        <LegendItem swatch={<circle cx={7} cy={7} r={5} fill="var(--chart-good)" />}>Your team's goals</LegendItem>
        <LegendItem swatch={<circle cx={7} cy={7} r={5} fill="var(--chart-bad)" />}>Their goals</LegendItem>
        <LegendItem swatch={<circle cx={7} cy={7} r={5.5} fill="none" stroke="var(--chart-ink)" strokeWidth={2} />}>
          Scored by you
        </LegendItem>
        <LegendItem
          swatch={<path d="M1 11 Q 7 -1 13 11" fill="none" stroke="var(--chart-flag)" strokeWidth={2.5} strokeLinecap="round" />}
        >
          Your flagged moments, taller when they cost a goal
        </LegendItem>
      </div>
    </div>
  );
}

function LegendItem({ swatch, children }: { swatch: React.ReactNode; children: React.ReactNode }) {
  return (
    <span className="inline-flex items-center gap-1.5">
      <svg viewBox="0 0 14 14" className="w-3.5 h-3.5" aria-hidden="true">
        {swatch}
      </svg>
      {children}
    </span>
  );
}
