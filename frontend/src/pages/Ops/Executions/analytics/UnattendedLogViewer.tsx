/**
 * unattended dedicated log view device
 * by device → account group show unattended execute log, supports search, level filter, only exception mode
 */
import { useState, useEffect, useCallback, useMemo } from 'react';
import { Collapse, Input, Select, Switch, Space, Tag, Card, Spin, Empty, Typography, DatePicker, theme } from 'antd';
import type { GlobalToken } from 'antd/es/theme/interface';
import {
  RocketOutlined,
  StopOutlined,
  WarningOutlined,
  ReloadOutlined,
  SwapOutlined,
  CheckCircleOutlined,
  SearchOutlined,
} from '@ant-design/icons';
import dayjs from 'dayjs';
import { useTranslation } from '@/i18n';
import { getUnattendedLogs, type UnattendedLogEntry } from '@/api/executions';

const { Text } = Typography;

/** log event type */
type EventType = 'start' | 'stop' | 'error' | 'recover' | 'switch' | 'complete';

/** log level */
type LogLevel = 'INFO' | 'WARN' | 'ERROR' | 'SUCCESS';

/** single record log record item (alias of UnattendedLogEntry for local readability) */
type LogEntry = UnattendedLogEntry;

/** by device group log structure */
interface DeviceLogGroup {
  device_name: string;
  accounts: AccountLogGroup[];
}

/** by account group log structure */
interface AccountLogGroup {
  account_name: string;
  logs: LogEntry[];
}

/** UnattendedLogViewer component props */
interface UnattendedLogViewerProps {
  date?: string;
}

/** event type to icon component mapping (uses design tokens for theme consistency) */
function getEventIconMap(token: GlobalToken): Record<EventType, React.ReactNode> {
  return {
    start: <RocketOutlined style={{ color: token.colorPrimary }} />,
    stop: <StopOutlined style={{ color: token.colorError }} />,
    error: <WarningOutlined style={{ color: token.colorWarning }} />,
    recover: <ReloadOutlined style={{ color: token.colorSuccess }} />,
    switch: <SwapOutlined style={{ color: '#722ed1' }} />,
    complete: <CheckCircleOutlined style={{ color: token.colorSuccess }} />,
  };
}

/** log level color mapping */
const LEVEL_COLOR_MAP: Record<LogLevel, string> = {
  INFO: 'blue',
  WARN: 'warning',
  ERROR: 'error',
  SUCCESS: 'success',
};

/** exception level aggregate ( used for " only exception " filter ) */
const ABNORMAL_LEVELS: Set<LogLevel> = new Set(['ERROR', 'WARN']);

/**
 * will flat log list by device → account group
 * @param logs - flatten log record item array
 */
function groupLogsByDeviceAndAccount(logs: LogEntry[]): DeviceLogGroup[] {
  const deviceMap = new Map<string, Map<string, LogEntry[]>>();
  logs.forEach((log) => {
    if (!deviceMap.has(log.device_name)) {
      deviceMap.set(log.device_name, new Map());
    }
    const accountMap = deviceMap.get(log.device_name)!;
    if (!accountMap.has(log.account_name)) {
      accountMap.set(log.account_name, []);
    }
    accountMap.get(log.account_name)!.push(log);
  });

  const groups: DeviceLogGroup[] = [];
  deviceMap.forEach((accountMap, deviceName) => {
    const accounts: AccountLogGroup[] = [];
    accountMap.forEach((accountLogs, accountName) => {
      accounts.push({ account_name: accountName, logs: accountLogs });
    });
    groups.push({ device_name: deviceName, accounts });
  });
  return groups;
}

/**
 * format transform time timestamp is can read time
 * @param ts - ISO time timestamp string
 */
function formatTimestamp(ts: string): string {
  try {
    return dayjs(ts).format('HH:mm:ss.SSS');
  } catch {
    return ts;
  }
}

/**
 * unattended dedicated log view device component
 */
