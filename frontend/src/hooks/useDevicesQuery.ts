/**
 * TD-335 P0 #4: react-query migration PoC — device list query.
 *
 * This is the first of 5 high-frequency queries to migrate from manual
 * useState+useEffect+fetch to react-query (TD-335 Phase 1). It demonstrates
 * the recommended pattern for future migrations (tasks/accounts/monitors).
 *
 * Benefits over the previous useDeviceStore.fetchDevices + useEffect pattern:
 *  - Automatic dedup: multiple components mounting simultaneously share one
 *    network request (the #1 cause of duplicate /devices/ calls on Dashboard).
 *  - Built-in cache: navigating away and back within staleTime (30s) returns
 *    cached data instantly while refetching in the background.
 *  - Cancellation: queries are automatically cancelled on unmount; no more
 *    "state update on unmounted component" warnings from race conditions.
 *  - isLoading/isError/isSuccess flags replace manual loading booleans.
 *
 * Coexistence with useDeviceStore:
 *  The store remains the source of truth for mutations (createDevice,
 *  updateDevice, deleteDevice) and for components that already use it.
 *  After a mutation, call `queryClient.invalidateQueries({ queryKey: ['devices'] })`
 *  to refetch. The store's fetchDevices is NOT removed — this hook is an
 *  alternative for new components or components that need caching.
 *
 * Migration target (next 4 hooks, tracked in TD-335):
 *  - useTasksQuery (task list)
 *  - useAccountsQuery (game account list)
 *  - useMonitorsQuery (monitor rule list)
 *  - useAgentsQuery (agent list)
 */
import { useQuery, keepPreviousData } from '@tanstack/react-query';
import { fetchDevices } from '@/api/devices';
import type { DeviceQueryParams, Device, PaginatedResponse } from '@/types/models';

/** Query key factory — stable keys for cache invalidation. */
export const devicesQueryKeys = {
  all: ['devices'] as const,
  list: (params?: DeviceQueryParams) => ['devices', 'list', params] as const,
};

/**
 * Fetch the device list with react-query caching.
 *
 * @param params - optional filter/pagination params (status, group_id, search, page, ...)
 *                 — included in the query key so different filters cache separately.
 * @param enabled - set false to skip the fetch (e.g. until a required filter is set).
 *
 * @example
 * const { data, isLoading, error } = useDevicesQuery({ status: 'online' });
 * // data: { results: Device[], count: number }
 *
 * @example invalidation after mutation
 * import { useQueryClient } from '@tanstack/react-query';
 * const queryClient = useQueryClient();
 * await createDevice(payload);
 * queryClient.invalidateQueries({ queryKey: ['devices'] });
 */
export function useDevicesQuery(params?: DeviceQueryParams, enabled = true) {
  return useQuery<PaginatedResponse<Device>>({
    queryKey: devicesQueryKeys.list(params),
    queryFn: () => fetchDevices(params),
    enabled,
    // Keep previous data while loading the next page/filter to avoid UI flicker.
    placeholderData: keepPreviousData,
  });
}

export type UseDevicesQueryResult = ReturnType<typeof useDevicesQuery>;
export type { Device, DeviceQueryParams };
