/** W, L or D in a filled square, then the score in scoreboard numerals. */
export function ResultMark({ result, score }: { result: string | null; score: string }) {
  const fill =
    result === 'WIN'
      ? 'bg-[var(--color-success)]'
      : result === 'LOSS'
        ? 'bg-[var(--color-error)]'
        : 'bg-[var(--color-warning)]';
  const letter = result === 'WIN' ? 'W' : result === 'LOSS' ? 'L' : 'D';
  return (
    <span className="inline-flex items-center gap-2">
      <span
        className={`type-score text-[13px] w-5 h-5 grid place-items-center rounded-sm text-[var(--color-on-primary)] ${fill}`}
      >
        {letter}
      </span>
      <span className="type-score text-[22px]">{score}</span>
    </span>
  );
}
