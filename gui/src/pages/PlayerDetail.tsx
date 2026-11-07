import { useState } from 'react';
import { useParams, Link } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { getPlayer, tagPlayer } from '../api/client';
import { Card, SkeletonCard, ErrorState } from '../components';
import { parseUtc } from './dataTransforms';

export function PlayerDetail() {
  const { playerId } = useParams<{ playerId: string }>();
  const queryClient = useQueryClient();
  const [notes, setNotes] = useState('');
  const [isEditing, setIsEditing] = useState(false);

  const { data, isLoading, error } = useQuery({
    queryKey: ['player', playerId],
    queryFn: () => getPlayer(playerId!),
    enabled: !!playerId,
  });

  const tagMutation = useMutation({
    mutationFn: ({ tagged, notes }: { tagged: boolean; notes?: string }) => tagPlayer(playerId!, { tagged, notes }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['player', playerId] });
      queryClient.invalidateQueries({ queryKey: ['players'] });
      setIsEditing(false);
    },
  });

  if (error) {
    return <ErrorState message="This player didn't load. Check that the server is running." />;
  }

  if (isLoading) {
    return (
      <div className="space-y-6">
        <SkeletonCard />
        <SkeletonCard />
      </div>
    );
  }

  if (!data) {
    return <ErrorState message="There's no player with this id." />;
  }

  const date = (value: string | null) => (value ? parseUtc(value).toLocaleDateString() : 'Unknown');

  return (
    <div className="space-y-8">
      <header>
        <Link
          to="/players"
          className="inline-flex items-center gap-1 text-[14px] text-[var(--color-text-muted)] hover:text-[var(--color-text)]"
        >
          <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" aria-hidden="true">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
          </svg>
          Players
        </Link>
        <div className="flex flex-wrap items-end gap-4 mt-4">
          <div className="mr-auto">
            <h1 className="type-display text-[30px] sm:text-[36px] break-all">{data.display_name}</h1>
            <p className="mt-2 text-[var(--color-text-muted)]">{data.platform || 'Unknown platform'}</p>
          </div>
          <button
            type="button"
            onClick={() => tagMutation.mutate({ tagged: !data.is_tagged_teammate })}
            disabled={tagMutation.isPending}
            aria-pressed={data.is_tagged_teammate}
            className={data.is_tagged_teammate ? 'btn btn-primary' : 'btn'}
          >
            {data.is_tagged_teammate ? 'Tagged as teammate' : 'Tag as teammate'}
          </button>
        </div>
      </header>

      <div className="grid lg:grid-cols-[minmax(0,2fr)_minmax(0,3fr)] gap-6 items-start">
        <Card className="p-5">
          <dl className="grid grid-cols-[auto_1fr] gap-x-6 gap-y-3">
            <dt className="text-[var(--color-text-muted)]">Games together</dt>
            <dd className="type-score text-[24px] text-right">{data.games_with_me}</dd>
            <dt className="text-[var(--color-text-muted)]">First seen</dt>
            <dd className="text-right">{date(data.first_seen_utc)}</dd>
            <dt className="text-[var(--color-text-muted)]">Last seen</dt>
            <dd className="text-right">{date(data.last_seen_utc)}</dd>
          </dl>
        </Card>

        <Card className="p-5">
          <div className="flex items-baseline justify-between gap-4 mb-3">
            <h2 className="type-display text-[19px]">Notes</h2>
            {!isEditing && (
              <button
                type="button"
                onClick={() => {
                  setNotes(data.teammate_notes || '');
                  setIsEditing(true);
                }}
                className="btn"
              >
                Edit notes
              </button>
            )}
          </div>
          {isEditing ? (
            <div className="space-y-3">
              <label className="sr-only" htmlFor="player-notes">
                Notes about {data.display_name}
              </label>
              <textarea
                id="player-notes"
                value={notes}
                onChange={(e) => setNotes(e.target.value)}
                placeholder="How they play, what works with them…"
                className="field w-full h-28 resize-y"
              />
              <div className="flex gap-2">
                <button
                  type="button"
                  onClick={() => tagMutation.mutate({ tagged: data.is_tagged_teammate, notes })}
                  disabled={tagMutation.isPending}
                  className="btn btn-primary"
                >
                  Save notes
                </button>
                <button type="button" onClick={() => setIsEditing(false)} className="btn">
                  Cancel
                </button>
              </div>
            </div>
          ) : (
            <p className={data.teammate_notes ? 'whitespace-pre-wrap' : 'text-[var(--color-text-muted)]'}>
              {data.teammate_notes || 'No notes yet.'}
            </p>
          )}
        </Card>
      </div>
    </div>
  );
}
