/**
 * UnattendedStrategySettings — unattended strategy config
 *
 * includes 5 items Collapse panel:
 * 1. 5 layer recover strategy ( step → task → app → device → system )
 * 2. night mode ( low power consumption downclock strategy )
 * 3. execute frequency limit + every daily upper limit
 * 4. exception notify strategy config
 * 5. restart interval cooldown time config
 */

import { useState, useCallback, useEffect } from 'react';
import {
  Card,
  Collapse,
  InputNumber,
  Switch,
  Radio,
  Checkbox,
  Slider,
  TimePicker,
  Button,
  Space,
  Typography,
  App,
  Spin,
  theme as antTheme,
} from 'antd';
import { SaveOutlined, ReloadOutlined } from '@ant-design/icons';
import dayjs from 'dayjs';
import { fetchUnattendedStrategy, saveUnattendedStrategy } from '@/api/misc';
import { useTranslation } from '@/i18n';

const { Text } = Typography;

interface StepLevelRecovery {
  maxRetries: number;
  retryIntervalSeconds: number;
  exponentialBackoff: boolean;
}

interface TaskLevelRecovery {
  consecutiveFailureThreshold: number;
  failureAction: 'skip' | 'restart' | 'switch_account';
}

interface AppLevelRecovery {
  freezeDetection: boolean;
  freezeTimeoutSeconds: number;
  freezeAction: 'restart_app' | 'relogin' | 'notify_only';
}

interface DeviceLevelRecovery {
  crashDetection: boolean;
  crashAction: 'restart_emulator' | 'reconnect_adb' | 'switch_backup';
  backupDeviceId: number | null;
  maxRestartCount: number;
}

interface SystemLevelRecovery {
  agentTimeoutSeconds: number;
  timeoutActions: ('notify' | 'mark_offline' | 'reassign')[];
}

interface RecoveryConfig {
  stepLevel: StepLevelRecovery;
  taskLevel: TaskLevelRecovery;
  appLevel: AppLevelRecovery;
  deviceLevel: DeviceLevelRecovery;
  systemLevel: SystemLevelRecovery;
}

interface NightModeConfig {
  isEnabled: boolean;
  timeRange: { start: string; end: string };
  screenshotIntervalMultiplier: number;
  operationIntervalMultiplier: number;
  cpuThrottle: boolean;
  autoPauseNonCritical: boolean;
}

interface FrequencyLimitConfig {
  maxPerAccountPerDay: number;
  maxGlobalPerDay: number;
  minTaskIntervalSeconds: number;
  mode: 'fixed' | 'adaptive';
}

interface NotificationPolicy {
  enabledEvents: string[];
}

interface CooldownConfig {
  emulatorRestartSeconds: number;
  gameRestartSeconds: number;
  consecutiveLoginSeconds: number;
  recoveryPauseSeconds: number;
}

interface StrategyData {
  recovery: RecoveryConfig;
  nightMode: NightModeConfig;
  frequencyLimit: FrequencyLimitConfig;
  notificationPolicy: NotificationPolicy;
  cooldown: CooldownConfig;
  is_active: boolean;
}

const DEFAULTS: StrategyData = {
  recovery: {
    stepLevel: { maxRetries: 3, retryIntervalSeconds: 5, exponentialBackoff: false },
    taskLevel: { consecutiveFailureThreshold: 3, failureAction: 'skip' },
    appLevel: { freezeDetection: true, freezeTimeoutSeconds: 120, freezeAction: 'restart_app' },
    deviceLevel: { crashDetection: true, crashAction: 'restart_emulator', backupDeviceId: null, maxRestartCount: 2 },
    systemLevel: { agentTimeoutSeconds: 300, timeoutActions: ['notify', 'mark_offline', 'reassign'] },
  },
  nightMode: {
    isEnabled: false,
    timeRange: { start: '00:00', end: '06:00' },
    screenshotIntervalMultiplier: 2,
    operationIntervalMultiplier: 2,
    cpuThrottle: true,
    autoPauseNonCritical: false,
  },
  frequencyLimit: {
    maxPerAccountPerDay: 10,
    maxGlobalPerDay: 100,
    minTaskIntervalSeconds: 30,
    mode: 'fixed',
  },
  notificationPolicy: {
    enabledEvents: [
      'task_failed',
      'device_offline',
      'account_blocked',
      'game_updated',
      'auto_stop_triggered',
      'recovery_triggered',
    ],
  },
  cooldown: {
    emulatorRestartSeconds: 120,
    gameRestartSeconds: 60,
    consecutiveLoginSeconds: 10,
    recoveryPauseSeconds: 180,
  },
  is_active: true,
};

