import type { ReactNode } from 'react';

/** A flat line on the monitor: nothing to show yet, and what to do about it. */
function Notice({ title, error = false, children }: { title: string; error?: boolean; children: ReactNode }) {
  return (
    <div className="flex flex-col items-center justify-center py-12 px-4 text-center">
      <FlatLine error={error} />
      <h3 className="type-display text-[18px] mt-5 mb-2">{title}</h3>
      <p className="text-[var(--color-text-muted)] max-w-md">{children}</p>
    </div>
  );
}

function FlatLine({ error }: { error: boolean }) {
  return (
    <svg viewBox="0 0 120 24" className="w-28 h-6" aria-hidden="true">
      <path
        d={error ? 'M2 12h40l6-8 8 16 6-8h56' : 'M2 12h50l4-3 4 3h58'}
        fill="none"
        stroke={error ? 'var(--chart-bad)' : 'var(--color-text-muted)'}
        strokeWidth={2}
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

/** Before the first replay has loaded */
export function NoGamesEmpty() {
  return (
    <Notice title="No games yet">
      Replays in your watch folder load on their own, about 30 seconds after a match ends. If none show up, check{' '}
      <code className="px-1 rounded bg-[var(--color-bg-tertiary)]">watch_folder</code> in{' '}
      <code className="px-1 rounded bg-[var(--color-bg-tertiary)]">~/.rlcoach/config.toml</code>.
    </Notice>
  );
}

/** A playlist, period or rank with nothing in it to show */
export function NoDataEmpty({ message, description }: { message: string; description: string }) {
  return <Notice title={message}>{description}</Notice>;
}

/** The API didn't answer, or answered with an error */
export function ErrorState({ message }: { message: string }) {
  return (
    <Notice title="Couldn't load this" error>
      {message}
    </Notice>
  );
}
