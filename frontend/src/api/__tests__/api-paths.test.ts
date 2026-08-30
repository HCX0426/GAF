/**
 * API path consistency test
 * verify frontend API module paths match backend routes
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import client from '@/api/client';

// Mock axios
vi.mock('../client', () => ({
  default: {
    get: vi.fn(() => Promise.resolve({ data: {} })),
    post: vi.fn(() => Promise.resolve({ data: {} })),
    put: vi.fn(() => Promise.resolve({ data: {} })),
    patch: vi.fn(() => Promise.resolve({ data: {} })),
    delete: vi.fn(() => Promise.resolve({ data: {} })),
  },
}));

describe('API 路径一致性', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('认证路径应以斜杠结尾', async () => {
    const { login } = await import('../auth');
    await login({ username: 'test', password: 'test' });
    expect(client.post).toHaveBeenCalledWith(
      expect.stringMatching(/\/login\/$/),
      expect.any(Object),
      expect.anything(),
    );
  });

  it('Worker 路径应以斜杠结尾', async () => {
    const { fetchAgents } = await import('../agents');
    await fetchAgents();
    expect(client.get).toHaveBeenCalledWith(expect.stringMatching(/\/agents\/$/), expect.anything());
  });

  it('Task 路径应以斜杠结尾', async () => {
    const { fetchTasks } = await import('../tasks');
    await fetchTasks();
    expect(client.get).toHaveBeenCalledWith(expect.stringMatching(/\/tasks\/$/), expect.anything());
  });

  it('资源包路径应使用 resource-packs', async () => {
    const { fetchResourcePacks } = await import('../resources');
    await fetchResourcePacks();
    expect(client.get).toHaveBeenCalledWith(expect.stringContaining('resource-packs'), expect.anything());
  });

  it('调试日志路径应使用 debug-logs', async () => {
    const { fetchDebugLogs } = await import('../debug');
    await fetchDebugLogs();
    expect(client.get).toHaveBeenCalledWith(expect.stringContaining('debug-logs'), expect.anything());
  });

  it('QA 路径应使用 qa-sessions', async () => {
    const { fetchQASessions } = await import('../ai');
    await fetchQASessions();
    expect(client.get).toHaveBeenCalledWith(expect.stringContaining('qa-sessions'), expect.anything());
  });

  it('监控路径应使用 monitor-rules', async () => {
    const { fetchMonitorRules } = await import('../monitors');
    await fetchMonitorRules();
    expect(client.get).toHaveBeenCalledWith(expect.stringContaining('monitor-rules'), expect.anything());
  });

  it('Skill 自动匹配应使用 auto-match', async () => {
    const { autoMatchSkills } = await import('../skills');
    await autoMatchSkills('test query');
    expect(client.post).toHaveBeenCalledWith(expect.stringContaining('auto-match'), expect.any(Object));
  });

  it('Accounts 路径应以斜杠结尾', async () => {
    const { fetchGameAccounts } = await import('../accounts');
    await fetchGameAccounts();
    expect(client.get).toHaveBeenCalledWith(expect.stringMatching(/\/accounts\/game-accounts\/$/), expect.anything());
  });

  it('AI 路径应以斜杠结尾', async () => {
    const { fetchModelEvaluations } = await import('../ai');
    await fetchModelEvaluations();
    expect(client.get).toHaveBeenCalledWith(expect.stringMatching(/\/ai\/model-evaluations\/$/));
  });

  it('AlertRules 路径应以斜杠结尾', async () => {
    const { fetchAlertRules } = await import('../monitors');
    await fetchAlertRules();
    expect(client.get).toHaveBeenCalledWith(
      expect.stringMatching(/\/notifications\/alert-rules\/$/),
      expect.anything(),
    );
  });

  it('Devices 路径应以斜杠结尾', async () => {
    const { fetchDevices } = await import('../devices');
    await fetchDevices();
    expect(client.get).toHaveBeenCalledWith(expect.stringMatching(/\/devices\/$/), expect.anything());
  });

  it('Executions 路径应以斜杠结尾', async () => {
    const { fetchAllExecutions } = await import('../executions');
    await fetchAllExecutions();
    expect(client.get).toHaveBeenCalledWith(expect.stringMatching(/\/tasks\/task-executions\/$/), expect.anything());
  });

  it('GameProfiles 路径应以斜杠结尾', async () => {
    const { fetchGameProfiles } = await import('../gameProfiles');
    await fetchGameProfiles();
    expect(client.get).toHaveBeenCalledWith(expect.stringMatching(/\/gamestate\/game-profiles\/$/), expect.anything());
  });

  it('Init 路径应以斜杠结尾', async () => {
    const { checkHasAdmin } = await import('../init');
    await checkHasAdmin();
    expect(client.get).toHaveBeenCalledWith(expect.stringMatching(/\/accounts\/init\/check-admin\/$/));
  });

  it('Logs 路径应以斜杠结尾', async () => {
    const { fetchLogEntries } = await import('../logs');
    await fetchLogEntries();
    expect(client.get).toHaveBeenCalledWith(expect.stringMatching(/\/logs\/$/), expect.anything());
  });

  it('Marketplace 路径应以斜杠结尾', async () => {
    const { fetchMarketItems } = await import('../skills');
    await fetchMarketItems();
    expect(client.get).toHaveBeenCalledWith(expect.stringMatching(/\/skills\/market\/$/), expect.anything());
  });

  it('Misc 路径应以斜杠结尾', async () => {
    const { fetchCurrentUser } = await import('../misc');
    await fetchCurrentUser();
    expect(client.get).toHaveBeenCalledWith(expect.stringMatching(/\/accounts\/users\/me\/$/));
  });

  it('Notifications 路径应以斜杠结尾', async () => {
    const { fetchUnreadCount } = await import('../notifications');
    await fetchUnreadCount();
    expect(client.get).toHaveBeenCalledWith(expect.stringMatching(/\/notifications\/unread-count\/$/));
  });

  it('Ops 路径应以斜杠结尾', async () => {
    const { fetchSlaMetrics } = await import('../ops');
    await fetchSlaMetrics();
    expect(client.get).toHaveBeenCalledWith(expect.stringMatching(/\/monitors\/sla\/$/));
  });

  it('Pipelines 路径应以斜杠结尾', async () => {
    const { listPipelines } = await import('../pipelines');
    await listPipelines();
    expect(client.get).toHaveBeenCalledWith(expect.stringMatching(/\/pipeline\/pipelines\/$/), expect.anything());
  });

  it('Plugins 路径应以斜杠结尾', async () => {
    const { fetchPlugins } = await import('../plugins');
    await fetchPlugins();
    expect(client.get).toHaveBeenCalledWith(expect.stringMatching(/\/plugins\/$/), expect.anything());
  });

  it('Recordings 路径应以斜杠结尾', async () => {
    const { fetchRecordings } = await import('../recordings');
    await fetchRecordings();
    expect(client.get).toHaveBeenCalledWith(expect.stringMatching(/\/pipeline\/recordings\/$/));
  });

  it('ScheduledTasks 路径应以斜杠结尾', async () => {
    const { fetchScheduledTasks } = await import('../scheduler');
    await fetchScheduledTasks();
    expect(client.get).toHaveBeenCalledWith(expect.stringMatching(/\/tasks\/scheduled-tasks\/$/), expect.anything());
  });

  it('Scheduler 路径应以斜杠结尾', async () => {
    const { fetchTimeWindows } = await import('../scheduler');
    await fetchTimeWindows();
    expect(client.get).toHaveBeenCalledWith(expect.stringMatching(/\/scheduler\/time-windows\/$/), expect.anything());
  });

  it('Settings 路径应以斜杠结尾', async () => {
    const { fetchUsers } = await import('../settings');
    await fetchUsers();
    expect(client.get).toHaveBeenCalledWith(expect.stringMatching(/\/accounts\/users\/$/), expect.anything());
  });

  it('Unattended 写请求路径必须以斜杠结尾', async () => {
    // Regression guard (2026-08-27): start/stop/pause/resume 曾丢失尾斜杠，
    // 在 Django APPEND_SLASH 下 POST 会直接 500（GET 有 301 重定向被掩盖）。
    const misc = await import('../misc');
    await misc.startUnattended(2);
    expect(client.post).toHaveBeenCalledWith(
      expect.stringMatching(/\/scheduler\/unattended\/start\/$/),
      expect.any(Object),
    );
    await misc.stopUnattended(9);
    expect(client.post).toHaveBeenCalledWith(
      expect.stringMatching(/\/scheduler\/unattended\/stop\/$/),
      expect.any(Object),
    );
    await misc.pauseUnattended(9);
    expect(client.post).toHaveBeenCalledWith(
      expect.stringMatching(/\/scheduler\/unattended\/pause\/$/),
      expect.any(Object),
    );
    await misc.resumeUnattended(9);
    expect(client.post).toHaveBeenCalledWith(
      expect.stringMatching(/\/scheduler\/unattended\/resume\/$/),
      expect.any(Object),
    );
  });
});
