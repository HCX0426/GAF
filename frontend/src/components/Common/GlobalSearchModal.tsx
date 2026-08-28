/**
 * GlobalSearchModal — global search Modal
 *
 * Ctrl+K trigger, cross-module search for tasks, devices, accounts, logs and settings.
 * 300ms debounce, grouped results, ↑↓ Enter ESC keyboard navigation.
 */

import { useState, useEffect, useCallback, useRef } from 'react';
import { Modal, Input, Tag, Typography, Spin, Empty } from 'antd';
import type { InputRef } from 'antd';
import {
  SearchOutlined,
  FileTextOutlined,
  DesktopOutlined,
  UserOutlined,
  FileSearchOutlined,
  SettingOutlined,
} from '@ant-design/icons';
import { useNavigate } from 'react-router-dom';
import useGlobalSearch from '@/hooks/useGlobalSearch';
import type { SearchResultItem } from '@/hooks/useGlobalSearch';

const { Text } = Typography;

interface GlobalSearchModalProps {
  visible: boolean;
  onClose: () => void;
}

const CATEGORY_ICONS: Record<string, React.ReactNode> = {
  tasks: <FileTextOutlined />,
  devices: <DesktopOutlined />,
  accounts: <UserOutlined />,
  logs: <FileSearchOutlined />,
  settings: <SettingOutlined />,
};

const CATEGORY_LABELS: Record<string, string> = {
  tasks: '任务',
  devices: '设备',
  accounts: '账户',
  logs: '日志',
  settings: '设置',
};

const CATEGORY_KEYS = ['tasks', 'devices', 'accounts', 'logs', 'settings'] as const;

export function GlobalSearchModal({ visible, onClose }: GlobalSearchModalProps) {
  const { query, setQuery, results, isLoading } = useGlobalSearch();
  const [selectedIndex, setSelectedIndex] = useState(-1);
  const inputRef = useRef<InputRef>(null);
  const navigate = useNavigate();

  const allItems = useCallback((): SearchResultItem[] => {
    if (!results) return [];
    const items: SearchResultItem[] = [];
    for (const key of CATEGORY_KEYS) {
      items.push(...(results as unknown as Record<string, SearchResultItem[]>)[key]);
    }
    return items;
  }, [results]);

  const handleSelect = useCallback(
    (item: SearchResultItem) => {
      navigate(item.url);
      onClose();
    },
    [navigate, onClose],
  );

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      const items = allItems();
      if (e.key === 'ArrowDown') {
        e.preventDefault();
        setSelectedIndex((prev) => Math.min(prev + 1, items.length - 1));
      } else if (e.key === 'ArrowUp') {
        e.preventDefault();
        setSelectedIndex((prev) => Math.max(prev - 1, -1));
      } else if (e.key === 'Enter' && selectedIndex >= 0 && items[selectedIndex]) {
        e.preventDefault();
        handleSelect(items[selectedIndex]);
      }
    },
    [allItems, selectedIndex, handleSelect],
  );

  useEffect(() => {
    if (visible) {
      setTimeout(() => inputRef.current?.focus(), 100);
    } else {
      setQuery('');
      setSelectedIndex(-1);
    }
  }, [visible, setQuery]);

  let flatIndex = 0;

  return (
    <Modal
      open={visible}
      onCancel={onClose}
      footer={null}
      width={600}
      centered
      closable
      mask={{ closable: true }}
      title={null}
      style={{ top: 60 }}
    >
      <div onKeyDown={handleKeyDown}>
        <Input
          ref={inputRef}
          prefix={<SearchOutlined style={{ color: '#bfbfbf' }} />}
          suffix={
            <Text type="secondary" className="gaf-text-sm">
              ESC 关闭
            </Text>
          }
          placeholder="搜索任务、设备、账户、日志…"
          value={query}
          onChange={(e) => {
            setQuery(e.target.value);
            setSelectedIndex(-1);
          }}
          size="large"
          variant="borderless"
          className="gaf-text-md"
        />

        {isLoading && (
          <div className="gaf-p-xl" style={{ textAlign: 'center' }}>
            <Spin />
          </div>
        )}

        {!isLoading && query && results && results.totalCount > 0 && (
          <div className="gaf-mt-sm" style={{ maxHeight: 400, overflowY: 'auto' }}>
            {CATEGORY_KEYS.map((key) => {
              const items = (results as unknown as Record<string, SearchResultItem[]>)[key] as SearchResultItem[];
              if (!items || items.length === 0) return null;
              return (
                <div key={key} className="gaf-mb-md">
                  <Text type="secondary" className="gaf-text-sm" style={{ paddingLeft: 8 }}>
                    {CATEGORY_ICONS[key]} {CATEGORY_LABELS[key]} ({items.length})
                  </Text>
                  {items.map((item) => {
                    const currentIdx = flatIndex++;
                    return (
                      <div
                        key={item.url}
                        onClick={() => handleSelect(item)}
                        className="gaf-flex-between"
                        style={{
                          padding: '6px 12px',
                          cursor: 'pointer',
                          borderRadius: 4,
                          background: currentIdx === selectedIndex ? '#e6f4ff' : 'transparent',
                        }}
                      >
                        <div>
                          <Text strong>{item.title}</Text>
                          <br />
                          <Text type="secondary" className="gaf-text-sm">
                            {item.subtitle}
                          </Text>
                        </div>
                        {item.tag && (
                          <Tag color={item.tagColor || 'default'} className="gaf-m-0" style={{ flexShrink: 0 }}>
                            {item.tag}
                          </Tag>
                        )}
                      </div>
                    );
                  })}
                </div>
              );
            })}
          </div>
        )}

        {!isLoading && query && results && results.totalCount === 0 && (
          <div className="gaf-p-xl">
            <Empty description={`未找到匹配"${query}"的结果`} image={Empty.PRESENTED_IMAGE_SIMPLE} />
          </div>
        )}

        {!query && (
          <div className="gaf-p-xl" style={{ textAlign: 'center', color: '#bfbfbf' }}>
            <Text type="secondary">输入关键词开始搜索</Text>
          </div>
        )}
      </div>
    </Modal>
  );
}

export default GlobalSearchModal;
