import { NavLink, Outlet } from 'react-router-dom';

const TABS = [
  { to: 'trends', label: 'Trends' },
  { to: 'compare', label: 'Compare' },
];

export function Stats() {
  return (
    <div>
      <nav aria-label="Stats views" className="mb-8">
        <ul className="inline-flex gap-1 p-1 rounded-md bg-[var(--color-bg-tertiary)]">
          {TABS.map((tab) => (
            <li key={tab.to}>
              <NavLink
                to={tab.to}
                className={({ isActive }) =>
                  `block px-4 py-1.5 rounded text-[14px] ${
                    isActive
                      ? 'bg-[var(--color-bg-secondary)] text-[var(--color-text)] font-semibold shadow-[0_0_0_1px_var(--color-border)]'
                      : 'text-[var(--color-text-muted)] hover:text-[var(--color-text)]'
                  }`
                }
              >
                {tab.label}
              </NavLink>
            </li>
          ))}
        </ul>
      </nav>
      <Outlet />
    </div>
  );
}
