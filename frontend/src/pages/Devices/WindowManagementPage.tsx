/**
 * window management page
 * includes: screenshot method config, input method config, after background screenshot,
 * registered window device, window discovery.
 *
 * v3 §2.8.2-2.8.3: shows "继承/自定义" tags (from resolved_methods) and provides
 * a test Modal to preview screenshot + try input methods before saving.
 */
import { useEffect, useMemo, useCallback, useState } from 'react';
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
  Divider,
  Table,
  Select,
  Switch,
  Button,
  Tooltip,
  Modal,
  Image,
} from 'antd';
import { WindowsOutlined, SaveOutlined, SettingOutlined, ExperimentOutlined } from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';
import DeviceCard from '@/components/Device/DeviceCard';
import PageWrapper from '@/components/Common/PageWrapper';
import { useDeviceStore } from '@/stores/useDeviceStore';
import { patchDevice, requestScreenshot } from '@/api/devices';
import type { ControlMode, Device } from '@/types/models';
import { useTranslation } from '@/i18n';

/** Screenshot method options — i18n keys. v3 §2.8.1: 'auto' inherits from GameProfile. */
const SCREENSHOT_METHOD_KEYS: Array<{ value: string; labelKey: string }> = [
  { value: 'auto', labelKey: 'windowMgmt.method_auto' },
  { value: 'wgc', labelKey: 'windowMgmt.method_wgc' },
  { value: 'bitblt', labelKey: 'windowMgmt.method_bitblt' },
  { value: 'printwindow', labelKey: 'windowMgmt.method_printwindow' },
  { value: 'dxgi', labelKey: 'windowMgmt.method_dxgi' },
  { value: 'gdi', labelKey: 'windowMgmt.method_gdi' },
];

/** Input method options — i18n keys. v3 §2.8.1: 'auto' inherits from GameProfile. */
const INPUT_METHOD_KEYS: Array<{ value: string; labelKey: string }> = [
  { value: 'auto', labelKey: 'windowMgmt.method_auto' },
  { value: 'sendinput', labelKey: 'windowMgmt.method_sendinput' },
  { value: 'postmessage', labelKey: 'windowMgmt.method_postmessage' },
  { value: 'sendmessage', labelKey: 'windowMgmt.method_sendmessage' },
];

/** Control mode options — i18n keys. v3 §2.8.1: 'auto' inherits from GameProfile. */
const CONTROL_MODE_KEYS: Array<{ value: ControlMode; labelKey: string; color: string }> = [
  { value: 'auto', labelKey: 'windowMgmt.control_mode_auto', color: 'default' },
  { value: 'foreground', labelKey: 'windowMgmt.control_mode_foreground', color: 'green' },
  { value: 'background', labelKey: 'windowMgmt.control_mode_background', color: 'blue' },
  { value: 'pseudo_background', labelKey: 'windowMgmt.control_mode_pseudo_background', color: 'orange' },
];

