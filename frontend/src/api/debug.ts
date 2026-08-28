/**
 * Debug log API: archive upload, list, LLM analysis trigger, review action.
 */
import client from './client';
import type { DebugLogArchive, LLMAnalysisResult, PaginatedResponse, ReviewStatus } from '@/types/models';

/** Fetch debug log archives (paginated). */
export async function fetchDebugLogs(params?: {
  page?: number;
  page_size?: number;
  analysis_status?: string;
  skill?: number;
}): Promise<PaginatedResponse<DebugLogArchive>> {
  const res = await client.get<PaginatedResponse<DebugLogArchive>>('/debug/debug-logs/', { params });
  return res.data;
}

/** Upload a debug log archive (multipart). Backend sets uploaded_by automatically. */
export async function uploadDebugLog(file: File): Promise<DebugLogArchive> {
  const formData = new FormData();
  formData.append('zip_file_path', file.name);
  formData.append('file', file);
  const res = await client.post<DebugLogArchive>('/debug/debug-logs/', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  });
  return res.data;
}

/** Trigger LLM analysis on a log archive. Backend requires skill_id in body. */
export async function analyzeDebugLog(logId: number | string, skillId: number): Promise<LLMAnalysisResult> {
  const res = await client.post<LLMAnalysisResult>(`/debug/debug-logs/${logId}/analyze/`, { skill_id: skillId });
  return res.data;
}

/** Fetch all LLM analysis results for a given log archive (spec 阶段 3.4c).
 * Used by ArchiveLogTab and LogAnalysisPanel to populate the analysis results list.
 * Backend LLMAnalysisResultViewSet supports `?log_archive=<id>` filter.
 */
export async function fetchAnalysisResults(logArchiveId: number | string): Promise<LLMAnalysisResult[]> {
  const res = await client.get<PaginatedResponse<LLMAnalysisResult>>('/debug/analysis-results/', {
    params: { log_archive: logArchiveId, page_size: 100 },
  });
  return res.data.results || [];
}

/** Update the review_status of an analysis result via the /review/ action (PUT). */
export async function reviewSuggestion(
  analysisResultId: number | string,
  reviewStatus: ReviewStatus,
): Promise<LLMAnalysisResult> {
  const res = await client.put<LLMAnalysisResult>(`/debug/analysis-results/${analysisResultId}/review/`, {
    review_status: reviewStatus,
  });
  return res.data;
}
