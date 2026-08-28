/**
 * ADB log view device page (P-021 H7)
 *
 * feature:
 * - WebSocket real-time connection /ws/devices/{device_id}/adb-logs/
 * - log stream show ( virtual scroll + auto scroll to bottom )
 * - filter (tag/level/pid)
 * - control button ( pause / recover / clear / download )
 * - search highlight
 */
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Button, Card, Empty, Input, Select, Space, Tag, Typography, message } from 'antd';
import {
  ClearOutlined,
  DownloadOutlined,
  PauseCircleOutlined,
  PlayCircleOutlined,
  ReloadOutlined,
  SearchOutlined,
} from '@ant-design/icons';
import { useNavigate, useParams } from 'react-router-dom';
import PageWrapper from '@/components/Common/PageWrapper';
import { fetchDevices } from '@/api/devices';
import { getAccessToken } from '@/utils/tokenStore';
import { WS_DEVICES_PATH } from '@/config/app';
import type { Device } from '@/types/models';
import { useTranslation } from '@/i18n';

const { Text, Title } = Typography;

/** log level color mapping */
const LEVEL_COLOR: Record<string, string> = {
  V: '#8c8c8c',
  D: '#1890ff',
  I: '#52c41a',
  W: '#faad14',
  E: '#ff4d4f',
  F: '#eb2f96',
};

/** log row API */
interface LogLine {
  seq: number;
  line: string;
  timestamp: string;
}

/** parse logcat row, extract level */
function parseLogLevel(line: string): string {
  // logcat -v time format: "MM-DD HH:MM:SS.UUU Level/Tag(PID): message"
  const match = line.match(/^\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}\.\d+\s+([VDIWEF])\//);
  return match ? match[1] : '';
}

