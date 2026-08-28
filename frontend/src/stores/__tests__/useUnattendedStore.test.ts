/**
 * P-011 Phase 3: useUnattendedStore multi-session state tests.
 *
 * Verifies that the store correctly manages an array of sessions
 * (start/stop/pause/resume) and syncs with the backend active_sessions
 * list returned by /scheduler/unattended/status.
 */
import { describe, it, expect, beforeEach, vi } from 'vitest';

// Mock the API module before importing the store. The store imports named
// functions from '@/api/misc', so we mock the whole module.
vi.mock('@/api/misc', () => ({
  startUnattended: vi.fn(),
  stopUnattended: vi.fn(),
  pauseUnattended: vi.fn(),
  resumeUnattended: vi.fn(),
  fetchUnattendedPreflight: vi.fn(),
  fetchUnattendedStatus: vi.fn(),
  fetchUnattendedQueue: vi.fn(),
  fetchUnattendedProgress: vi.fn(),
}));

// Mock useAuthStore.getState().isAuthenticated → true so fetchMatrix runs
vi.mock('@/stores/useAuthStore', () => ({
  useAuthStore: {
    getState: () => ({ isAuthenticated: true }),
  },
}));

import { useUnattendedStore } from '@/stores/useUnattendedStore';
import {
  startUnattended as apiStartUnattended,
  stopUnattended as apiStopUnattended,
  pauseUnattended as apiPauseUnattended,
  resumeUnattended as apiResumeUnattended,
  fetchUnattendedStatus as apiFetchStatus,
  fetchUnattendedQueue as apiFetchQueue,
  fetchUnattendedProgress as apiFetchProgress,
} from '@/api/misc';

