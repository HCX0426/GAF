/**
 * TD-335 P0 #4: react-query migration — agent list query.
 *
 * Mirrors useDevicesQuery pattern. Coexists with useDeviceStore.fetchAgents —
 * after mutations, invalidate:
 *   queryClient.invalidateQueries({ queryKey: ['agents'] })
 */
import { useQuery, keepPreviousData } from '@tanstack/react-query';
import { fetchAgents } from '@/api/agents';
import type { Agent, PaginatedResponse } from '@/types/models';

/** Query key factory — stable keys for cache invalidation. */
export const agentsQueryKeys = {
  all: ['agents'] as const,
  list: (params?: Record<string, unknown>) => ['agents', 'list', params] as const,
};

/**
 * Fetch the agent list with react-query caching.
 *
 * @param params - optional filter/pagination params (page, page_size, status, ...)
 * @param enabled - set false to skip the fetch
 */
export function useAgentsQuery(params?: Record<string, unknown>, enabled = true) {
  return useQuery<PaginatedResponse<Agent>>({
    queryKey: agentsQueryKeys.list(params),
    queryFn: () => fetchAgents(params),
    enabled,
    placeholderData: keepPreviousData,
  });
}

export type UseAgentsQueryResult = ReturnType<typeof useAgentsQuery>;
