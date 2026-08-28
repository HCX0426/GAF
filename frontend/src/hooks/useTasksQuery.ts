/**
 * TD-335 P0 #4: react-query migration — task list query.
 *
 * Mirrors useDevicesQuery pattern: useQuery + keepPreviousData + queryKey
 * factory. Coexists with useTaskStore — after mutations, invalidate:
 *   queryClient.invalidateQueries({ queryKey: ['tasks'] })
 */
import { useQuery, keepPreviousData } from '@tanstack/react-query';
import { fetchTasks } from '@/api/tasks';
import type { Task, PaginationParams, PaginatedResponse } from '@/types/models';

/** Query key factory — stable keys for cache invalidation. */
export const tasksQueryKeys = {
  all: ['tasks'] as const,
  list: (params?: Partial<PaginationParams>) => ['tasks', 'list', params] as const,
};

/**
 * Fetch the task list with react-query caching.
 *
 * @param params - optional pagination/filter params (page, page_size, search, ...)
 * @param enabled - set false to skip the fetch
 */
export function useTasksQuery(params?: Partial<PaginationParams>, enabled = true) {
  return useQuery<PaginatedResponse<Task>>({
    queryKey: tasksQueryKeys.list(params),
    queryFn: () => fetchTasks(params),
    enabled,
    placeholderData: keepPreviousData,
  });
}

export type UseTasksQueryResult = ReturnType<typeof useTasksQuery>;
