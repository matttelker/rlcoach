import type { ReactNode } from 'react';

type BoxProps = { children: ReactNode; className?: string };

/** The box's own classes, then any the caller adds */
const withExtra = (own: string, extra?: string) => (extra ? `${own} ${extra}` : own);

/** A sheet on the chart paper. */
export function Card({ children, className }: BoxProps) {
  return (
    <div className={withExtra('bg-[var(--color-bg-secondary)] rounded-md border border-[var(--color-border)]', className)}>
      {children}
    </div>
  );
}

export function CardHeader({ children, className }: BoxProps) {
  return <div className={withExtra('px-4 sm:px-5 pt-4 pb-3', className)}>{children}</div>;
}

export function CardContent({ children, className }: BoxProps) {
  return <div className={withExtra('p-4 sm:p-5', className)}>{children}</div>;
}
