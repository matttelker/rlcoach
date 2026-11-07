interface CardProps {
  children: React.ReactNode;
  className?: string;
}

/** A sheet on the chart paper. */
export function Card({ children, className = '' }: CardProps) {
  return (
    <div className={`bg-[var(--color-bg-secondary)] rounded-md border border-[var(--color-border)] ${className}`}>
      {children}
    </div>
  );
}

export function CardHeader({ children, className = '' }: CardProps) {
  return <div className={`px-4 sm:px-5 pt-4 pb-3 ${className}`}>{children}</div>;
}

export function CardContent({ children, className = '' }: CardProps) {
  return <div className={`p-4 sm:p-5 ${className}`}>{children}</div>;
}
