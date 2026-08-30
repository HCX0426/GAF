/**
 * Universal scan result modal component
 * Supports windows/android modes, auto-scans on open, checkbox selection, batch register
 */
import { useState, useCallback, useEffect } from 'react';
import { Modal, Table, Tag, Progress, Empty, Button, Space, Checkbox, App } from 'antd';
import type { TableRowSelection } from 'antd/es/table/interface';
import type { ColumnsType } from 'antd/es/table';
import { AndroidOutlined, ThunderboltOutlined, WindowsOutlined } from '@ant-design/icons';
import { scanDevices, registerDevice } from '@/api/devices';
import type { ScanEmulatorItem, ScanWindowItem, DeviceRegisterParams } from '@/types/models';

/** Emulator brand icon mapping */
const EMULATOR_ICON_MAP: Record<string, React.ReactNode> = {
  bluestacks: <ThunderboltOutlined style={{ color: '#00bcd4' }} />,
  nox: <AndroidOutlined style={{ color: '#ff6f00' }} />,
  mumu: <AndroidOutlined style={{ color: '#2196f3' }} />,
  ldplayer: <AndroidOutlined style={{ color: '#4caf50' }} />,
  memu: <AndroidOutlined style={{ color: '#e91e63' }} />,
  unknown: <AndroidOutlined style={{ color: '#999' }} />,
};

/** Emulator brand label mapping */
const EMULATOR_LABEL_MAP: Record<string, string> = {
  bluestacks: '蓝叠',
  nox: '夜神',
  mumu: 'MuMu',
  ldplayer: '雷电',
  memu: '逍遥',
  unknown: '未知',
};

/** Status color mapping */
const STATUS_COLOR_MAP: Record<string, string> = {
  connected: 'green',
  registered: 'green',
  running: 'blue',
  discovered: 'gold',
  registerable: 'gold',
  offline: 'default',
};

/** Status label mapping */
const STATUS_LABEL_MAP: Record<string, string> = {
  connected: '已注册',
  registered: '已注册',
  running: '运行中',
  discovered: '可注册',
  registerable: '可注册',
  offline: '离线',
};

/** Android scan stages */
const ANDROID_SCAN_STAGES = [
  'Scanning config files...',
  'Scanning MuMu emulator...',
  'Scanning LDPlayer emulator...',
  'Scanning BlueStacks emulator...',
  'Scanning Xiaoyao/Nox emulator...',
  'Detecting ADB devices...',
  'Identifying emulator brands...',
];

/** Windows scan stages */
const WINDOWS_SCAN_STAGES = [
  'Enumerating system windows...',
  'Identifying game windows...',
  'Excluding system windows...',
  'Analysis complete...',
];

interface ScanModalProps {
  /** Scan mode: android for emulators, windows for window devices */
  mode: 'android' | 'windows';
  /** Whether the modal is visible */
  open: boolean;
  /** Callback when modal closes */
  onClose: () => void;
  /** Callback after successful registration (refresh parent list) */
  onRegistered?: () => void;
}

/** Helper: compute unique key for a scan item based on mode */
function getScanItemKey(item: ScanEmulatorItem | ScanWindowItem, mode: 'android' | 'windows'): string {
  if (mode === 'android') {
    const em = item as ScanEmulatorItem;
    return em.adb_serial || `127.0.0.1:${em.adb_port}`;
  }
  const win = item as ScanWindowItem;
  return win.hwnd || win.title;
}

/**
 * Universal scan result modal
 * Auto-starts scan when opened, displays results with checkboxes and register buttons
 */
