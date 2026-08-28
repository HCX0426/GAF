/**
 * Resource pack API
 * Covers resource pack list, activate, validate, template, config, export
 * Template version management (P-013) and tag system (P-014) API
 * R37-P1: TemplateAnnotation CRUD for TemplateAnnotationPage Tab 2 persistence
 */
import client from './client';
import type { ResourcePack, TemplateAnnotation, PaginatedResponse, PaginationParams } from '@/types/models';

/** Fetch resource pack list.
 *  Accepts Partial<PaginationParams> so callers may omit `page` (the backend
 *  defaults to page 1) — see TemplateGallery.loadPacks. */
export async function fetchResourcePacks(
  params?: Partial<PaginationParams> & { signal?: AbortSignal },
): Promise<PaginatedResponse<ResourcePack>> {
  const { signal, ...queryParams } = params || {};
  const res = await client.get<PaginatedResponse<ResourcePack>>('/resources/resource-packs/', {
    params: queryParams,
    signal,
  });
  return res.data;
}

/** Fetch single resource pack detail */
export async function fetchResourcePack(packId: number): Promise<ResourcePack> {
  const res = await client.get<ResourcePack>(`/resources/resource-packs/${packId}/`);
  return res.data;
}

/** Template match preview result box (image-pixel coordinates). */
export interface TemplateMatchBox {
  x: number;
  y: number;
  w: number;
  h: number;
  confidence: number;
}

/** R37-P2: real cv2 template match preview — replaces the annotation page's hard-coded mock.
 *  image/template accept either a bare base64 string or a `data:` URL. */
export async function matchTemplatePreview(
  imageBase64: string,
  templateBase64: string,
  threshold?: number,
): Promise<{ matches: TemplateMatchBox[]; error: string | null }> {
  const res = await client.post<{ matches: TemplateMatchBox[]; error: string | null }>(
    '/resources/template-match-preview/',
    { image_base64: imageBase64, template_base64: templateBase64, threshold: threshold ?? 0.8 },
  );
  return res.data;
}

/** Activate resource pack */
export async function activateResourcePack(packId: number): Promise<ResourcePack> {
  const res = await client.post<ResourcePack>(`/resources/resource-packs/${packId}/activate/`);
  return res.data;
}

/** Deactivate resource pack */
export async function deactivateResourcePack(packId: number): Promise<ResourcePack> {
  const res = await client.post<ResourcePack>(`/resources/resource-packs/${packId}/deactivate/`);
  return res.data;
}

/** Import resource pack */
export async function importResourcePack(file: File): Promise<ResourcePack> {
  const formData = new FormData();
  formData.append('file', file);
  const res = await client.post<ResourcePack>('/resources/resource-packs/', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  });
  return res.data;
}

/** Single scan result item */
export interface ScanResultItem {
  name?: string;
  error?: string;
  resource_pack_id?: number;
  tasks_imported?: { created: number; updated: number; errors: string[] };
  templates_imported?: { created: number; updated: number; errors: string[] };
}

/** Aggregate scan result for resources/ directory */
export interface ScanResult {
  total: number;
  success: number;
  failed: number;
  results: ScanResultItem[];
  ghost_packs?: Array<{ id: number; name: string; directory: string }>;
}

/** Scan resources/ directory, auto-import subfolders as resource packs with deep import (tasks + templates) */
export async function scanResourcePacks(): Promise<ScanResult> {
  const res = await client.post<ScanResult>('/resources/resource-packs/scan/');
  return res.data;
}

/** Validate resource pack */
export async function validateResourcePack(packId: number): Promise<ResourcePack> {
  const res = await client.post<ResourcePack>(`/resources/resource-packs/${packId}/validate/`);
  return res.data;
}

/** Validate resource pack path */
export async function validateResourcePackPath(data: { path: string }): Promise<ResourcePack> {
  const res = await client.post<ResourcePack>('/resources/resource-packs/validate-path/', data);
  return res.data;
}

/** Fetch resource pack templates */
export async function fetchResourcePackTemplates(packId: number): Promise<Record<string, unknown>[]> {
  const res = await client.get<Record<string, unknown>[]>(`/resources/resource-packs/${packId}/templates/`);
  return res.data;
}

/** Fetch resource pack config */
export async function fetchResourcePackConfig(packId: number): Promise<Record<string, unknown>> {
  const res = await client.get<Record<string, unknown>>(`/resources/resource-packs/${packId}/config/`);
  return res.data;
}