export function WindowManagementPage() {
  const { message } = App.useApp();
  const { devices, loading, fetchDevices } = useDeviceStore();
  const t = useTranslation();
  const [savingId, setSavingId] = useState<number | null>(null);
  const [editData, setEditData] = useState<
    Record<
      number,
      {
        control_mode: ControlMode;
        screenshot_method: string;
        input_method: string;
        background_screenshot: boolean;
      }
    >
  >({});

  // v3 §2.8.3: test Modal state — preview screenshot + try methods before saving
  const [testDevice, setTestDevice] = useState<Device | null>(null);
  const [testScreenshot, setTestScreenshot] = useState<string | null>(null);
  const [testLoading, setTestLoading] = useState(false);

  const screenshotMethods = useMemo(
    () => SCREENSHOT_METHOD_KEYS.map((m) => ({ value: m.value, label: t(m.labelKey) })),
    [t],
  );
  const inputMethods = useMemo(() => INPUT_METHOD_KEYS.map((m) => ({ value: m.value, label: t(m.labelKey) })), [t]);

  const controlModes = useMemo(
    () => CONTROL_MODE_KEYS.map((m) => ({ value: m.value, label: t(m.labelKey), color: m.color })),
    [t],
  );

  // P-011 Spec A: build per-device method options with `disabled` flag for
  // methods blocked in multi-game parallel mode. 'auto' is always allowed
  // (resolved at runtime; backend safety_gate enforces the actual whitelist).
  // Non-auto options whose lowercase value is not in `allowedList` get
  // `disabled: true` + a native title tooltip explaining why.
  const buildMethodOptions = useCallback(
    (
      allMethods: Array<{ value: string; label: string }>,
      device: Device,
      allowedList: string[] | null | undefined,
    ): Array<{ value: string; label: string; disabled?: boolean; title?: string }> => {
      if (!device.multi_game_restricted || !allowedList) {
        return allMethods;
      }
      const allowed = new Set(allowedList.map((v) => v.toLowerCase()));
      const blockedHint = t('dashboard.blocked_in_multi_game');
      return allMethods.map((m) => {
        if (m.value === 'auto') {
          return m;
        }
        const isBlocked = !allowed.has(m.value.toLowerCase());
        return {
          ...m,
          disabled: isBlocked,
          title: isBlocked ? blockedHint : undefined,
        };
      });
    },
    [t],
  );

  useEffect(() => {
    fetchDevices();
  }, [fetchDevices]);

  const windowDevices = useMemo(() => (devices || []).filter((d: Device) => d.device_type === 'windows'), [devices]);

  useEffect(() => {
    if (windowDevices.length > 0) {
      const initial: Record<
        number,
        { control_mode: ControlMode; screenshot_method: string; input_method: string; background_screenshot: boolean }
      > = {};
      windowDevices.forEach((d) => {
        initial[d.id] = {
          // v3 §2.8.1: default to 'auto' (inherit from GameProfile) instead of pseudo_background
          control_mode: d.control_mode || 'auto',
          screenshot_method: d.screenshot_method || 'auto',
          input_method: d.input_method || 'auto',
          background_screenshot: (d.extra_info as Record<string, unknown>)?.background_screenshot === true || false,
        };
      });
      setEditData((prev) => ({ ...initial, ...prev }));
    }
  }, [windowDevices]);

  const handleSave = useCallback(
    async (deviceId: number) => {
      const data = editData[deviceId];
      if (!data) return;
      setSavingId(deviceId);
      try {
        await patchDevice(deviceId, {
          control_mode: data.control_mode,
          screenshot_method: data.screenshot_method,
          input_method: data.input_method,
          extra_info: {
            ...(windowDevices.find((d) => d.id === deviceId)?.extra_info || {}),
            background_screenshot: data.background_screenshot,
          },
        });
        message.success(t('windowMgmt.msg_save_success'));
        fetchDevices();
      } catch {
        message.error(t('windowMgmt.msg_save_failed'));
      } finally {
        setSavingId(null);
      }
    },
    [editData, windowDevices, fetchDevices, message, t],
  );

  // v3 §2.8.3: open test Modal and capture an initial screenshot preview.
  // ScreenshotResponse.screenshot_base64 is a raw base64 string (no data: prefix),
  // so we prepend the data URL prefix for <Image src>.
  const buildScreenshotSrc = (b64: string | null | undefined): string | null =>
    b64 ? `data:image/png;base64,${b64}` : null;

  const handleOpenTest = useCallback(async (device: Device) => {
    setTestDevice(device);
    setTestScreenshot(null);
    setTestLoading(true);
    try {
      const res = await requestScreenshot(device.id);
      setTestScreenshot(buildScreenshotSrc(res.screenshot_base64));
    } catch {
      // Ignore — user can retry via the capture button in the modal
    } finally {
      setTestLoading(false);
    }
  }, []);

  const handleTestScreenshot = useCallback(async () => {
    if (!testDevice) return;
    setTestLoading(true);
    try {
      const res = await requestScreenshot(testDevice.id);
      setTestScreenshot(buildScreenshotSrc(res.screenshot_base64));
    } catch {
      message.error(t('windowMgmt.msg_test_screenshot_failed'));
    } finally {
      setTestLoading(false);
    }
  }, [testDevice, message, t]);

  // v3 §2.8.2: render inheritance tag for a device field
  const renderInheritanceTag = (device: Device, field: 'screenshot_method' | 'input_method' | 'control_mode') => {
    const ownValue = device[field];
    const resolved = device.resolved_methods?.[field];
    const isAuto = ownValue === 'auto' || ownValue === '' || ownValue == null;
    if (isAuto && device.game_profile) {
      // 'auto' + has GameProfile → inherited
      return (
        <Tooltip
          title={
            resolved ? `${t('windowMgmt.inherited_from_profile')}: ${resolved}` : t('windowMgmt.inherited_from_profile')
          }
        >
          <Tag color="purple" className="gaf-ml-1">
            {t('windowMgmt.tag_inherited')}
            {resolved ? `: ${resolved}` : ''}
          </Tag>
        </Tooltip>
      );
    }
    if (isAuto) {
      // 'auto' + no GameProfile → platform picks at runtime
      return (
        <Tooltip title={t('windowMgmt.tooltip_auto_no_profile')}>
          <Tag color="default" className="gaf-ml-1">
            {t('windowMgmt.tag_auto_platform')}
          </Tag>
        </Tooltip>
      );
    }
    // concrete value → custom override
    return (
      <Tag color="gold" className="gaf-ml-1">
        {t('windowMgmt.tag_custom')}: {ownValue}
      </Tag>
    );
  };

  const configColumns: ColumnsType<Device> = [
    {
      title: t('windowMgmt.col_name'),
      dataIndex: 'name',
      key: 'name',
      width: 200,
      ellipsis: true,
    },
    {
      title: t('windowMgmt.col_resolution'),
      key: 'resolution',
      width: 120,
      render: (_: unknown, rcd: Device) => {
        const w = rcd.resolution_width;
        const h = rcd.resolution_height;
        return w && h ? `${w}×${h}` : '-';
      },
    },
    {
      title: t('windowMgmt.col_control_mode'),
      key: 'control_mode',
      width: 160,
      render: (_: unknown, rcd: Device) => (
        <Select
          data-testid="control-mode-select"
          value={editData[rcd.id]?.control_mode}
          onChange={(val) =>
            setEditData((prev) => ({
              ...prev,
              [rcd.id]: { ...prev[rcd.id], control_mode: val as ControlMode },
            }))
          }
          options={controlModes.map((m) => ({
            value: m.value,
            label: <Tag color={m.color}>{m.label}</Tag>,
          }))}
          placeholder={t('windowMgmt.placeholder_control_mode')}
          className="gaf-w-full"
          size="small"
          labelRender={(props) => {
            const selected = controlModes.find((m) => m.value === props.value);
            return selected ? <Tag color={selected.color}>{selected.label}</Tag> : props.value;
          }}
        />
      ),
    },
    {
      title: (
        <Tooltip title={t('windowMgmt.tooltip_screenshot_override')}>
          <span>{t('windowMgmt.col_screenshot_method')}</span>
        </Tooltip>
      ),
      key: 'screenshot_method',
      width: 180,
      render: (_: unknown, rcd: Device) => (
        <Select
          value={editData[rcd.id]?.screenshot_method || undefined}
          onChange={(val) =>
            setEditData((prev) => ({
              ...prev,
              [rcd.id]: { ...prev[rcd.id], screenshot_method: val },
            }))
          }
          options={buildMethodOptions(screenshotMethods, rcd, rcd.allowed_screenshot_methods)}
          placeholder={t('windowMgmt.placeholder_screenshot')}
          allowClear
          className="gaf-w-full"
          size="small"
        />
      ),
    },
    {
      title: (
        <Tooltip title={t('windowMgmt.tooltip_input_override')}>
          <span>{t('windowMgmt.col_input_method')}</span>
        </Tooltip>
      ),
      key: 'input_method',
      width: 180,
      render: (_: unknown, rcd: Device) => (
        <Select
          value={editData[rcd.id]?.input_method || undefined}
          onChange={(val) =>
            setEditData((prev) => ({
              ...prev,
              [rcd.id]: { ...prev[rcd.id], input_method: val },
            }))
          }
          options={buildMethodOptions(inputMethods, rcd, rcd.allowed_input_methods)}
          placeholder={t('windowMgmt.placeholder_input')}
          allowClear
          className="gaf-w-full"
          size="small"
        />
      ),
    },
    {
      title: t('windowMgmt.col_background_screenshot'),
      key: 'background_screenshot',
      width: 100,
      align: 'center',
      render: (_: unknown, rcd: Device) => (
        <Tooltip title={t('windowMgmt.tooltip_background')}>
          <Switch
            checked={editData[rcd.id]?.background_screenshot || false}
            onChange={(val) =>
              setEditData((prev) => ({
                ...prev,
                [rcd.id]: { ...prev[rcd.id], background_screenshot: val },
              }))
            }
            size="small"
          />
        </Tooltip>
      ),
    },
    {
      title: t('windowMgmt.col_action'),
      key: 'action',
      width: 120,
      align: 'center',
      render: (_: unknown, rcd: Device) => (
        <Space size="small">
          <Button
            type="primary"
            size="small"
            icon={<SaveOutlined />}
            loading={savingId === rcd.id}
            onClick={() => handleSave(rcd.id)}
            aria-label="保存窗口配置"
          />
          <Tooltip title={t('windowMgmt.btn_test_methods')}>
            <Button
              size="small"
              icon={<ExperimentOutlined />}
              onClick={() => handleOpenTest(rcd)}
              aria-label={t('windowMgmt.btn_test_methods')}
            />
          </Tooltip>
        </Space>
      ),
    },
  ];

  // v3 §2.8.2: inheritance status column — shows resolved values per field
  const inheritanceColumns: ColumnsType<Device> = [
    {
      title: t('windowMgmt.col_name'),
      dataIndex: 'name',
      key: 'name',
      width: 200,
      ellipsis: true,
    },
    {
      title: t('windowMgmt.col_game_profile'),
      key: 'game_profile',
      width: 160,
      render: (_: unknown, rcd: Device) =>
        rcd.game_profile_detail ? (
          <Tag color="purple">{rcd.game_profile_detail.game_name}</Tag>
        ) : rcd.game_profile ? (
          <Tag color="purple">#{rcd.game_profile}</Tag>
        ) : (
          <Tag>{t('windowMgmt.no_profile')}</Tag>
        ),
    },
    {
      title: t('windowMgmt.col_resolved_screenshot'),
      key: 'resolved_screenshot',
      width: 200,
      render: (_: unknown, rcd: Device) => (
        <Space orientation="vertical" size={0}>
          <Typography.Text className="gaf-text-xs">{rcd.screenshot_method || 'auto'}</Typography.Text>
          {renderInheritanceTag(rcd, 'screenshot_method')}
        </Space>
      ),
    },
    {
      title: t('windowMgmt.col_resolved_input'),
      key: 'resolved_input',
      width: 200,
      render: (_: unknown, rcd: Device) => (
        <Space orientation="vertical" size={0}>
          <Typography.Text className="gaf-text-xs">{rcd.input_method || 'auto'}</Typography.Text>
          {renderInheritanceTag(rcd, 'input_method')}
        </Space>
      ),
    },
    {
      title: t('windowMgmt.col_resolved_control_mode'),
      key: 'resolved_control_mode',
      width: 200,
      render: (_: unknown, rcd: Device) => (
        <Space orientation="vertical" size={0}>
          <Typography.Text className="gaf-text-xs">{rcd.control_mode || 'auto'}</Typography.Text>
          {renderInheritanceTag(rcd, 'control_mode')}
        </Space>
      ),
    },
  ];

  return (
    <PageWrapper>
      <Card
        title={
          <div className="gaf-toolbar-group">
            <SettingOutlined />
            <span>{t('windowMgmt.title_config')}</span>
            <Tag color="blue">{t('windowMgmt.window_count', { count: windowDevices.length })}</Tag>
          </div>
        }
        className="gaf-mb-lg"
      >
        <Spin spinning={loading}>
          {windowDevices.length === 0 ? (
            <Empty description={t('windowMgmt.empty')}>
              <Typography.Text type="secondary">{t('windowMgmt.empty_hint')}</Typography.Text>
            </Empty>
          ) : (
            <Table
              rowKey="id"
              columns={configColumns}
              dataSource={windowDevices}
              size="small"
              pagination={false}
              scroll={{ x: 960 }}
            />
          )}
        </Spin>
      </Card>

      <Card
        title={
          <div className="gaf-toolbar-group">
            <span>{t('windowMgmt.title_registered')}</span>
            <Tag color="blue">{t('windowMgmt.registered_count', { count: windowDevices.length })}</Tag>
          </div>
        }
        className="gaf-mb-lg"
      >
        <Spin spinning={loading}>
          {windowDevices.length === 0 ? (
            <Empty description={t('windowMgmt.empty')}>
              <Typography.Text type="secondary">{t('windowMgmt.empty_hint')}</Typography.Text>
            </Empty>
          ) : (
            <Row gutter={[12, 12]}>
              {windowDevices.map((device: Device) => (
                <Col key={device.id} xs={24} sm={12} md={8} lg={6}>
                  <DeviceCard device={device} onSelect={() => {}} onTestScreenshot={() => {}} />
                </Col>
              ))}
            </Row>
          )}
        </Spin>
      </Card>

      {/* v3 §2.8.2: inheritance status card — shows resolved values per device */}
      <Card
        title={
          <div className="gaf-toolbar-group">
            <span>{t('windowMgmt.title_inheritance')}</span>
            <Tag color="purple">{t('windowMgmt.inheritance_hint')}</Tag>
          </div>
        }
        className="gaf-mb-lg"
      >
        <Spin spinning={loading}>
          {windowDevices.length === 0 ? (
            <Empty description={t('windowMgmt.empty')} image={Empty.PRESENTED_IMAGE_SIMPLE} />
          ) : (
            <Table
              rowKey="id"
              columns={inheritanceColumns}
              dataSource={windowDevices}
              size="small"
              pagination={false}
              scroll={{ x: 'max-content' }}
            />
          )}
        </Spin>
      </Card>

      <Divider />

      {/* v3 §2.8.3: test Modal — screenshot preview + method dropdowns */}
      <Modal
        open={testDevice !== null}
        title={
          testDevice ? `${t('windowMgmt.test_modal_title')} — ${testDevice.name}` : t('windowMgmt.test_modal_title')
        }
        onCancel={() => {
          setTestDevice(null);
          setTestScreenshot(null);
        }}
        footer={[
          <Button
            key="close"
            onClick={() => {
              setTestDevice(null);
              setTestScreenshot(null);
            }}
          >
            {t('windowMgmt.btn_close')}
          </Button>,
          <Button
            key="capture"
            type="primary"
            icon={<WindowsOutlined />}
            loading={testLoading}
            onClick={handleTestScreenshot}
          >
            {t('windowMgmt.btn_capture_screenshot')}
          </Button>,
        ]}
        width={640}
        destroyOnHidden
      >
        {testDevice && (
          <div>
            <div className="gaf-toolbar gaf-mb-md">
              <Tag color={testDevice.status === 'online' ? 'green' : 'default'}>{testDevice.status}</Tag>
              {testDevice.game_profile_detail && <Tag color="purple">{testDevice.game_profile_detail.game_name}</Tag>}
              <Typography.Text type="secondary" className="gaf-text-xs">
                {t('windowMgmt.test_modal_hint')}
              </Typography.Text>
            </div>
            <Spin spinning={testLoading}>
              {testScreenshot ? (
                <Image src={testScreenshot} alt="screenshot" width="100%" className="gaf-mb-md" />
              ) : (
                <Empty
                  description={t('windowMgmt.test_no_screenshot')}
                  image={Empty.PRESENTED_IMAGE_SIMPLE}
                  className="gaf-mb-md"
                />
              )}
            </Spin>
            <Space orientation="vertical" className="gaf-w-full">
              <Typography.Text className="gaf-text-xs" type="secondary">
                {t('windowMgmt.col_screenshot_method')}: {testDevice.screenshot_method || 'auto'}
                {testDevice.resolved_methods && (
                  <Tag color="purple" className="gaf-ml-1">
                    {t('windowMgmt.tag_resolved')}: {testDevice.resolved_methods.screenshot_method}
                  </Tag>
                )}
              </Typography.Text>
              <Typography.Text className="gaf-text-xs" type="secondary">
                {t('windowMgmt.col_input_method')}: {testDevice.input_method || 'auto'}
                {testDevice.resolved_methods && (
                  <Tag color="purple" className="gaf-ml-1">
                    {t('windowMgmt.tag_resolved')}: {testDevice.resolved_methods.input_method}
                  </Tag>
                )}
              </Typography.Text>
              <Typography.Text className="gaf-text-xs" type="secondary">
                {t('windowMgmt.col_control_mode')}: {testDevice.control_mode || 'auto'}
                {testDevice.resolved_methods && (
                  <Tag color="purple" className="gaf-ml-1">
                    {t('windowMgmt.tag_resolved')}: {testDevice.resolved_methods.control_mode}
                  </Tag>
                )}
              </Typography.Text>
            </Space>
          </div>
        )}
      </Modal>
    </PageWrapper>
  );
}

export default WindowManagementPage;