export function ScanModal({ mode, open, onClose, onRegistered }: ScanModalProps) {
  const { message } = App.useApp();
  const [loading, setLoading] = useState(false);
  const [progress, setProgress] = useState(0);
  const [stageText, setStageText] = useState('');
  const [results, setResults] = useState<(ScanEmulatorItem | ScanWindowItem)[]>([]);
  const [scanned, setScanned] = useState(false);
  const [registering, setRegistering] = useState(false);
  const [selectedRowKeys, setSelectedRowKeys] = useState<React.Key[]>([]);

  /** Auto-trigger scan when modal opens */
  useEffect(() => {
    if (open) {
      handleScan();
    }
    // Reset state when modal closes
    if (!open) {
      setResults([]);
      setScanned(false);
      setSelectedRowKeys([]);
      setProgress(0);
      setStageText('');
    }
  }, [open]);

  /**
   * Execute scan with progress animation
   * Calls backend API after simulated progress stages
   */
  const handleScan = useCallback(async () => {
    setLoading(true);
    setProgress(0);
    setScanned(false);
    setResults([]);
    setSelectedRowKeys([]);

    const stages = mode === 'android' ? ANDROID_SCAN_STAGES : WINDOWS_SCAN_STAGES;
    const stageCount = stages.length;
    for (let i = 0; i < stageCount; i++) {
      setStageText(stages[i]);
      setProgress(Math.round(((i + 1) / stageCount) * 85));
      await new Promise((resolve) => setTimeout(resolve, mode === 'android' ? 350 : 250));
    }

    try {
      const res = await scanDevices(mode);
      setProgress(100);
      setStageText('Scan complete');
      setResults(mode === 'android' ? res.android || [] : res.windows || []);
      setScanned(true);
    } catch {
      message.error(`${mode === 'android' ? 'Emulator' : 'Window'} scan failed, please check backend service`);
      setProgress(0);
      setStageText('');
    } finally {
      setLoading(false);
    }
  }, [mode, message]);

  /**
   * Register a single device
   * @param item - Device item to register
   * @returns Device key for tracking
   */
  const handleRegisterOne = useCallback(
    async (item: ScanEmulatorItem | ScanWindowItem) => {
      const key =
        mode === 'android'
          ? (item as ScanEmulatorItem).adb_serial || `127.0.0.1:${(item as ScanEmulatorItem).adb_port}`
          : (item as ScanWindowItem).hwnd || (item as ScanWindowItem).title;

      try {
        if (mode === 'android') {
          const emItem = item as ScanEmulatorItem;
          const params: DeviceRegisterParams = {
            name: emItem.name,
            agent_type: 'android',
            adb_serial: emItem.adb_serial || `127.0.0.1:${emItem.adb_port}`,
            emulator: emItem.emulator_brand,
          };
          if (emItem.resolution) {
            params.resolution = emItem.resolution;
            params.resolution_width = emItem.resolution.width;
            params.resolution_height = emItem.resolution.height;
          }
          await registerDevice(params);
        } else {
          const winItem = item as ScanWindowItem;
          const params: DeviceRegisterParams = {
            name: winItem.title,
            agent_type: 'windows',
            hwnd: winItem.hwnd?.toString(),
            window_title: winItem.title,
            resolution: winItem.resolution,
            resolution_width: winItem.resolution?.width,
            resolution_height: winItem.resolution?.height,
          };
          await registerDevice(params);
        }
        return key;
      } catch {
        throw key;
      }
    },
    [mode],
  );

  /**
   * Batch register all selected devices
   * Iterates through selected items and registers each one
   */
  const handleBatchRegister = useCallback(async () => {
    const toRegister = results.filter((r) => {
      const key = getScanItemKey(r, mode);
      const status = (r as ScanEmulatorItem).status;
      return status !== 'registered' && status !== 'connected' && selectedRowKeys.includes(key);
    });

    if (toRegister.length === 0) {
      message.warning(`Please select ${mode === 'android' ? 'emulators' : 'windows'} to register`);
      return;
    }

    setRegistering(true);
    let success = 0;
    let fail = 0;

    for (const item of toRegister) {
      try {
        await handleRegisterOne(item);
        success++;
        const key = getScanItemKey(item, mode);
        setResults((prev) => prev.map((r) => (getScanItemKey(r, mode) === key ? { ...r, status: 'registered' } : r)));
      } catch {
        fail++;
      }
    }

    setRegistering(false);
    setSelectedRowKeys([]);
    if (fail === 0) {
      message.success(`Successfully registered ${success} ${mode === 'android' ? 'emulator(s)' : 'window(s)'}`);
      onRegistered?.();
    } else {
      message.warning(`Registration complete: ${success} success, ${fail} failed`);
    }
  }, [results, selectedRowKeys, handleRegisterOne, onRegistered, mode, message]);

  /** Toggle select all / deselect all */
  const handleToggleSelectAll = useCallback(() => {
    if (selectedRowKeys.length === results.length) {
      setSelectedRowKeys([]);
    } else {
      const allKeys = results.map((r) => getScanItemKey(r, mode));
      setSelectedRowKeys(allKeys);
    }
  }, [results, selectedRowKeys, mode]);

  /** Get table columns based on scan mode */
  const getColumns = useCallback((): ColumnsType<ScanEmulatorItem | ScanWindowItem> => {
    if (mode === 'android') {
      return [
        {
          title: 'Name',
          dataIndex: 'name',
          key: 'name',
          width: 160,
        },
        {
          title: 'Emulator Type',
          dataIndex: 'emulator',
          key: 'emulator',
          width: 120,
          render: (val: string) => (
            <Tag icon={EMULATOR_ICON_MAP[val] || EMULATOR_ICON_MAP.unknown}>{EMULATOR_LABEL_MAP[val] || val}</Tag>
          ),
        },
        {
          title: 'ADB Address',
          key: 'adb_serial',
          width: 160,
          render: (_: unknown, record: ScanEmulatorItem | ScanWindowItem) => {
            const em = record as ScanEmulatorItem;
            return em.adb_serial || `127.0.0.1:${em.adb_port}`;
          },
        },
        {
          title: 'Resolution',
          key: 'resolution',
          width: 120,
          render: (_: unknown, record: ScanEmulatorItem | ScanWindowItem) => {
            const r = (record as ScanEmulatorItem).resolution ?? (record as ScanWindowItem).resolution;
            return r ? `${r.width}×${r.height}` : '-';
          },
        },
        {
          title: 'Status',
          dataIndex: 'status',
          key: 'status',
          width: 90,
          render: (val: string) => <Tag color={STATUS_COLOR_MAP[val] || 'default'}>{STATUS_LABEL_MAP[val] || val}</Tag>,
        },
        {
          title: 'Action',
          key: 'action',
          width: 80,
          render: (_: unknown, record: ScanEmulatorItem | ScanWindowItem) => {
            const em = record as ScanEmulatorItem;
            if (em.status === 'registered' || em.status === 'connected') {
              return <Tag color="green">Registered</Tag>;
            }
            return (
              <Button
                size="small"
                type="primary"
                onClick={(e) => {
                  e.stopPropagation();
                  handleRegisterOne(record)
                    .then(() => {
                      const key = getScanItemKey(record, mode);
                      setResults((prev) =>
                        prev.map((r) => (getScanItemKey(r, mode) === key ? { ...r, status: 'registered' } : r)),
                      );
                      message.success(`${em.name} registered successfully`);
                    })
                    .catch(() => {
                      message.error(`${em.name} registration failed`);
                    });
                }}
              >
                Register
              </Button>
            );
          },
        },
      ];
    }

    // Windows mode columns
    return [
      {
        title: 'Window Title',
        dataIndex: 'title',
        key: 'title',
        width: 200,
        ellipsis: true,
      },
      {
        title: 'Type',
        dataIndex: 'emulator',
        key: 'type',
        width: 90,
        render: (val: string) => <Tag icon={<WindowsOutlined />}>{val || 'Window'}</Tag>,
      },
      {
        title: 'Resolution',
        key: 'resolution',
        width: 130,
        render: (_: unknown, rcd: ScanEmulatorItem | ScanWindowItem) => {
          const r = (rcd as ScanEmulatorItem).resolution ?? (rcd as ScanWindowItem).resolution;
          return r ? `${r.width}×${r.height}` : '-';
        },
      },
      {
        title: 'Status',
        dataIndex: 'status',
        key: 'status',
        width: 80,
        render: (val: string) => (
          <Tag color={val === 'registered' ? 'green' : 'gold'}>{val === 'registered' ? 'Registered' : 'Available'}</Tag>
        ),
      },
      {
        title: 'Action',
        key: 'action',
        width: 80,
        render: (_: unknown, record: ScanEmulatorItem | ScanWindowItem) => {
          const recEm = record as ScanEmulatorItem;
          if (recEm.status === 'registered' || recEm.status === 'connected') {
            return <Tag color="green">Registered</Tag>;
          }
          return (
            <Button
              size="small"
              type="primary"
              onClick={(e) => {
                e.stopPropagation();
                handleRegisterOne(record)
                  .then(() => {
                    const key = getScanItemKey(record, mode);
                    setResults((prev) =>
                      prev.map((r) => (getScanItemKey(r, mode) === key ? { ...r, status: 'registered' } : r)),
                    );
                    message.success(
                      `${(record as ScanEmulatorItem).name || (record as ScanWindowItem).title} registered successfully`,
                    );
                    onRegistered?.();
                  })
                  .catch(() => {
                    message.error(
                      `${(record as ScanEmulatorItem).name || (record as ScanWindowItem).title} registration failed`,
                    );
                  });
              }}
            >
              Register
            </Button>
          );
        },
      },
    ];
  }, [mode, handleRegisterOne, message]);

  /** Generate unique row key for table */
  const rowKeyFn = (record: ScanEmulatorItem | ScanWindowItem) => getScanItemKey(record, mode);

  /** Row selection configuration with checkbox */
  const rowSelection: TableRowSelection<ScanEmulatorItem | ScanWindowItem> = {
    selectedRowKeys,
    onChange: (keys) => setSelectedRowKeys(keys),
    getCheckboxProps: (record) => ({
      disabled:
        (record as ScanEmulatorItem).status === 'registered' || (record as ScanEmulatorItem).status === 'connected',
    }),
  };

  const isAllSelected = selectedRowKeys.length > 0 && selectedRowKeys.length === results.length;
  const selectableCount = results.filter(
    (r) => (r as ScanEmulatorItem).status !== 'registered' && (r as ScanEmulatorItem).status !== 'connected',
  ).length;

  return (
    <Modal
      title={mode === 'android' ? '📱 Scan Emulators' : '🖥 Scan Windows'}
      open={open}
      onCancel={onClose}
      width={800}
      destroyOnHidden
      footer={
        <Space>
          <Button onClick={onClose}>Close</Button>
          {scanned && selectableCount > 0 && (
            <>
              <Checkbox
                checked={isAllSelected}
                indeterminate={selectedRowKeys.length > 0 && !isAllSelected}
                onChange={handleToggleSelectAll}
              >
                Select All ({selectedRowKeys.length}/{selectableCount})
              </Checkbox>
              <Button
                type="primary"
                loading={registering}
                disabled={selectedRowKeys.length === 0}
                onClick={handleBatchRegister}
              >
                Batch Register Selected ({selectedRowKeys.length})
              </Button>
            </>
          )}
        </Space>
      }
    >
      {/* Progress bar during scanning */}
      {loading && (
        <div className="gaf-py-lg">
          <Progress percent={progress} status="active" />
          <div className="gaf-mt-sm" style={{ textAlign: 'center', color: '#888' }}>
            {stageText}
          </div>
        </div>
      )}

      {/* Empty state when no results */}
      {scanned && results.length === 0 && (
        <Empty
          description={
            mode === 'android'
              ? 'No emulators found, please ensure emulators are installed and running'
              : 'No windows found'
          }
        />
      )}

      {/* Results table with checkboxes */}
      {scanned && results.length > 0 && (
        <Table
          rowKey={rowKeyFn}
          rowSelection={rowSelection}
          columns={getColumns()}
          dataSource={results}
          size="small"
          pagination={false}
          scroll={{ y: 400 }}
          locale={{
            emptyText: mode === 'android' ? 'No emulators found' : 'No windows found',
          }}
        />
      )}
    </Modal>
  );
}

export default ScanModal;
