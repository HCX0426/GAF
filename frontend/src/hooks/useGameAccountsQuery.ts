/**
 * TD-335 P0 #4: react-query migration — game account list query.
 *
 * Mirrors useDevicesQuery pattern. Coexists with useAccountStore — after
 * mutations, invalidate:
 *   queryClient.invalidateQueries({ queryKey: ['game-accounts'] })
 */
import { useQuery, keepPreviousData } from '@tanstack/react-query';
import { fetchGameAccounts } from '@/api/accounts';
import type { GameAccount, PaginatedResponse } from '@/types/models';

/** Query key factory — stable keys for cache invalidation. */
export const gameAccountsQueryKeys = {
  all: ['game-accounts'] as const,
  list: (params?: Record<string, unknown>) => ['game-accounts', 'list', params] as const,
};

/**
 * Fetch the game account list with react-query caching.
 *
 * @param params - optional filter/pagination params (page, page_size, search, status, group, ...)
 * @param enabled - set false to skip the fetch
 */
export function useGameAccountsQuery(params?: Record<string, unknown>, enabled = true) {
  return useQuery<PaginatedResponse<GameAccount>>({
    queryKey: gameAccountsQueryKeys.list(params),
    queryFn: () => fetchGameAccounts(params),
    enabled,
    placeholderData: keepPreviousData,
  });
}

export type UseGameAccountsQueryResult = ReturnType<typeof useGameAccountsQuery>;
