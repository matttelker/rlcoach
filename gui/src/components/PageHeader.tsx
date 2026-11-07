interface PageHeaderProps {
  title: React.ReactNode;
  note?: React.ReactNode;
  /** Filters and other controls, set at the right on wide screens */
  children?: React.ReactNode;
}

export function PageHeader({ title, note, children }: PageHeaderProps) {
  return (
    <div className="flex flex-wrap items-end gap-x-4 gap-y-5 mb-8">
      <div className="mr-auto">
        <h1 className="type-display text-[30px] sm:text-[36px]">{title}</h1>
        {note && <p className="mt-2 text-[var(--color-text-muted)]">{note}</p>}
      </div>
      {children && <div className="flex flex-wrap items-end gap-3">{children}</div>}
    </div>
  );
}

/** A section heading with an optional note beside it. */
export function SectionTitle({ title, note }: { title: string; note?: string }) {
  return (
    <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1 mb-4">
      <h2 className="type-display text-[21px]">{title}</h2>
      {note && <span className="text-[13px] text-[var(--color-text-muted)]">{note}</span>}
    </div>
  );
}
