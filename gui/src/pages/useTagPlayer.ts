import { useMutation, useQueryClient } from '@tanstack/react-query';
import { tagPlayer } from '../api/client';
import type { TagRequest } from '../types/api';

/** Tag or untag a player, or save notes on them, then reload that player and the Players list. */
export function useTagPlayer() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ playerId, ...request }: TagRequest & { playerId: string }) => tagPlayer(playerId, request),
    onSuccess: (_saved, { playerId }) => {
      queryClient.invalidateQueries({ queryKey: ['player', playerId] });
      queryClient.invalidateQueries({ queryKey: ['players'] });
    },
  });
}
