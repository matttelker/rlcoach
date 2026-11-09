import type { ReactNode } from 'react';
import type { PaginatedResponse } from '../types/api';
import { Card } from './Card';
import { ErrorState } from './EmptyState';
import { Pagination } from './Pagination';
import { SkeletonTable } from './Skeleton';

/**
 * A card holding one page of a list from the API: what went wrong, rows of
 * placeholders while it loads, what to say when it's empty, or the table with
 * Previous and Next under it.
 */
export function PagedList<T>({
  list,
  loading,
  failed,
  failure,
  empty,
  offset,
  onOffset,
  children,
}: {
  list: PaginatedResponse<T> | undefined;
  loading: boolean;
  failed: boolean;
  /** What to say when the list doesn't load */
  failure: string;
  /** What to show when nothing matches */
  empty: ReactNode;
  offset: number;
  onOffset: (offset: number) => void;
  /** The table of this page's items */
  children: (items: T[]) => ReactNode;
}) {
  let body: ReactNode;
  if (failed) {
    body = <ErrorState message={failure} />;
  } else if (loading) {
    body = (
      <div className="p-4">
        <SkeletonTable />
      </div>
    );
  } else if (list?.items.length === 0) {
    body = empty;
  } else {
    body = (
      <>
        {children(list?.items ?? [])}
        <Pagination offset={offset} total={list?.total ?? 0} onOffset={onOffset} />
      </>
    );
  }
  return <Card className="overflow-x-auto">{body}</Card>;
}
