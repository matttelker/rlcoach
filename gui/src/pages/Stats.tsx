import { NavLink, Outlet } from 'react-router-dom';

const TABS = [
  { to: 'trends', label: 'Trends' },
  { to: 'compare', label: 'Compare' },
  { to: 'benchmarks', label: 'Benchmarks' },
];

export function Stats() {
  return (
    <div className="space-y-6">
      <nav className="flex gap-1 border-b border-[var(--color-border)]" aria-label="Stats views">
        {TABS.map((tab) => (
          <NavLink
            key={tab.to}
            to={tab.to}
            className={({ isActive }) =>
              `px-4 py-2 text-sm font-medium -mb-px border-b-2 ${
                isActive
                  ? 'border-[var(--color-primary)] text-[var(--color-text)]'
                  : 'border-transparent text-[var(--color-text-muted)] hover:text-[var(--color-text)]'
              }`
            }
          >
            {tab.label}
          </NavLink>
        ))}
      </nav>
      <Outlet />
    </div>
  );
}
