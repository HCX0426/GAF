/**
 * TD-335 P0 #4: react-query migration — monitor rule list query.
 *
 * Mirrors useDevicesQuery pattern. Coexists with useMonitorStore — after
 * mutations, invalidate:
 *   queryClient.invalidateQueries({ queryKey: ['monitor-rules'] })
 */
import { useQuery, keepPreviousData } from '@tanstack/react-query';
import { fetchMonitorRules } from '@/api/monitors';
import type { MonitorRule, PaginatedResponse } from '@/types/models';

/** Query key factory — stable keys for cache invalidation. */
export const monitorRulesQueryKeys = {
  all: ['monitor-rules'] as const,
  list: (params?: Record<string, unknown>) => ['monitor-rules', 'list', params] as const,
};

/**
 * Fetch the monitor rule list with react-query caching.
 *
 * @param params - optional filter/pagination params (page, page_size, search, ...)
 * @param enabled - set false to skip the fetch
 */
export function useMonitorRulesQuery(params?: Record<string, unknown>, enabled = true) {
  return useQuery<PaginatedResponse<MonitorRule>>({
    queryKey: monitorRulesQueryKeys.list(params),
    queryFn: () => fetchMonitorRules(params),
    enabled,
    placeholderData: keepPreviousData,
  });
}

export type UseMonitorRulesQueryResult = ReturnType<typeof useMonitorRulesQuery>;