/** ADB log view device main component */
export function AdbLogViewerPage() {
  const { deviceId } = useParams<{ deviceId: string }>();
  const navigate = useNavigate();
  const t = useTranslation();
  const [devices, setDevices] = useState<Device[]>([]);
  const [selectedDeviceId, setSelectedDeviceId] = useState<number | undefined>(deviceId ? Number(deviceId) : undefined);
  const [logs, setLogs] = useState<LogLine[]>([]);
  const [paused, setPaused] = useState(false);
  const [searchText, setSearchText] = useState('');
  const [filterTag, setFilterTag] = useState('');
  const [filterLevel, setFilterLevel] = useState('');
  const [filterPid, setFilterPid] = useState('');
  const [connected, setConnected] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const wsRef = useRef<WebSocket | null>(null);
  const logsContainerRef = useRef<HTMLDivElement>(null);
  const autoScrollRef = useRef(true);
  const pausedRef = useRef(false);

  // load device list
  useEffect(() => {
    fetchDevices()
      .then((res) => {
        // F11 fix (2026-08-28): 此前仅过滤 adb_serial 非空 → Windows 窗口设备(如 Endfield)
        // 无 adb_serial 被丢弃, 模拟器离线也消失 → 下拉恒空。
        // 放宽为 ADB 可达设备: 有 adb_serial 或 type=emulator 均列入；离线仍可选（连接时提示）。
        const adbDevices = res.results.filter((d) => d.adb_serial || d.device_type === 'emulator');
        setDevices(adbDevices);
        if (!selectedDeviceId && adbDevices.length > 0) {
          setSelectedDeviceId(adbDevices[0].id);
        }
      })
      .catch(() => {
        message.error(t('devices.adb_log_load_failed'));
      });
  }, [selectedDeviceId]);

  // sync pausedRef
  useEffect(() => {
    pausedRef.current = paused;
  }, [paused]);

  // WebSocket connection
  useEffect(() => {
    if (!selectedDeviceId) return;

    const token = getAccessToken();
    if (!token) {
      // Defer setState to avoid setState-in-effect lint error
      const timer = setTimeout(() => setError(t('devices.adb_log_token_expired')), 0);
      return () => clearTimeout(timer);
    }
    const clearErrorTimer = setTimeout(() => setError(null), 0);

    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    // C8 fix: do NOT put JWT in URL query string. Filters (tag/level/pid) are non-secret
    // and stay in the URL; token goes via Sec-WebSocket-Protocol subprotocol.
    const params = new URLSearchParams();
    if (filterTag) params.set('tag', filterTag);
    if (filterLevel) params.set('level', filterLevel);
    if (filterPid) params.set('pid', filterPid);

    const url = `${protocol}//${window.location.host}${WS_DEVICES_PATH}${selectedDeviceId}/adb-logs/?${params.toString()}`;
    const ws = new WebSocket(url, [`access.${token}`]);
    wsRef.current = ws;

    ws.onopen = () => {
      setConnected(true);
      setError(null);
      setLogs([]);
    };

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        if (data.type === 'adb_log.line') {
          if (pausedRef.current) return;
          setLogs((prev) => {
            const newLogs = [
              ...prev,
              {
                seq: data.seq,
                line: data.line,
                timestamp: new Date().toISOString(),
              },
            ];
            // limit most large row count
            if (newLogs.length > 5000) {
              return newLogs.slice(-4000);
            }
            return newLogs;
          });
        } else if (data.type === 'adb_log.error') {
          setError(data.message);
        } else if (data.type === 'adb_log.paused') {
          // server confirmed pause
        } else if (data.type === 'adb_log.resumed') {
          // server confirmed resume
        }
      } catch {
        // ignore non-JSON
      }
    };

    ws.onerror = () => {
      setError(t('devices.adb_log_ws_error'));
      setConnected(false);
    };

    ws.onclose = () => {
      setConnected(false);
    };

    return () => {
      clearTimeout(clearErrorTimer);
      ws.close();
      wsRef.current = null;
    };
  }, [selectedDeviceId, filterTag, filterLevel, filterPid]);

  // auto scroll to bottom
  useEffect(() => {
    if (autoScrollRef.current && logsContainerRef.current) {
      logsContainerRef.current.scrollTop = logsContainerRef.current.scrollHeight;
    }
  }, [logs]);

  // pause / recover
  const handlePauseResume = useCallback(() => {
    const newPaused = !paused;
    setPaused(newPaused);
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type: newPaused ? 'pause' : 'resume' }));
    }
  }, [paused]);

  // clear log
  const handleClear = useCallback(() => {
    setLogs([]);
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type: 'clear' }));
    }
  }, []);

  // download log
  const handleDownload = useCallback(() => {
    const content = logs.map((l) => l.line).join('\n');
    const blob = new Blob([content], { type: 'text/plain;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `adb-logs-device-${selectedDeviceId}-${Date.now()}.txt`;
    a.click();
    URL.revokeObjectURL(url);
    message.success(t('devices.adb_log_downloaded'));
  }, [logs, selectedDeviceId]);

  // app filter device
  const handleApplyFilter = useCallback(() => {
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      wsRef.current.send(
        JSON.stringify({
          type: 'filter',
          tag: filterTag,
          level: filterLevel,
          pid: filterPid,
        }),
      );
      setLogs([]);
    }
  }, [filterTag, filterLevel, filterPid]);

  // filter after log ( before end search )
  const filteredLogs = useMemo(() => {
    if (!searchText) return logs;
    return logs.filter((l) => l.line.toLowerCase().includes(searchText.toLowerCase()));
  }, [logs, searchText]);

  // scroll event handle ( detect is no in footer )
  const handleScroll = useCallback(() => {
    if (!logsContainerRef.current) return;
    const { scrollTop, scrollHeight, clientHeight } = logsContainerRef.current;
    autoScrollRef.current = scrollHeight - scrollTop - clientHeight < 50;
  }, []);

  return (
    <PageWrapper
      title={t('devices.adb_log_title')}
      extra={
        <Space>
          <Tag color={connected ? 'green' : 'red'}>
            {connected ? t('devices.adb_log_connected') : t('devices.adb_log_disconnected')}
          </Tag>
          {error && <Text type="danger">{error}</Text>}
        </Space>
      }
    >
      <Card className="gaf-mb-lg">
        <Space wrap>
          <Select
            style={{ width: 240 }}
            placeholder={t('devices.adb_log_select_device')}
            value={selectedDeviceId}
            onChange={(v) => {
              setSelectedDeviceId(v);
              navigate(`/devices/adb-logs/${v}`);
            }}
            options={devices.map((d) => ({
              label: `${d.name} (${d.adb_serial})`,
              value: d.id,
            }))}
          />
          <Input
            style={{ width: 160 }}
            placeholder={t('devices.adb_log_filter_tag')}
            value={filterTag}
            onChange={(e) => setFilterTag(e.target.value)}
            onPressEnter={handleApplyFilter}
          />
          <Select
            className="gaf-w-xs"
            placeholder={t('devices.adb_log_filter_level')}
            value={filterLevel || undefined}
            onChange={(v) => setFilterLevel(v || '')}
            allowClear
            options={[
              { label: 'V (Verbose)', value: 'V' },
              { label: 'D (Debug)', value: 'D' },
              { label: 'I (Info)', value: 'I' },
              { label: 'W (Warn)', value: 'W' },
              { label: 'E (Error)', value: 'E' },
              { label: 'F (Fatal)', value: 'F' },
            ]}
          />
          <Input
            className="gaf-w-sm"
            placeholder="PID"
            value={filterPid}
            onChange={(e) => setFilterPid(e.target.value)}
            onPressEnter={handleApplyFilter}
          />
          <Button icon={<ReloadOutlined />} onClick={handleApplyFilter}>
            {t('devices.adb_log_apply_filter')}
          </Button>
          <Button
            icon={paused ? <PlayCircleOutlined /> : <PauseCircleOutlined />}
            onClick={handlePauseResume}
            disabled={!connected}
          >
            {paused ? t('devices.adb_log_resume') : t('devices.adb_log_pause')}
          </Button>
          <Button icon={<ClearOutlined />} onClick={handleClear} disabled={!connected}>
            {t('devices.adb_log_clear')}
          </Button>
          <Button icon={<DownloadOutlined />} onClick={handleDownload} disabled={logs.length === 0}>
            {t('devices.adb_log_download')}
          </Button>
        </Space>
      </Card>

      <Card className="gaf-mb-lg">
        <Input
          placeholder={t('devices.adb_log_search_placeholder')}
          prefix={<SearchOutlined />}
          value={searchText}
          onChange={(e) => setSearchText(e.target.value)}
          allowClear
        />
      </Card>

      <Card
        title={
          <Space>
            <Title level={5} className="gaf-m-0">
              {t('devices.adb_log_output')}
            </Title>
            <Text type="secondary">{t('devices.adb_log_line_count', { count: filteredLogs.length })}</Text>
          </Space>
        }
        styles={{ body: { padding: 0 } }}
      >
        <div
          ref={logsContainerRef}
          onScroll={handleScroll}
          className="gaf-text-xs gaf-py-sm gaf-px-md gaf-overflow-y-auto"
          style={{
            height: 'calc(100vh - 420px)',
            minHeight: 400,
            backgroundColor: '#1e1e1e',
            fontFamily: 'Consolas, Monaco, "Courier New", monospace',
            lineHeight: '1.6',
          }}
        >
          {filteredLogs.length === 0 ? (
            <div className="gaf-text-center" style={{ color: '#666', paddingTop: 80 }}>
              <Empty
                description={connected ? t('devices.adb_log_waiting') : t('devices.adb_log_not_connected')}
                image={Empty.PRESENTED_IMAGE_SIMPLE}
              />
            </div>
          ) : (
            filteredLogs.map((log) => {
              const level = parseLogLevel(log.line);
              const color = level ? LEVEL_COLOR[level] : '#d4d4d4';
              return (
                <div
                  key={log.seq}
                  className="gaf-whitespace-pre-wrap"
                  style={{
                    color,
                    wordBreak: 'break-all',
                    padding: '1px 0',
                  }}
                >
                  {searchText ? highlightSearch(log.line, searchText, color) : log.line}
                </div>
              );
            })
          )}
        </div>
      </Card>
    </PageWrapper>
  );
}

/** highlight search text */
function highlightSearch(text: string, search: string, baseColor: string): React.ReactNode {
  if (!search) return text;
  const lowerText = text.toLowerCase();
  const lowerSearch = search.toLowerCase();
  const parts: React.ReactNode[] = [];
  let lastIndex = 0;
  let idx = lowerText.indexOf(lowerSearch, lastIndex);
  let key = 0;
  while (idx !== -1) {
    if (idx > lastIndex) {
      parts.push(text.substring(lastIndex, idx));
    }
    parts.push(
      <mark key={key++} style={{ backgroundColor: '#fff3b0', color: '#000', padding: '0 2px' }}>
        {text.substring(idx, idx + search.length)}
      </mark>,
    );
    lastIndex = idx + search.length;
    idx = lowerText.indexOf(lowerSearch, lastIndex);
  }
  if (lastIndex < text.length) {
    parts.push(text.substring(lastIndex));
  }
  return <span style={{ color: baseColor }}>{parts}</span>;
}

export default AdbLogViewerPage;