describe('useUnattendedStore (P-011 multi-session)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    // Reset store to a clean state
    useUnattendedStore.setState({
      sessions: [],
      preflightChecks: [],
      preflightLoading: false,
      matrix: [],
      matrixLoading: false,
      queue: [],
      queueLoading: false,
      progress: null,
      progressLoading: false,
    });
  });

  it('initial state has empty sessions array', () => {
    const state = useUnattendedStore.getState();
    expect(state.sessions).toEqual([]);
    expect(state.matrix).toEqual([]);
    expect(state.queue).toEqual([]);
    expect(state.progress).toBeNull();
  });

  it('startUnattended adds new session to sessions list', async () => {
    vi.mocked(apiStartUnattended).mockResolvedValue({
      status: 'running',
      session_id: 42,
      game_profile_id: 7,
      game_profile_name: 'BrownDust II',
      started_at: '2026-07-16T10:00:00Z',
      rotation_rule_id: null,
      dispatched_count: 3,
      skipped_count: 0,
      failed_count: 0,
      dispatched_chain_execution_ids: [100, 101, 102],
      skipped: [],
      failed: [],
      message: 'started',
    });
    // After start, backend status includes the new session (production behavior)
    vi.mocked(apiFetchStatus).mockResolvedValue({
      mode_status: 'running',
      active_sessions: [
        {
          id: 42,
          status: 'RUNNING',
          mode_status: 'running',
          game_profile_id: 7,
          game_profile_name: 'BrownDust II',
          started_at: '2026-07-16T10:00:00Z',
          total_devices: 3,
          total_accounts: 5,
        },
      ],
      total_devices: 3,
      total_accounts: 5,
      matrix: [],
    });
    vi.mocked(apiFetchQueue).mockResolvedValue({ queue: [] });
    vi.mocked(apiFetchProgress).mockResolvedValue({
      date: '2026-07-16',
      totalAccounts: 0,
      completed: 0,
      success: 0,
      failed: 0,
      skipped: 0,
      successRate: 0,
      estimatedRemainingSeconds: 0,
    });

    const { startUnattended } = useUnattendedStore.getState();
    await startUnattended(7);

    const state = useUnattendedStore.getState();
    expect(state.sessions).toHaveLength(1);
    expect(state.sessions[0]).toMatchObject({
      id: 42,
      gameProfileId: 7,
      gameProfileName: 'BrownDust II',
      isRunning: true,
      isPaused: false,
      startedAt: '2026-07-16T10:00:00Z',
    });
    // Verify API was called with gameProfileId (rotationRuleId + loopRotation
    // omitted → both undefined)
    expect(apiStartUnattended).toHaveBeenCalledWith(7, '', undefined, undefined);
  });

  it('startUnattended for same game_profile replaces existing session', async () => {
    // Pre-populate with an existing session for profile 7
    useUnattendedStore.setState({
      sessions: [
        {
          id: 41,
          gameProfileId: 7,
          gameProfileName: 'BrownDust II',
          isRunning: true,
          isPaused: false,
          startedAt: '2026-07-16T09:00:00Z',
          stoppedAt: null,
          stopReason: null,
        },
      ],
    });
    vi.mocked(apiStartUnattended).mockResolvedValue({
      status: 'running',
      session_id: 42,
      game_profile_id: 7,
      game_profile_name: 'BrownDust II',
      started_at: '2026-07-16T10:00:00Z',
      rotation_rule_id: null,
      dispatched_count: 3,
      skipped_count: 0,
      failed_count: 0,
      dispatched_chain_execution_ids: [],
      skipped: [],
      failed: [],
      message: 'started',
    });
    vi.mocked(apiFetchStatus).mockResolvedValue({
      mode_status: 'running',
      active_sessions: [
        {
          id: 42,
          status: 'RUNNING',
          mode_status: 'running',
          game_profile_id: 7,
          game_profile_name: 'BrownDust II',
          started_at: '2026-07-16T10:00:00Z',
          total_devices: 3,
          total_accounts: 5,
        },
      ],
      total_devices: 3,
      total_accounts: 5,
      matrix: [],
    });
    vi.mocked(apiFetchQueue).mockResolvedValue({ queue: [] });
    vi.mocked(apiFetchProgress).mockResolvedValue({
      date: '2026-07-16',
      totalAccounts: 0,
      completed: 0,
      success: 0,
      failed: 0,
      skipped: 0,
      successRate: 0,
      estimatedRemainingSeconds: 0,
    });

    const { startUnattended } = useUnattendedStore.getState();
    await startUnattended(7);

    const state = useUnattendedStore.getState();
    // Old session (id=41) replaced by new (id=42), not appended
    expect(state.sessions).toHaveLength(1);
    expect(state.sessions[0].id).toBe(42);
  });

  it('startUnattended for different game_profile keeps both sessions', async () => {
    useUnattendedStore.setState({
      sessions: [
        {
          id: 41,
          gameProfileId: 7,
          gameProfileName: 'BrownDust II',
          isRunning: true,
          isPaused: false,
          startedAt: '2026-07-16T09:00:00Z',
          stoppedAt: null,
          stopReason: null,
        },
      ],
    });
    vi.mocked(apiStartUnattended).mockResolvedValue({
      status: 'running',
      session_id: 50,
      game_profile_id: 9,
      game_profile_name: 'Genshin Impact',
      started_at: '2026-07-16T10:00:00Z',
      rotation_rule_id: null,
      dispatched_count: 2,
      skipped_count: 0,
      failed_count: 0,
      dispatched_chain_execution_ids: [],
      skipped: [],
      failed: [],
      message: 'started',
    });
    vi.mocked(apiFetchStatus).mockResolvedValue({
      mode_status: 'running',
      active_sessions: [
        {
          id: 41,
          status: 'RUNNING',
          mode_status: 'running',
          game_profile_id: 7,
          game_profile_name: 'BrownDust II',
          started_at: '2026-07-16T09:00:00Z',
          total_devices: 3,
          total_accounts: 5,
        },
        {
          id: 50,
          status: 'RUNNING',
          mode_status: 'running',
          game_profile_id: 9,
          game_profile_name: 'Genshin Impact',
          started_at: '2026-07-16T10:00:00Z',
          total_devices: 2,
          total_accounts: 3,
        },
      ],
      total_devices: 5,
      total_accounts: 8,
      matrix: [],
    });
    vi.mocked(apiFetchQueue).mockResolvedValue({ queue: [] });
    vi.mocked(apiFetchProgress).mockResolvedValue({
      date: '2026-07-16',
      totalAccounts: 0,
      completed: 0,
      success: 0,
      failed: 0,
      skipped: 0,
      successRate: 0,
      estimatedRemainingSeconds: 0,
    });

    const { startUnattended } = useUnattendedStore.getState();
    await startUnattended(9);

    const state = useUnattendedStore.getState();
    // Both sessions coexist (different game_profile_id)
    expect(state.sessions).toHaveLength(2);
    expect(state.sessions.map((s) => s.gameProfileId).sort()).toEqual([7, 9]);
  });

  it('stopUnattended marks the targeted session as stopped', async () => {
    useUnattendedStore.setState({
      sessions: [
        {
          id: 42,
          gameProfileId: 7,
          gameProfileName: 'BrownDust II',
          isRunning: true,
          isPaused: false,
          startedAt: '2026-07-16T10:00:00Z',
          stoppedAt: null,
          stopReason: null,
        },
      ],
    });
    vi.mocked(apiStopUnattended).mockResolvedValue(undefined);

    const { stopUnattended } = useUnattendedStore.getState();
    await stopUnattended(42, 'manual');

    const state = useUnattendedStore.getState();
    expect(state.sessions).toHaveLength(1);
    expect(state.sessions[0]).toMatchObject({
      id: 42,
      isRunning: false,
      isPaused: false,
      stopReason: 'manual',
    });
    expect(state.sessions[0].stoppedAt).toBeTruthy();
    expect(apiStopUnattended).toHaveBeenCalledWith(42, 'manual');
  });

  it('pauseUnattended marks the targeted session as paused', async () => {
    useUnattendedStore.setState({
      sessions: [
        {
          id: 42,
          gameProfileId: 7,
          gameProfileName: 'BrownDust II',
          isRunning: true,
          isPaused: false,
          startedAt: '2026-07-16T10:00:00Z',
          stoppedAt: null,
          stopReason: null,
        },
      ],
    });
    vi.mocked(apiPauseUnattended).mockResolvedValue(undefined);

    const { pauseUnattended } = useUnattendedStore.getState();
    await pauseUnattended(42);

    const state = useUnattendedStore.getState();
    expect(state.sessions[0]).toMatchObject({
      id: 42,
      isRunning: true,
      isPaused: true,
    });
    expect(apiPauseUnattended).toHaveBeenCalledWith(42);
  });

  it('resumeUnattended marks the targeted session as running again', async () => {
    useUnattendedStore.setState({
      sessions: [
        {
          id: 42,
          gameProfileId: 7,
          gameProfileName: 'BrownDust II',
          isRunning: true,
          isPaused: true,
          startedAt: '2026-07-16T10:00:00Z',
          stoppedAt: null,
          stopReason: null,
        },
      ],
    });
    vi.mocked(apiResumeUnattended).mockResolvedValue(undefined);

    const { resumeUnattended } = useUnattendedStore.getState();
    await resumeUnattended(42);

    const state = useUnattendedStore.getState();
    expect(state.sessions[0]).toMatchObject({
      id: 42,
      isRunning: true,
      isPaused: false,
    });
    expect(apiResumeUnattended).toHaveBeenCalledWith(42);
  });

  it('fetchMatrix syncs sessions from backend active_sessions list', async () => {
    vi.mocked(apiFetchStatus).mockResolvedValue({
      mode_status: 'running',
      active_sessions: [
        {
          id: 42,
          status: 'RUNNING',
          mode_status: 'running',
          game_profile_id: 7,
          game_profile_name: 'BrownDust II',
          started_at: '2026-07-16T10:00:00Z',
          total_devices: 3,
          total_accounts: 5,
        },
        {
          id: 50,
          status: 'PAUSED',
          mode_status: 'paused',
          game_profile_id: 9,
          game_profile_name: 'Genshin Impact',
          started_at: '2026-07-16T09:00:00Z',
          total_devices: 2,
          total_accounts: 3,
        },
      ],
      total_devices: 5,
      total_accounts: 8,
      matrix: [
        {
          // real backend returns snake_case keys — the store maps them to
          // camelCase MatrixRow (see matrixRowToState)
          device_id: 1,
          device_name: 'Device-A',
          device_status: 'online',
          cells: [],
        },
      ],
    });

    const { fetchMatrix } = useUnattendedStore.getState();
    await fetchMatrix();

    const state = useUnattendedStore.getState();
    // sessions list rebuilt from active_sessions
    expect(state.sessions).toHaveLength(2);
    expect(state.sessions[0]).toMatchObject({
      id: 42,
      gameProfileId: 7,
      gameProfileName: 'BrownDust II',
      isRunning: true,
      isPaused: false,
    });
    expect(state.sessions[1]).toMatchObject({
      id: 50,
      gameProfileId: 9,
      gameProfileName: 'Genshin Impact',
      isRunning: true,
      isPaused: true,
    });
    // matrix also populated
    expect(state.matrix).toHaveLength(1);
    expect(state.matrix[0].deviceName).toBe('Device-A');
  });

  it('fetchMatrix with empty active_sessions clears sessions list', async () => {
    // Pre-populate with a session
    useUnattendedStore.setState({
      sessions: [
        {
          id: 42,
          gameProfileId: 7,
          gameProfileName: 'BrownDust II',
          isRunning: true,
          isPaused: false,
          startedAt: '2026-07-16T10:00:00Z',
          stoppedAt: null,
          stopReason: null,
        },
      ],
    });
    vi.mocked(apiFetchStatus).mockResolvedValue({
      mode_status: 'stopped',
      active_sessions: [],
      total_devices: 0,
      total_accounts: 0,
      matrix: [],
    });

    const { fetchMatrix } = useUnattendedStore.getState();
    await fetchMatrix();

    const state = useUnattendedStore.getState();
    // Backend reports no active sessions → local sessions list cleared
    expect(state.sessions).toEqual([]);
  });
});