const NOTIFICATION_EVENTS: { key: string; label: string }[] = [
  { key: 'task_failed', label: '任务执行失败' },
  { key: 'device_offline', label: '设备离线/断开' },
  { key: 'account_blocked', label: '账户被封禁' },
  { key: 'game_updated', label: '游戏版本更新' },
  { key: 'consecutive_failures', label: '连续失败达到阈值' },
  { key: 'auto_stop_triggered', label: '无人值守自动停止' },
  { key: 'night_mode_switch', label: '夜间模式切换' },
  { key: 'resource_expiring', label: '资源包即将过期' },
  { key: 'recovery_triggered', label: '恢复策略触发' },
  { key: 'daily_report_generated', label: '每日报告生成' },
];

function formatSeconds(s: number): string {
  if (s < 60) return `${s} 秒`;
  const m = Math.floor(s / 60);
  const sec = s % 60;
  return sec > 0 ? `${m} 分 ${sec} 秒` : `${m} 分钟`;
}

export function UnattendedStrategySettings() {
  const [data, setData] = useState<StrategyData>(DEFAULTS);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const { token } = antTheme.useToken();
  const { message } = App.useApp();
  const t = useTranslation();

  const fetchConfig = useCallback(async () => {
    setLoading(true);
    try {
      const json = await fetchUnattendedStrategy<StrategyData | null>();
      if (json && json.recovery) {
        setData(json);
      }
    } catch {
      // Use default values on failure
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchConfig();
  }, [fetchConfig]);

  const handleSave = useCallback(async () => {
    setSaving(true);
    try {
      await saveUnattendedStrategy<StrategyData>(data);
      message.success(t('settings.strategy_config_saved'));
    } catch {
      message.error(t('settings.strategy_save_failed_retry'));
    } finally {
      setSaving(false);
    }
  }, [data]);

  const update = useCallback((path: string[], value: unknown) => {
    setData((prev) => {
      const next = structuredClone(prev);
      let obj: Record<string, unknown> = next as unknown as Record<string, unknown>;
      for (let i = 0; i < path.length - 1; i++) {
        obj = obj[path[i]] as Record<string, unknown>;
      }
      obj[path[path.length - 1]] = value;
      return next;
    });
  }, []);

  if (loading) {
    return (
      <div style={{ textAlign: 'center', padding: 48 }}>
        <Spin size="large" />
      </div>
    );
  }

  const r = data.recovery;
  const nm = data.nightMode;
  const fl = data.frequencyLimit;
  const np = data.notificationPolicy;
  const cd = data.cooldown;

  return (
    <Space orientation="vertical" className="gaf-w-full" size="large">
      <Collapse
        defaultActiveKey={['recovery']}
        size="small"
        items={[
          {
            key: 'recovery',
            label: (
              <Space>
                <Text strong>5 层恢复策略</Text>
                <Text type="secondary" className="gaf-text-xs">
                  步骤失败时逐级兜底的恢复机制
                </Text>
              </Space>
            ),
            children: (
              <Space orientation="vertical" className="gaf-w-full" size="small">
                <Card size="small" title="层级 1：步骤级恢复">
                  <Text type="secondary" className="gaf-mb-sm" style={{ display: 'block' }}>
                    单个 Pipeline 步骤执行失败时的恢复策略
                  </Text>
                  <Space wrap>
                    <Text type="secondary">最大重试次数：</Text>
                    <InputNumber
                      min={0}
                      max={100}
                      value={r.stepLevel.maxRetries}
                      onChange={(v) => update(['recovery', 'stepLevel', 'maxRetries'], v || 3)}
                    />
                    <Text type="secondary">重试间隔（秒）：</Text>
                    <InputNumber
                      min={0}
                      max={3600}
                      value={r.stepLevel.retryIntervalSeconds}
                      onChange={(v) => update(['recovery', 'stepLevel', 'retryIntervalSeconds'], v || 5)}
                    />
                    <Switch
                      checked={r.stepLevel.exponentialBackoff}
                      onChange={(v) => update(['recovery', 'stepLevel', 'exponentialBackoff'], v)}
                      checkedChildren="指数退避"
                      unCheckedChildren="固定间隔"
                    />
                  </Space>
                </Card>

                <Card size="small" title="层级 2：任务级恢复">
                  <Text type="secondary" className="gaf-mb-sm" style={{ display: 'block' }}>
                    单个任务的多个步骤都失败时的恢复策略
                  </Text>
                  <Space wrap>
                    <Text type="secondary">连续失败阈值：</Text>
                    <InputNumber
                      min={1}
                      max={100}
                      value={r.taskLevel.consecutiveFailureThreshold}
                      onChange={(v) => update(['recovery', 'taskLevel', 'consecutiveFailureThreshold'], v || 3)}
                    />
                    <Text type="secondary">达到阈值后：</Text>
                    <Radio.Group
                      value={r.taskLevel.failureAction}
                      onChange={(e) => update(['recovery', 'taskLevel', 'failureAction'], e.target.value)}
                    >
                      <Radio.Button value="skip">跳过当前任务</Radio.Button>
                      <Radio.Button value="restart">重启当前任务（从头执行）</Radio.Button>
                      <Radio.Button value="switch_account">切换到备用账户</Radio.Button>
                    </Radio.Group>
                  </Space>
                </Card>

                <Card size="small" title="层级 3：应用级恢复">
                  <Text type="secondary" className="gaf-mb-sm" style={{ display: 'block' }}>
                    游戏应用卡死/无响应时的恢复策略
                  </Text>
                  <Space wrap>
                    <Switch
                      checked={r.appLevel.freezeDetection}
                      onChange={(v) => update(['recovery', 'appLevel', 'freezeDetection'], v)}
                      checkedChildren="卡死检测"
                    />
                    <Text type="secondary">卡死超时（秒）：</Text>
                    <InputNumber
                      min={10}
                      max={3600}
                      value={r.appLevel.freezeTimeoutSeconds}
                      onChange={(v) => update(['recovery', 'appLevel', 'freezeTimeoutSeconds'], v || 120)}
                    />
                  </Space>
                  <div className="gaf-mt-sm">
                    <Text type="secondary">卡死后动作：</Text>
                    <Radio.Group
                      value={r.appLevel.freezeAction}
                      onChange={(e) => update(['recovery', 'appLevel', 'freezeAction'], e.target.value)}
                    >
                      <Radio.Button value="restart_app">重启游戏应用</Radio.Button>
                      <Radio.Button value="relogin">重新登录账户</Radio.Button>
                      <Radio.Button value="notify_only">仅发送通知</Radio.Button>
                    </Radio.Group>
                  </div>
                </Card>

                <Card size="small" title="层级 4：设备级恢复">
                  <Text type="secondary" className="gaf-mb-sm" style={{ display: 'block' }}>
                    设备/模拟器崩溃或断开时的恢复策略
                  </Text>
                  <Space wrap>
                    <Switch
                      checked={r.deviceLevel.crashDetection}
                      onChange={(v) => update(['recovery', 'deviceLevel', 'crashDetection'], v)}
                      checkedChildren="崩溃检测"
                    />
                    <Text type="secondary">最大重启次数：</Text>
                    <InputNumber
                      min={0}
                      max={100}
                      value={r.deviceLevel.maxRestartCount}
                      onChange={(v) => update(['recovery', 'deviceLevel', 'maxRestartCount'], v || 2)}
                    />
                  </Space>
                  <div className="gaf-mt-sm">
                    <Text type="secondary">崩溃后动作：</Text>
                    <Radio.Group
                      value={r.deviceLevel.crashAction}
                      onChange={(e) => update(['recovery', 'deviceLevel', 'crashAction'], e.target.value)}
                    >
                      <Radio.Button value="restart_emulator">重启模拟器</Radio.Button>
                      <Radio.Button value="reconnect_adb">重连 ADB</Radio.Button>
                      <Radio.Button value="switch_backup">切换到备用设备</Radio.Button>
                    </Radio.Group>
                  </div>
                </Card>

                <Card size="small" title="层级 5：系统级恢复">
                  <Text type="secondary" className="gaf-mb-sm" style={{ display: 'block' }}>
                    Agent 进程无响应或系统级异常时的恢复策略
                  </Text>
                  <Space wrap>
                    <Text type="secondary">Agent 无响应超时（秒）：</Text>
                    <InputNumber
                      min={30}
                      max={7200}
                      value={r.systemLevel.agentTimeoutSeconds}
                      onChange={(v) => update(['recovery', 'systemLevel', 'agentTimeoutSeconds'], v || 300)}
                    />
                  </Space>
                  <div className="gaf-mt-sm">
                    <Text type="secondary">超时后动作（可多选）：</Text>
                    <Checkbox.Group
                      value={r.systemLevel.timeoutActions}
                      onChange={(vals) => update(['recovery', 'systemLevel', 'timeoutActions'], vals)}
                      options={[
                        { label: '发送通知给管理员', value: 'notify' },
                        { label: '标记设备为离线', value: 'mark_offline' },
                        { label: '将任务分配给其他可用设备', value: 'reassign' },
                      ]}
                    />
                  </div>
                </Card>

                <Card size="small" style={{ background: token.colorBgLayout }}>
                  <Text type="secondary" className="gaf-text-xs" style={{ whiteSpace: 'pre-line' }}>
                    {/* TD-406 (2026-08-27): summary now derives from the live
                        config so edits to any layer are reflected here. */}
                    {(() => {
                      // r === data.recovery (顶层已是 recovery 层, 见上方 const r = data.recovery)
                      const rec = r ?? {};
                      const step = rec.stepLevel ?? {};
                      const task = rec.taskLevel ?? {};
                      const app = rec.appLevel ?? {};
                      const dev = rec.deviceLevel ?? {};
                      const sys = rec.systemLevel ?? {};
                      const taskAction =
                        { skip: '跳过任务', restart: '重启任务', switch_account: '切换备用账户' }[
                          task.failureAction ?? 'skip'
                        ] ?? task.failureAction;
                      const appAction =
                        { restart_app: '重启游戏', relogin: '重新登录', notify_only: '仅通知' }[
                          app.freezeAction ?? 'restart_app'
                        ] ?? app.freezeAction;
                      const devAction =
                        { restart_emulator: '重启模拟器', reconnect_adb: '重连 ADB', switch_backup: '切换备用设备' }[
                          dev.crashAction ?? 'restart_emulator'
                        ] ?? dev.crashAction;
                      const sysAction =
                        (sys.timeoutActions ?? [])
                          .map((v) => ({ notify: '通知', mark_offline: '标记离线', reassign: '重新分配' })[v] || v)
                          .join('+') || '无';
                      return `恢复策略执行流程：\n步骤失败 → (步骤级: 重试${step.maxRetries ?? 3}次, ${step.exponentialBackoff ? '指数退避' : '固定间隔'}) → 仍失败\n  → (任务级: 连续${task.consecutiveFailureThreshold ?? 3}个任务失败) → ${taskAction}\n    → (应用级: 游戏卡死${app.freezeTimeoutSeconds ?? 120}秒) → ${appAction}\n      → (设备级: 设备崩溃) → ${devAction}\n        → (系统级: Agent无响应${sys.agentTimeoutSeconds ?? 300}秒) → ${sysAction}`;
                    })()}
                  </Text>
                </Card>
              </Space>
            ),
          },
          {
            key: 'nightMode',
            label: (
              <Space>
                <Text strong>夜间模式配置</Text>
                <Text type="secondary" className="gaf-text-xs">
                  低功耗时段的降频策略
                </Text>
              </Space>
            ),
            children: (
              <Space orientation="vertical" className="gaf-w-full" size="small">
                <Switch
                  checked={nm.isEnabled}
                  onChange={(v) => update(['nightMode', 'isEnabled'], v)}
                  checkedChildren="已开启"
                  unCheckedChildren="已关闭"
                />
                <Space>
                  <Text type="secondary">低功耗时段：</Text>
                  <TimePicker
                    format="HH:mm"
                    value={dayjs(nm.timeRange.start, 'HH:mm')}
                    onChange={(v) => update(['nightMode', 'timeRange', 'start'], v ? v.format('HH:mm') : '00:00')}
                  />
                  <Text type="secondary">至</Text>
                  <TimePicker
                    format="HH:mm"
                    value={dayjs(nm.timeRange.end, 'HH:mm')}
                    onChange={(v) => update(['nightMode', 'timeRange', 'end'], v ? v.format('HH:mm') : '06:00')}
                  />
                </Space>
                <div>
                  <Text type="secondary">截图间隔倍数：{nm.screenshotIntervalMultiplier}x</Text>
                  <Slider
                    min={1}
                    max={10}
                    value={nm.screenshotIntervalMultiplier}
                    onChange={(v) => update(['nightMode', 'screenshotIntervalMultiplier'], v)}
                    marks={{ 1: '1x', 3: '3x', 5: '5x', 7: '7x', 10: '10x' }}
                  />
                </div>
                <div>
                  <Text type="secondary">操作间隔倍数：{nm.operationIntervalMultiplier}x</Text>
                  <Slider
                    min={1}
                    max={5}
                    value={nm.operationIntervalMultiplier}
                    onChange={(v) => update(['nightMode', 'operationIntervalMultiplier'], v)}
                    marks={{ 1: '1x', 2: '2x', 3: '3x', 4: '4x', 5: '5x' }}
                  />
                </div>
                <Space>
                  <Switch
                    checked={nm.cpuThrottle}
                    onChange={(v) => update(['nightMode', 'cpuThrottle'], v)}
                    checkedChildren="CPU 节流"
                  />
                  <Switch
                    checked={nm.autoPauseNonCritical}
                    onChange={(v) => update(['nightMode', 'autoPauseNonCritical'], v)}
                    checkedChildren="自动暂停非关键任务"
                  />
                </Space>
              </Space>
            ),
          },
          {
            key: 'frequencyLimit',
            label: (
              <Space>
                <Text strong>执行频率限制 + 每日上限</Text>
                <Text type="secondary" className="gaf-text-xs">
                  防止过度执行
                </Text>
              </Space>
            ),
            children: (
              <Space orientation="vertical" className="gaf-w-full" size="small">
                <Space wrap>
                  <Text type="secondary">每账户每日最大执行次数：</Text>
                  <InputNumber
                    min={1}
                    max={99}
                    value={fl.maxPerAccountPerDay}
                    onChange={(v) => update(['frequencyLimit', 'maxPerAccountPerDay'], v || 10)}
                  />
                </Space>
                <Space wrap>
                  <Text type="secondary">全局每日最大执行次数：</Text>
                  <InputNumber
                    min={1}
                    max={999}
                    value={fl.maxGlobalPerDay}
                    onChange={(v) => update(['frequencyLimit', 'maxGlobalPerDay'], v || 100)}
                  />
                </Space>
                <Space wrap>
                  <Text type="secondary">每任务最小间隔（秒）：</Text>
                  <InputNumber
                    min={0}
                    max={3600}
                    value={fl.minTaskIntervalSeconds}
                    onChange={(v) => update(['frequencyLimit', 'minTaskIntervalSeconds'], v || 30)}
                  />
                </Space>
                <Space>
                  <Text type="secondary">频率限制模式：</Text>
                  <Radio.Group value={fl.mode} onChange={(e) => update(['frequencyLimit', 'mode'], e.target.value)}>
                    <Radio.Button value="fixed">固定间隔</Radio.Button>
                    <Radio.Button value="adaptive">智能间隔（动态调整）</Radio.Button>
                  </Radio.Group>
                </Space>
              </Space>
            ),
          },
          {
            key: 'notificationPolicy',
            label: (
              <Space>
                <Text strong>异常通知策略配置</Text>
                <Text type="secondary" className="gaf-text-xs">
                  控制哪些事件触发推送通知
                </Text>
              </Space>
            ),
            children: (
              <Space orientation="vertical" className="gaf-w-full" size="small">
                <Text type="secondary">发生以下事件时发送通知：</Text>
                <Checkbox.Group
                  value={np.enabledEvents}
                  onChange={(vals) => update(['notificationPolicy', 'enabledEvents'], vals)}
                  className="gaf-flex-col gaf-gap-sm"
                >
                  {NOTIFICATION_EVENTS.map((e) => (
                    <Checkbox key={e.key} value={e.key}>
                      {e.label}
                    </Checkbox>
                  ))}
                </Checkbox.Group>
                <Space>
                  <Button
                    size="small"
                    onClick={() =>
                      update(
                        ['notificationPolicy', 'enabledEvents'],
                        NOTIFICATION_EVENTS.map((e) => e.key),
                      )
                    }
                  >
                    全部开启
                  </Button>
                  <Button size="small" onClick={() => update(['notificationPolicy', 'enabledEvents'], [])}>
                    全部关闭
                  </Button>
                  <Button
                    size="small"
                    onClick={() =>
                      update(
                        ['notificationPolicy', 'enabledEvents'],
                        [
                          'task_failed',
                          'device_offline',
                          'account_blocked',
                          'game_updated',
                          'auto_stop_triggered',
                          'recovery_triggered',
                        ],
                      )
                    }
                  >
                    恢复默认
                  </Button>
                </Space>
              </Space>
            ),
          },
          {
            key: 'cooldown',
            label: (
              <Space>
                <Text strong>重启间冷却时间配置</Text>
                <Text type="secondary" className="gaf-text-xs">
                  防止过热或封号风险
                </Text>
              </Space>
            ),
            children: (
              <Space orientation="vertical" className="gaf-w-full" size="large">
                <div>
                  <Text type="secondary">
                    模拟器重启冷却：<Text strong>{formatSeconds(cd.emulatorRestartSeconds)}</Text>
                  </Text>
                  <Text type="secondary" className="gaf-text-xxs" style={{ display: 'block' }}>
                    模拟器重启后等待这段时间再开始任务
                  </Text>
                  <Slider
                    min={60}
                    max={600}
                    step={10}
                    value={cd.emulatorRestartSeconds}
                    onChange={(v) => update(['cooldown', 'emulatorRestartSeconds'], v)}
                    marks={{ 60: '60s', 180: '3分', 300: '5分', 600: '10分' }}
                  />
                </div>
                <div>
                  <Text type="secondary">
                    游戏重启冷却：<Text strong>{formatSeconds(cd.gameRestartSeconds)}</Text>
                  </Text>
                  <Text type="secondary" className="gaf-text-xxs" style={{ display: 'block' }}>
                    游戏重启后等待这段时间再开始操作
                  </Text>
                  <Slider
                    min={30}
                    max={300}
                    step={10}
                    value={cd.gameRestartSeconds}
                    onChange={(v) => update(['cooldown', 'gameRestartSeconds'], v)}
                    marks={{ 30: '30s', 120: '2分', 300: '5分' }}
                  />
                </div>
                <div>
                  <Text type="secondary">
                    连续登录冷却：<Text strong>{formatSeconds(cd.consecutiveLoginSeconds)}</Text>
                  </Text>
                  <Text type="secondary" className="gaf-text-xxs" style={{ display: 'block' }}>
                    同一设备连续登录两个账户之间的冷却时间
                  </Text>
                  <Slider
                    min={5}
                    max={120}
                    step={5}
                    value={cd.consecutiveLoginSeconds}
                    onChange={(v) => update(['cooldown', 'consecutiveLoginSeconds'], v)}
                    marks={{ 5: '5s', 30: '30s', 60: '60s', 120: '120s' }}
                  />
                </div>
                <div>
                  <Text type="secondary">
                    异常恢复冷却：<Text strong>{formatSeconds(cd.recoveryPauseSeconds)}</Text>
                  </Text>
                  <Text type="secondary" className="gaf-text-xxs" style={{ display: 'block' }}>
                    任何恢复策略触发后，暂停所有操作的最短时间
                  </Text>
                  <Slider
                    min={60}
                    max={600}
                    step={10}
                    value={cd.recoveryPauseSeconds}
                    onChange={(v) => update(['cooldown', 'recoveryPauseSeconds'], v)}
                    marks={{ 60: '60s', 180: '3分', 300: '5分', 600: '10分' }}
                  />
                </div>
              </Space>
            ),
          },
        ]}
      />

      <div className="gaf-gap-sm" style={{ display: 'flex', justifyContent: 'flex-end' }}>
        <Button icon={<ReloadOutlined />} onClick={fetchConfig}>
          重置
        </Button>
        <Button type="primary" icon={<SaveOutlined />} loading={saving} onClick={handleSave}>
          保存策略配置
        </Button>
      </div>
    </Space>
  );
}

export default UnattendedStrategySettings;
