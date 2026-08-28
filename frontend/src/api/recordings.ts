import client from './client';

export interface RecordingItem {
  id: number;
  name: string;
  duration: number;
  event_count: number;
  screenshot_count: number;
  resolution: string;
  pipeline_json?: Record<string, unknown> | null;
  created_at: string;
}

/** Single recorded event (click/key/screenshot/wait) */
export interface RecordingEvent {
  event_type: 'click' | 'key' | 'screenshot' | 'wait';
  timestamp: number;
  x: number;
  y: number;
  button: string;
  key: string;
  screenshot_path: string;
  screenshot_url?: string;
  duration: number;
}

/** Recording detail with full event list */
export interface RecordingDetail extends RecordingItem {
  recording_data?: {
    id: string;
    name: string;
    events: RecordingEvent[];
    screenshot_dir: string;
  };
  events?: RecordingEvent[]; // Some backends may flatten events to top level
}

export interface CreateRecordingPayload {
  name: string;
  recording_data?: Record<string, unknown>;
  duration?: number;
  screenshot_count?: number;
  resolution?: string;
}

export async function fetchRecordings(): Promise<RecordingItem[]> {
  const res = await client.get('/pipeline/recordings/');
  /** Handle DRF paginated response { count, results } or plain array */
  const data = res.data;
  if (Array.isArray(data)) return data;
  if (data && Array.isArray(data.results)) return data.results;
  return [];
}

export async function fetchRecordingDetail(id: number): Promise<RecordingDetail> {
  const res = await client.get<RecordingDetail>(`/pipeline/recordings/${id}/`);
  return res.data;
}

export async function createRecording(payload: CreateRecordingPayload): Promise<RecordingItem> {
  const res = await client.post<RecordingItem>('/pipeline/recordings/', payload);
  return res.data;
}

export async function updateRecording(id: number, payload: Partial<CreateRecordingPayload>): Promise<RecordingItem> {
  const res = await client.patch<RecordingItem>(`/pipeline/recordings/${id}/`, payload);
  return res.data;
}

export async function convertRecordingToPipeline(id: number): Promise<{ id: number; name: string }> {
  // A015 fix: snake_case URL convert_to_pipeline -> kebab-case convert-to-pipeline
  // P-008: migrated from /tasks/recordings/ to /pipeline/recordings/
  const res = await client.post(`/pipeline/recordings/${id}/convert-to-pipeline/`);
  return res.data;
}

export async function deleteRecording(id: number): Promise<void> {
  await client.delete(`/pipeline/recordings/${id}/`);
}
