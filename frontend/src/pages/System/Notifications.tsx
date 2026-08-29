/**
 * notify center page
 * supports category filter, mark already read, batch operations, paginate
 */
import { useEffect, useState, useCallback, useMemo } from 'react';
import {
  Card,
  Tabs,
  Tag,
  Button,
  Space,
  Pagination,
  Badge,
  App,
  Popconfirm,
  Empty,
  Spin,
  Typography,
  theme as antTheme,
} from 'antd';
import { DeleteOutlined, CheckCircleOutlined, MailOutlined, ReloadOutlined } from '@ant-design/icons';
import dayjs from 'dayjs';
import NotificationPreferences from '@/components/Notifications/NotificationPreferences';
import WebhookConfigPanel from '@/components/Notifications/WebhookConfigPanel';
import PageWrapper from '@/components/Common/PageWrapper';
import {
  fetchNotifications,
  fetchUnreadCount,
  markNotificationRead,
  markAllNotificationsRead,
  deleteNotification as deleteNotificationApi,
} from '@/api/notifications';
import type { NotificationItem as NotifItem } from '@/api/notifications';
import { useTranslation, getLocale } from '@/i18n';
import { fetchNotificationChainHealth, type NotificationChainHealth } from '@/api/monitors';

/** category label i18n key mapping */
const CATEGORY_LABEL_KEYS: Record<string, string> = {
  all: 'notifications.category_all',
  system: 'notifications.category_system',
  alert: 'notifications.category_alert',
  community: 'notifications.category_community',
  other: 'notifications.category_other',
};

/** category label color */
const CATEGORY_COLOR: Record<string, string> = {
  system: 'blue',
  alert: 'red',
  community: 'green',
  other: 'default',
};

