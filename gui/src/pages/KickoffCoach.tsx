import { Card, CardContent, CardHeader } from '../components';
import type {
  KickoffDay,
  KickoffGoing,
  KickoffResults,
  KickoffSummary,
  LadderStatus,
  LadderStep,
  ReviewKickoff,
} from '../types/api';
import { parseLocalDate } from './dataTransforms';
import {
  RESULT_LABELS,
  STEP_STATUS,
  approachLabel,
  flipText,
  goalAfterText,
  kickoffSeat,
  percent,
  shareOf,
} from './coachTransforms';

const UU_S_TO_KPH = 0.036;

/** Your kickoffs across the games on the Coach page, led by what to learn next. */
export function KickoffCoach({ summary }: { summary: KickoffSummary }) {
  if (summary.count === 0) {
    return (
      <Card className="p-5 text-[var(--color-text-muted)]">
        No kickoffs stored for these games yet. Run{' '}
        <code className="px-1 rounded bg-[var(--color-bg-tertiary)]">uv run rlcoach reviews --redo</code> to add them
        to games loaded before kickoff coaching.
      </Card>
    );
  }
  return (
    <div className="space-y-6">
      <Ladder steps={summary.ladder} />
      <div className="grid lg:grid-cols-2 gap-6 items-start">
        <GoingCard going={summary.going} />
        <SupportCard summary={summary} />
      </div>
      {summary.sessions.length > 1 && <OnTimeByDay days={summary.sessions} />}
    </div>
  );
}

const STATUS_STYLES: Record<LadderStatus, string> = {
  solid: 'text-[var(--color-success)]',
  focus: 'text-[var(--color-error)] font-semibold',
  later: 'text-[var(--color-text-muted)]',
  unknown: 'text-[var(--color-text-muted)]',
};

function Ladder({ steps }: { steps: LadderStep[] }) {
  return (
    <ol className="rounded-md border border-[var(--color-border)] bg-[var(--color-bg-secondary)] divide-y divide-[var(--color-border)] overflow-hidden">
      {steps.map((step, index) => {
        const focus = step.status === 'focus';
        return (
          <li
            key={step.key}
            className={`grid grid-cols-[2.25rem_minmax(0,1fr)] gap-x-3 p-5 ${focus ? 'bg-[var(--strip-paper)]' : ''}`}
          >
            <span
              className={`type-score text-[30px] ${focus ? 'text-[var(--color-error)]' : 'text-[var(--color-text-muted)]'}`}
            >
              <span className="sr-only">Step </span>
              {index + 1}
            </span>
            <div className="min-w-0">
              <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
                <span className={`font-semibold ${focus ? 'text-[19px]' : 'text-[17px]'}`}>{step.title}</span>
                <span className="text-[13px] text-[var(--color-text-muted)]">{step.level}</span>
                <span className={`text-[13px] ${STATUS_STYLES[step.status]}`}>{STEP_STATUS[step.status]}</span>
              </div>
              <StepMeter step={step} />
              <p className="mt-2 text-[14px] text-[var(--color-text-muted)] max-w-[72ch]">{step.why}</p>
              {focus ? (
                <div className="mt-3 rounded border border-[var(--color-border)] bg-[var(--color-bg-secondary)] p-4">
                  <div className="text-[13px] font-semibold text-[var(--color-error)]">What to practise</div>
                  <p className="mt-1 text-[17px] leading-[1.55] max-w-[60ch]">{step.how}</p>
                </div>
              ) : (
                <details className="mt-2 text-[14px]">
                  <summary className="cursor-pointer text-[var(--color-text-muted)] hover:text-[var(--color-text)]">
                    What to practise
                  </summary>
                  <p className="mt-1.5 max-w-[60ch]">{step.how}</p>
                </details>
              )}
            </div>
          </li>
        );
      })}
    </ol>
  );
}

