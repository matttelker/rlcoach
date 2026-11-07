interface PaginationProps {
  currentPage: number;
  totalPages: number;
  previousDisabled: boolean;
  nextDisabled: boolean;
  onPrevious: () => void;
  onNext: () => void;
}

export function Pagination({
  currentPage,
  totalPages,
  previousDisabled,
  nextDisabled,
  onPrevious,
  onNext,
}: PaginationProps) {
  return (
    <div className="flex items-center justify-between gap-4 px-4 sm:px-5 py-3 border-t border-[var(--color-border)]">
      <div className="text-[13px] text-[var(--color-text-muted)]">
        Page {currentPage} of {totalPages}
      </div>
      <div className="flex gap-2">
        <button type="button" onClick={onPrevious} disabled={previousDisabled} className="btn">
          Previous
        </button>
        <button type="button" onClick={onNext} disabled={nextDisabled} className="btn">
          Next
        </button>
      </div>
    </div>
  );
}