/** notify center page component */
export function NotificationsPage() {
  const { token: designToken } = antTheme.useToken();
  const { message } = App.useApp();
  const t = useTranslation();
  const [notifications, setNotifications] = useState<NotifItem[]>([]);

  const categoryLabel = useMemo(() => {
    const map: Record<string, string> = {};
    Object.entries(CATEGORY_LABEL_KEYS).forEach(([k, key]) => {
      map[k] = t(key);
    });
    return map;
  }, [t]);

  const [unreadCount, setUnreadCount] = useState(0);
  const [loading, setLoading] = useState(false);
  const [category, setCategory] = useState('all');
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);
  const [selectedIds, setSelectedIds] = useState<number[]>([]);
  const [chainHealth, setChainHealth] = useState<NotificationChainHealth | null>(null);
  const pageSize = 20;

  /** load notification list */
  const loadNotifications = useCallback(async () => {
    setLoading(true);
    try {
      const data = await fetchNotifications({
        page,
        page_size: pageSize,
        category: category !== 'all' ? category : undefined,
      });
      setNotifications(data.items || data.results || []);
      setTotal(data.total || 0);
    } catch {
      setNotifications([]);
    } finally {
      setLoading(false);
    }
  }, [page, category]);

  /** load not reading */
  const loadUnreadCount = useCallback(async () => {
    try {
      const data = await fetchUnreadCount();
      setUnreadCount(data.unread_count || 0);
    } catch (err) {
      console.error('Notifications load failed:', err);
    }
  }, []);

  /** load 通知链路健康指标 (TD-421: 区分"无告警"与"链路异常") */
  const loadChainHealth = useCallback(async () => {
    try {
      const data = await fetchNotificationChainHealth();
      setChainHealth(data);
    } catch (err) {
      console.error('Notification chain health load failed:', err);
    }
  }, []);

  useEffect(() => {
    loadNotifications();
    loadUnreadCount();
    loadChainHealth();
  }, [loadNotifications, loadUnreadCount, loadChainHealth]);

  /** Mark single as read */
  const markRead = async (id: number) => {
    try {
      await markNotificationRead(id);
      setNotifications((prev) => prev.map((n) => (n.id === id ? { ...n, is_read: true } : n)));
      setUnreadCount((prev) => Math.max(0, prev - 1));
      message.success(t('notifications.msg_mark_success'));
    } catch {
      message.error(t('notifications.msg_mark_failed'));
    }
  };

  /** Mark all as read */
  const markAllRead = async () => {
    try {
      await markAllNotificationsRead();
      setNotifications((prev) => prev.map((n) => ({ ...n, is_read: true })));
      setUnreadCount(0);
      message.success(t('notifications.msg_mark_all_success'));
    } catch {
      message.error(t('notifications.msg_mark_failed'));
    }
  };

  /** Delete single notification */
  const deleteNotification = async (id: number) => {
    try {
      await deleteNotificationApi(id);
      setNotifications((prev) => {
        const filtered = prev.filter((n) => n.id !== id);
        return filtered;
      });
      setTotal((prev) => Math.max(0, prev - 1));
      loadUnreadCount();
      message.success(t('notifications.msg_delete_success'));
    } catch {
      message.error(t('notifications.msg_delete_failed'));
    }
  };

  /** batch delete */
  const batchDelete = async () => {
    if (selectedIds.length === 0) return;
    try {
      await Promise.all(selectedIds.map((id) => deleteNotificationApi(id)));
      setNotifications((prev) => prev.filter((n) => !selectedIds.includes(n.id)));
      setTotal((prev) => Math.max(0, prev - selectedIds.length));
      setSelectedIds([]);
      loadUnreadCount();
      message.success(t('notifications.msg_batch_success', { count: selectedIds.length }));
    } catch {
      message.error(t('notifications.msg_batch_failed'));
    }
  };

  /** category Tab switch */
  const handleCategoryChange = (key: string) => {
    setCategory(key);
    setPage(1);
    setSelectedIds([]);
  };

  /** Toggle selection */
  const toggleSelect = (id: number) => {
    setSelectedIds((prev) => (prev.includes(id) ? prev.filter((i) => i !== id) : [...prev, id]));
  };

  return (
    <PageWrapper
      title={
        <div className="gaf-flex-center gaf-gap-sm">
          <Typography.Title level={4} className="gaf-m-0">
            {t('notifications.page_title')}
          </Typography.Title>
          {unreadCount > 0 && <Badge count={unreadCount} overflowCount={999} size="small" />}
        </div>
      }
      extra={
        <>
          {selectedIds.length > 0 && (
            <Typography.Text type="secondary" className="gaf-text-xs">
              {t('notifications.selected_count', { count: selectedIds.length })}
            </Typography.Text>
          )}
          <Space>
            <Button
              icon={<ReloadOutlined />}
              onClick={() => {
                loadNotifications();
                loadUnreadCount();
                loadChainHealth();
              }}
            >
              {t('notifications.btn_refresh')}
            </Button>
            <Button icon={<CheckCircleOutlined />} onClick={markAllRead} disabled={unreadCount === 0}>
              {t('notifications.btn_mark_all_read')}
            </Button>
            <Popconfirm
              title={t('notifications.confirm_batch_delete', { count: selectedIds.length })}
              onConfirm={batchDelete}
              disabled={selectedIds.length === 0}
            >
              <Button icon={<DeleteOutlined />} danger disabled={selectedIds.length === 0}>
                {t('notifications.btn_batch_delete')} {selectedIds.length > 0 && `(${selectedIds.length})`}
              </Button>
            </Popconfirm>
          </Space>
        </>
      }
    >
      <Card>
        <Tabs
          defaultActiveKey="list"
          items={[
            {
              key: 'list',
              label: (
                <span>
                  <MailOutlined /> {t('notifications.tab_list')}
                </span>
              ),
              children: (
                <>
                  <Tabs
                    activeKey={category}
                    onChange={handleCategoryChange}
                    size="small"
                    items={Object.entries(categoryLabel).map(([key, label]) => ({
                      key,
                      label,
                      icon: key === 'all' ? <MailOutlined /> : undefined,
                    }))}
                  />

                  <Spin spinning={loading}>
                    {notifications.length === 0 && !loading ? (
                      <Empty
                        description={
                          chainHealth && chainHealth.event_count_24h === 0 ? (
                            <Typography.Text type="secondary">
                              {t('notifications.chain_idle_hint')}
                              <br />
                              <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                                {t('notifications.chain_idle_detail')}
                              </Typography.Text>
                            </Typography.Text>
                          ) : (
                            t('notifications.empty')
                          )
                        }
                        style={{ padding: 48 }}
                      />
                    ) : (
                      <div>
                        {(notifications || []).map((item) => {
                          const isSelected = selectedIds.includes(item.id);
                          return (
                            <div
                              key={item.id}
                              className="gaf-mb-xs gaf-py-md gaf-px-lg gaf-radius-md gaf-cursor-pointer"
                              style={{
                                background: isSelected
                                  ? designToken.colorPrimaryBg
                                  : item.is_read
                                    ? designToken.colorBgContainer
                                    : designToken.colorBgLayout,
                              }}
                              onClick={() => toggleSelect(item.id)}
                            >
                              <div className="gaf-flex" style={{ alignItems: 'flex-start' }}>
                                <div className="gaf-mr-md" style={{ marginTop: 2 }}>
                                  <Badge
                                    dot
                                    color={item.is_read ? designToken.colorBorder : designToken.colorPrimary}
                                    offset={[-2, 8]}
                                  />
                                </div>
                                <div className="gaf-flex-1" style={{ minWidth: 0 }}>
                                  <div className="gaf-mb-xs">
                                    <Typography.Text
                                      strong={!item.is_read}
                                      style={{ fontSize: item.is_read ? 14 : 15 }}
                                    >
                                      {item.title}
                                    </Typography.Text>
                                  </div>
                                  <div>
                                    <div
                                      className="gaf-mb-xs"
                                      style={{
                                        overflow: 'hidden',
                                        textOverflow: 'ellipsis',
                                        display: '-webkit-box',
                                        WebkitLineClamp: 2,
                                        WebkitBoxOrient: 'vertical',
                                        color: designToken.colorTextSecondary,
                                      }}
                                    >
                                      {item.content}
                                    </div>
                                    <Space size="small">
                                      {item.category && (
                                        <Tag color={CATEGORY_COLOR[item.category] || 'default'}>
                                          {categoryLabel[item.category] || item.category}
                                        </Tag>
                                      )}
                                      <span className="gaf-text-xs" style={{ color: designToken.colorTextTertiary }}>
                                        {dayjs(item.created_at).locale(getLocale()).format('YYYY-MM-DD HH:mm')}
                                      </span>
                                    </Space>
                                  </div>
                                </div>
                                <div className="gaf-flex-center gaf-gap-xs gaf-ml-md gaf-flex-shrink-0">
                                  {!item.is_read && (
                                    <Button
                                      type="link"
                                      size="small"
                                      icon={<CheckCircleOutlined />}
                                      onClick={(e) => {
                                        e.stopPropagation();
                                        markRead(item.id);
                                      }}
                                    >
                                      {t('notifications.btn_mark_read')}
                                    </Button>
                                  )}
                                  <Popconfirm
                                    title={t('notifications.confirm_delete')}
                                    onConfirm={(e) => {
                                      e?.stopPropagation();
                                      deleteNotification(item.id);
                                    }}
                                    onCancel={(e) => {
                                      e?.stopPropagation();
                                    }}
                                  >
                                    <Button
                                      type="link"
                                      danger
                                      size="small"
                                      icon={<DeleteOutlined />}
                                      onClick={(e) => e.stopPropagation()}
                                    >
                                      {t('notifications.btn_delete')}
                                    </Button>
                                  </Popconfirm>
                                </div>
                              </div>
                            </div>
                          );
                        })}
                      </div>
                    )}
                  </Spin>

                  {total > pageSize && (
                    <div className="gaf-mt-lg" style={{ textAlign: 'right' }}>
                      <Pagination
                        current={page}
                        total={total}
                        pageSize={pageSize}
                        showTotal={(total) => t('notifications.total_count', { count: total })}
                        onChange={(p) => setPage(p)}
                        showSizeChanger={false}
                      />
                    </div>
                  )}
                </>
              ),
            },
            {
              key: 'preferences',
              label: <span>⚙ {t('notifications.tab_preferences')}</span>,
              children: <NotificationPreferences />,
            },
            {
              key: 'webhooks',
              label: <span>🔗 {t('notifications.tab_webhooks')}</span>,
              children: <WebhookConfigPanel />,
            },
          ]}
        />
      </Card>
    </PageWrapper>
  );
}

export default NotificationsPage;
