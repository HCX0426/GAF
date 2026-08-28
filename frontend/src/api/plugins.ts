/**
 * Plugin management API
 * Covers plugin CRUD, enable/disable, install/uninstall, hot reload,
 * sandbox execute, and upload of .gafplugin packs.
 */
import client from './client';

/** Plugin item — matches backend PluginSerializer */
export interface PluginItem {
  id: number;
  name: string;
  version: string;
  author: string;
  description: string;
  manifest: Record<string, unknown>;
  is_installed: boolean;
  is_active: boolean;
  installed_at: string | null;
  checksum: string;
  created_at: string | null;
  updated_at: string | null;
  sandbox_status: string | null;
  sandbox_pid: number | null;
}

/**
 * Fetch the plugin list.
 * Backend may return either an array or an object wrapping an array;
 * normalize to a plain array here so callers do not need to branch.
 */
export async function fetchPlugins(signal?: AbortSignal): Promise<PluginItem[]> {
  const res = await client.get<PluginItem[] | { results?: PluginItem[] }>('/plugins/', { signal });
  const data = res.data;
  if (Array.isArray(data)) return data;
  return data?.results ?? [];
}

/** Install a plugin by id */
export async function installPlugin(id: number): Promise<PluginItem> {
  const res = await client.post<PluginItem>(`/plugins/${id}/install/`);
  return res.data;
}

/** Toggle a plugin's active state (enable/disable) */
export async function togglePlugin(id: number): Promise<PluginItem> {
  const res = await client.post<PluginItem>(`/plugins/${id}/toggle/`);
  return res.data;
}

/** Uninstall a plugin by id */
export async function uninstallPlugin(id: number): Promise<void> {
  await client.post(`/plugins/${id}/uninstall/`);
}

/** Hot reload a plugin by id */
export async function reloadPlugin(id: number): Promise<PluginItem> {
  const res = await client.post<PluginItem>(`/plugins/${id}/reload/`);
  return res.data;
}

/** Run a plugin in the sandbox and return the execution result */
export async function sandboxExecPlugin(id: number): Promise<{ message?: string }> {
  const res = await client.post<{ message?: string }>(`/plugins/${id}/sandbox-exec/`);
  return res.data;
}

/** Upload a .gafplugin pack and return the resulting plugin item */
export async function uploadPlugin(file: File): Promise<PluginItem> {
  const formData = new FormData();
  formData.append('file', file);
  const res = await client.post<PluginItem>('/plugins/upload/', formData);
  return res.data;
}
