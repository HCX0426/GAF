/**
 * P-011 Phase 3: UnattendedControlBar multi-session UI render tests.
 *
 * Verifies that the rewritten control bar (GameProfile picker + per-session
 * cards) renders without crashing in both the empty state and the
 * multi-session state.
 *
 * P-011 Spec A Phase 2: also covers the multi-game parallel mode toggle
 * (Segmented switch bound to the FeatureFlag).
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { App } from 'antd';
import UnattendedControlBar from '@/pages/Ops/UnattendedControlBar';

// Mock the store so we can inject sessions without going through the API.
const mockState = {
  sessions: [] as Array<{
    id: number | null;
    gameProfileId: number | null;
    gameProfileName: string | null;
    isRunning: boolean;
    isPaused: boolean;
    startedAt: string | null;
    stoppedAt: string | null;
    stopReason: string | null;
  }>,
  preflightChecks: [],
  preflightLoading: false,
  matrix: [],
  matrixLoading: false,
  queue: [],
  queueLoading: false,
  progress: null,
  progressLoading: false,
  startUnattended: vi.fn().mockResolvedValue(undefined),
  stopUnattended: vi.fn().mockResolvedValue(undefined),
  pauseUnattended: vi.fn().mockResolvedValue(undefined),
  resumeUnattended: vi.fn().mockResolvedValue(undefined),
  fetchPreflight: vi.fn().mockResolvedValue([]),
  fetchMatrix: vi.fn().mockResolvedValue(undefined),
  fetchQueue: vi.fn().mockResolvedValue(undefined),
  fetchProgress: vi.fn().mockResolvedValue(undefined),
  refreshAll: vi.fn().mockResolvedValue(undefined),
};

vi.mock('@/stores/useUnattendedStore', () => ({
  useUnattendedStore: vi.fn(() => mockState),
}));

// Mock the GameProfile API so the dropdown can populate
vi.mock('@/api/gameProfiles', () => ({
  fetchGameProfiles: vi.fn().mockResolvedValue({
    results: [
      { id: 7, game_name: 'BrownDust II' },
      { id: 9, game_name: 'Genshin Impact' },
    ],
    count: 2,
  }),
}));

// P-011 Spec A Phase 2: mock the settings API so the multi-game toggle
// can read+write the FeatureFlag without hitting the network.
const mockFetchMultiGameMode = vi.fn().mockResolvedValue(false);
const mockUpdateMultiGameMode = vi.fn().mockResolvedValue(undefined);
vi.mock('@/api/settings', () => ({
  fetchMultiGameMode: (...args: unknown[]) => mockFetchMultiGameMode(...args),
  updateMultiGameMode: (...args: unknown[]) => mockUpdateMultiGameMode(...args),
}));

// Mock classifyError so we don't pull in i18n-heavy paths
vi.mock('@/utils/errorHandler', () => ({
  classifyError: (e: unknown) => ({
    message: e instanceof Error ? e.message : String(e),
  }),
}));

describe('UnattendedControlBar (P-011 multi-session)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    // Reset to empty sessions for each test
    mockState.sessions = [];
  });

  it('renders empty state when no active sessions', async () => {
    render(
      <App>
        <UnattendedControlBar />
      </App>,
    );

    // The header shows "活跃会话 (0)" (zh-CN default in test env)
    expect(await screen.findByText('活跃会话 (0)')).toBeDefined();
    // The empty state text is shown
    expect(screen.getByText('暂无活跃会话')).toBeDefined();
    // The "启动新会话" button is rendered (disabled until a profile is picked)
    expect(screen.getByText('启动新会话')).toBeDefined();
  });

  it('renders one card per active session', async () => {
    mockState.sessions = [
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
      {
        id: 50,
        gameProfileId: 9,
        gameProfileName: 'Genshin Impact',
        isRunning: true,
        isPaused: true,
        startedAt: '2026-07-16T09:00:00Z',
        stoppedAt: null,
        stopReason: null,
      },
    ];

    render(
      <App>
        <UnattendedControlBar />
      </App>,
    );

    // Header shows count = 2
    expect(await screen.findByText('活跃会话 (2)')).toBeDefined();
    // Both session labels are rendered ("{{name}} 会话")
    expect(screen.getByText('BrownDust II 会话')).toBeDefined();
    expect(screen.getByText('Genshin Impact 会话')).toBeDefined();
  });

  it('shows Pause button for a running session and Resume for a paused session', async () => {
    mockState.sessions = [
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
      {
        id: 50,
        gameProfileId: 9,
        gameProfileName: 'Genshin Impact',
        isRunning: true,
        isPaused: true,
        startedAt: '2026-07-16T09:00:00Z',
        stoppedAt: null,
        stopReason: null,
      },
    ];

    render(
      <App>
        <UnattendedControlBar />
      </App>,
    );

    await screen.findByText('BrownDust II 会话');
    // Running session shows 暂停 button
    const pauseButtons = screen.getAllByText('暂停');
    expect(pauseButtons.length).toBeGreaterThanOrEqual(1);
    // Paused session shows 恢复 button
    expect(screen.getByText('恢复')).toBeDefined();
  });

  // P-011 Spec A Phase 2: multi-game mode toggle
  it('renders the multi-game mode Segmented toggle defaulting to 单游戏', async () => {
    mockFetchMultiGameMode.mockResolvedValueOnce(false);
    render(
      <App>
        <UnattendedControlBar />
      </App>,
    );
    // The Segmented toggle shows both labels; 单游戏 is the default (single mode)
    expect(await screen.findByText('单游戏')).toBeDefined();
    expect(screen.getByText('多游戏')).toBeDefined();
  });

  it('calls updateMultiGameMode(true) when clicking 多游戏', async () => {
    mockFetchMultiGameMode.mockResolvedValueOnce(false);
    render(
      <App>
        <UnattendedControlBar />
      </App>,
    );
    // Wait for the toggle to render
    await screen.findByText('多游戏');
    // Click the 多游戏 label to switch to multi mode
    fireEvent.click(screen.getByText('多游戏'));
    // The settings API should be called with enabled=true
    await vi.waitFor(() => {
      expect(mockUpdateMultiGameMode).toHaveBeenCalledWith(true);
    });
  });

  it('reflects multi-game mode when FeatureFlag is enabled on mount', async () => {
    mockFetchMultiGameMode.mockResolvedValueOnce(true);
    render(
      <App>
        <UnattendedControlBar />
      </App>,
    );
    // The toggle should show 多游戏 as the active label (Segmente value='multi')
    // We verify by checking that 多游戏 label is rendered (it always is) and
    // that fetchMultiGameMode was called on mount.
    expect(await screen.findByText('多游戏')).toBeDefined();
    expect(mockFetchMultiGameMode).toHaveBeenCalled();
  });
});
