// Pulsing grey bars in the shape of what's still loading

function Bar({ size }: { size: string }) {
  return <div className={`animate-pulse bg-[var(--color-bg-tertiary)] rounded ${size}`} />;
}

const CARD_BARS = ['h-4 w-1/3', 'h-8 w-1/2', 'h-3 w-2/3'];
const ROW_BARS = ['h-4 w-24', 'h-4 w-32', 'h-4 w-20', 'h-4 flex-1'];
const TABLE_ROWS = 10;

export function SkeletonCard() {
  return (
    <div className="bg-[var(--color-bg-secondary)] border border-[var(--color-border)] rounded-md p-5 space-y-3">
      {CARD_BARS.map((size) => (
        <Bar key={size} size={size} />
      ))}
    </div>
  );
}

/** Two cards, for a page that waits on one answer before it shows anything */
export function LoadingCards() {
  return (
    <div className="space-y-6">
      <SkeletonCard />
      <SkeletonCard />
    </div>
  );
}

/** A page of table rows */
export function SkeletonTable() {
  const rows = Array.from({ length: TABLE_ROWS }, (_, row) => row);
  return (
    <div className="space-y-2">
      {rows.map((row) => (
        <div key={row} className="flex gap-4 p-3">
          {ROW_BARS.map((size) => (
            <Bar key={size} size={size} />
          ))}
        </div>
      ))}
    </div>
  );
}

export function SkeletonChart() {
  return <Bar size="h-72 w-full" />;
}
