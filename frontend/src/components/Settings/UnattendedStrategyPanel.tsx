/**
 * unattended strategy config panel
 * Phase 7 — includes recover strategy, night mode, frequency limit, notify strategy, cooldown config
 */
import { useEffect, useState } from 'react';
import {
  Card,
  Form,
  InputNumber,
  Switch,
  Button,
  Select,
  Checkbox,
  Divider,
  Space,
  Spin,
  message,
  Row,
  Col,
  Typography,
  Tooltip,
} from 'antd';
import {
  ReloadOutlined,
  ThunderboltOutlined,
  SafetyOutlined,
  BellOutlined,
  ClockCircleOutlined,
  DashboardOutlined,
} from '@ant-design/icons';
import { fetchUnattendedStrategy, saveUnattendedStrategy } from '@/api/misc';
import type { UnattendedStrategy } from '@/types/models';
import { useTranslation } from '@/i18n';

const { Text } = Typography;

/** default strategy value */
const DEFAULTS: UnattendedStrategy = {
  id: 0,
  recovery_config: { max_retries: 3, retry_interval_seconds: 5, exponential_backoff: true },
  task_recovery_config: { consecutive_failure_threshold: 3, on_threshold_action: 'switch_account' },
  app_recovery_config: { game_freeze_detection: true, freeze_timeout_seconds: 30, on_freeze_action: 'restart_app' },
  device_recovery_config: {
    crash_detection: true,
    on_crash_action: 'reboot',
    backup_device_id: '',
    max_reboot_count: 3,
  },
  system_recovery_config: { agent_no_response_timeout: 300, on_no_response_actions: ['notify', 'mark_offline'] },
  night_mode_config: {
    enabled: false,
    low_power_hours: ['22:00', '06:00'],
    screenshot_interval_multiplier: 3,
    operation_interval_multiplier: 2,
    cpu_throttle: true,
    auto_pause_non_critical: true,
  },
  frequency_limit_config: {
    max_per_account_per_day: 50,
    max_global_per_day: 500,
    min_interval_per_task: 10,
    mode: 'strict',
  },
  notification_policy: { enabled_events: ['task_failed', 'device_offline', 'recovery_triggered', 'night_mode_toggle'] },
  cooldown_config: {
    emulator_reboot_cooldown: 120,
    game_restart_cooldown: 60,
    consecutive_login_cooldown: 30,
    recovery_cooldown: 300,
  },
  is_active: false,
  created_at: '',
  updated_at: '',
};

