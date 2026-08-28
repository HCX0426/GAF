/**
 * emulator management page
 * includes: emulator lifecycle cycle control ( start / stop / restart / delete ),ADB command panel, device list, emulator discovery
 */
import { useEffect, useMemo, useCallback, useState, type CSSProperties } from 'react';
import {
  Card,
  Row,
  Col,
  Empty,
  Spin,
  Typography,
  App,
  Tag,
  Space,
  Button,
  Divider,
  Input,
  Tooltip,
  Popconfirm,
  Alert,
  Modal,
  Form,
  Select,
  InputNumber,
  Checkbox,
  theme as antTheme,
} from 'antd';
import {
  PlayCircleOutlined,
  PauseCircleOutlined,
  ReloadOutlined,
  DeleteOutlined,
  CodeOutlined,
  HeartOutlined,
  WarningOutlined,
  CheckCircleOutlined,
  SyncOutlined,
  MedicineBoxOutlined,
  SettingOutlined,
} from '@ant-design/icons';
import DeviceCard from '@/components/Device/DeviceCard';
import PageWrapper from '@/components/Common/PageWrapper';
import { useDeviceStore } from '@/stores/useDeviceStore';
import {
  fetchEmulatorInstances,
  executeEmulatorAction,
  type EmulatorInstance,
  type HealthCheckResult,
} from '@/api/devices';
import type { Device } from '@/types/models';
import { useTranslation } from '@/i18n';

// F010 fix: helper function replaces 3-level nested ternary for heart icon color
function getHealthCheckStyle(
  hc: HealthCheckResult | undefined,
  successColor: string,
  errorColor: string,
): CSSProperties {
  if (!hc) return {};
  return { color: hc.is_healthy ? successColor : errorColor };
}