/** Export resource pack */
export async function exportResourcePack(packId: number): Promise<Blob> {
  const res = await client.get(`/resources/resource-packs/${packId}/export/`, {
    responseType: 'blob',
  });
  return res.data as Blob;
}

/** Delete resource pack */
export async function deleteResourcePack(packId: number): Promise<void> {
  await client.delete(`/resources/resource-packs/${packId}/`);
}

// ==================== P-013: Template Version Management ====================

/** Template version history entry */
export interface TemplateVersion {
  id: number;
  template_id: number;
  version_number: number;
  image_url: string;
  thumbnail_url: string;
  comment: string;
  created_by: string;
  created_at: string;
}

/** Create template version request params */
export interface CreateTemplateVersionRequest {
  template_id: number;
  image_url: string;
  thumbnail_url?: string;
  comment?: string;
}

/** Fetch template version history list */
export async function fetchTemplateVersions(
  templateId: number,
  params?: Record<string, unknown>,
): Promise<TemplateVersion[]> {
  const res = await client.get<TemplateVersion[]>('/resources/template-versions/', {
    params: { template_id: templateId, ...params },
  });
  return res.data;
}

/** Create new template version */
export async function createTemplateVersion(data: CreateTemplateVersionRequest): Promise<TemplateVersion> {
  const res = await client.post<TemplateVersion>('/resources/template-versions/', data);
  return res.data;
}

/** Restore template to specific version */
export async function restoreTemplateVersion(id: number): Promise<TemplateVersion> {
  const res = await client.post<TemplateVersion>(`/resources/template-versions/${id}/restore/`);
  return res.data;
}

// ==================== P-014: Tag System ====================

/** Tag definition */
export interface Tag {
  id: number;
  name: string;
  color: string;
  created_by: string;
  created_at: string;
}

/** Create tag request params */
export interface CreateTagRequest {
  name: string;
  color: string;
}

/** Update tag request params */
export interface UpdateTagRequest {
  name?: string;
  color?: string;
}

/** Fetch tag list */
export async function fetchTags(params?: Record<string, unknown>): Promise<Tag[]> {
  const res = await client.get<Tag[]>('/resources/tags/', { params });
  if (Array.isArray(res.data)) {
    return res.data;
  }
  return (res.data as { results: Tag[] }).results ?? [];
}

/** Create new tag */
export async function createTag(data: CreateTagRequest): Promise<Tag> {
  const res = await client.post<Tag>('/resources/tags/', data);
  return res.data;
}

/** Update tag */
export async function updateTag(id: number, data: UpdateTagRequest): Promise<Tag> {
  const res = await client.patch<Tag>(`/resources/tags/${id}/`, data);
  return res.data;
}

/** Delete tag */
export async function deleteTag(id: number): Promise<void> {
  await client.delete(`/resources/tags/${id}/`);
}

// ==================== R37-P1: Template Annotation CRUD ====================

/** Fetch template annotations, optionally filtered by template_id */
export async function fetchTemplateAnnotations(
  templateId?: number,
  params?: Partial<PaginationParams>,
): Promise<PaginatedResponse<TemplateAnnotation>> {
  const res = await client.get<PaginatedResponse<TemplateAnnotation>>('/resources/annotations/', {
    params: { ...(templateId ? { template: templateId } : {}), ...params },
  });
  return res.data;
}

/** Create a new template annotation */
export async function createTemplateAnnotation(
  data: Omit<TemplateAnnotation, 'id' | 'created_at'>,
): Promise<TemplateAnnotation> {
  const res = await client.post<TemplateAnnotation>('/resources/annotations/', data);
  return res.data;
}

/** Update an existing template annotation */
export async function updateTemplateAnnotation(
  id: number,
  data: Partial<Omit<TemplateAnnotation, 'id' | 'created_at'>>,
): Promise<TemplateAnnotation> {
  const res = await client.patch<TemplateAnnotation>(`/resources/annotations/${id}/`, data);
  return res.data;
}

/** Delete a template annotation */
export async function deleteTemplateAnnotation(id: number): Promise<void> {
  await client.delete(`/resources/annotations/${id}/`);
}

