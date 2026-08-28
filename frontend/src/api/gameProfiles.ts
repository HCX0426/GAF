/**
 * Game Profile API
 *
 * R37-P1: extracted from GameProfilesPage.tsx inline functions so that
 * TaskFormModal and other components can fetch game profile options
 * without duplicating the API calls. GameProfilesPage.tsx still imports
 * client directly for its own use — this module is the canonical API
 * surface for game profiles.
 *
 * Spec v3 §2.5.2: extended with 5 sub-resource endpoints for the
 * GameProfile detail page tabs (tasks / task_chains / devices / accounts /
 * resource_packs) + default-routine / dispatch-routine actions.
 */
import client from './client';
import type {
  GameProfile,
  PaginatedResponse,
  PaginationParams,
  Task,
  TaskChain,
  Device,
  GameAccount,
  ResourcePack,
} from '@/types/models';

const API_BASE = '/gamestate/game-profiles/';

// ---------------------------------------------------------------------------
// CRUD
// ---------------------------------------------------------------------------

/** Fetch game profiles list */
export async function fetchGameProfiles(
  params?: Partial<PaginationParams> & { search?: string },
): Promise<PaginatedResponse<GameProfile>> {
  const res = await client.get<PaginatedResponse<GameProfile>>(API_BASE, { params });
  return res.data;
}

/** Fetch single game profile detail */
export async function fetchGameProfile(id: number): Promise<GameProfile> {
  const res = await client.get<GameProfile>(`${API_BASE}${id}/`);
  return res.data;
}

/** Create a new game profile */
export async function createGameProfile(data: Record<string, unknown>): Promise<GameProfile> {
  const res = await client.post<GameProfile>(API_BASE, data);
  return res.data;
}

/** Update an existing game profile */
export async function updateGameProfile(id: number | string, data: Record<string, unknown>): Promise<GameProfile> {
  const res = await client.put<GameProfile>(`${API_BASE}${id}/`, data);
  return res.data;
}

/** Delete a game profile */
export async function deleteGameProfile(id: number): Promise<void> {
  await client.delete(`${API_BASE}${id}/`);
}

// ---------------------------------------------------------------------------
// Sub-resource endpoints (Spec v3 §2.5.2 — GameProfile detail page tabs)
// ---------------------------------------------------------------------------

/** Fetch tasks belonging to this GameProfile */
export async function fetchGameProfileTasks(
  id: number,
  params?: Partial<PaginationParams>,
): Promise<PaginatedResponse<Task>> {
  const res = await client.get<PaginatedResponse<Task>>(`${API_BASE}${id}/tasks/`, { params });
  return res.data;
}

/** Fetch task chains belonging to this GameProfile */
export async function fetchGameProfileTaskChains(
  id: number,
  params?: Partial<PaginationParams>,
): Promise<PaginatedResponse<TaskChain>> {
  const res = await client.get<PaginatedResponse<TaskChain>>(`${API_BASE}${id}/task_chains/`, { params });
  return res.data;
}

/** Fetch devices bound to this GameProfile */
export async function fetchGameProfileDevices(
  id: number,
  params?: Partial<PaginationParams>,
): Promise<PaginatedResponse<Device>> {
  const res = await client.get<PaginatedResponse<Device>>(`${API_BASE}${id}/devices/`, { params });
  return res.data;
}

/** Fetch accounts belonging to this GameProfile */
export async function fetchGameProfileAccounts(
  id: number,
  params?: Partial<PaginationParams>,
): Promise<PaginatedResponse<GameAccount>> {
  const res = await client.get<PaginatedResponse<GameAccount>>(`${API_BASE}${id}/accounts/`, { params });
  return res.data;
}

/** Fetch resource packs bound to this GameProfile's accounts */
export async function fetchGameProfileResourcePacks(
  id: number,
  params?: Partial<PaginationParams>,
): Promise<PaginatedResponse<ResourcePack>> {
  const res = await client.get<PaginatedResponse<ResourcePack>>(`${API_BASE}${id}/resource_packs/`, { params });
  return res.data;
}

// ---------------------------------------------------------------------------
// v3 §2.7.2 default-routine / dispatch-routine actions
// ---------------------------------------------------------------------------

/** Set the default TaskChain for this GameProfile (spec v3 §2.7.2) */
export async function setDefaultRoutine(profileId: number, taskChainId: number): Promise<GameProfile> {
  const res = await client.patch<GameProfile>(`${API_BASE}${profileId}/default-routine/`, {
    task_chain_id: taskChainId,
  });
  return res.data;
}

/** Dispatch the default routine to all online devices bound to this profile (spec v3 §2.7.2) */
export async function dispatchRoutine(profileId: number): Promise<{
  status: string;
  started_at: string;
  dispatched_count: number;
  skipped_count: number;
  failed_count: number;
  dispatched_chain_execution_ids: number[];
  skipped: Array<{ device_id: number; reason: string }>;
  failed: Array<{ device_id: number; reason: string }>;
  message: string;
}> {
  const res = await client.post(`${API_BASE}${profileId}/dispatch-routine/`);
  return res.data;
}

// ---------------------------------------------------------------------------
// bind/unbind sub-resources (spec v3 §2.5.2 — attach existing child
// resources to this GameProfile from the detail page tabs)
// ---------------------------------------------------------------------------

export async function bindTask(profileId: number, taskId: number): Promise<Task> {
  const res = await client.post<Task>(`${API_BASE}${profileId}/bind-task/`, { task_id: taskId });
  return res.data;
}

export async function unbindTask(profileId: number, taskId: number): Promise<void> {
  await client.post(`${API_BASE}${profileId}/unbind-task/`, { task_id: taskId });
}

export async function bindTaskChain(profileId: number, taskChainId: number): Promise<TaskChain> {
  const res = await client.post<TaskChain>(`${API_BASE}${profileId}/bind-task-chain/`, { task_chain_id: taskChainId });
  return res.data;
}

export async function unbindTaskChain(profileId: number, taskChainId: number): Promise<void> {
  await client.post(`${API_BASE}${profileId}/unbind-task-chain/`, { task_chain_id: taskChainId });
}

export async function bindAccount(profileId: number, accountId: number): Promise<GameAccount> {
  const res = await client.post<GameAccount>(`${API_BASE}${profileId}/bind-account/`, { account_id: accountId });
  return res.data;
}

export async function unbindAccount(profileId: number, accountId: number): Promise<void> {
  await client.post(`${API_BASE}${profileId}/unbind-account/`, { account_id: accountId });
}

// ---------------------------------------------------------------------------
// v3 §2.6 per-device dispatch — execute a TaskChain on one device+account
// ---------------------------------------------------------------------------

/** Execute a TaskChain on a specific device + account (spec v3 §2.6 / §2.7.2).
 *
 * POST /api/v2/pipeline/task-chains/{id}/execute/
 * Body: { device_id, game_account_id, agent_id? }
 */
export async function executeTaskChain(
  taskChainId: number,
  payload: {
    device_id: number;
    game_account_id?: number | null;
    agent_id?: string;
  },
): Promise<{
  chain_id: number;
  chain_name: string;
  chain_execution_id: number;
  agent_id: string;
  device_id: number;
  game_account_id: number | null;
  first_node_order: number | null;
  first_task_name: string | null;
  status: string;
  message: string;
}> {
  const res = await client.post(`/pipeline/task-chains/${taskChainId}/execute/`, payload);
  return res.data;
}
