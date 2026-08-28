/**
 * app main layout component — GAF V2 Phase 10
 * includes sidebar navigation, top user info bar ( includes notify bell, theme switch,DPI scale ), content area
 * integrate HeaderStatusIndicator system status light + GlobalSearchModal (Ctrl+K) global search
 * Win11 acrylic visual effect + theme system + DPI adapt
 */
import { useState, useEffect, useRef, useCallback } from 'react';
import { Outlet, useNavigate, useLocation } from 'react-router-dom';
import { Layout, Button, Dropdown, Avatar, Badge, theme as antTheme, Modal, Form, Input, App, Space, Tag } from 'antd';
import {
  MenuFoldOutlined,
  MenuUnfoldOutlined,
  UserOutlined,
  LogoutOutlined,
  BellOutlined,
  SearchOutlined,
  UserSwitchOutlined,
  KeyOutlined,
  PlusOutlined,
  LockOutlined,
  SoundOutlined,
  SoundFilled,
} from '@ant-design/icons';
import Sidebar from './Sidebar';
import HeaderStatusIndicator from './HeaderStatusIndicator';
import GlobalSearchModal from '@/components/Common/GlobalSearchModal';
import ErrorBoundary from '@/components/Common/ErrorBoundary';
import OnboardingTour from '@/components/Common/OnboardingTour';
import { useAuthStore } from '@/stores/useAuthStore';
import { useDeviceStore } from '@/stores/useDeviceStore';
import { useAudioAlert } from '@/hooks/useAudioAlert';
import { useNotificationWebSocket } from '@/hooks/useNotificationWebSocket';
import LanguageSwitcher from '@/i18n/LanguageSwitcher';
import ThemeSwitcher from '@/theme/ThemeSwitcher';
import DpiScaler from '@/components/Common/DpiScaler';
import { getStoredTheme, resolveTheme, subscribeTheme } from '@/theme';
import type { ThemeMode } from '@/theme';
import { classifyError } from '@/utils/errorHandler';
import { fetchUnreadCount } from '@/api/misc';
import { wsClient } from '@/websocket/client';
import type { SavedAccount } from '@/utils/tokenStore';
import type { MenuProps } from 'antd';
import { useTranslation } from '@/i18n';
import '../../styles/acrylic.css';

const { Header, Sider, Content } = Layout;

/** Change password form values */
interface ChangePasswordFormValues {
  old_password: string;
  new_password: string;
  confirm_password: string;
}

/** Add account form values */
interface AddAccountFormValues {
  username: string;
  password: string;
}

/** Change password modal content — isolated to avoid useForm unconnected warning */
function ChangePasswordModalContent({
  loading,
  onSubmit,
}: {
  loading: boolean;
  onSubmit: (values: ChangePasswordFormValues) => void;
}) {
  const t = useTranslation();
  const [form] = Form.useForm<ChangePasswordFormValues>();
  return (
    <Form form={form} layout="vertical" onFinish={onSubmit} requiredMark="optional">
      <Form.Item
        name="old_password"
        label={t('layout.cp_old_password_label')}
        rules={[{ required: true, message: t('layout.cp_old_password_required') }]}
      >
        <Input.Password
          prefix={<LockOutlined />}
          placeholder={t('layout.cp_old_password_placeholder')}
          autoComplete="current-password"
        />
      </Form.Item>
      <Form.Item
        name="new_password"
        label={t('layout.cp_new_password_label')}
        rules={[{ required: true, min: 6, message: t('layout.cp_new_password_required') }]}
      >
        <Input.Password
          prefix={<LockOutlined />}
          placeholder={t('layout.cp_new_password_placeholder')}
          autoComplete="new-password"
        />
      </Form.Item>
      <Form.Item
        name="confirm_password"
        label={t('layout.cp_confirm_password_label')}
        dependencies={['new_password']}
        rules={[
          { required: true, message: t('layout.cp_confirm_password_required') },
          ({ getFieldValue }) => ({
            validator(_, value) {
              if (!value || getFieldValue('new_password') === value) {
                return Promise.resolve();
              }
              return Promise.reject(new Error(t('layout.cp_password_mismatch')));
            },
          }),
        ]}
      >
        <Input.Password
          prefix={<LockOutlined />}
          placeholder={t('layout.cp_confirm_password_placeholder')}
          autoComplete="new-password"
        />
      </Form.Item>
      <Form.Item className="gaf-m-0" style={{ textAlign: 'right' }}>
        <Button type="primary" htmlType="submit" loading={loading}>
          {t('layout.cp_btn_submit')}
        </Button>
      </Form.Item>
    </Form>
  );
}

