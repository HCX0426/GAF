/**
 * device center page
 * device card grid / table view, filter panel, search, device discovery, group management
 * Phase 3 added: emulator scan, window scan, manual add, test screenshot, lock, config to export
 */
import { useEffect, useState, useMemo, useCallback, useRef } from 'react';
import {
  Row,
  Col,
  Input,
  Select,
  Button,
  Space,
  Typography,
  Segmented,
  Table,
  Tag,
  App,
  Card,
  Empty,
  Skeleton,
  Modal,
  Tabs,
  Alert,
} from 'antd';
import {
  SearchOutlined,
  ReloadOutlined,
  AppstoreOutlined,
  UnorderedListOutlined,
  PlusOutlined,
  ScanOutlined,
  WindowsOutlined,
  AndroidOutlined,
  ThunderboltOutlined,
  VideoCameraOutlined,
} from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';
import DeviceCard from '@/components/Device/DeviceCard';
import DeviceDetailPanel from '@/components/Device/DeviceDetailPanel';
import DeviceGroupComponent from '@/components/Device/DeviceGroup';
import ScreenshotTester from '@/components/Device/ScreenshotTester';
import ConfigWizard from '@/components/Device/ConfigWizard';
import DeviceBenchmark from '@/components/Device/DeviceBenchmark';
import ScanModal from '@/components/Device/ScanModal';
import PageWrapper from '@/components/Common/PageWrapper';
import { useDeviceStore } from '@/stores/useDeviceStore';
import { registerDevice as apiRegisterDevice } from '@/api/devices';
import { wsClient } from '@/websocket/client';
import type { Device, DeviceStatus, DeviceType, DeviceRegisterParams } from '@/types/models';
import { useTranslation } from '@/i18n';

/** view mode */
type ViewMode = 'grid' | 'table';

/** device status text mapping — i18n keys */
const STATUS_LABEL_KEY: Record<string, string> = {
  online: 'deviceCenter.status_online',
  offline: 'deviceCenter.status_offline',
  busy: 'deviceCenter.status_busy',
  error: 'deviceCenter.status_error',
  locked: 'deviceCenter.status_locked',
};

/** device status color mapping */
const STATUS_COLOR_MAP: Record<string, string> = {
  online: 'green',
  offline: 'default',
  busy: 'orange',
  error: 'red',
  locked: 'purple',
};

/** device type text mapping — i18n keys */
const TYPE_LABEL_KEY: Record<string, string> = {
  windows: 'deviceCenter.type_windows',
  emulator: 'deviceCenter.type_emulator',
};

/** device type icon text mapping */
const TYPE_EMOJI_MAP: Record<string, string> = {
  windows: '🖥️',
  emulator: '📺',
};

/**
 * device center page
 * includes filter panel, grid / table view, search, send discovery, group management
 * Phase 3: scan, manual add, test screenshot, lock
 */
