/**
 * unattended state management Store
 *
 * management unattended mode run row status, pre-check result, execute matrix, queue and progress data.
 * via API and after end sync status change.
 *
 * P-011 (2026-07-16): store refactored from single global session to a
 * `sessions: UnattendedSession[]` array. Each session is scoped to a
 * GameProfile and runs independently — start/stop/pause/resume all take
 * either a gameProfileId (start) or a sessionId (stop/pause/resume).
 *
 * F002 fix: migrated from raw fetch() to client-based API calls for
 * automatic token injection, 401 refresh handling, and consistent error
 * interception.
 */
import { create } from 'zustand';
import type { UnattendedSession, PreflightCheck, MatrixRow, MatrixCell, QueueItem, ProgressData } from '@/types/models';
import { useAuthStore } from './useAuthStore';
import {
  startUnattended as apiStartUnattended,
  stopUnattended as apiStopUnattended,
  pauseUnattended as apiPauseUnattended,
  resumeUnattended as apiResumeUnattended,
  fetchUnattendedPreflight as apiFetchPreflight,
  fetchUnattendedStatus as apiFetchStatus,
  fetchUnattendedQueue as apiFetchQueue,
  fetchUnattendedProgress as apiFetchProgress,
  type ActiveSessionEntry,
  type UnattendedMatrixRow,
  type UnattendedQueueEntry,
} from '@/api/misc';

/** unattended Store status API */
interface UnattendedState {
  /** active sessions (P-011: multi-session parallel, scoped by game_profile) */
  sessions: UnattendedSession[];
  /** pre-check list result */
  preflightChecks: PreflightCheck[];
  /** pre-check is no currently load */
  preflightLoading: boolean;
  /** device × account run row status matrix */
  matrix: MatrixRow[];
  /** matrix is no load in */
  matrixLoading: boolean;
  /** execute queue list */
  queue: QueueItem[];
  /** queue is no load in */
  queueLoading: boolean;
  /** today progress data */
  progress: ProgressData | null;
  /** progress is no load in */
  progressLoading: boolean;

  /** start unattended for a game_profile (P-011) */
  startUnattended: (
    gameProfileId: number,
    reason?: string,
    rotationRuleId?: number,
    loopRotation?: boolean,
  ) => Promise<void>;
  /** stop unattended by session_id (P-011) */
  stopUnattended: (sessionId: number, reason?: string) => Promise<void>;
  /** pause a session by session_id (P-011) */
  pauseUnattended: (sessionId: number) => Promise<void>;
  /** resume a session by session_id (P-011) */
  resumeUnattended: (sessionId: number) => Promise<void>;
  /** get pre-check list */
  fetchPreflight: (gameProfileId?: number) => Promise<PreflightCheck[]>;
  /** get run row status matrix + sync sessions from backend active_sessions */
  fetchMatrix: () => Promise<void>;
  /** get execute queue */
  fetchQueue: (limit?: number) => Promise<void>;
  /** get today progress */
  fetchProgress: () => Promise<void>;
  /** refresh has data (matrix, queue, progress) */
  refreshAll: () => Promise<void>;
}

/** Convert a backend ActiveSessionEntry into the frontend UnattendedSession shape.
 *
 * Convention (matches pauseUnattended/resumeUnattended): `isRunning` is true
 * for any session that is still active (running OR paused); only a stopped
 * session has `isRunning: false`. `isPaused` distinguishes the two active
 * sub-states.
 */
function activeSessionToState(entry: ActiveSessionEntry): UnattendedSession {
  return {
    id: entry.id,
    gameProfileId: entry.game_profile_id,
    gameProfileName: entry.game_profile_name,
    isRunning: entry.mode_status !== 'stopped',
    isPaused: entry.mode_status === 'paused',
    startedAt: entry.started_at,
    stoppedAt: null,
    stopReason: null,
  };
}

/** Convert backend snake_case matrix rows into the frontend camelCase MatrixRow
 * shape. The backend `status` view returns snake_case keys (`device_id`,
 * `device_name`, `device_status`, cells with `account_name` …); the frontend
 * types + matrix table read camelCase. Without this mapping, every device row
 * would render as offline and account columns would be empty.
 */
function matrixRowToState(row: UnattendedMatrixRow): MatrixRow {
  return {
    deviceId: row.device_id ?? '',
    deviceName: row.device_name ?? '',
    deviceStatus: row.device_status ?? 'unknown',
    cells: (row.cells ?? []).map((c) => ({
      accountId: c.account_id ?? 0,
      accountName: c.account_name ?? '',
      taskName: c.task_name ?? null,
      status: (c.status ?? 'idle') as MatrixCell['status'],
      progress: c.progress ?? 0,
      startedAt: c.started_at ?? null,
      errorMessage: c.error_message ?? null,
    })),
  };
}

/** Convert backend snake_case queue entries into the frontend QueueItem shape. */
function queueItemToState(q: UnattendedQueueEntry): QueueItem {
  return {
    id: q.id ?? 0,
    deviceName: q.device_name ?? '',
    accountName: q.account_name ?? '',
    taskName: q.task_name ?? '',
    estimatedStart: q.estimated_start ?? '',
    status: (q.status ?? 'queued') as QueueItem['status'],
    priority: q.priority ?? 0,
  };
}

/** Convert backend snake_case today-progress payload into ProgressData. */
function progressToState(p: {
  date?: string;
  total_accounts?: number;
  completed?: number;
  success?: number;
  failed?: number;
  skipped?: number;
  success_rate?: number;
  estimated_remaining_seconds?: number;
}): ProgressData {
  return {
    date: p.date ?? '',
    totalAccounts: p.total_accounts ?? 0,
    completed: p.completed ?? 0,
    success: p.success ?? 0,
    failed: p.failed ?? 0,
    skipped: p.skipped ?? 0,
    successRate: p.success_rate ?? 0,
    estimatedRemainingSeconds: p.estimated_remaining_seconds ?? 0,
  };
}

