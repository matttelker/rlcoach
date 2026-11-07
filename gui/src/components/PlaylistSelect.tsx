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
    <label>
      <span className="field-label">Playlist</span>
      <select value={value ?? ''} onChange={(e) => onChange(e.target.value)} className="field">
        {PLAYLIST_OPTIONS.map((opt) => (
          <option key={opt.value} value={opt.value}>
            {opt.label}
          </option>
        ))}
      </select>
    </label>
  );
}

/** A labelled select for short option lists like period and rank. */
export function SelectField<T extends string>({
  label,
  value,
  options,
  onChange,
}: {
  label: string;
  value: T;
  options: { value: T; label: string }[];
  onChange: (value: T) => void;
}) {
  return (
    <label>
      <span className="field-label">{label}</span>
      <select value={value} onChange={(e) => onChange(e.target.value as T)} className="field">
        {options.map((opt) => (
          <option key={opt.value} value={opt.value}>
            {opt.label}
          </option>
        ))}
      </select>
    </label>
  );
}
