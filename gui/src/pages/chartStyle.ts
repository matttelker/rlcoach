// Shared Recharts styling, so every chart reads from the same tokens

export const AXIS_PROPS = {
  stroke: 'var(--color-border)',
  tick: { fill: 'var(--color-text-muted)', fontSize: 13 },
  tickLine: false,
} as const;

export const TOOLTIP_PROPS = {
  contentStyle: {
    backgroundColor: 'var(--color-bg-secondary)',
    border: '1px solid var(--color-border)',
    borderRadius: '6px',
    color: 'var(--color-text)',
    fontSize: 14,
  },
  labelStyle: { color: 'var(--color-text)', fontWeight: 600 },
  itemStyle: { color: 'var(--color-text)' },
  cursor: { stroke: 'var(--color-text-muted)', strokeDasharray: '3 3' },
} as const;
