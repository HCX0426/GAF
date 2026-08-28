/**
 * monitor domain models (s37 split from models.ts — TD-365).
 */

export type CellStatus = 'idle' | 'running' | 'completed' | 'failed' | 'skipped';

/** matrix cell */

export interface MatrixCell {
  accountId: number;
  accountName: string;
  taskName: string | null;
  status: CellStatus;
  progress: number;
  startedAt: string | null;
  errorMessage: string | null;
}

/** status matrix row ( device dimension ) */

export interface MatrixRow {
  deviceId: number | string;
  deviceName: string;
  deviceStatus: string;
  cells: MatrixCell[];
}

/** execute queue item status */

export type QueueItemStatus = 'queued' | 'warming_up' | 'running';

/** execute queue item */

export interface QueueItem {
  id: number;
  deviceName: string;
  accountName: string;
  taskName: string;
  estimatedStart: string;
  status: QueueItemStatus;
  priority: number;
}

/** today progress data */

export interface ProgressData {
  date: string;
  totalAccounts: number;
  completed: number;
  success: number;
  failed: number;
  skipped: number;
  successRate: number;
  estimatedRemainingSeconds: number;
}

/** API Key model — matches backend APIKeySerializer */

export interface ApiKey {
  id: number;
  name: string;
  permissions: Record<string, unknown>;
  ip_whitelist: string[];
  call_count: number;
  expires_at: string | null;
  is_active: boolean;
  created_at: string;
  key_display?: string;
  plain_key?: string;
}

/** Feature Flag model — matches backend FeatureFlagSerializer */

export interface FeatureFlag {
  id: number;
  name: string;
  description: string;
  enabled: boolean;
  rollout_percentage: number;
  allowed_roles: string[];
  allowed_ips: string[];
  created_at: string;
  updated_at: string;
}

/** Audit Log model — matches backend AuditLogSerializer */

export interface AuditLog {
  id: number;
  user: number | null;
  username: string | null;
  action: string;
  resource_type: string;
  resource_id: string;
  details: Record<string, unknown>;
  ip_address: string | null;
  created_at: string;
}

/** Log Entry model — matches backend LogEntrySerializer (core app) */

export interface LogEntry {
  id: number;
  timestamp: string;
  level: 'DEBUG' | 'INFO' | 'WARNING' | 'ERROR' | 'CRITICAL';
  source: string;
  message: string;
  traceback: string;
  task_id: number | null;
  agent_id: number | null;
  device_id: number | null;
  /** Trace ID for request correlation (from TracingMiddleware contextvar) */
  trace_id: string | null;
}

/** DAG task chain — multi task orchestrate */

export interface TaskChain {
  id: number;
  name: string;
  description: string;
  dag_data: DagData;
  is_enabled: boolean;
  created_by: number;
  created_by_username: string;
  node_count: number;
  // Spec v3 §2.2: TaskChain now belongs to a GameProfile + has is_default flag
  game_profile?: number | null;
  game_profile_name?: string | null;
  is_default?: boolean;
  created_at: string;
  updated_at: string;
}

/**
 * TD-110: TaskChainNode can reference either a Task or a Pipeline.
 * node_type discriminates which FK is populated. Mirrors the backend
 * TaskChainNodeSerializer (pipeline/serializers.py).
 */

export type ChainNodeType = 'task' | 'pipeline';

export interface TaskChainNode {
  id: number;
  chain: number;
  node_type: ChainNodeType;
  task: number | null;
  task_name: string | null;
  pipeline: number | null;
  pipeline_name: string | null;
  parent: number | null;
  parent_task_name: string | null;
  parent_pipeline_name: string | null;
  condition: Record<string, unknown>;
  order: number | null;
}

/** DAG data (React Flow nodes + edges) */

export interface DagData {
  nodes: DagNode[];
  edges: DagEdge[];
  viewport?: { x: number; y: number; zoom: number };
}

/**
 * DAG node — represents one Task OR one Pipeline (TD-110).
 *
 * node_type defaults to 'task' for backward compatibility with existing
 * dag_data blobs that don't include the field. When node_type='pipeline',
 * pipeline_id/pipeline_name are set and task_id/task_name are undefined.
 */

export interface DagNode {
  id: string;
  type?: string;
  position: { x: number; y: number };
  data: {
    label: string;
    node_type?: ChainNodeType;
    task_id?: number;
    task_name?: string;
    pipeline_id?: number;
    pipeline_name?: string;
    status?: string;
  };
}

/** DAG connection — represent depends on relation */

export interface DagEdge {
  id: string;
  source: string;
  target: string;
  sourceHandle?: string | null;
  targetHandle?: string | null;
  type?: string;
  animated?: boolean;
  label?: string;
}
