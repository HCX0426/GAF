/**
 * device search/filter bar component
 * provides device name search, status filter, type filter and group filter
 */
import { useState, useEffect, useRef, useMemo } from 'react';
import { Input, Select, Button, Space } from 'antd';
import { SearchOutlined, ReloadOutlined } from '@ant-design/icons';
import { useDeviceStore } from '@/stores/useDeviceStore';
import { useTranslation } from '@/i18n';

/** filter condition value API */
export interface FilterValues {
  search?: string;
  status?: string;
  device_type?: string;
  group_id?: number;
}

/** DeviceFilterBar component props */
interface DeviceFilterBarProps {
  onFilter: (filters: FilterValues) => void;
  initialValues?: FilterValues;
}

/**
 * device filter bar
 * supports search by name, status, type, group filter, with 300ms debounce
 */
export function DeviceFilterBar({ onFilter, initialValues }: DeviceFilterBarProps) {
  const t = useTranslation();
  const groups = useDeviceStore((s) => s.groups);
  const [filters, setFilters] = useState<FilterValues>(initialValues ?? {});
  const [searchText, setSearchText] = useState(initialValues?.search ?? '');
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  /** device status options */
  const STATUS_OPTIONS = useMemo(
    () => [
      { value: '', label: t('devices.all') },
      { value: 'online', label: t('devices.filter_status_online') },
      { value: 'offline', label: t('devices.filter_status_offline') },
      { value: 'busy', label: t('devices.filter_status_busy') },
      { value: 'error', label: t('devices.filter_status_error') },
      { value: 'locked', label: t('devices.filter_status_locked') },
    ],
    [t],
  );

  /** device type options */
  const DEVICE_TYPE_OPTIONS = useMemo(
    () => [
      { value: '', label: t('devices.all') },
      { value: 'windows', label: 'Windows' },
      { value: 'adb', label: 'ADB' },
      { value: 'emulator', label: t('devices.filter_type_emulator') },
    ],
    [t],
  );

  /** Clear any pending debounce timer on unmount */
  useEffect(() => {
    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
    };
  }, []);

  /** group option */
  const groupOptions = useMemo(
    () => [
      { value: '', label: t('devices.filter_all_groups') },
      ...groups.map((g) => ({ value: g.id, label: g.name })),
    ],
    [groups, t],
  );

  /** search change handler with 300ms debounce */
  const handleSearchChange = (value: string) => {
    setSearchText(value);
    if (debounceRef.current) {
      clearTimeout(debounceRef.current);
    }
    debounceRef.current = setTimeout(() => {
      const newFilters = { ...filters, search: value || undefined };
      setFilters(newFilters);
      onFilter(newFilters);
    }, 300);
  };

  /** selector change more handle */
  const handleSelectChange = (key: keyof FilterValues, value: string | number | undefined) => {
    const newFilters = {
      ...filters,
      [key]: value || undefined,
    };
    setFilters(newFilters);
    onFilter(newFilters);
  };

  /** reset has filter condition */
  const handleReset = () => {
    setSearchText('');
    setFilters({});
    onFilter({});
  };

  useEffect(() => {
    return () => {
      if (debounceRef.current) {
        clearTimeout(debounceRef.current);
      }
    };
  }, []);

  return (
    <Space wrap>
      <Input.Search
        placeholder={t('devices.filter_search_placeholder')}
        allowClear
        value={searchText}
        onChange={(e) => handleSearchChange(e.target.value)}
        style={{ width: 240 }}
        prefix={<SearchOutlined />}
      />

      <Select
        placeholder={t('devices.filter_status_placeholder')}
        allowClear
        value={filters.status}
        onChange={(v) => handleSelectChange('status', v)}
        options={STATUS_OPTIONS}
        className="gaf-w-xs"
        getPopupContainer={(triggerNode) => triggerNode.parentElement}
      />

      <Select
        placeholder={t('devices.filter_type_placeholder')}
        allowClear
        value={filters.device_type}
        onChange={(v) => handleSelectChange('device_type', v)}
        options={DEVICE_TYPE_OPTIONS}
        className="gaf-w-sm"
        getPopupContainer={(triggerNode) => triggerNode.parentElement}
      />

      <Select
        placeholder={t('devices.filter_group_placeholder')}
        allowClear
        value={filters.group_id}
        onChange={(v) => handleSelectChange('group_id', v)}
        options={groupOptions}
        style={{ width: 140 }}
        getPopupContainer={(triggerNode) => triggerNode.parentElement}
      />

      <Button icon={<ReloadOutlined />} onClick={handleReset}>
        {t('devices.filter_reset')}
      </Button>
    </Space>
  );
}

export default DeviceFilterBar;
