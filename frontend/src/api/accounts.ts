/**
 * game account system API
 * includes account CRUD, batch operations, group management, rotation rules and all interfaces
 */
import client from './client';
import type { GameAccount, AccountGroup, RotationRule, LoginHistory, PaginatedResponse } from '@/types/models';

/**
 * get paginated game account list
 * @param params - query params (page, page_size, search, status, group etc. )
 */
export async function fetchGameAccounts(params?: Record<string, unknown>): Promise<PaginatedResponse<GameAccount>> {
  const res = await client.get<PaginatedResponse<GameAccount>>('/accounts/game-accounts/', { params });
  return res.data;
}

/**
 * get available game list ( from GameProfile table )
 */
export async function fetchGameOptions(): Promise<{ games: string[] }> {
  const res = await client.get<{ games: string[] }>('/accounts/game-accounts/game-options/');
  return res.data;
}

/**
 * get single game account details
 * @param id - account ID
 */
export async function fetchGameAccount(id: number): Promise<GameAccount> {
  const res = await client.get<GameAccount>(`/accounts/game-accounts/${id}/`);
  return res.data;
}

/**
 * create game account
 * @param data - account data
 */
export async function createAccount(data: Record<string, unknown>): Promise<GameAccount> {
  const res = await client.post<GameAccount>('/accounts/game-accounts/', data);
  return res.data;
}

/**
 * update game account
 * @param id - account ID
 * @param data - update data
 */
export async function updateAccount(id: number, data: Record<string, unknown>): Promise<GameAccount> {
  const res = await client.put<GameAccount>(`/accounts/game-accounts/${id}/`, data);
  return res.data;
}

/**
 * delete game account
 * @param id - account ID
 */
export async function deleteAccount(id: number): Promise<void> {
  await client.delete(`/accounts/game-accounts/${id}/`);
}

/**
 * test account login
 * @param id - account ID
 * @param data - includes device_id
 */
export async function testLoginAccount(
  id: number,
  data: { device_id: number },
): Promise<{ success: boolean; message: string; screenshot_url: string | null }> {
  const res = await client.post(`/accounts/game-accounts/${id}/test-login/`, data);
  return res.data;
}

/**
 * batch check account status
 * @param data - includes account_ids or check_all
 */
export async function batchCheckAccounts(data: {
  account_ids?: number[];
  check_all?: boolean;
}): Promise<{ results: Array<{ id: number; status: string; message: string }>; summary: Record<string, number> }> {
  const res = await client.post('/accounts/game-accounts/batch-check/', data);
  return res.data;
}

/**
 * batch import accounts
 * @param data - includes accounts array
 */
export async function batchImportAccounts(data: {
  accounts: Record<string, unknown>[];
}): Promise<{ total: number; created: number; skipped: number; errors: unknown[] }> {
  const res = await client.post('/accounts/game-accounts/batch-import/', data);
  return res.data;
}

/**
 * get account group list
 */
export async function fetchAccountGroups(): Promise<PaginatedResponse<AccountGroup>> {
  const res = await client.get<PaginatedResponse<AccountGroup>>('/accounts/groups/');
  return res.data;
}

/**
 * create account group
 * @param data - includes name
 */
export async function createAccountGroup(data: { name: string }): Promise<AccountGroup> {
  const res = await client.post<AccountGroup>('/accounts/groups/', data);
  return res.data;
}

/**
 * update account group
 * @param id - group ID
 * @param data - includes name, slug
 */
export async function updateAccountGroup(id: number, data: { name?: string; slug?: string }): Promise<AccountGroup> {
  const res = await client.put<AccountGroup>(`/accounts/groups/${id}/`, data);
  return res.data;
}

/**
 * delete account group
 * @param id - group ID
 */
export async function deleteAccountGroup(id: number): Promise<void> {
  await client.delete(`/accounts/groups/${id}/`);
}

/**
 * get rotation rules list
 */
export async function fetchRotationRules(): Promise<PaginatedResponse<RotationRule>> {
  const res = await client.get<PaginatedResponse<RotationRule>>('/accounts/rotation-rules/');
  return res.data;
}

/**
 * create rotation rule
 * @param data - rule data
 */
export async function createRotationRule(data: Record<string, unknown>): Promise<RotationRule> {
  const res = await client.post<RotationRule>('/accounts/rotation-rules/', data);
  return res.data;
}

/**
 * update rotation rule
 * @param id - rule ID
 * @param data - update data
 */
export async function updateRotationRule(id: number, data: Record<string, unknown>): Promise<RotationRule> {
  const res = await client.put<RotationRule>(`/accounts/rotation-rules/${id}/`, data);
  return res.data;
}

/**
 * delete rotation rule
 * @param id - rule ID
 */
export async function deleteRotationRule(id: number): Promise<void> {
  await client.delete(`/accounts/rotation-rules/${id}/`);
}

// API Key management

/**
 * Fetch API keys list
 */
export async function fetchApiKeys(params?: Record<string, unknown>) {
  const res = await client.get('/accounts/api-keys/', { params });
  return res.data;
}

/**
 * Create a new API key
 */
export async function createApiKey(data: Record<string, unknown>) {
  const res = await client.post('/accounts/api-keys/', data);
  return res.data;
}

/**
 * Update an API key
 */
export async function updateApiKey(id: number, data: Record<string, unknown>) {
  const res = await client.put(`/accounts/api-keys/${id}/`, data);
  return res.data;
}

/**
 * Delete an API key
 */
export async function deleteApiKey(id: number): Promise<void> {
  await client.delete(`/accounts/api-keys/${id}/`);
}

/**
 * Fetch login history (M4 audit trail)
 * @param params - Optional filters: user (admin only), page, page_size
 */
export async function fetchLoginHistory(params?: Record<string, unknown>): Promise<PaginatedResponse<LoginHistory>> {
  const res = await client.get<PaginatedResponse<LoginHistory>>('/accounts/login-history/', { params });
  return res.data;
}

/**
 * Fetch all users' login history (admin only)
 */
export async function fetchAllLoginHistory(params?: Record<string, unknown>): Promise<PaginatedResponse<LoginHistory>> {
  const res = await client.get<PaginatedResponse<LoginHistory>>('/accounts/login-history/all/', { params });
  return res.data;
}

// Audit Log (R37-P3 Stage 7 Task 20a: backend AuditLog moved from tasks to
// accounts app — TD-039. Endpoint base changed from /tasks/audit-logs/ to
// /accounts/audit-logs/. db_table unchanged — zero data migration.)

/**
 * Fetch audit logs (read-only)
 * @param params - Optional filters: action, resource_type, page, page_size
 */
export async function fetchAuditLogs(params?: Record<string, unknown>) {
  const res = await client.get('/accounts/audit-logs/', { params });
  return res.data;
}