export function UnattendedLogViewer({ date: propDate }: UnattendedLogViewerProps) {
  const t = useTranslation();
  const { token } = theme.useToken();
  const eventIconMap = getEventIconMap(token);
  const [selectedDate, setSelectedDate] = useState<string>(propDate || dayjs().format('YYYY-MM-DD'));
  const [rawLogs, setRawLogs] = useState<LogEntry[]>([]);
  const [loading, setLoading] = useState(false);
  const [searchKeyword, setSearchKeyword] = useState('');
  const [levelFilter, setLevelFilter] = useState<string>('all');
  const [abnormalOnly, setAbnormalOnly] = useState(false);

  /** load log data */
  const loadLogs = useCallback(async (targetDate: string) => {
    setLoading(true);
    try {
      // F005 fix: use client-based API instead of raw fetch() (which had no auth headers).
      const data = await getUnattendedLogs(targetDate);
      // F4 fix (2026-08-28): 接口空态可能返回非数组(对象/错误包) → 守卫后 groupLogs/forEach 不再崩溃
      setRawLogs(Array.isArray(data) ? data : []);
    } catch {
      setRawLogs([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadLogs(selectedDate);
  }, [selectedDate, loadLogs]);

  /** handle date change */
  const handleDateChange = (_date: dayjs.Dayjs | null, dateString: string | null) => {
    if (dateString) setSelectedDate(dateString);
  };

  /** filter after log list */
  const filteredLogs = useMemo(() => {
    let result = rawLogs;
    if (searchKeyword.trim()) {
      const kw = searchKeyword.toLowerCase();
      result = result.filter(
        (log) =>
          log.message.toLowerCase().includes(kw) ||
          log.device_name.toLowerCase().includes(kw) ||
          log.account_name.toLowerCase().includes(kw),
      );
    }
    if (levelFilter !== 'all') {
      result = result.filter((log) => log.level === levelFilter);
    }
    if (abnormalOnly) {
      result = result.filter((log) => ABNORMAL_LEVELS.has(log.level));
    }
    return result;
  }, [rawLogs, searchKeyword, levelFilter, abnormalOnly]);

  /** group after log data */
  const groupedLogs = useMemo(() => groupLogsByDeviceAndAccount(filteredLogs), [filteredLogs]);

  /** render single record log record item */
  const renderLogItem = (log: LogEntry) => (
    <div
      key={log.id}
      className="gaf-flex-center gaf-gap-sm gaf-text-13"
      style={{
        padding: '6px 8px',
        borderRadius: 4,
        background: ABNORMAL_LEVELS.has(log.level) ? token.colorWarningBg : 'transparent',
        lineHeight: '20px',
      }}
    >
      <Text type="secondary" className="gaf-text-xxs gaf-font-mono" style={{ minWidth: 80 }}>
        {formatTimestamp(log.timestamp)}
      </Text>
      <span className="gaf-text-sm">{eventIconMap[log.event_type]}</span>
      <Tag color={LEVEL_COLOR_MAP[log.level]} className="gaf-m-0">
        {log.level}
      </Tag>
      <Text ellipsis={{ tooltip: log.message }} className="gaf-flex-1">
        {log.message}
      </Text>
    </div>
  );

  /** render account group Collapse panel */
  const renderAccountPanels = (accounts: AccountLogGroup[]) =>
    accounts.map((acc) => ({
      key: acc.account_name,
      label: (
        <Space>
          <Text strong>{acc.account_name}</Text>
          <Tag>{t('executions.text_log_count', { count: acc.logs.length })}</Tag>
        </Space>
      ),
      children: <div>{acc.logs.map(renderLogItem)}</div>,
    }));

  /** render device group Collapse panel */
  const devicePanels = groupedLogs.map((device) => ({
    key: device.device_name,
    label: (
      <Space>
        <Text strong className="gaf-text-sm">
          📱 {device.device_name}
        </Text>
        <Tag color="processing">
          {t('executions.text_log_count', { count: device.accounts.reduce((sum, a) => sum + a.logs.length, 0) })}
        </Tag>
      </Space>
    ),
    children: (
      <Collapse
        size="small"
        ghost
        items={renderAccountPanels(device.accounts)}
        defaultActiveKey={device.accounts.map((a) => a.account_name)}
      />
    ),
  }));

  return (
    <div>
      <Card size="small" className="gaf-mb-lg">
        <Space wrap>
          <DatePicker value={dayjs(selectedDate)} onChange={handleDateChange} />
          <Input
            placeholder={t('executions.placeholder_search_logs')}
            prefix={<SearchOutlined />}
            value={searchKeyword}
            onChange={(e) => setSearchKeyword(e.target.value)}
            allowClear
            className="gaf-w-200"
          />
          <Select
            value={levelFilter}
            onChange={setLevelFilter}
            options={[
              { value: 'all', label: t('executions.option_all') },
              { value: 'INFO', label: 'INFO' },
              { value: 'WARN', label: 'WARN' },
              { value: 'ERROR', label: 'ERROR' },
              { value: 'SUCCESS', label: 'SUCCESS' },
            ]}
            style={{ width: 110 }}
          />
          <Switch
            checkedChildren={t('executions.switch_abnormal_only')}
            unCheckedChildren={t('executions.switch_all')}
            checked={abnormalOnly}
            onChange={setAbnormalOnly}
          />
          <Text type="secondary" className="gaf-text-xs">
            {t('executions.text_log_summary', { filtered: filteredLogs.length, total: rawLogs.length })}
          </Text>
        </Space>
      </Card>

      <Spin spinning={loading}>
        {!loading && filteredLogs.length === 0 ? (
          <Empty description={t('executions.text_no_matching_logs')} />
        ) : (
          <Collapse items={devicePanels} defaultActiveKey={groupedLogs.map((g) => g.device_name)} />
        )}
      </Spin>
    </div>
  );
}

export default UnattendedLogViewer;
