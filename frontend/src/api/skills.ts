/**
 * Skill-related API
 * Covers skill list query, auto-match, sync built-in, toggle enable,
 * plus Skill market (publish/import/review/my_published).
 */
import client from './client';
import type { SkillDefinition, PaginatedResponse } from '@/types/models';

/** Fetch skill list */
export async function fetchSkills(params?: Record<string, unknown>): Promise<PaginatedResponse<SkillDefinition>> {
  const res = await client.get<PaginatedResponse<SkillDefinition>>('/skills/skills/', { params });
  return res.data;
}

/** Skill auto-match */
export async function autoMatchSkills(
  query: string,
): Promise<{ matches: Array<{ skill: SkillDefinition; score: number }> }> {
  const res = await client.post('/skills/skills/auto-match/', { query });
  return res.data;
}

/** Sync built-in skills */
export async function syncBuiltinSkills(): Promise<{ count: number }> {
  // A013 fix: snake_case URL sync_builtin -> kebab-case sync-builtin
  const res = await client.post('/skills/skills/sync-builtin/');
  return res.data;
}

/** Toggle skill enabled/disabled (via toggle action) */
export async function toggleSkillEnabled(skillId: number): Promise<SkillDefinition> {
  const res = await client.post<SkillDefinition>(`/skills/skills/${skillId}/toggle/`);
  return res.data;
}

// ===== Skill Market =====

/** Skill market item (matches backend SkillMarketItemSerializer) */
export interface SkillMarketItem {
  id: number;
  skill: number;
  skill_name: string;
  skill_description: string;
  skill_yaml_content: string;
  skill_version: string;
  skill_applicable_scenarios: string[];
  publisher: number;
  publisher_name: string;
  title: string;
  description: string;
  tags: string[];
  status: 'pending' | 'approved' | 'rejected' | 'removed';
  download_count: number;
  rating_avg: number;
  rating_count: number;
  version: string;
  published_at: string | null;
  created_at: string;
  updated_at: string;
}

/** Skill market review (matches backend SkillMarketReviewSerializer) */
export interface SkillMarketReview {
  id: number;
  item: number;
  user: number;
  user_name: string;
  rating: number;
  comment: string;
  created_at: string;
}

/** Fetch approved market items (public list) */
export async function fetchMarketItems(params?: Record<string, unknown>): Promise<PaginatedResponse<SkillMarketItem>> {
  const res = await client.get<PaginatedResponse<SkillMarketItem>>('/skills/market/', { params });
  return res.data;
}

/** Fetch single market item (any status, for preview) */
export async function fetchMarketItem(id: number): Promise<SkillMarketItem> {
  const res = await client.get<SkillMarketItem>(`/skills/market/${id}/`);
  return res.data;
}

/** Publish a skill to market */
export async function publishSkill(payload: {
  skill: number;
  title: string;
  description?: string;
  tags?: string[];
  version?: string;
}): Promise<SkillMarketItem> {
  const res = await client.post<SkillMarketItem>('/skills/market/publish/', payload);
  return res.data;
}

/** Import a market skill into current user (copies SkillDefinition) */
export async function importMarketItem(id: number): Promise<{ detail: string; skill_id: number; skill_name: string }> {
  const res = await client.post(`/skills/market/${id}/import/`);
  return res.data;
}

/** Review (rate/comment) a market item */
export async function reviewMarketItem(
  id: number,
  payload: { rating: number; comment?: string },
): Promise<SkillMarketReview> {
  const res = await client.post<SkillMarketReview>(`/skills/market/${id}/review/`, payload);
  return res.data;
}

/** Fetch current user's published items (all statuses) */
export async function fetchMyPublished(params?: Record<string, unknown>): Promise<PaginatedResponse<SkillMarketItem>> {
  // A014 fix: snake_case URL my_published -> kebab-case my-published
  const res = await client.get<PaginatedResponse<SkillMarketItem>>('/skills/market/my-published/', { params });
  return res.data;
}

// ─────────────────────────────────────────────
// Task Marketplace (from marketplace.ts, merged 2026-08-04)
// Functions prefixed with "taskMarket" to distinguish from skill market.
// ─────────────────────────────────────────────

/** Task marketplace item shape */
export interface TaskMarketplaceItem {
  id: number;
  publisher_name: string;
  pipeline_name: string;
  game_name: string;
  title: string;
  description: string;
  tags: string[];
  download_count: number;
  rating_avg: number;
  rating_count: number;
  version: string;
  created_at: string;
}

/** Fetch task marketplace items list */
export async function fetchTaskMarketItems(params?: Record<string, string>): Promise<TaskMarketplaceItem[]> {
  const res = await client.get('/tasks/marketplace/', { params });
  return res.data;
}

/** Fetch task marketplace item detail */
export async function fetchTaskMarketItemDetail(id: number): Promise<TaskMarketplaceItem> {
  const res = await client.get(`/tasks/marketplace/${id}/`);
  return res.data;
}

/** Publish a pipeline to task marketplace */
export async function publishTaskToMarket(data: Record<string, unknown>): Promise<TaskMarketplaceItem> {
  const res = await client.post('/tasks/marketplace/publish/', data);
  return res.data;
}

/** Import a task marketplace item */
export async function importTaskMarketItem(id: number): Promise<void> {
  await client.post(`/tasks/marketplace/${id}/import-item/`);
}

/** Review a task marketplace item */
export async function reviewTaskMarketItem(id: number, rating: number, comment?: string): Promise<void> {
  await client.post(`/tasks/marketplace/${id}/review/`, { rating, comment });
}
