import { PAGE_SIZE, pageOf } from './paging';

/** Previous and Next under a list the API sends a page at a time. Nothing when it fits on one page. */
export function Pagination({
  offset,
  total,
  onOffset,
}: {
  offset: number;
  total: number;
  onOffset: (offset: number) => void;
}) {
  const { page, pages } = pageOf(offset, total);
  if (pages < 2) return null;
  return (
    <div className="flex items-center justify-between gap-4 px-4 sm:px-5 py-3 border-t border-[var(--color-border)]">
      <div className="text-[13px] text-[var(--color-text-muted)]">
        Page {page} of {pages}
      </div>
      <div className="flex gap-2">
        <button type="button" className="btn" disabled={offset === 0} onClick={() => onOffset(offset - PAGE_SIZE)}>
          Previous
        </button>
        <button type="button" className="btn" disabled={page >= pages} onClick={() => onOffset(offset + PAGE_SIZE)}>
          Next
        </button>
      </div>
    </div>
  );
}
