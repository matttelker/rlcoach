interface EmptyStateProps {
  title: string;
  description?: React.ReactNode;
  tone?: 'neutral' | 'error';
  action?: React.ReactNode;
}

/** A flat line on the monitor: nothing to show yet, and what to do about it. */
export function EmptyState({ title, description, tone = 'neutral', action }: EmptyStateProps) {
  return (
    <div className="flex flex-col items-center justify-center py-12 px-4 text-center">
      <FlatLine error={tone === 'error'} />
      <h3 className="type-display text-[18px] mt-5 mb-2">{title}</h3>
      {description && <p className="text-[var(--color-text-muted)] max-w-md">{description}</p>}
      {action && <div className="mt-4">{action}</div>}
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

export function NoGamesEmpty() {
  return (
    <EmptyState
      title="No games yet"
      description={
        <>
          Replays in your watch folder load on their own, about 30 seconds after a match ends. If none show up, check{' '}
          <code className="px-1 rounded bg-[var(--color-bg-tertiary)]">watch_folder</code> in{' '}
          <code className="px-1 rounded bg-[var(--color-bg-tertiary)]">~/.rlcoach/config.toml</code>.
        </>
      }
    />
  );
}

export function NoDataEmpty({
  message = 'No data yet',
  description = 'Play more games to fill this in.',
}: {
  message?: string;
  description?: string;
}) {
  return <EmptyState title={message} description={description} />;
}

export function ErrorState({ message = 'Something went wrong' }: { message?: string }) {
  return <EmptyState tone="error" title="Couldn't load this" description={message} />;
}