export function EmulatorManagementPage() {
  const { token } = antTheme.useToken();
  const { message } = App.useApp();
  const { devices, loading, fetchDevices } = useDeviceStore();
  const t = useTranslation();

  const [instances, setInstances] = useState<EmulatorInstance[]>([]);
  const [instancesLoading, setInstancesLoading] = useState(false);
  const [ldconsoleAvailable, setLdconsoleAvailable] = useState(false);
  const [actionLoading, setActionLoading] = useState<Record<string, boolean>>({});
  const [adbSerial, setAdbSerial] = useState('');
  const [adbCommand, setAdbCommand] = useState('');
  const [adbResult, setAdbResult] = useState('');
  const [adbRunning, setAdbRunning] = useState(false);
  const [healthStatus, setHealthStatus] = useState<Record<string, HealthCheckResult>>({});
  const [healthLoading, setHealthLoading] = useState<Record<string, boolean>>({});
  const [autoRestartLoading, setAutoRestartLoading] = useState<Record<string, boolean>>({});
  const [configModalOpen, setConfigModalOpen] = useState(false);
  const [configTarget, setConfigTarget] = useState<{ name: string; index: number } | null>(null);
  const [configLoading, setConfigLoading] = useState(false);
  const [configForm] = Form.useForm();
  const [selectedInstances, setSelectedInstances] = useState<number[]>([]);
  const [batchLoading, setBatchLoading] = useState(false);

  useEffect(() => {
    fetchDevices();
  }, [fetchDevices]);

  const emulatorDevices = useMemo(() => (devices || []).filter((d: Device) => d.device_type === 'emulator'), [devices]);

  const loadInstances = useCallback(async () => {
    setInstancesLoading(true);
    try {
      const res = await fetchEmulatorInstances();
      setInstances(res.instances || []);
      setLdconsoleAvailable(res.ldconsole_available);
      if (res.error) {
        message.warning(res.error);
      }
    } catch {
      message.error(t('emulator.msg_load_failed'));
    } finally {
      setInstancesLoading(false);
    }
  }, [message, t]);

  useEffect(() => {
    loadInstances();
  }, [loadInstances]);

  const handleAction = async (action: string, nameOrIndex: string) => {
    const key = `${action}-${nameOrIndex}`;
    setActionLoading((prev) => ({ ...prev, [key]: true }));
    try {
      const result = await executeEmulatorAction(action, { name_or_index: nameOrIndex });
      if (result.success) {
        message.success(result.message);
        await loadInstances();
      } else {
        message.error(result.message);
      }
    } catch {
      message.error(t('emulator.msg_action_failed', { action }));
    } finally {
      setActionLoading((prev) => ({ ...prev, [key]: false }));
    }
  };

  const handleAdbSend = async () => {
    if (!adbSerial || !adbCommand) {
      message.warning(t('emulator.msg_adb_required'));
      return;
    }
    setAdbRunning(true);
    try {
      const result = await executeEmulatorAction('adb', {
        adb_serial: adbSerial,
        command: adbCommand,
      });
      setAdbResult(
        result.success
          ? result.raw_output || result.message
          : t('emulator.adb_error_prefix', { message: result.message }),
      );
    } catch {
      setAdbResult(t('emulator.adb_exception'));
    } finally {
      setAdbRunning(false);
    }
  };

  const handleHealthCheck = async (nameOrIndex: string, index: number) => {
    const key = `hc-${index}`;
    setHealthLoading((prev) => ({ ...prev, [key]: true }));
    try {
      const result = await executeEmulatorAction('health_check', { name_or_index: nameOrIndex });
      if (result.success && result.health_check) {
        setHealthStatus((prev) => ({ ...prev, [index]: result.health_check }));
        message.success(
          result.health_check.is_healthy
            ? t('emulator.msg_health_check_success', { name: result.health_check.instance_name })
            : t('emulator.msg_health_check_failed', {
                name: result.health_check.instance_name,
                error: result.health_check.error,
              }),
        );
      } else {
        message.error(result.message || t('emulator.msg_health_check_failed_default'));
      }
    } catch {
      message.error(t('emulator.msg_health_check_exception'));
    } finally {
      setHealthLoading((prev) => ({ ...prev, [key]: false }));
    }
  };

  const handleHealthCheckAll = async () => {
    try {
      const result = await executeEmulatorAction('health_check_all', {});
      if (result.success && result.health_checks) {
        const newHealthStatus: Record<string, HealthCheckResult> = {};
        for (const hc of result.health_checks) {
          newHealthStatus[hc.instance_index] = hc;
        }
        setHealthStatus(newHealthStatus);
        const healthyCount = result.health_checks.filter((h: HealthCheckResult) => h.is_healthy).length;
        message.success(
          t('emulator.msg_health_check_all_success', { healthy: healthyCount, total: result.health_checks.length }),
        );
      } else {
        message.error(result.message || t('emulator.msg_health_check_all_failed'));
      }
    } catch {
      message.error(t('emulator.msg_health_check_all_exception'));
    }
  };

  const handleAutoRestart = async (nameOrIndex: string, index: number) => {
    const key = `ar-${index}`;
    setAutoRestartLoading((prev) => ({ ...prev, [key]: true }));
    try {
      const result = await executeEmulatorAction('auto_restart', {
        name_or_index: nameOrIndex,
        max_retries: 3,
      });
      if (result.success) {
        message.success(result.message);
        await loadInstances();
      } else {
        message.error(result.message);
      }
    } catch {
      message.error(t('emulator.msg_auto_restart_exception'));
    } finally {
      setAutoRestartLoading((prev) => ({ ...prev, [key]: false }));
    }
  };

  const openConfigModal = (name: string, index: number) => {
    setConfigTarget({ name, index });
    configForm.setFieldsValue({ resolution: '1280x720', dpi: 240, cpu_count: 4, memory_mb: 4096 });
    setConfigModalOpen(true);
  };

  const handleConfigSave = async () => {
    if (!configTarget) return;
    try {
      const values = await configForm.validateFields();
      setConfigLoading(true);
      const result = await executeEmulatorAction('configure', {
        name_or_index: String(configTarget.index),
        ...values,
      });
      if (result.success) {
        message.success(result.message);
        setConfigModalOpen(false);
      } else {
        message.error(result.message);
      }
    } catch {
      // Form validation failed — antd displays field-level errors automatically
    } finally {
      setConfigLoading(false);
    }
  };

  const handleBatchAction = async (action: string) => {
    if (selectedInstances.length === 0) {
      message.warning(t('emulator.msg_no_selection'));
      return;
    }
    setBatchLoading(true);
    let successCount = 0;
    let failCount = 0;
    for (const index of selectedInstances) {
      try {
        const result = await executeEmulatorAction(action, { name_or_index: String(index) });
        if (result.success) successCount++;
        else failCount++;
      } catch {
        failCount++;
      }
    }
    message.info(t('emulator.msg_batch_result', { action, success: successCount, fail: failCount }));
    setSelectedInstances([]);
    await loadInstances();
    setBatchLoading(false);
  };

  const statusColor = (status: string) => {
    if (status === 'running') return 'green';
    if (status === 'stopped') return 'default';
    return 'orange';
  };

  return (
    <PageWrapper>
      <div>
        {/* 模拟器生命周期控制 */}
        <Card
          title={
            <div className="gaf-toolbar-group">
              <span>{t('emulator.title_lifecycle')}</span>
              <Tag color={ldconsoleAvailable ? 'blue' : 'red'}>
                {ldconsoleAvailable ? t('emulator.ldconsole_available') : t('emulator.ldconsole_unavailable')}
              </Tag>
            </div>
          }
          extra={
            <div className="gaf-toolbar">
              <Checkbox
                checked={selectedInstances.length === instances.length && instances.length > 0}
                indeterminate={selectedInstances.length > 0 && selectedInstances.length < instances.length}
                onChange={(e) => {
                  if (e.target.checked) {
                    setSelectedInstances(instances.map((i) => i.index));
                  } else {
                    setSelectedInstances([]);
                  }
                }}
              >
                {t('emulator.select_all', { selected: selectedInstances.length, total: instances.length })}
              </Checkbox>
              {selectedInstances.length > 0 && (
                <>
                  <Button
                    icon={<PlayCircleOutlined />}
                    size="small"
                    loading={batchLoading}
                    onClick={() => handleBatchAction('start')}
                  >
                    {t('emulator.btn_batch_start')}
                  </Button>
                  <Popconfirm
                    title={t('emulator.confirm_batch_stop', { count: selectedInstances.length })}
                    onConfirm={() => handleBatchAction('stop')}
                  >
                    <Button icon={<PauseCircleOutlined />} size="small" danger loading={batchLoading}>
                      {t('emulator.btn_batch_stop')}
                    </Button>
                  </Popconfirm>
                  <Button
                    icon={<ReloadOutlined />}
                    size="small"
                    loading={batchLoading}
                    onClick={() => handleBatchAction('restart')}
                  >
                    {t('emulator.btn_batch_restart')}
                  </Button>
                </>
              )}
              <Divider />
              <Button icon={<MedicineBoxOutlined />} onClick={handleHealthCheckAll}>
                {t('emulator.btn_health_check_all')}
              </Button>
              <Button icon={<ReloadOutlined />} onClick={loadInstances} loading={instancesLoading}>
                {t('emulator.btn_refresh_instances')}
              </Button>
            </div>
          }
          className="gaf-mb-lg"
        >
          <Spin spinning={instancesLoading}>
            {!ldconsoleAvailable ? (
              <Alert
                type="warning"
                showIcon
                title={t('emulator.alert_no_ldconsole')}
                description={t('emulator.alert_no_ldconsole_desc')}
              />
            ) : instances.length === 0 ? (
              <Empty description={t('emulator.empty_instances')} image={Empty.PRESENTED_IMAGE_SIMPLE}>
                <Typography.Text type="secondary">{t('emulator.empty_instances_hint')}</Typography.Text>
              </Empty>
            ) : (
              <Row gutter={[12, 12]}>
                {instances.map((inst) => {
                  const actionKey = (a: string) => `${a}-${inst.index}`;
                  const hc = healthStatus[inst.index];
                  return (
                    <Col key={inst.index} xs={24} sm={12} md={8} lg={6}>
                      <Card
                        size="small"
                        title={
                          <Space>
                            <Checkbox
                              checked={selectedInstances.includes(inst.index)}
                              onChange={(e) => {
                                if (e.target.checked) {
                                  setSelectedInstances((prev) => [...prev, inst.index]);
                                } else {
                                  setSelectedInstances((prev) => prev.filter((i) => i !== inst.index));
                                }
                              }}
                              onClick={(e) => e.stopPropagation()}
                            />
                            <Tag color={statusColor(inst.status)}>
                              {inst.status === 'running' ? t('emulator.status_running') : t('emulator.status_stopped')}
                            </Tag>
                            <span>{inst.name}</span>
                            {hc && (
                              <Tag
                                color={hc.is_healthy ? 'green' : 'red'}
                                icon={hc.is_healthy ? <CheckCircleOutlined /> : <WarningOutlined />}
                              >
                                {hc.is_healthy ? t('emulator.status_healthy') : t('emulator.status_unhealthy')}
                              </Tag>
                            )}
                          </Space>
                        }
                        actions={
                          [
                            inst.is_running ? (
                              <Popconfirm
                                key="stop"
                                title={t('emulator.confirm_stop')}
                                onConfirm={() => handleAction('stop', String(inst.index))}
                              >
                                <Tooltip title={t('emulator.action_stop')}>
                                  <PauseCircleOutlined key="stop-icon" style={{ color: token.colorError }} />
                                </Tooltip>
                              </Popconfirm>
                            ) : (
                              <Tooltip title={t('emulator.action_start')} key="start">
                                <PlayCircleOutlined
                                  style={{ color: token.colorSuccess }}
                                  onClick={() => handleAction('start', String(inst.index))}
                                />
                              </Tooltip>
                            ),
                            <Tooltip title={t('emulator.action_restart')} key="restart">
                              <ReloadOutlined
                                onClick={() => handleAction('restart', String(inst.index))}
                                spin={!!actionLoading[actionKey('restart')]}
                              />
                            </Tooltip>,
                            inst.is_running ? (
                              <Tooltip title={t('emulator.action_health_check')} key="health">
                                <HeartOutlined
                                  style={getHealthCheckStyle(hc, token.colorSuccess, token.colorError)}
                                  onClick={() => handleHealthCheck(String(inst.index), inst.index)}
                                  spin={!!healthLoading[`hc-${inst.index}`]}
                                />
                              </Tooltip>
                            ) : null,
                            inst.is_running ? (
                              <Popconfirm
                                key="auto_restart"
                                title={t('emulator.confirm_auto_restart')}
                                onConfirm={() => handleAutoRestart(String(inst.index), inst.index)}
                              >
                                <Tooltip title={t('emulator.action_auto_restart')}>
                                  <SyncOutlined spin={!!autoRestartLoading[`ar-${inst.index}`]} />
                                </Tooltip>
                              </Popconfirm>
                            ) : null,
                            <Tooltip title={t('emulator.action_config')} key="config">
                              <SettingOutlined onClick={() => openConfigModal(inst.name, inst.index)} />
                            </Tooltip>,
                            <Popconfirm
                              key="delete"
                              title={t('emulator.confirm_delete')}
                              onConfirm={() => handleAction('delete', String(inst.index))}
                            >
                              <Tooltip title={t('emulator.action_delete')}>
                                <DeleteOutlined style={{ color: token.colorError }} />
                              </Tooltip>
                            </Popconfirm>,
                          ].filter(Boolean) as React.ReactNode[]
                        }
                      >
                        <Space orientation="vertical" size={4}>
                          <Typography.Text type="secondary">
                            {t('emulator.lbl_index', { index: inst.index })}
                          </Typography.Text>
                          <Typography.Text type="secondary">
                            {t('emulator.lbl_type', { type: inst.emulator_type })}
                          </Typography.Text>
                          {hc && (
                            <>
                              <Typography.Text type="secondary">
                                {hc.adb_connected
                                  ? t('emulator.lbl_adb_connected')
                                  : t('emulator.lbl_adb_disconnected')}
                              </Typography.Text>
                              <Typography.Text type="secondary">
                                {t('emulator.lbl_fps', { fps: hc.screen_fps > 0 ? `${hc.screen_fps} fps` : '-' })}
                              </Typography.Text>
                              {hc.error && (
                                <Typography.Text type="danger" className="gaf-text-xxs">
                                  {hc.error}
                                </Typography.Text>
                              )}
                            </>
                          )}
                        </Space>
                      </Card>
                    </Col>
                  );
                })}
              </Row>
            )}
          </Spin>
        </Card>

        {/* ADB 命令面板 */}
        <Card
          title={
            <div className="gaf-toolbar-group">
              <CodeOutlined />
              <span>{t('emulator.title_adb_panel')}</span>
            </div>
          }
          className="gaf-mb-lg"
        >
          <Space orientation="vertical" className="gaf-w-full" size="middle">
            <div className="gaf-toolbar">
              <Input
                placeholder={t('emulator.placeholder_adb_serial')}
                value={adbSerial}
                onChange={(e) => setAdbSerial(e.target.value)}
                style={{ width: 240 }}
                allowClear
              />
              <Input
                placeholder={t('emulator.placeholder_adb_command')}
                value={adbCommand}
                onChange={(e) => setAdbCommand(e.target.value)}
                style={{ width: 360 }}
                allowClear
                onPressEnter={handleAdbSend}
              />
              <Button type="primary" icon={<CodeOutlined />} onClick={handleAdbSend} loading={adbRunning}>
                {t('emulator.btn_send')}
              </Button>
            </div>
            {adbResult && (
              <Card size="small" style={{ background: token.colorBgLayout }}>
                <pre
                  className="gaf-m-0 gaf-text-xs gaf-font-mono gaf-whitespace-pre-wrap gaf-overflow-auto"
                  style={{ wordBreak: 'break-all', maxHeight: 200 }}
                >
                  {adbResult}
                </pre>
              </Card>
            )}
          </Space>
        </Card>

        {/* 已注册设备 */}
        <Card
          title={
            <div className="gaf-toolbar-group">
              <span>{t('emulator.title_registered')}</span>
              <Tag color="blue">{t('emulator.registered_count', { count: emulatorDevices.length })}</Tag>
            </div>
          }
          className="gaf-mb-lg"
        >
          <Spin spinning={loading}>
            {emulatorDevices.length === 0 ? (
              <Empty description={t('emulator.empty_registered')}>
                <Typography.Text type="secondary">{t('emulator.empty_registered_hint')}</Typography.Text>
              </Empty>
            ) : (
              <Row gutter={[12, 12]}>
                {emulatorDevices.map((device: Device) => (
                  <Col key={device.id} xs={24} sm={12} md={8} lg={6}>
                    <DeviceCard device={device} onSelect={() => {}} onTestScreenshot={() => {}} />
                  </Col>
                ))}
              </Row>
            )}
          </Spin>
        </Card>

        <Modal
          title={t('emulator.modal_config_title', { name: configTarget?.name || '' })}
          open={configModalOpen}
          onOk={handleConfigSave}
          onCancel={() => setConfigModalOpen(false)}
          confirmLoading={configLoading}
          width={520}
        >
          <Form
            form={configForm}
            layout="vertical"
            initialValues={{
              resolution: '1280x720',
              dpi: 240,
              cpu_count: 4,
              memory_mb: 4096,
            }}
          >
            <Form.Item
              label={t('emulator.lbl_resolution')}
              name="resolution"
              rules={[{ required: true, message: t('emulator.msg_resolution_required') }]}
            >
              <Select
                options={[
                  { value: '1280x720', label: t('emulator.resolution_hd') },
                  { value: '1920x1080', label: t('emulator.resolution_fhd') },
                  { value: '2560x1440', label: t('emulator.resolution_2k') },
                  { value: '3840x2160', label: t('emulator.resolution_4k') },
                ]}
              />
            </Form.Item>
            <Form.Item
              label={t('emulator.lbl_dpi')}
              name="dpi"
              rules={[{ required: true, message: t('emulator.msg_dpi_required') }]}
            >
              <Select
                options={[
                  { value: 120, label: t('emulator.dpi_120') },
                  { value: 160, label: t('emulator.dpi_160') },
                  { value: 240, label: t('emulator.dpi_240') },
                  { value: 320, label: t('emulator.dpi_320') },
                  { value: 480, label: t('emulator.dpi_480') },
                ]}
              />
            </Form.Item>
            <Form.Item
              label={t('emulator.lbl_cpu_count')}
              name="cpu_count"
              rules={[{ required: true, message: t('emulator.msg_cpu_required') }]}
            >
              <InputNumber min={1} max={16} className="gaf-w-full" />
            </Form.Item>
            <Form.Item
              label={t('emulator.lbl_memory')}
              name="memory_mb"
              rules={[{ required: true, message: t('emulator.msg_memory_required') }]}
            >
              <Select
                options={[
                  { value: 2048, label: t('emulator.memory_2gb') },
                  { value: 4096, label: t('emulator.memory_4gb') },
                  { value: 8192, label: t('emulator.memory_8gb') },
                  { value: 16384, label: t('emulator.memory_16gb') },
                ]}
              />
            </Form.Item>
          </Form>
        </Modal>
      </div>
    </PageWrapper>
  );
}

export default EmulatorManagementPage;