/** Batch-delete all annotations for a template (POST /annotations/batch-delete/) */
export async function batchDeleteTemplateAnnotations(templateId: number): Promise<{ deleted: number }> {
  const res = await client.post<{ deleted: number }>('/resources/annotations/batch-delete/', {
    template_id: templateId,
  });
  return res.data;
}

// ==================== R37-P2 C3: ROI CRUD ====================

/** Full rois.json structure: {public: {...}, tasks: {task_name: {...}}} */
export interface RoiData {
  public?: Record<string, number[]>;
  tasks?: Record<string, Record<string, number[]>>;
}

/** Fetch all ROIs for a resource pack */
export async function fetchRois(packId: number): Promise<RoiData> {
  const res = await client.get<RoiData>(`/resources/resource-packs/${packId}/rois/`);
  return res.data;
}

/** Replace all ROIs (full rois.json) */
export async function replaceRois(packId: number, data: RoiData): Promise<RoiData> {
  const res = await client.put<RoiData>(`/resources/resource-packs/${packId}/rois/`, data);
  return res.data;
}

/** Fetch ROIs for a single task */
export async function fetchTaskRois(packId: number, taskName: string): Promise<Record<string, number[]>> {
  const res = await client.get<{ task_name: string; rois: Record<string, number[]> }>(
    `/resources/resource-packs/${packId}/rois/${encodeURIComponent(taskName)}/`,
  );
  return res.data.rois;
}

/** Replace ROIs for a single task */
export async function replaceTaskRois(
  packId: number,
  taskName: string,
  rois: Record<string, number[]>,
): Promise<Record<string, number[]>> {
  const res = await client.put<{ task_name: string; rois: Record<string, number[]> }>(
    `/resources/resource-packs/${packId}/rois/${encodeURIComponent(taskName)}/`,
    { task_name: taskName, rois },
  );
  return res.data.rois;
}

/** Add a single ROI to a task */
export async function addRoi(packId: number, taskName: string, name: string, coords: number[]): Promise<void> {
  await client.post(`/resources/resource-packs/${packId}/rois/${encodeURIComponent(taskName)}/`, {
    name,
    coords,
  });
}

/** Delete a single ROI from a task */
export async function deleteRoi(packId: number, taskName: string, roiName: string): Promise<void> {
  await client.delete(
    `/resources/resource-packs/${packId}/rois/${encodeURIComponent(taskName)}/${encodeURIComponent(roiName)}/`,
  );
}

// ==================== Template CRUD (P-015) ====================

/** Template item — matches backend TemplateSerializer (union of fields used across pages) */
export interface Template {
  id: number;
  name: string;
  image_url: string;
  thumbnail_url?: string;
  is_valid?: boolean;
  is_active?: boolean;
  match_threshold?: number;
  region_info?: string;
  pack_id?: number;
  /** Server-assigned tag IDs (P-014) */
  tag_ids?: number[];
}

/** Fetch templates list, optionally filtered by pack_id.
 *  Backend may return either an array or a paginated response; both shapes are normalized to an array. */
export async function fetchTemplates(params?: { pack_id?: number } & Record<string, unknown>): Promise<Template[]> {
  const res = await client.get<Template[] | PaginatedResponse<Template>>('/resources/templates/', { params });
  const data = res.data;
  if (Array.isArray(data)) return data;
  return data?.results || [];
}

/** Update a template (partial PATCH). Used for toggling is_active / is_valid, etc. */
export async function updateTemplate(
  templateId: number,
  data: Partial<Pick<Template, 'is_active' | 'is_valid' | 'name' | 'match_threshold' | 'region_info'>>,
): Promise<Template> {
  const res = await client.patch<Template>(`/resources/templates/${templateId}/`, data);
  return res.data;
}

/** Delete a template */
export async function deleteTemplate(templateId: number): Promise<void> {
  await client.delete(`/resources/templates/${templateId}/`);
}

/** Check template references before toggling valid status.
 *  Returns whether the template is referenced by annotations / effectiveness records. */
export async function checkTemplateReferences(
  templateId: number,
): Promise<{ has_references: boolean; references: Record<string, number> }> {
  const res = await client.get<{ has_references: boolean; references: Record<string, number> }>(
    '/resources/templates/check-references/',
    { params: { id: templateId } },
  );
  return res.data;
}