/** Your share against the target, as a bar with the target marked on it. */
function StepMeter({ step }: { step: LadderStep }) {
  const filled = step.value === null ? 0 : Math.min(1, step.value) * 100;
  return (
    <div className="mt-2.5">
      <div className="text-[14px]">
        {step.measure}:{' '}
        <span className="font-semibold">
          {step.count} of {step.of}
        </span>{' '}
        <span className="text-[var(--color-text-muted)]">
          ({percent(step.value)}, your target {percent(step.target)})
        </span>
      </div>
      <div
        className="relative mt-1.5 h-2 max-w-80 rounded bg-[var(--color-bg-tertiary)]"
        role="img"
        aria-label={`${percent(step.value)} against a target of ${percent(step.target)}`}
      >
        <div
          className="h-2 rounded"
          style={{
            width: `${filled}%`,
            background: step.status === 'solid' ? 'var(--chart-good)' : 'var(--chart-bad)',
          }}
        />
        <div
          className="absolute -top-1 h-4 w-0.5 bg-[var(--color-text)]"
          style={{ left: `${step.target * 100}%` }}
          aria-hidden="true"
        />
      </div>
    </div>
  );
}

function ResultShares({ results, count }: { results: KickoffResults; count: number }) {
  return (
    <span>
      <span className="text-[var(--color-success)]">{shareOf(results.won, count)} went your way</span>,{' '}
      {shareOf(results.even, count)} even,{' '}
      <span className="text-[var(--color-error)]">{shareOf(results.lost, count)} came back at you</span>
    </span>
  );
}

const FLIP_ROWS = { ON_TIME: 'Flip on time', LATE: 'Flip late', NONE: 'No flip into the ball' } as const;

