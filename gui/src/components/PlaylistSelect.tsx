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
        {options.map((option) => (
          <option key={option.value} value={option.value}>{option.label}</option>
        ))}
      </select>
    </label>
  );
}

// The playlists the stats views offer
const PLAYLISTS = [
  { value: 'STANDARD', label: 'Standard' },
  { value: 'DOUBLES', label: 'Doubles' },
  { value: 'DUEL', label: 'Duel' },
];

/** The playlist for a stats view. Until you pick one, the API's choice, once it's known. */
export function PlaylistSelect({ value, onChange }: { value: string | undefined; onChange: (playlist: string) => void }) {
  return <SelectField label="Playlist" value={value ?? ''} options={PLAYLISTS} onChange={onChange} />;
}
