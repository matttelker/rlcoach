import { useState } from 'react';
import { useParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { getPlayer } from '../api/client';
import { BackLink, Card, ErrorState, LoadingCards } from '../components';
import type { Player, TagRequest } from '../types/api';
import { parseUtc } from './dataTransforms';
import { useTagPlayer } from './useTagPlayer';

/** One player: how often you've played together, whether they're your teammate, and your notes. */
export function PlayerDetail() {
  const { playerId = '' } = useParams();
  const player = useQuery({
    queryKey: ['player', playerId],
    queryFn: () => getPlayer(playerId),
    enabled: playerId !== '',
  });
  const tag = useTagPlayer();
  // The notes being written, or null when they're not open for editing
  const [draft, setDraft] = useState<string | null>(null);

  if (player.error) return <ErrorState message="This player didn't load. Check that the server is running." />;
  if (player.isLoading) return <LoadingCards />;
  if (!player.data) return <ErrorState message="There's no player with this id." />;

  const data = player.data;
  // Whatever was saved, tag or notes, the notes close
  const save = (request: TagRequest) => tag.mutate({ playerId, ...request }, { onSuccess: () => setDraft(null) });

  return (
    <div className="space-y-8">
      <header>
        <BackLink to="/players">Players</BackLink>
        <div className="flex flex-wrap items-end gap-4 mt-4">
          <div className="mr-auto">
            <h1 className="type-display text-[30px] sm:text-[36px] break-all">{data.display_name}</h1>
            <p className="mt-2 text-[var(--color-text-muted)]">{data.platform || 'Unknown platform'}</p>
          </div>
          <button
            type="button"
            className={data.is_tagged_teammate ? 'btn btn-primary' : 'btn'}
            aria-pressed={data.is_tagged_teammate}
            disabled={tag.isPending}
            onClick={() => save({ tagged: !data.is_tagged_teammate })}
          >
            {data.is_tagged_teammate ? 'Tagged as teammate' : 'Tag as teammate'}
          </button>
        </div>
      </header>

      <div className="grid lg:grid-cols-[minmax(0,2fr)_minmax(0,3fr)] gap-6 items-start">
        <Together player={data} />
        <Card className="p-5">
          <div className="flex items-baseline justify-between gap-4 mb-3">
            <h2 className="type-display text-[19px]">Notes</h2>
            {draft === null && (
              <button type="button" className="btn" onClick={() => setDraft(data.teammate_notes || '')}>
                Edit notes
              </button>
            )}
          </div>
          {draft === null ? (
            <p className={data.teammate_notes ? 'whitespace-pre-wrap' : 'text-[var(--color-text-muted)]'}>
              {data.teammate_notes || 'No notes yet.'}
            </p>
          ) : (
            <NotesEditor
              name={data.display_name}
              draft={draft}
              saving={tag.isPending}
              onChange={setDraft}
              onSave={() => save({ tagged: data.is_tagged_teammate, notes: draft })}
              onCancel={() => setDraft(null)}
            />
          )}
        </Card>
      </div>
    </div>
  );
}

function Together({ player }: { player: Player }) {
  const day = (utc: string | null) => (utc ? parseUtc(utc).toLocaleDateString() : 'Unknown');
  return (
    <Card className="p-5">
      <dl className="grid grid-cols-[auto_1fr] gap-x-6 gap-y-3">
        <dt className="text-[var(--color-text-muted)]">Games together</dt>
        <dd className="type-score text-[24px] text-right">{player.games_with_me}</dd>
        <dt className="text-[var(--color-text-muted)]">First seen</dt>
        <dd className="text-right">{day(player.first_seen_utc)}</dd>
        <dt className="text-[var(--color-text-muted)]">Last seen</dt>
        <dd className="text-right">{day(player.last_seen_utc)}</dd>
      </dl>
    </Card>
  );
}

function NotesEditor({
  name,
  draft,
  saving,
  onChange,
  onSave,
  onCancel,
}: {
  name: string;
  draft: string;
  saving: boolean;
  onChange: (draft: string) => void;
  onSave: () => void;
  onCancel: () => void;
}) {
  return (
    <div className="space-y-3">
      <label className="sr-only" htmlFor="player-notes">
        Notes about {name}
      </label>
      <textarea
        id="player-notes"
        className="field w-full h-28 resize-y"
        placeholder="How they play, what works with them…"
        value={draft}
        onChange={(e) => onChange(e.target.value)}
      />
      <div className="flex gap-2">
        <button type="button" className="btn btn-primary" disabled={saving} onClick={onSave}>
          Save notes
        </button>
        <button type="button" className="btn" onClick={onCancel}>
          Cancel
        </button>
      </div>
    </div>
  );
}