/** Upload a single template file (multipart/form-data) */
export async function uploadTemplate(file: File, packId?: number): Promise<Template> {
  const formData = new FormData();
  formData.append('file', file);
  if (packId !== undefined) {
    formData.append('pack_id', String(packId));
  }
  const res = await client.post<Template>('/resources/templates/upload/', formData);
  return res.data;
}

/** Batch import templates from a ZIP file */
export async function batchImportTemplates(
  file: File,
  packId: number,
): Promise<{ imported: number; skipped: number; pack_name: string }> {
  const formData = new FormData();
  formData.append('zip_file', file);
  formData.append('pack_id', String(packId));
  const res = await client.post<{ imported: number; skipped: number; pack_name: string }>(
    '/resources/templates/batch-import/',
    formData,
  );
  return res.data;
}

/** Fetch template image as an authenticated blob.
 *  The template files endpoint (IsAuthenticated) cannot be hit by a bare <img src=...>
 *  because the browser will not attach the JWT. We fetch via the axios client (which
 *  injects the Authorization header) and return the blob for the caller to wrap in an object URL.
 *
 *  `imageUrl` is stored as an absolute path (`/api/v2/resources/...`) but the axios client
 *  already has `baseURL='/api/v2'`, so we strip the prefix to avoid a doubled path. */
export async function fetchTemplateImageBlob(imageUrl: string): Promise<Blob> {
  const stripped = imageUrl.replace(/^\/api\/v2/, '');
  const res = await client.get(stripped, { responseType: 'blob' });
  return res.data as Blob;
}

// ==================== Resource Pack: Create & Version History ====================

/** Create a new resource pack via the /create/ endpoint */
export async function createResourcePack(values: Record<string, unknown>): Promise<ResourcePack> {
  const res = await client.post<ResourcePack>('/resources/resource-packs/create/', values);
  return res.data;
}

/** Fetch resource pack version history */
export async function fetchResourcePackVersionHistory(packId: number): Promise<Record<string, unknown>> {
  const res = await client.get<Record<string, unknown>>(`/resources/resource-packs/${packId}/version-history/`);
  return res.data;
}

// ==================== Validation Status ====================

/** Validation status item — matches backend ValidationStatusSerializer */
export interface ValidationStatus {
  pack_id: number;
  pack_name: string;
  status: 'ok' | 'partial' | 'stale';
  total_count: number;
  valid_count: number;
  invalid_count: number;
  last_validated_at: string;
}

/** Fetch validation statuses for all resource packs.
 *  Backend may return either an array or a paginated response; both shapes are normalized to an array. */
export async function fetchValidationStatuses(): Promise<ValidationStatus[]> {
  const res = await client.get<ValidationStatus[] | PaginatedResponse<ValidationStatus>>('/resources/validation/');
  const data = res.data;
  if (Array.isArray(data)) return data;
  return data?.results || [];
}

/** Trigger revalidate-all on resource packs */
export async function revalidateAllResourcePacks(): Promise<void> {
  await client.post('/resources/validation/revalidate-all/');
}

// ==================== Template Effectiveness ====================

/** Template effectiveness stat item — matches backend TemplateEffectivenessSerializer */
export interface TemplateEffectiveness {
  id: number;
  template_name: string;
  total_attempts: number;
  success_count: number;
  failure_count: number;
  success_rate: number;
  avg_confidence: number;
  degraded: boolean;
  last_match_time: string;
  match_history?: Array<{
    timestamp: string;
    confidence: number;
    success: boolean;
    screenshot_id: string;
  }>;
}

/** Fetch template effectiveness stats.
 *  Backend may return either an array or a paginated response; both shapes are normalized to an array.
 *  R37-P3 Stage 7 Task 20a: migrated from /tasks/template-effectiveness/ to /resources/template-effectiveness/. */
export async function fetchTemplateEffectiveness(): Promise<TemplateEffectiveness[]> {
  const res = await client.get<TemplateEffectiveness[] | PaginatedResponse<TemplateEffectiveness>>(
    '/resources/template-effectiveness/',
  );
  const data = res.data;
  if (Array.isArray(data)) return data;
  return data?.results || [];
}

/** Trigger revalidate on selected templates.
 *  R37-P3 Stage 7 Task 20a: migrated path. */
export async function revalidateTemplateEffectiveness(templateIds: number[]): Promise<void> {
  await client.post('/resources/template-effectiveness/revalidate/', {
    template_ids: templateIds,
  });
}