function GoingCard({ going }: { going: KickoffGoing }) {
  const speed = going.median_speed === null ? '–' : `${Math.round(going.median_speed * UU_S_TO_KPH)} km/h`;
  return (
    <Card>
      <CardHeader className="border-b border-[var(--color-border)]">
        <h3 className="type-display text-[19px]">When you go</h3>
        <p className="text-[13px] text-[var(--color-text-muted)] mt-1">
          {going.count} kickoffs, {going.fakes} of them faked. Where the ball was a second after the hit.
        </p>
      </CardHeader>
      <div className="overflow-x-auto">
        <table className="w-full min-w-[26rem]">
          <thead>
            <tr className="border-b border-[var(--color-border)]">
              <th className="th text-left pl-5">Your flip</th>
              <th className="th text-right w-20">Kickoffs</th>
              <th className="th text-right w-24">Your way</th>
              <th className="th text-right w-28 pr-5">Back at you</th>
            </tr>
          </thead>
          <tbody>
            {going.by_flip.map((group) => (
              <tr key={group.flip} className="border-b last:border-b-0 border-[var(--color-border)]">
                <td className="px-3 pl-5 py-2.5">{FLIP_ROWS[group.flip]}</td>
                <td className="px-3 py-2.5 text-right">{group.count}</td>
                <td className="px-3 py-2.5 text-right text-[var(--color-success)]">{shareOf(group.won, group.count)}</td>
                <td className="px-3 pr-5 py-2.5 text-right text-[var(--color-error)]">
                  {shareOf(group.lost, group.count)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <CardContent>
        <dl className="grid grid-cols-[auto_minmax(0,1fr)] gap-x-4 gap-y-2 text-[14px]">
          <dt className="text-[var(--color-text-muted)]">Speedflips</dt>
          <dd>
            {going.speedflips} of {going.went}
          </dd>
          <dt className="text-[var(--color-text-muted)]">Race to the ball</dt>
          <dd>
            {going.race.compared === 0
              ? '–'
              : `There first in ${going.race.sooner}, second in ${going.race.later} of ${going.race.compared}`}
          </dd>
          <dt className="text-[var(--color-text-muted)]">Speed at the hit</dt>
          <dd>{speed}, the middle of your kickoffs</dd>
          <dt className="text-[var(--color-text-muted)]">Goals within 10 s</dt>
          <dd>
            {going.goals_for} for, {going.goals_against} against
          </dd>
        </dl>
      </CardContent>
    </Card>
  );
}

function SupportCard({ summary }: { summary: KickoffSummary }) {
  const support = summary.support;
  return (
    <Card>
      <CardHeader className="border-b border-[var(--color-border)]">
        <h3 className="type-display text-[19px]">When a teammate goes</h3>
        <p className="text-[13px] text-[var(--color-text-muted)] mt-1">{support.count} kickoffs</p>
      </CardHeader>
      <CardContent>
        <dl className="grid grid-cols-[auto_minmax(0,1fr)] gap-x-4 gap-y-2 text-[14px]">
          <dt className="text-[var(--color-text-muted)]">Where the ball went</dt>
          <dd>
            <ResultShares results={support.results} count={support.count} />
          </dd>
          <dt className="text-[var(--color-text-muted)]">You cheated up</dt>
          <dd>{support.cheat}</dd>
          <dt className="text-[var(--color-text-muted)]">You held back</dt>
          <dd>{support.hold}</dd>
          <dt className="text-[var(--color-text-muted)]">You went too</dt>
          <dd className={support.double_commits ? 'text-[var(--color-error)]' : ''}>{support.double_commits}</dd>
          <dt className="text-[var(--color-text-muted)]">Goals within 10 s</dt>
          <dd>
            {support.goals_for} for, {support.goals_against} against
          </dd>
        </dl>
      </CardContent>
    </Card>
  );
}

function dayLabel(playDate: string): string {
  return parseLocalDate(playDate).toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
}

/** On-time flips each day you played, to see the step you're working on move. */
function OnTimeByDay({ days }: { days: KickoffDay[] }) {
  const played = days.filter((day) => day.went > 0);
  if (played.length < 2) return null;
  return (
    <Card>
      <CardHeader className="border-b border-[var(--color-border)]">
        <h3 className="type-display text-[19px]">Flips on time, by day</h3>
        <p className="text-[13px] text-[var(--color-text-muted)] mt-1">Of the kickoffs you went for</p>
      </CardHeader>
      <ul className="divide-y divide-[var(--color-border)]">
        {played.map((day) => (
          <li key={day.play_date} className="grid grid-cols-[5rem_minmax(0,1fr)_6rem] items-center gap-x-4 px-5 py-2.5">
            <span className="text-[14px]">{dayLabel(day.play_date)}</span>
            <div className="h-2 rounded bg-[var(--color-bg-tertiary)]">
              <div
                className="h-2 rounded"
                style={{ width: `${(100 * day.on_time) / day.went}%`, background: 'var(--chart-good)' }}
              />
            </div>
            <span className="text-[14px] text-right">
              {day.on_time} of {day.went}
            </span>
          </li>
        ))}
      </ul>
    </Card>
  );
}

const RESULT_STYLES = {
  WON: 'text-[var(--color-success)]',
  EVEN: 'text-[var(--color-text-muted)]',
  LOST: 'text-[var(--color-error)]',
} as const;

/** Every kickoff of one game on the clock, as you played it. */
export function KickoffList({ kickoffs }: { kickoffs: ReviewKickoff[] }) {
  const going = kickoffs.filter((k) => k.role === 'GO').length;
  return (
    <Card>
      <CardHeader className="border-b border-[var(--color-border)]">
        <h2 className="type-display text-[19px]">Kickoffs</h2>
        <p className="text-[13px] text-[var(--color-text-muted)] mt-1">
          {kickoffs.length} in this game, {going} with you going. The result is where the ball was a second after the
          hit.
        </p>
      </CardHeader>
      <CardContent>
        <ul className="space-y-4">
          {kickoffs.map((k) => {
            const flip = flipText(k.flip, k.flip_lead);
            const goal = goalAfterText(k);
            return (
              <li key={k.t} className="grid grid-cols-[3.25rem_minmax(0,1fr)] gap-x-3">
                <span className="type-score text-[20px] pt-0.5">{k.phase === 'OT' ? 'OT' : k.clock}</span>
                <div className="space-y-1 text-[15px]">
                  <p>
                    <span className="font-semibold">{kickoffSeat(k)}.</span> {approachLabel(k.approach)}
                    {flip && <span className="text-[var(--color-text-muted)]">, {flip.charAt(0).toLowerCase() + flip.slice(1)}</span>}
                    {k.result && <span className={`ml-2 text-[13px] ${RESULT_STYLES[k.result]}`}>{RESULT_LABELS[k.result]}</span>}
                  </p>
                  {(k.double_commit || goal) && (
                    <p className="text-[13px] text-[var(--color-text-muted)]">
                      {k.double_commit && <span className="text-[var(--color-error)]">You and a teammate both went. </span>}
                      {goal && (
                        <span className={k.goal_after === 'against' ? 'text-[var(--color-error)] font-semibold' : ''}>
                          {goal}.
                        </span>
                      )}
                    </p>
                  )}
                </div>
              </li>
            );
          })}
        </ul>
      </CardContent>
    </Card>
  );
}