/** Add account modal content — isolated to avoid useForm unconnected warning */
function AddAccountModalContent({
  loading,
  onSubmit,
}: {
  loading: boolean;
  onSubmit: (values: AddAccountFormValues) => void;
}) {
  const t = useTranslation();
  const { token } = antTheme.useToken();
  const [form] = Form.useForm<AddAccountFormValues>();
  return (
    <>
      <Form form={form} layout="vertical" requiredMark="optional" onFinish={onSubmit}>
        <Form.Item
          name="username"
          label={t('layout.aa_username_label')}
          rules={[{ required: true, message: t('layout.aa_username_required') }]}
        >
          <Input placeholder={t('layout.aa_username_placeholder')} autoComplete="username" />
        </Form.Item>
        <Form.Item
          name="password"
          label={t('layout.aa_password_label')}
          rules={[{ required: true, message: t('layout.aa_password_required') }]}
        >
          <Input.Password placeholder={t('layout.aa_password_placeholder')} autoComplete="current-password" />
        </Form.Item>
        <Form.Item className="gaf-m-0" style={{ textAlign: 'right' }}>
          <Button type="primary" htmlType="submit" loading={loading}>
            {t('layout.aa_btn_submit')}
          </Button>
        </Form.Item>
      </Form>
      <div className="gaf-text-sm gaf-mt-sm" style={{ color: token.colorTextTertiary }}>
        {t('layout.add_account_hint')}
      </div>
    </>
  );
}

