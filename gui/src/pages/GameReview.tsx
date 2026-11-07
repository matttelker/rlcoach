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
    return (
      <Card>
        <CardContent className="text-sm text-[var(--color-text-muted)]">{message}</CardContent>
      </Card>
    );
  }

  const groups = groupByCategory(review.mistakes);
  const against = review.goals.filter((g) => !g.ours);

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader>
          <h2 className="text-lg font-semibold">Timeline</h2>
        </CardHeader>
        <CardContent>
          <Timeline review={review} />
        </CardContent>
      </Card>

      <div className="grid lg:grid-cols-2 gap-6">
        <Card>
          <CardHeader className="flex items-baseline gap-3">
            <h2 className="text-lg font-semibold">Your flagged moments</h2>
            <span className="text-xs text-[var(--color-text-muted)]">
              {review.mistakes.length} in this game · mark each right or wrong as you rewatch
            </span>
          </CardHeader>
          <CardContent className="space-y-5">
            {groups.length === 0 && (
              <p className="text-sm text-[var(--color-text-muted)]">Nothing flagged. Clean game.</p>
            )}
            {groups.map((group) => (
              <div key={group.category}>
                <div className="text-sm font-semibold mb-2">
                  {group.label}
                  {group.goals > 0 && (
                    <span className="ml-2 text-xs font-normal text-[var(--color-error)]">
                      cost {group.goals} goal{group.goals === 1 ? '' : 's'}
                    </span>
                  )}
                </div>
                <ul className="space-y-3">
                  {group.items.map((m) => (
                    <li key={`${m.t}-${m.kind}`} className="text-sm grid grid-cols-[48px_1fr] gap-2">
                      <span className="text-[var(--color-text-muted)] tabular-nums">{m.clock}</span>
                      <div className="space-y-1">
                        <div>
                          <span className="font-medium">{m.label}.</span> {m.what}
                        </div>
                        {m.outcome && (
                          <div className={m.cost_goal ? 'text-[var(--color-error)]' : 'text-[var(--color-text-muted)]'}>
                            {m.outcome}
                          </div>
                        )}
                        <div className="text-[var(--color-text-muted)]">Instead: {m.instead}</div>
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
              <p className="text-xs text-[var(--color-text-muted)] pt-2 border-t border-[var(--color-border)]">
                {review.clears_given_back} of {review.clears} clears from your half went to an opponent before
                leaving your third.
              </p>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex items-baseline gap-3">
            <h2 className="text-lg font-semibold">Goals against</h2>
            <span className="text-xs text-[var(--color-text-muted)]">
              {against.filter((g) => g.on_me).length} of {against.length} on you
            </span>
          </CardHeader>
          <CardContent className="space-y-4">
            {against.length === 0 && <p className="text-sm text-[var(--color-text-muted)]">Clean sheet.</p>}
            {against.map((g) => (
              <div key={g.t} className="text-sm grid grid-cols-[48px_1fr] gap-2">
                <span className="text-[var(--color-text-muted)] tabular-nums">{g.clock}</span>
                <div className="space-y-1">
                  <div>
                    <span className="font-medium">{g.scorer}</span>{' '}
                    <span className="text-[var(--color-text-muted)]">({g.score})</span>{' '}
                    <span className={g.on_me ? 'text-[var(--color-error)]' : 'text-[var(--color-text-muted)]'}>
                      {g.summary}
                    </span>
                  </div>
                  <ul className="text-xs text-[var(--color-text-muted)] space-y-0.5">
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
              </div>
            ))}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

const GRADE_STYLES: Record<Grade, string> = {
  right: 'border-[var(--color-success)] bg-[var(--color-success)]/15 text-[var(--color-success)]',
  wrong: 'border-[var(--color-error)] bg-[var(--color-error)]/15 text-[var(--color-error)]',
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
            className={`px-2 py-0.5 rounded border text-xs transition-colors ${
              active
                ? GRADE_STYLES[value]
                : 'border-[var(--color-border)] text-[var(--color-text-muted)] hover:text-[var(--color-text)]'
            }`}
          >
            {value === 'right' ? 'Right' : 'Wrong'}
          </button>
        );
      })}
    </div>
  );
}

const WIDTH = 720;
const PAD = 16;

function Timeline({ review }: { review: ReplayReview }) {
  const times = [...review.goals.map((g) => g.seconds_left), ...review.mistakes.map((m) => m.seconds_left)];
  const overtime = Math.max(0, -Math.min(0, ...times));
  const x = (seconds: number) => PAD + timelineX(seconds, overtime, WIDTH - 2 * PAD);
  const ticks = [REGULATION_SECONDS, REGULATION_SECONDS / 2, 0];

  return (
    <div>
      <svg viewBox={`0 0 ${WIDTH} 120`} className="w-full" role="img" aria-label="Goals and flagged moments on the game clock">
        <line x1={PAD} y1={60} x2={WIDTH - PAD} y2={60} stroke="var(--color-border)" strokeWidth={2} />
        {overtime > 0 && (
          <rect x={x(0)} y={54} width={x(-overtime) - x(0)} height={12} fill="var(--color-warning)" opacity={0.15} />
        )}
        {ticks.map((s) => (
          <text key={s} x={x(s)} y={114} fontSize={15} textAnchor="middle" fill="var(--color-text-muted)">
            {Math.floor(s / 60)}:{String(s % 60).padStart(2, '0')}
          </text>
        ))}
        {overtime > 0 && (
          <text x={x(-overtime)} y={114} fontSize={15} textAnchor="end" fill="var(--color-warning)">
            OT
          </text>
        )}
        {review.mistakes.map((m) => (
          <line
            key={`m-${m.t}-${m.kind}`}
            x1={x(m.seconds_left)}
            x2={x(m.seconds_left)}
            y1={m.cost_goal ? 46 : 50}
            y2={m.cost_goal ? 74 : 70}
            stroke="var(--color-warning)"
            strokeWidth={m.cost_goal ? 4 : 3}
          >
            <title>{`${m.clock} ${m.label}`}</title>
          </line>
        ))}
        {review.goals.map((g) => (
          <circle
            key={`g-${g.t}`}
            cx={x(g.seconds_left)}
            cy={g.ours ? 24 : 96}
            r={8}
            fill={g.ours ? 'var(--color-success)' : 'var(--color-error)'}
            stroke={g.by_me ? 'var(--color-primary)' : 'none'}
            strokeWidth={g.by_me ? 4 : 0}
          >
            <title>{`${g.clock} ${g.scorer} scored${g.winner ? ', the winner' : ''}`}</title>
          </circle>
        ))}
      </svg>
      <div className="flex flex-wrap gap-x-5 gap-y-1 text-xs text-[var(--color-text-muted)] mt-1">
        <span>
          <span className="inline-block w-2.5 h-2.5 rounded-full bg-[var(--color-success)] mr-1.5" />
          Your team's goals
        </span>
        <span>
          <span className="inline-block w-2.5 h-2.5 rounded-full bg-[var(--color-error)] mr-1.5" />
          Their goals
        </span>
        <span>
          <span className="inline-block w-2.5 h-2.5 rounded-full border-2 border-[var(--color-primary)] mr-1.5" />
          Scored by you
        </span>
        <span>
          <span className="inline-block w-1 h-3 bg-[var(--color-warning)] mr-1.5 align-middle" />
          Your flagged moments, taller when they cost a goal
        </span>
      </div>
    </div>
  );
}