/**
 * unattended state management Store
 */
export const useUnattendedStore = create<UnattendedState>((set, get) => ({
  sessions: [],
  preflightChecks: [],
  preflightLoading: false,
  matrix: [],
  matrixLoading: false,
  queue: [],
  queueLoading: false,
  progress: null,
  progressLoading: false,

  /**
   * Start unattended mode for a game_profile (P-011).
   *
   * On success, appends the new session to `sessions` and triggers a
   * refresh of matrix/queue/progress so the UI reflects the new dispatch.
   */
  startUnattended: async (gameProfileId, reason = '', rotationRuleId?, loopRotation?) => {
    try {
      // F002 fix: use API module instead of raw fetch() for token injection + 401 refresh.
      const data = await apiStartUnattended(gameProfileId, reason, rotationRuleId, loopRotation);
      const newSession: UnattendedSession = {
        id: data.session_id,
        gameProfileId: data.game_profile_id,
        gameProfileName: data.game_profile_name,
        isRunning: true,
        isPaused: false,
        startedAt: data.started_at,
        stoppedAt: null,
        stopReason: null,
      };
      set((s) => {
        // Replace any existing entry for the same game_profile (defensive —
        // backend 409 should already prevent this) and append the new one.
        const filtered = s.sessions.filter((sess) => sess.gameProfileId !== newSession.gameProfileId);
        return { sessions: [...filtered, newSession] };
      });
      await get().refreshAll();
    } catch (e) {
      throw e instanceof Error ? e : new Error('启动失败');
    }
  },

  /**
   * Stop unattended mode by session_id (P-011).
   *
   * On success, removes the session from `sessions` (backend marks it
   * STOPPED and it no longer appears in active_sessions on next fetch).
   */
  stopUnattended: async (sessionId, reason = 'manual') => {
    try {
      await apiStopUnattended(sessionId, reason);
      set((s) => ({
        sessions: s.sessions.map((sess) =>
          sess.id === sessionId
            ? {
                ...sess,
                isRunning: false,
                isPaused: false,
                stoppedAt: new Date().toISOString(),
                stopReason: reason,
              }
            : sess,
        ),
      }));
    } catch {
      // Stop unattended failed — state unchanged (next status fetch will reconcile)
    }
  },

  /**
   * Pause a session by session_id (P-011).
   */
  pauseUnattended: async (sessionId) => {
    try {
      await apiPauseUnattended(sessionId);
      set((s) => ({
        sessions: s.sessions.map((sess) =>
          sess.id === sessionId ? { ...sess, isPaused: true, isRunning: true } : sess,
        ),
      }));
    } catch {
      // Pause unattended failed — state unchanged
    }
  },

  /**
   * Resume a session by session_id (P-011).
   */
  resumeUnattended: async (sessionId) => {
    try {
      await apiResumeUnattended(sessionId);
      set((s) => ({
        sessions: s.sessions.map((sess) =>
          sess.id === sessionId ? { ...sess, isPaused: false, isRunning: true } : sess,
        ),
      }));
    } catch {
      // Resume unattended failed — state unchanged
    }
  },

  /**
   * get pre-check list
   */
  fetchPreflight: async (gameProfileId?: number) => {
    if (!useAuthStore.getState().isAuthenticated) return [];
    set({ preflightLoading: true });
    try {
      const data = await apiFetchPreflight(gameProfileId);
      const checks = (data.checks ?? []) as PreflightCheck[];
      set({ preflightChecks: checks, preflightLoading: false });
      return checks;
    } catch {
      set({ preflightLoading: false });
      return [];
    }
  },

  /**
   * get run row status matrix + sync sessions from backend active_sessions.
   *
   * P-011: backend `/scheduler/unattended/status` now returns both the
   * matrix and an `active_sessions` list. We sync `sessions` from this
   * list so the store stays consistent with the database even if events
   * like auto-stop fire on the backend.
   */
  fetchMatrix: async () => {
    if (!useAuthStore.getState().isAuthenticated) return;
    set({ matrixLoading: true });
    try {
      const data = await apiFetchStatus();
      const sessions = (data.active_sessions ?? []).map(activeSessionToState);
      set({
        matrix: (data.matrix ?? []).map(matrixRowToState),
        sessions,
        matrixLoading: false,
      });
    } catch {
      set({ matrixLoading: false });
    }
  },

  /**
   * get execute queue
   */
  fetchQueue: async (limit = 12) => {
    if (!useAuthStore.getState().isAuthenticated) return;
    set({ queueLoading: true });
    try {
      const data = await apiFetchQueue(limit);
      set({ queue: (data.queue ?? []).map(queueItemToState), queueLoading: false });
    } catch {
      set({ queueLoading: false });
    }
  },

  /**
   * get today progress
   */
  fetchProgress: async () => {
    if (!useAuthStore.getState().isAuthenticated) return;
    set({ progressLoading: true });
    try {
      const data = await apiFetchProgress();
      set({
        progress: progressToState(data),
        progressLoading: false,
      });
    } catch {
      set({ progressLoading: false });
    }
  },

  /**
   * refresh has unattended data ( matrix, queue, progress )
   */
  refreshAll: async () => {
    await Promise.all([get().fetchMatrix(), get().fetchQueue(20), get().fetchProgress()]);
  },
}));
