import type { ReactNode } from 'react';
import { Link } from 'react-router-dom';

/** A chevron and the name of the list a detail page came from, linking back to it. */
export function BackLink({ to, children }: { to: string; children: ReactNode }) {
  return (
    <Link
      to={to}
      className="inline-flex items-center gap-1 text-[14px] text-[var(--color-text-muted)] hover:text-[var(--color-text)]"
    >
      <svg
        className="w-4 h-4"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth={2}
        strokeLinecap="round"
        strokeLinejoin="round"
        aria-hidden="true"
      >
        <path d="M15 19l-7-7 7-7" />
      </svg>
      {children}
    </Link>
  );
}