export function UnattendedStrategyPanel() {
  const [form] = Form.useForm();
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const t = useTranslation();

  const loadConfig = async () => {
    setLoading(true);
    try {
      const config = await fetchUnattendedStrategy();
      form.setFieldsValue(config);
    } catch {
      form.setFieldsValue(DEFAULTS);
    } finally {
      setLoading(false);
    }
  };

  // M10: mount-only initial config load — intentionally [] deps (mount-only).
  // loadConfig calls setLoading synchronously; acceptable for mount-only fetch.
  // eslint-disable-next-line react-hooks/set-state-in-effect, react-hooks/exhaustive-deps
  useEffect(() => {
    loadConfig();
  }, []);

  const handleSave = async () => {
    try {
      const values = await form.validateFields();
      setSaving(true);
      await saveUnattendedStrategy(values);
      message.success(t('settings.unattended_strategy_saved'));
    } catch {
      message.error(t('settings.unattended_strategy_save_failed'));
    } finally {
      setSaving(false);
    }
  };

  return (
    <Spin spinning={loading}>
      <Form form={form} layout="vertical" onFinish={handleSave} initialValues={DEFAULTS}>
        <div className="gaf-flex-between gaf-mb-lg">
          <Space>
            <Form.Item name="is_active" valuePropName="checked" noStyle>
              <Switch checkedChildren="策略已启用" unCheckedChildren="策略已停用" />
            </Form.Item>
            <Text type="secondary">启用后自动接管故障恢复和夜间降频</Text>
          </Space>
          <Space>
            <Button icon={<ReloadOutlined />} onClick={loadConfig}>
              重置
            </Button>
            <Button type="primary" htmlType="submit" loading={saving} icon={<SafetyOutlined />}>
              保存策略
            </Button>
          </Space>
        </div>

        <Row gutter={[24, 24]}>
          {/* 恢复策略 */}
          <Col xs={24} lg={12}>
            <Card
              title={
                <>
                  <ThunderboltOutlined /> 步骤级恢复
                </>
              }
              size="small"
            >
              <Form.Item
                name={['recovery_config', 'max_retries']}
                label="最大重试次数"
                tooltip="单步骤失败后的最大重试次数"
              >
                <InputNumber min={0} max={10} className="gaf-w-full" />
              </Form.Item>
              <Form.Item name={['recovery_config', 'retry_interval_seconds']} label="重试间隔(秒)">
                <InputNumber min={1} max={300} className="gaf-w-full" />
              </Form.Item>
              <Form.Item
                name={['recovery_config', 'exponential_backoff']}
                label="指数退避"
                valuePropName="checked"
                tooltip="每次重试间隔翻倍"
              >
                <Switch />
              </Form.Item>
            </Card>
          </Col>

          <Col xs={24} lg={12}>
            <Card
              title={
                <>
                  <SafetyOutlined /> 任务级恢复
                </>
              }
              size="small"
            >
              <Form.Item
                name={['task_recovery_config', 'consecutive_failure_threshold']}
                label="连续失败阈值"
                tooltip="连续失败达到此次数触发任务级恢复"
              >
                <InputNumber min={1} max={20} className="gaf-w-full" />
              </Form.Item>
              <Form.Item name={['task_recovery_config', 'on_threshold_action']} label="触发动作">
                <Select
                  options={[
                    { value: 'switch_account', label: '切换账号' },
                    { value: 'skip_task', label: '跳过任务' },
                    { value: 'retry_full_pipeline', label: '重新执行完整 Pipeline' },
                  ]}
                />
              </Form.Item>
            </Card>
          </Col>

          {/* 应用级和设备级恢复 */}
          <Col xs={24} lg={12}>
            <Card title="应用级恢复" size="small">
              <Form.Item
                name={['app_recovery_config', 'game_freeze_detection']}
                label="游戏卡死检测"
                valuePropName="checked"
              >
                <Switch />
              </Form.Item>
              <Form.Item name={['app_recovery_config', 'freeze_timeout_seconds']} label="卡死超时(秒)">
                <InputNumber min={5} max={120} className="gaf-w-full" />
              </Form.Item>
              <Form.Item name={['app_recovery_config', 'on_freeze_action']} label="卡死动作">
                <Select
                  options={[
                    { value: 'restart_app', label: '重启游戏' },
                    { value: 'clear_cache', label: '清除缓存' },
                    { value: 'reboot_emulator', label: '重启模拟器' },
                  ]}
                />
              </Form.Item>
            </Card>
          </Col>

          <Col xs={24} lg={12}>
            <Card title="设备级恢复" size="small">
              <Form.Item name={['device_recovery_config', 'crash_detection']} label="崩溃检测" valuePropName="checked">
                <Switch />
              </Form.Item>
              <Form.Item name={['device_recovery_config', 'on_crash_action']} label="崩溃动作">
                <Select
                  options={[
                    { value: 'reboot', label: '重启设备' },
                    { value: 'switch_to_backup', label: '切换备用设备' },
                    { value: 'mark_offline', label: '标记离线' },
                  ]}
                />
              </Form.Item>
              <Form.Item name={['device_recovery_config', 'max_reboot_count']} label="最大重启次数">
                <InputNumber min={0} max={10} className="gaf-w-full" />
              </Form.Item>
            </Card>
          </Col>
        </Row>

        <Card
          title={
            <>
              <BellOutlined /> 系统级恢复
            </>
          }
          size="small"
          className="gaf-mt-lg"
        >
          <Form.Item name={['system_recovery_config', 'agent_no_response_timeout']} label="Worker 无响应超时(秒)">
            <InputNumber min={30} max={3600} className="gaf-w-full" />
          </Form.Item>
          <Form.Item name={['system_recovery_config', 'on_no_response_actions']} label="超时动作">
            <Checkbox.Group
              options={[
                { value: 'notify', label: '发送通知' },
                { value: 'mark_offline', label: '标记离线' },
                { value: 'auto_restart_agent', label: '自动重启 Worker' },
                { value: 'switch_device', label: '切换设备' },
              ]}
            />
          </Form.Item>
        </Card>

        <Divider>夜间模式</Divider>

        <Card size="small">
          <Form.Item name={['night_mode_config', 'enabled']} label="启用夜间模式" valuePropName="checked">
            <Switch />
          </Form.Item>
          <Row gutter={16}>
            <Col span={12}>
              <Form.Item
                name={['night_mode_config', 'low_power_hours']}
                label="低功耗时段"
                tooltip="[开始时间, 结束时间]"
              >
                <Select
                  mode="multiple"
                  className="gaf-w-full"
                  placeholder="选择时段"
                  options={[
                    { value: '22:00', label: '22:00' },
                    { value: '23:00', label: '23:00' },
                    { value: '00:00', label: '00:00' },
                    { value: '01:00', label: '01:00' },
                    { value: '02:00', label: '02:00' },
                    { value: '03:00', label: '03:00' },
                    { value: '04:00', label: '04:00' },
                    { value: '05:00', label: '05:00' },
                    { value: '06:00', label: '06:00' },
                    { value: '07:00', label: '07:00' },
                  ]}
                />
              </Form.Item>
            </Col>
            <Col span={6}>
              <Form.Item
                name={['night_mode_config', 'screenshot_interval_multiplier']}
                label={<Tooltip title="截图间隔倍数">截图间隔×</Tooltip>}
              >
                <InputNumber min={1} max={10} step={0.5} className="gaf-w-full" />
              </Form.Item>
            </Col>
            <Col span={6}>
              <Form.Item
                name={['night_mode_config', 'operation_interval_multiplier']}
                label={<Tooltip title="操作间隔倍数">操作间隔×</Tooltip>}
              >
                <InputNumber min={1} max={10} step={0.5} className="gaf-w-full" />
              </Form.Item>
            </Col>
          </Row>
          <Space size="large">
            <Form.Item name={['night_mode_config', 'cpu_throttle']} label="CPU 降频" valuePropName="checked">
              <Switch />
            </Form.Item>
            <Form.Item
              name={['night_mode_config', 'auto_pause_non_critical']}
              label="自动暂停非关键任务"
              valuePropName="checked"
            >
              <Switch />
            </Form.Item>
          </Space>
        </Card>

        <Divider>
          <DashboardOutlined /> 频率限制
        </Divider>

        <Card size="small">
          <Row gutter={16}>
            <Col span={8}>
              <Form.Item name={['frequency_limit_config', 'max_per_account_per_day']} label="每账号每日上限">
                <InputNumber min={0} max={1000} className="gaf-w-full" />
              </Form.Item>
            </Col>
            <Col span={8}>
              <Form.Item name={['frequency_limit_config', 'max_global_per_day']} label="全局每日上限">
                <InputNumber min={0} max={10000} className="gaf-w-full" />
              </Form.Item>
            </Col>
            <Col span={8}>
              <Form.Item name={['frequency_limit_config', 'min_interval_per_task']} label="任务最小间隔(秒)">
                <InputNumber min={1} max={3600} className="gaf-w-full" />
              </Form.Item>
            </Col>
          </Row>
          <Form.Item name={['frequency_limit_config', 'mode']} label="限制模式">
            <Select
              options={[
                { value: 'strict', label: '严格模式 - 超出上限立即拒绝' },
                { value: 'queue', label: '排队模式 - 超出上限排队等待' },
                { value: 'degrade', label: '降级模式 - 超出上限降低频率' },
              ]}
            />
          </Form.Item>
        </Card>

        <Divider>
          <BellOutlined /> 通知策略
        </Divider>

        <Card size="small">
          <Form.Item name={['notification_policy', 'enabled_events']} label="启用通知事件">
            <Checkbox.Group className="gaf-w-full">
              <Row>
                {[
                  { value: 'task_failed', label: '任务失败' },
                  { value: 'task_completed', label: '任务完成' },
                  { value: 'device_offline', label: '设备离线' },
                  { value: 'device_reconnected', label: '设备重连' },
                  { value: 'recovery_triggered', label: '恢复策略触发' },
                  { value: 'night_mode_toggle', label: '夜间模式切换' },
                  { value: 'frequency_limit_hit', label: '频率限制触发' },
                  { value: 'heuristic_change', label: '策略自动调整' },
                ].map((item) => (
                  <Col span={8} key={item.value}>
                    <Checkbox value={item.value}>{item.label}</Checkbox>
                  </Col>
                ))}
              </Row>
            </Checkbox.Group>
          </Form.Item>
        </Card>

        <Divider titlePlacement="left">
          <ClockCircleOutlined /> 冷却时间
        </Divider>

        <Card size="small">
          <Row gutter={16}>
            <Col span={6}>
              <Form.Item name={['cooldown_config', 'emulator_reboot_cooldown']} label="模拟器重启(秒)">
                <InputNumber min={0} max={3600} className="gaf-w-full" />
              </Form.Item>
            </Col>
            <Col span={6}>
              <Form.Item name={['cooldown_config', 'game_restart_cooldown']} label="游戏重启(秒)">
                <InputNumber min={0} max={3600} className="gaf-w-full" />
              </Form.Item>
            </Col>
            <Col span={6}>
              <Form.Item name={['cooldown_config', 'consecutive_login_cooldown']} label="连续登录(秒)">
                <InputNumber min={0} max={3600} className="gaf-w-full" />
              </Form.Item>
            </Col>
            <Col span={6}>
              <Form.Item name={['cooldown_config', 'recovery_cooldown']} label="恢复操作(秒)">
                <InputNumber min={0} max={3600} className="gaf-w-full" />
              </Form.Item>
            </Col>
          </Row>
        </Card>

        <div className="gaf-mt-xl" style={{ textAlign: 'center' }}>
          <Button type="primary" size="large" htmlType="submit" loading={saving} icon={<SafetyOutlined />}>
            保存全部策略配置
          </Button>
        </div>
      </Form>
    </Spin>
  );
}

export default UnattendedStrategyPanel;
