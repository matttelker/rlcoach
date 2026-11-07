import { NavLink, Outlet } from 'react-router-dom';

const navItems = [
  { path: '/', label: 'Coach' },
  { path: '/games', label: 'Games' },
  { path: '/stats', label: 'Stats' },
  { path: '/players', label: 'Players' },
];

export function Layout() {
  return (
    <div className="min-h-screen">
      <header className="border-b border-[var(--color-border)] bg-[var(--color-bg-secondary)]">
        <div className="mx-auto max-w-6xl px-4 sm:px-6 flex flex-wrap items-center gap-x-8 gap-y-1 pt-3 sm:pt-0">
          <NavLink to="/" className="flex items-center gap-2.5 py-1 sm:py-3.5 text-[var(--color-text)]">
            <BrandMark className="h-7 w-auto" />
            <span className="type-display text-[19px]">Soccar Doctor</span>
          </NavLink>
          <nav aria-label="Main" className="-mx-4 sm:mx-0 w-[calc(100%+2rem)] sm:w-auto overflow-x-auto overflow-y-hidden">
            <ul className="flex px-2 sm:px-0">
              {navItems.map((item) => (
                <li key={item.path}>
                  <NavLink
                    to={item.path}
                    end={item.path === '/'}
                    className={({ isActive }) =>
                      `block px-3 py-3 sm:py-[18px] text-[15px] whitespace-nowrap border-b-2 ${
                        isActive
                          ? 'border-[var(--color-text)] text-[var(--color-text)] font-semibold'
                          : 'border-transparent text-[var(--color-text-muted)] hover:text-[var(--color-text)]'
                      }`
                    }
                  >
                    {item.label}
                  </NavLink>
                </li>
              ))}
            </ul>
          </nav>
        </div>
      </header>

      <main className="mx-auto max-w-6xl px-4 sm:px-6 py-8 sm:py-10">
        <Outlet />
      </main>
    </div>
  );
}

/** A heartbeat with a ball at its peak. The same mark is the favicon. */
function BrandMark({ className }: { className?: string }) {
  return (
    <svg className={className} viewBox="2 2 28 26" aria-hidden="true">
      <path
        d="M3 20h5l2-3 2 3h3l3.5-12L22 26l2-6h5"
        fill="none"
        stroke="var(--chart-bad)"
        strokeWidth={2.4}
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <circle cx={18.5} cy={6.5} r={3.6} fill="var(--color-text)" />
    </svg>
  );
}
