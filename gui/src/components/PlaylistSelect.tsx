const PLAYLIST_OPTIONS = [
  { value: 'STANDARD', label: 'Standard' },
  { value: 'DOUBLES', label: 'Doubles' },
  { value: 'DUEL', label: 'Duel' },
];

interface PlaylistSelectProps {
  value: string | undefined;
  onChange: (playlist: string) => void;
}

export function PlaylistSelect({ value, onChange }: PlaylistSelectProps) {
  return (
    <div>
      <label className="block text-xs text-[var(--color-text-muted)] mb-1">Playlist</label>
      <select
        value={value ?? ''}
        onChange={(e) => onChange(e.target.value)}
        className="bg-[var(--color-bg-tertiary)] border border-[var(--color-border)] rounded px-3 py-2 text-sm text-[var(--color-text)]"
      >
        {PLAYLIST_OPTIONS.map((opt) => (
          <option key={opt.value} value={opt.value}>
            {opt.label}
          </option>
        ))}
      </select>
    </div>
  );
}