export function DeviceCenterPage() {
  const { devices, loading, fetchDevices, fetchGroups } = useDeviceStore();
  const { message } = App.useApp();
  const t = useTranslation();

  const [viewMode, setViewMode] = useState<ViewMode>('grid');
  const [searchText, setSearchText] = useState('');
  const [filterType, setFilterType] = useState<DeviceType | 'all'>('all');
  const [filterStatus, setFilterStatus] = useState<DeviceStatus | 'all'>('all');
  const [selectedGroupId, setSelectedGroupId] = useState<number | null>(null);
  const [selectedDevice, setSelectedDevice] = useState<Device | null>(null);
  const [detailOpen, setDetailOpen] = useState(false);

  const [addDeviceOpen, setAddDeviceOpen] = useState(false);
  const [addTab, setAddTab] = useState('android');
  const [adbAddress, setAdbAddress] = useState('');
  const [windowHwnd, setWindowHwnd] = useState('');
  const [deviceName, setDeviceName] = useState('');
  const [adding, setAdding] = useState(false);

  const [screenshotDevice, setScreenshotDevice] = useState<Device | null>(null);
  const [screenshotOpen, setScreenshotOpen] = useState(false);

  const [configWizardDevice, setConfigWizardDevice] = useState<{ id: number; type: 'android' | 'windows' } | null>(
    null,
  );
  const [configWizardOpen, setConfigWizardOpen] = useState(false);
  const [benchmarkDevice, setBenchmarkDevice] = useState<{ id: number; name: string } | null>(null);
  const [benchmarkOpen, setBenchmarkOpen] = useState(false);
  const [emulatorScanOpen, setEmulatorScanOpen] = useState(false);
  const [windowScanOpen, setWindowScanOpen] = useState(false);

  /**
   * TD-014: per-device screenshot stream filter.
   * Empty array = stream all devices (backward compatible). When non-empty,
   * only frames for the selected DB Device.id values are requested; the
   * backend consumer translates these to agent-side device_id strings.
   */
  const [streamDeviceIds, setStreamDeviceIds] = useState<number[]>([]);

  /** Screenshot preview cache: deviceId -> base64 string (via WebSocket) */
  const [screenshotMap, setScreenshotMap] = useState<Record<number, string>>({});

  /** WebSocket screenshot stream subscription */
  useEffect(() => {
    const handleScreenshotFrame = (data: Record<string, unknown>) => {
      const deviceId = data.device_id as number | undefined;
      const imageBase64 = data.image_base64 as string | undefined;
      if (deviceId && imageBase64) {
        setScreenshotMap((prev) => ({ ...prev, [deviceId]: imageBase64 }));
      }
    };

    wsClient.onMessage('screenshot_frame', handleScreenshotFrame);
    return () => {
      wsClient.offMessage('screenshot_frame', handleScreenshotFrame);
    };
  }, []);

  /**
   * Start the global screenshot stream once an online device with a connected
   * agent is available. The agent only sends frames for the active device, so
   * the matching device card (by numeric device_id) will receive the thumbnail.
   *
   * TD-014: when `streamDeviceIds` is non-empty, only frames for the selected
   * DB Device.id values are requested. The backend consumer translates these
   * numeric ids to agent-side device_id strings.
   */
  const streamAgentIdRef = useRef<string | null>(null);
  useEffect(() => {
    const onlineWithAgent = (devices || []).find((d: Device) => d.status !== 'offline' && d.agent_info?.agent_id);
    const agentId = onlineWithAgent?.agent_info?.agent_id || null;
    streamAgentIdRef.current = agentId;
    if (agentId) {
      const payload: Record<string, unknown> = { agent_id: agentId };
      if (streamDeviceIds.length > 0) {
        payload.device_ids = streamDeviceIds;
      }
      wsClient.send('request_screenshot_stream', payload);
    }
    return () => {
      const currentAgentId = streamAgentIdRef.current;
      if (currentAgentId) {
        wsClient.send('stop_screenshot_stream', { agent_id: currentAgentId });
      }
    };
  }, [devices, streamDeviceIds]);

  /**
   * Manually restart the screenshot stream. Stops the current stream (if any),
   * clears the per-device frame cache so stale thumbnails don't linger, then
   * requests a fresh stream from the agent. Used when the stream appears stuck
   * or when the user wants to force a reconnect.
   */
  const handleRefreshStream = useCallback(() => {
    const agentId = streamAgentIdRef.current;
    if (!agentId) {
      message.warning(t('deviceCenter.msg_no_agent'));
      return;
    }
    wsClient.send('stop_screenshot_stream', { agent_id: agentId });
    setScreenshotMap({});
    // Brief delay so the agent processes the stop before the start arrives.
    setTimeout(() => {
      const payload: Record<string, unknown> = { agent_id: agentId };
      if (streamDeviceIds.length > 0) {
        payload.device_ids = streamDeviceIds;
      }
      wsClient.send('request_screenshot_stream', payload);
    }, 200);
    message.success(t('deviceCenter.msg_stream_refreshed'));
  }, [message, t, streamDeviceIds]);

  useEffect(() => {
    fetchDevices();
    fetchGroups();
  }, []);

  /** based on filter condition filter device */
  const filteredDevices = useMemo(() => {
    let result = devices || [];

    if (searchText) {
      const lower = searchText.toLowerCase();
      result = result.filter((d: Device) => d.name.toLowerCase().includes(lower));
    }

    if (filterType !== 'all') {
      result = result.filter((d: Device) => d.device_type === filterType);
    }

    if (filterStatus !== 'all') {
      if (filterStatus === 'locked') {
        result = result.filter((d: Device) => d.locked_by_username != null);
      } else {
        result = result.filter((d: Device) => d.status === filterStatus);
      }
    }

    if (selectedGroupId != null) {
      const groups = useDeviceStore.getState().groups;
      const group = groups?.find((g) => g.id === selectedGroupId);
      if (group?.devices) {
        const groupDeviceIds = new Set(group.devices);
        result = result.filter((d: Device) => groupDeviceIds.has(d.id));
      }
    }

    return result;
  }, [devices, searchText, filterType, filterStatus, selectedGroupId]);

  /** open device detail drawer */
  const handleSelectDevice = useCallback((device: Device) => {
    setSelectedDevice(device);
    setDetailOpen(true);
  }, []);

  /** close device detail drawer */
  const handleCloseDetail = useCallback(() => {
    setDetailOpen(false);
    setSelectedDevice(null);
  }, []);

  /** manual add device */
  const handleAddDevice = async () => {
    if (!deviceName.trim()) {
      message.warning(t('deviceCenter.msg_name_required'));
      return;
    }

    const params: DeviceRegisterParams = {
      name: deviceName.trim(),
      agent_type: addTab as 'android' | 'windows',
    };

    if (addTab === 'android') {
      if (!adbAddress.trim()) {
        message.warning(t('deviceCenter.msg_adb_required'));
        return;
      }
      params.adb_serial = adbAddress.trim();
    } else {
      if (!windowHwnd.trim()) {
        message.warning(t('deviceCenter.msg_hwnd_required'));
        return;
      }
      params.hwnd = windowHwnd.trim();
    }

    setAdding(true);
    try {
      await apiRegisterDevice(params);
      message.success(t('deviceCenter.msg_register_success'));
      setAddDeviceOpen(false);
      setDeviceName('');
      setAdbAddress('');
      setWindowHwnd('');
      fetchDevices();
    } catch {
      message.error(t('deviceCenter.msg_register_failed'));
    } finally {
      setAdding(false);
    }
  };

  /** open test screenshot */
  const handleTestScreenshot = useCallback((device: Device) => {
    setScreenshotDevice(device);
    setScreenshotOpen(true);
  }, []);

  /** close test screenshot */
  const handleCloseScreenshot = useCallback(() => {
    setScreenshotOpen(false);
    setScreenshotDevice(null);
  }, []);

  /** drag start: settings device ID to dataTransfer */
  const handleDragStart = (e: React.DragEvent, deviceId: number) => {
    e.dataTransfer.setData('text/plain', String(deviceId));
    e.dataTransfer.effectAllowed = 'move';
  };

  /** table column config */
  const columns: ColumnsType<Device> = [
    {
      title: t('deviceCenter.col_name'),
      dataIndex: 'name',
      key: 'name',
      width: 200,
      ellipsis: true,
      render: (name: string, record: Device) => (
        <Space>
          <span>{TYPE_EMOJI_MAP[record.device_type] || '🖥️'}</span>
          <Typography.Link onClick={() => handleSelectDevice(record)}>{name}</Typography.Link>
          {record.locked_by_username && (
            <Tag color="purple" style={{ fontSize: 10 }}>
              🔒 {record.locked_by_username}
            </Tag>
          )}
        </Space>
      ),
    },
    {
      title: t('deviceCenter.col_type'),
      dataIndex: 'device_type',
      key: 'device_type',
      width: 100,
      render: (dt: DeviceType) => <Tag>{t(TYPE_LABEL_KEY[dt] || dt)}</Tag>,
    },
    {
      title: t('deviceCenter.col_status'),
      dataIndex: 'status',
      key: 'status',
      width: 80,
      render: (s: DeviceStatus, record: Device) => {
        if (record.locked_by_username) {
          return <Tag color="purple">{t('deviceCenter.status_locked')}</Tag>;
        }
        return <Tag color={STATUS_COLOR_MAP[s]}>{t(STATUS_LABEL_KEY[s] || s)}</Tag>;
      },
    },
    {
      title: t('deviceCenter.col_resolution'),
      key: 'resolution',
      width: 130,
      render: (_: unknown, record: Device) =>
        record.resolution_width && record.resolution_height
          ? `${record.resolution_width}×${record.resolution_height}`
          : '-',
    },
    {
      title: t('deviceCenter.col_fps'),
      dataIndex: 'screenshot_fps',
      key: 'fps',
      width: 70,
      render: (fps: number) => (fps > 0 ? `${fps.toFixed(0)} FPS` : '-'),
    },
    {
      title: t('deviceCenter.col_agent'),
      key: 'agent',
      width: 120,
      render: (_: unknown, record: Device) => (record.agent_info ? record.agent_info.hostname : '-'),
    },
    {
      title: t('deviceCenter.col_actions'),
      key: 'actions',
      width: 100,
      render: (_: unknown, record: Device) => (
        <Button
          size="small"
          type="link"
          onClick={(e) => {
            e.stopPropagation();
            handleTestScreenshot(record);
          }}
        >
          {t('deviceCenter.btn_test_screenshot')}
        </Button>
      ),
    },
  ];

  return (
    <PageWrapper>
      <div>
        {/* 顶部工具栏 */}
        <Card size="small" className="gaf-mb-lg">
          <Row gutter={[12, 12]} align="middle">
            <Col flex="auto">
              <div className="gaf-toolbar">
                <Input
                  placeholder={t('deviceCenter.search_placeholder')}
                  prefix={<SearchOutlined />}
                  value={searchText}
                  onChange={(e) => setSearchText(e.target.value)}
                  style={{ width: 240 }}
                  allowClear
                  name="device_search"
                  autoComplete="off"
                />
                <Select
                  value={filterType}
                  onChange={setFilterType}
                  style={{ width: 110 }}
                  options={[
                    { value: 'all', label: t('deviceCenter.filter_all_types') },
                    { value: 'windows', label: `🖥️ ${t('deviceCenter.type_windows')}` },
                    { value: 'emulator', label: `📺 ${t('deviceCenter.type_emulator')}` },
                  ]}
                />
                <Select
                  value={filterStatus}
                  onChange={setFilterStatus}
                  className="gaf-w-xs"
                  options={[
                    { value: 'all', label: t('deviceCenter.filter_all_status') },
                    { value: 'online', label: t('deviceCenter.status_online') },
                    { value: 'offline', label: t('deviceCenter.status_offline') },
                    { value: 'busy', label: t('deviceCenter.status_busy') },
                    { value: 'error', label: t('deviceCenter.status_error') },
                    { value: 'locked', label: t('deviceCenter.status_locked') },
                  ]}
                />
                <Button icon={<ScanOutlined />} onClick={() => setEmulatorScanOpen(true)}>
                  {t('deviceCenter.btn_scan_emulator')}
                </Button>
                <Button icon={<WindowsOutlined />} onClick={() => setWindowScanOpen(true)}>
                  {t('deviceCenter.btn_scan_window')}
                </Button>
                <Button type="primary" icon={<PlusOutlined />} onClick={() => setAddDeviceOpen(true)}>
                  {t('deviceCenter.btn_add_device')}
                </Button>
                <Button
                  icon={<ThunderboltOutlined />}
                  onClick={() => {
                    const first =
                      (filteredDevices || []).find((d) => d.device_type === 'emulator') || filteredDevices?.[0];
                    if (first) {
                      setBenchmarkDevice({ id: first.id, name: first.name });
                      setBenchmarkOpen(true);
                    } else {
                      message.warning(t('deviceCenter.msg_no_devices_benchmark'));
                    }
                  }}
                >
                  {t('deviceCenter.btn_benchmark')}
                </Button>
                <Button
                  icon={<ReloadOutlined />}
                  onClick={() => {
                    fetchDevices();
                    fetchGroups();
                  }}
                >
                  {t('deviceCenter.btn_refresh')}
                </Button>
                <Button icon={<VideoCameraOutlined />} onClick={handleRefreshStream}>
                  {t('deviceCenter.btn_refresh_stream')}
                </Button>
                <Select
                  mode="multiple"
                  allowClear
                  placeholder={t('deviceCenter.stream_filter_placeholder')}
                  value={streamDeviceIds}
                  onChange={(vals: number[]) => setStreamDeviceIds(vals)}
                  style={{ minWidth: 220, maxWidth: 360 }}
                  maxTagCount="responsive"
                  aria-label={t('deviceCenter.stream_filter_label')}
                  options={(devices || []).map((d: Device) => ({
                    value: d.id,
                    label: `${TYPE_EMOJI_MAP[d.device_type] || ''} ${d.name}`,
                  }))}
                  notFoundContent={t('deviceCenter.empty')}
                />
                <Segmented
                  value={viewMode}
                  onChange={(val) => setViewMode(val as ViewMode)}
                  options={[
                    { value: 'grid', icon: <AppstoreOutlined /> },
                    { value: 'table', icon: <UnorderedListOutlined /> },
                  ]}
                />
              </div>
            </Col>
          </Row>
        </Card>

        <Row gutter={[16, 16]}>
          {/* 左侧筛选面板 */}
          <Col xs={24} sm={24} md={6} lg={5} xl={4}>
            <Card size="small" title={t('deviceCenter.group_title')}>
              <DeviceGroupComponent onSelectGroup={setSelectedGroupId} selectedGroupId={selectedGroupId} />
            </Card>
          </Col>

          {/* 右侧内容区 */}
          <Col xs={24} sm={24} md={18} lg={19} xl={20}>
            {loading ? (
              <div className="gaf-p-xl">
                <Skeleton active paragraph={{ rows: 6 }} />
                <Skeleton active paragraph={{ rows: 6 }} className="gaf-mt-lg" />
              </div>
            ) : (
              <>
                {filteredDevices.length === 0 ? (
                  <Card>
                    <Empty description={t('deviceCenter.empty')}>
                      <Space orientation="vertical" size="small">
                        <Typography.Text type="secondary">{t('deviceCenter.empty_hint')}</Typography.Text>
                        <div className="gaf-toolbar">
                          <Button type="primary" icon={<ScanOutlined />} onClick={() => setEmulatorScanOpen(true)}>
                            {t('deviceCenter.btn_scan_emulator')}
                          </Button>
                          <Button icon={<WindowsOutlined />} onClick={() => setWindowScanOpen(true)}>
                            {t('deviceCenter.btn_scan_window')}
                          </Button>
                        </div>
                      </Space>
                    </Empty>
                  </Card>
                ) : viewMode === 'grid' ? (
                  /* grid view */
                  <Row
                    gutter={[12, 12]}
                    aria-live="polite"
                    aria-atomic="true"
                    aria-label={t('deviceCenter.screenshot_area_label')}
                  >
                    {filteredDevices.map((device: Device) => (
                      <Col key={device.id} xs={24} sm={12} md={8} lg={6} xl={6}>
                        <div draggable onDragStart={(e) => handleDragStart(e, device.id)}>
                          <DeviceCard
                            device={device}
                            onSelect={handleSelectDevice}
                            onTestScreenshot={handleTestScreenshot}
                            selected={selectedDevice?.id === device.id}
                            screenshotFrame={screenshotMap[device.id] || null}
                          />
                        </div>
                      </Col>
                    ))}
                  </Row>
                ) : (
                  /* table view */
                  <Card>
                    <Table
                      columns={columns}
                      dataSource={filteredDevices || []}
                      rowKey="id"
                      size="small"
                      pagination={{
                        pageSize: 20,
                        showSizeChanger: true,
                        showTotal: (total) => t('deviceCenter.total_devices', { count: total }),
                      }}
                      onRow={(record) => ({
                        onClick: () => handleSelectDevice(record),
                        style: { cursor: 'pointer' },
                      })}
                    />
                  </Card>
                )}
              </>
            )}
          </Col>
        </Row>

        {/* 设备详情抽屉 */}
        <DeviceDetailPanel
          device={selectedDevice ? (devices || []).find((d) => d.id === selectedDevice.id) || selectedDevice : null}
          open={detailOpen}
          onClose={handleCloseDetail}
          onDelete={() => {
            fetchDevices();
          }}
        />

        {/* 设备详情抽屉 */}
        <Modal
          title={t('deviceCenter.modal_add_title')}
          open={addDeviceOpen}
          onCancel={() => {
            setAddDeviceOpen(false);
            setDeviceName('');
            setAdbAddress('');
            setWindowHwnd('');
          }}
          onOk={handleAddDevice}
          confirmLoading={adding}
          okText={t('deviceCenter.btn_register')}
          width={500}
          destroyOnHidden
        >
          <Tabs
            activeKey={addTab}
            onChange={setAddTab}
            items={[
              {
                key: 'android',
                label: (
                  <>
                    <AndroidOutlined /> {t('deviceCenter.tab_android')}
                  </>
                ),
                children: (
                  <Space orientation="vertical" className="gaf-w-full" size="middle">
                    <div>
                      <Typography.Text strong>{t('deviceCenter.lbl_device_name')}</Typography.Text>
                      <Input
                        placeholder={t('deviceCenter.placeholder_device_name_android')}
                        value={deviceName}
                        onChange={(e) => setDeviceName(e.target.value)}
                      />
                    </div>
                    <div>
                      <Typography.Text strong>{t('deviceCenter.lbl_adb_address')}</Typography.Text>
                      <Input
                        placeholder="192.168.1.100:5555"
                        value={adbAddress}
                        onChange={(e) => setAdbAddress(e.target.value)}
                      />
                    </div>
                    <Alert type="info" title={t('deviceCenter.alert_adb_format')} className="gaf-text-xs" />
                  </Space>
                ),
              },
              {
                key: 'windows',
                label: (
                  <>
                    <WindowsOutlined /> {t('deviceCenter.tab_windows')}
                  </>
                ),
                children: (
                  <Space orientation="vertical" className="gaf-w-full" size="middle">
                    <div>
                      <Typography.Text strong>{t('deviceCenter.lbl_device_name')}</Typography.Text>
                      <Input
                        placeholder={t('deviceCenter.placeholder_device_name_windows')}
                        value={deviceName}
                        onChange={(e) => setDeviceName(e.target.value)}
                      />
                    </div>
                    <div>
                      <Typography.Text strong>{t('deviceCenter.lbl_window_hwnd')}</Typography.Text>
                      <Input
                        placeholder={t('deviceCenter.placeholder_window_hwnd')}
                        value={windowHwnd}
                        onChange={(e) => setWindowHwnd(e.target.value)}
                        name="window_hwnd"
                        autoComplete="off"
                      />
                    </div>
                    <Alert type="info" title={t('deviceCenter.alert_scan_window')} className="gaf-text-xs" />
                  </Space>
                ),
              },
            ]}
          />
        </Modal>

        {/* 测试截图弹窗 */}
        {screenshotDevice && (
          <ScreenshotTester
            deviceId={screenshotDevice.id}
            deviceName={screenshotDevice.name}
            open={screenshotOpen}
            onClose={handleCloseScreenshot}
          />
        )}

        {/* 配置向导 */}
        {configWizardDevice && (
          <ConfigWizard
            deviceId={configWizardDevice.id}
            deviceType={configWizardDevice.type}
            open={configWizardOpen}
            onClose={() => {
              setConfigWizardOpen(false);
              setConfigWizardDevice(null);
              fetchDevices();
            }}
          />
        )}

        {benchmarkDevice && (
          <DeviceBenchmark
            deviceId={benchmarkDevice.id}
            deviceName={benchmarkDevice.name}
            visible={benchmarkOpen}
            onClose={() => {
              setBenchmarkOpen(false);
              setBenchmarkDevice(null);
            }}
          />
        )}

        {/* Scan Modal - Android/Emulator */}
        <ScanModal
          mode="android"
          open={emulatorScanOpen}
          onClose={() => setEmulatorScanOpen(false)}
          onRegistered={() => {
            fetchDevices();
            setEmulatorScanOpen(false);
          }}
        />

        {/* Scan Modal - Windows */}
        <ScanModal
          mode="windows"
          open={windowScanOpen}
          onClose={() => setWindowScanOpen(false)}
          onRegistered={() => {
            fetchDevices();
            setWindowScanOpen(false);
          }}
        />
      </div>
    </PageWrapper>
  );
}

export default DeviceCenterPage;