/** app main layout */
export function AppLayout() {
  const t = useTranslation();
  const { message: antMessage } = App.useApp();
  const [collapsed, setCollapsed] = useState(false);
  const [unreadCount, setUnreadCount] = useState(0);
  const [searchVisible, setSearchVisible] = useState(false);
  const [siderTheme, setSiderTheme] = useState<'light' | 'dark'>(() => resolveTheme(getStoredTheme()));
  const [changePwdOpen, setChangePwdOpen] = useState(false);
  const [addAccountOpen, setAddAccountOpen] = useState(false);
  const [switching, setSwitching] = useState(false);
  const [pwdLoading, setPwdLoading] = useState(false);

  const { user, logout, isAuthenticated, switchAccount, getSavedAccountsList, changePassword, login } = useAuthStore();
  const navigate = useNavigate();
  const location = useLocation();
  const { token: themeToken } = antTheme.useToken();
  const { isMuted, playAlert, mute, unmute } = useAudioAlert();

  /** subscribe theme change more, sync sidebar theme */
  useEffect(() => {
    return subscribeTheme((mode: ThemeMode) => {
      setSiderTheme(resolveTheme(mode));
    });
  }, []);

  /** Fetch unread notification count on auth, then rely on WS push for
   *  real-time increments. A 5-minute safety-net poll corrects drift
   *  (e.g. notifications marked read on another device/session). */
  const unreadControllerRef = useRef<AbortController | null>(null);
  /** skip StrictMode test mount to avoid spurious ERR_ABORTED */
  const unreadIsRealMountRef = useRef(false);
  useEffect(() => {
    if (!unreadIsRealMountRef.current) {
      unreadIsRealMountRef.current = true;
      return;
    }
    if (!isAuthenticated) return;
    const doFetch = () => {
      const controller = new AbortController();
      unreadControllerRef.current?.abort();
      unreadControllerRef.current = controller;
      fetchUnreadCount(controller.signal)
        .then((data) => {
          if (!controller.signal.aborted) setUnreadCount(data.unread_count || 0);
        })
        .catch((err: unknown) => {
          // M21: ignore AbortError (fetch) and CanceledError (axios) from aborted
          // in-flight requests when the polling interval refreshes or component unmounts.
          if (err instanceof Error && (err.name === 'AbortError' || err.name === 'CanceledError')) return;
          else {
            console.error('Unread count poll failed:', err);
          }
        });
    };
    doFetch();
    // Safety-net poll: 5 minutes (down from 30s). Real-time increments are
    // handled by the WS notification callback below.
    const interval = setInterval(doFetch, 300000);
    return () => {
      clearInterval(interval);
      unreadControllerRef.current?.abort();
      unreadControllerRef.current = null;
    };
  }, [isAuthenticated]);

  /** Ctrl+K global search shortcut key */
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
        e.preventDefault();
        setSearchVisible((prev) => !prev);
      }
      if (e.key === 'Escape') {
        setSearchVisible(false);
      }
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, []);

  /**
   * Subscribe the device store to device.* WS events so any change pushed by
   * the backend (PATCH from another tab, screenshot test, registration)
   * refreshes the device list across all open pages. The subscription lives
   * for the whole authenticated session; unsubscribe on logout.
   *
   * Also registers a WS reconnect callback that triggers a full refreshAll
   * so the device list catches up on any events missed while the connection
   * was down. This replaces the per-page visibilitychange polling that
   * DeviceCenterPage used to do.
   */
  useEffect(() => {
    if (!isAuthenticated) return;
    const unsubscribe = useDeviceStore.getState().subscribeToDeviceUpdates();
    const handleReconnect = () => {
      void useDeviceStore.getState().refreshAll();
    };
    wsClient.onReconnect(handleReconnect);
    return () => {
      unsubscribe();
      wsClient.offReconnect(handleReconnect);
    };
  }, [isAuthenticated]);

  /** Wire audio alerts + unread-count increments to user-scoped notification
   *  WebSocket events. New notifications increment the badge in real time
   *  so we no longer need the 30s polling interval. */
  useNotificationWebSocket(isAuthenticated, (payload) => {
    const level = payload.level;
    if (level === 'error') {
      playAlert('critical');
    } else if (level === 'warning') {
      playAlert('warning');
    }
    // Increment unread count — the backend pushed a new notification.
    setUnreadCount((prev) => prev + 1);
  });

  /** user logout handle */
  const handleLogout = async () => {
    wsClient.disconnect();
    await logout();
    navigate('/login');
  };

  /** switch account */
  const handleSwitchAccount = useCallback(
    async (username: string) => {
      const currentUsername = user?.username || '';
      if (username === currentUsername) {
        antMessage.info(t('layout.msg_already_current_account'));
        return;
      }
      setSwitching(true);
      try {
        await switchAccount(username);
        antMessage.success(t('layout.msg_account_switched', { username }));
      } catch (err: unknown) {
        const classified = classifyError(err);
        antMessage.error(t('layout.msg_switch_failed', { message: classified.message }));
      } finally {
        setSwitching(false);
      }
    },
    [user, switchAccount, antMessage, t],
  );

  /** change password submit */
  const handleChangePasswordSubmit = useCallback(
    async (values: ChangePasswordFormValues) => {
      setPwdLoading(true);
      try {
        await changePassword(values.old_password, values.new_password);
        antMessage.success(t('layout.msg_password_changed'));
        setChangePwdOpen(false);
      } catch {
        antMessage.error(t('layout.msg_password_change_failed'));
      } finally {
        setPwdLoading(false);
      }
    },
    [changePassword, antMessage, t],
  );

  /** TD-335 spec-133: add account submit — replaces querySelector + btn.click()
   *  hack. Uses the same pattern as handleChangePasswordSubmit (form.onSubmit
   *  triggers store.login, which auto-saves the account via saveAccountToStore). */
  const handleAddAccountSubmit = useCallback(
    async (values: AddAccountFormValues) => {
      setSwitching(true);
      try {
        await login(values.username, values.password, true);
        antMessage.success(t('layout.msg_account_added', { username: values.username }));
        setAddAccountOpen(false);
      } catch (err: unknown) {
        const classified = classifyError(err);
        antMessage.error(t('layout.msg_add_account_failed', { message: classified.message }));
      } finally {
        setSwitching(false);
      }
    },
    [login, antMessage, t],
  );

  /** get already save account list */
  const savedAccounts = getSavedAccountsList();
  const currentUsername = user?.username || '';

  /** build user dropdown menu single item */
  const dropdownItems: MenuProps['items'] = [
    {
      key: 'current-user',
      label: (
        <Space>
          <Avatar size="small" className="gaf-text-sm" style={{ backgroundColor: '#1677ff' }}>
            {currentUsername ? currentUsername.charAt(0).toUpperCase() : '?'}
          </Avatar>
          <span className="gaf-font-medium">{currentUsername || t('layout.not_logged_in')}</span>
          {savedAccounts.length > 1 && (
            <Tag color="blue">{t('layout.accounts_count', { count: savedAccounts.length })}</Tag>
          )}
        </Space>
      ),
      disabled: true,
    },
    {
      type: 'divider',
    },
    {
      key: 'switch-group',
      label: t('layout.menu_switch_account'),
      icon: <UserSwitchOutlined />,
      children: savedAccounts
        .filter((account: SavedAccount) => account.username !== currentUsername)
        .map((account: SavedAccount) => ({
          key: `switch-${account.username}`,
          label: (
            <Space>
              <Avatar size="small" className="gaf-text-sm" style={{ backgroundColor: '#1890ff' }}>
                {account.username.charAt(0).toUpperCase()}
              </Avatar>
              <span>{account.username}</span>
            </Space>
          ),
          onClick: () => handleSwitchAccount(account.username),
          disabled: switching,
        })),
    },
    {
      type: 'divider',
    },
    {
      key: 'add-account',
      icon: <PlusOutlined />,
      label: t('layout.menu_add_account'),
      onClick: () => setAddAccountOpen(true),
    },
    {
      key: 'change-password',
      icon: <KeyOutlined />,
      label: t('layout.menu_change_password'),
      onClick: () => setChangePwdOpen(true),
    },
    {
      type: 'divider',
    },
    {
      key: 'logout',
      icon: <LogoutOutlined />,
      label: t('layout.menu_logout'),
      danger: true,
      onClick: handleLogout,
    },
  ];

  return (
    <Layout style={{ minHeight: '100vh' }}>
      <Sider
        trigger={null}
        collapsible
        collapsed={collapsed}
        theme={siderTheme}
        width={220}
        className="win11-sidebar gaf-flex-col"
        style={{ height: '100vh', position: 'fixed', left: 0, top: 0, bottom: 0 }}
      >
        <div
          className="gaf-flex-center"
          style={{
            height: 48,
            margin: 12,
            color: siderTheme === 'dark' ? '#fff' : 'rgba(0, 0, 0, 0.88)',
            fontSize: collapsed ? 16 : 20,
            fontWeight: 'bold',
            whiteSpace: 'nowrap',
            overflow: 'hidden',
            flexShrink: 0,
            justifyContent: 'center',
          }}
        >
          {collapsed ? 'GAF' : t('layout.brand')}
        </div>
        <div className="gaf-flex-1" style={{ overflow: 'auto', minHeight: 0 }}>
          <Sidebar theme={siderTheme} />
        </div>
      </Sider>
      <Layout style={{ marginLeft: collapsed ? 80 : 220, transition: 'margin-left 0.2s' }}>
        <Header
          className="win11-header gaf-flex-between"
          style={{
            padding: '0 24px',
            position: 'sticky',
            top: 0,
            zIndex: 10,
            height: 56,
            lineHeight: '56px',
          }}
        >
          <Button
            type="text"
            icon={collapsed ? <MenuUnfoldOutlined /> : <MenuFoldOutlined />}
            onClick={() => setCollapsed(!collapsed)}
            aria-label={collapsed ? t('layout.aria_expand_menu') : t('layout.aria_collapse_menu')}
            className="gaf-text-md"
            style={{ width: 48, height: 48 }}
          />
          <div className="gaf-flex-center gaf-gap-sm">
            <DpiScaler />
            <ThemeSwitcher />
            <HeaderStatusIndicator />
            <SearchOutlined
              className="gaf-text-md"
              style={{ cursor: 'pointer', color: themeToken.colorTextSecondary }}
              onClick={() => setSearchVisible(true)}
              title={t('layout.title_global_search')}
            />
            <Badge count={unreadCount} size="small" offset={[-2, 2]}>
              <BellOutlined
                className="gaf-text-lg"
                style={{ cursor: 'pointer', color: themeToken.colorTextSecondary }}
                onClick={() => navigate('/notifications')}
              />
            </Badge>
            {isMuted ? (
              <SoundOutlined
                className="gaf-text-md"
                style={{ cursor: 'pointer', color: themeToken.colorTextSecondary }}
                onClick={unmute}
                title={t('layout.title_unmute')}
              />
            ) : (
              <SoundFilled
                className="gaf-text-md"
                style={{ cursor: 'pointer', color: themeToken.colorTextSecondary }}
                onClick={() => mute()}
                title={t('layout.title_mute')}
              />
            )}
            <LanguageSwitcher />
            <Dropdown menu={{ items: dropdownItems }} placement="bottomRight">
              <div className="gaf-flex-center gaf-gap-sm" style={{ cursor: 'pointer' }}>
                <Avatar icon={<UserOutlined />} />
                <span>{user?.username || t('layout.user_default')}</span>
              </div>
            </Dropdown>
          </div>
        </Header>
        <Content
          style={{
            padding: 'var(--spacing-lg, 16px)',
            minHeight: 280,
          }}
        >
          <div
            className="acrylic-panel"
            style={{
              background: themeToken.colorBgContainer,
              borderRadius: 'var(--radius-md, 8px)',
              boxShadow: 'var(--shadow-sm, 0 1px 2px rgba(0,0,0,0.06))',
              padding: 'var(--spacing-lg, 16px)',
              minHeight: '100%',
            }}
          >
            <ErrorBoundary key={location.pathname}>
              <Outlet />
            </ErrorBoundary>
          </div>
        </Content>
        <GlobalSearchModal visible={searchVisible} onClose={() => setSearchVisible(false)} />

        {/* 更改密码 Modal */}
        <Modal
          title={t('layout.modal_change_password_title')}
          open={changePwdOpen}
          onCancel={() => setChangePwdOpen(false)}
          footer={null}
          destroyOnHidden
        >
          <ChangePasswordModalContent loading={pwdLoading} onSubmit={handleChangePasswordSubmit} />
        </Modal>

        {/* TD-335 spec-133: 添加账户 Modal — footer=null + form-internal submit
            替代 querySelector('.ant-modal:has(...)') + btn.click() 反模式 */}
        <Modal
          title={t('layout.modal_add_account_title')}
          open={addAccountOpen}
          onCancel={() => setAddAccountOpen(false)}
          footer={null}
          destroyOnHidden
        >
          <AddAccountModalContent loading={switching} onSubmit={handleAddAccountSubmit} />
        </Modal>
        <OnboardingTour isFirstLogin={user?.is_first_login} />
      </Layout>
    </Layout>
  );
}

export default AppLayout;
