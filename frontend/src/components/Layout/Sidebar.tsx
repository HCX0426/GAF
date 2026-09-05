/**
 * Sidebar navigation component
 * 9 top-level menus: Dashboard, GameProfiles, Tasks, Devices, Resources, Accounts, Ops, AI, System
 */
import { useMemo, useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { Menu } from 'antd';
import {
  DashboardOutlined,
  ScheduleOutlined,
  DesktopOutlined,
  InboxOutlined,
  TeamOutlined,
  MonitorOutlined,
  RobotOutlined,
  SettingOutlined,
  AppstoreOutlined,
} from '@ant-design/icons';
import { usePermission } from '@/hooks/usePermission';
import { useAuthStore } from '@/stores/useAuthStore';
import { useLocale, t } from '@/i18n';
import type { MenuProps } from 'antd';
import type { SupportedLocale } from '@/i18n';

type MenuItemType = NonNullable<MenuProps['items']>[number] & {
  permission?: string;
  roles?: string[];
  children?: MenuItemType[];
};

type MenuItemConfig = {
  key: string;
  icon?: React.ReactNode;
  labelKey: string;
  /** 'group' renders a non-clickable sub-section heading inside a menu. */
  type?: 'group' | 'divider';
  permission?: string;
  roles?: string[];
  children?: MenuItemConfig[];
};

const ADMIN_ROLES = ['admin', 'operator'];

function hasRequiredRole(item: MenuItemType): boolean {
  if (!item.roles || item.roles.length === 0) return true;
  const user = useAuthStore.getState().user;
  if (!user?.role) return false;
  return item.roles.includes(user.role);
}

const menuItemConfigs: MenuItemConfig[] = [
  { key: '/dashboard', icon: <DashboardOutlined />, labelKey: 'sidebar.dashboard', permission: 'dashboard.view' },
  // Spec v3 §2.5.1: GameProfile promoted to top-level menu (moved from /system/game-profiles)
  {
    key: 'game-profiles-group',
    icon: <AppstoreOutlined />,
    labelKey: 'sidebar.game_profiles',
    permission: 'resource.view',
    children: [{ key: '/game-profiles', labelKey: 'sidebar.game_profiles_list', permission: 'resource.view' }],
  },
  {
    key: 'tasks-group',
    icon: <ScheduleOutlined />,
    labelKey: 'sidebar.tasks',
    children: [
      { key: '/tasks', labelKey: 'sidebar.task_list', permission: 'task.view' },
      { key: '/tasks/pipeline', labelKey: 'sidebar.pipeline_editor', permission: 'task.view' },
      { key: '/tasks/recordings', labelKey: 'sidebar.recordings', permission: 'task.view' },
      { key: '/tasks/marketplace', labelKey: 'sidebar.marketplace', permission: 'task.view' },
    ],
  },
  {
    key: 'devices-group',
    icon: <DesktopOutlined />,
    labelKey: 'sidebar.devices',
    children: [
      { key: '/devices', labelKey: 'sidebar.device_list', permission: 'device.view' },
      { key: '/devices/emulators', labelKey: 'sidebar.emulators', permission: 'device.view' },
      { key: '/devices/windows', labelKey: 'sidebar.windows', permission: 'device.view' },
      // TD-099 fix 3: /devices/adb-logs exposed in sidebar (was hidden route)
      { key: '/devices/adb-logs', labelKey: 'sidebar.adb_logs', permission: 'device.view' },
    ],
  },
  {
    key: 'resources-group',
    icon: <InboxOutlined />,
    labelKey: 'sidebar.resources',
    children: [
      { key: '/resources', labelKey: 'sidebar.resource_packs', permission: 'resource.view' },
      {
        key: '/resources/template-effectiveness',
        labelKey: 'sidebar.template_effectiveness',
        permission: 'resource.view',
      },
      { key: '/resources/annotation', labelKey: 'sidebar.annotation', permission: 'resource.view' },
    ],
  },
  {
    key: 'accounts-group',
    icon: <TeamOutlined />,
    labelKey: 'sidebar.accounts',
    roles: ADMIN_ROLES,
    children: [
      { key: '/accounts/users', labelKey: 'sidebar.users', permission: 'account.view', roles: ADMIN_ROLES },
      {
        key: '/accounts/game-accounts',
        labelKey: 'sidebar.game_accounts',
        permission: 'account.view',
        roles: ADMIN_ROLES,
      },
    ],
  },
  {
    key: 'ops-group',
    icon: <MonitorOutlined />,
    labelKey: 'sidebar.ops',
    children: [
      { key: '/ops/unattended', labelKey: 'sidebar.unattended', permission: 'execution.view' },
      { key: '/ops/executions', labelKey: 'sidebar.executions', permission: 'execution.view' },
      { key: '/ops/scheduler', labelKey: 'sidebar.scheduler', permission: 'schedule.view' },
      { key: '/ops/monitors', labelKey: 'sidebar.monitors', permission: 'monitor.view' },
      { key: '/ops/analytics', labelKey: 'sidebar.analytics', permission: 'monitor.view' },
      // TD-099 fix 3: /ops/sla exposed in sidebar (was hidden route)
      { key: '/ops/sla', labelKey: 'sidebar.sla', permission: 'monitor.view' },
      // Normalized: log viewing in /ops/logs (8 tabs incl. archive); LLM analysis in /ai/log-analysis
      { key: '/ops/logs', labelKey: 'sidebar.log_center', permission: 'debug.view' },
    ],
  },
  {
    key: 'ai-group',
    icon: <RobotOutlined />,
    labelKey: 'sidebar.ai',
    roles: ADMIN_ROLES,
    children: [
      {
        key: 'ai-group-dialog',
        type: 'group',
        labelKey: 'sidebar.ai_group_dialog',
        children: [
          { key: '/ai/qa', labelKey: 'sidebar.qa', permission: 'ai.view' },
        ],
      },
      {
        key: 'ai-group-analysis',
        type: 'group',
        labelKey: 'sidebar.ai_group_analysis',
        children: [
          { key: '/ai/log-analysis', labelKey: 'sidebar.log_analysis', permission: 'ai.view' },
        ],
      },
      {
        key: 'ai-group-skill',
        type: 'group',
        labelKey: 'sidebar.ai_group_skill',
        children: [
          { key: '/ai/skill-editor', labelKey: 'sidebar.skill_editor', permission: 'ai.view', roles: ADMIN_ROLES },
          { key: '/ai/skill-market', labelKey: 'sidebar.skill_market', permission: 'ai.view' },
        ],
      },
      {
        key: 'ai-group-config',
        type: 'group',
        labelKey: 'sidebar.ai_group_config',
        children: [
          // v3 §2.8.1: AI config + usage moved from /system/* to /ai/* for cohesion
          { key: '/ai/config', labelKey: 'sidebar.ai_config', permission: 'ai.view', roles: ADMIN_ROLES },
          { key: '/ai/usage', labelKey: 'sidebar.ai_usage', permission: 'ai.view', roles: ADMIN_ROLES },
        ],
      },
    ],
  },
  {
    key: 'system-group',
    icon: <SettingOutlined />,
    labelKey: 'sidebar.system',
    roles: ADMIN_ROLES,
    children: [
      { key: '/system/settings', labelKey: 'sidebar.settings', permission: 'settings.view', roles: ADMIN_ROLES },
      // spec 2026-08-29-services-management-monitor: 服务管理页
      { key: '/system/services', labelKey: 'sidebar.services', permission: 'settings.view', roles: ADMIN_ROLES },
      { key: '/system/config', labelKey: 'sidebar.config', permission: 'settings.view', roles: ADMIN_ROLES },
      { key: '/system/api-keys', labelKey: 'sidebar.api_keys', permission: 'settings.view', roles: ADMIN_ROLES },
      // TD-099 fix 3: /ops/backup moved to /system/backup (system admin function)
      { key: '/system/backup', labelKey: 'sidebar.backup', permission: 'settings.view', roles: ADMIN_ROLES },
      {
        key: '/system/feature-flags',
        labelKey: 'sidebar.feature_flags',
        permission: 'settings.view',
        roles: ADMIN_ROLES,
      },
      { key: '/system/audit-log', labelKey: 'sidebar.audit_log', permission: 'settings.view', roles: ADMIN_ROLES },
      {
        key: '/system/notifications',
        labelKey: 'sidebar.notifications',
        permission: 'notification.view',
        roles: ADMIN_ROLES,
      },
      { key: '/system/plugins', labelKey: 'sidebar.plugins', permission: 'plugin.view', roles: ADMIN_ROLES },
    ],
  },
];

/** Translate config keys to current locale labels recursively. */
function translateMenuItems(items: MenuItemConfig[], locale: SupportedLocale): MenuItemType[] {
  return items.map((item) => {
    const translated = {
      key: item.key,
      icon: item.icon,
      label: t(item.labelKey, locale),
      permission: item.permission,
      roles: item.roles,
      type: item.type,
    } as MenuItemType;
    if (item.children) {
      translated.children = translateMenuItems(item.children, locale);
    }
    return translated;
  });
}

/** Recursively filter menu items, hide SubMenu with no visible children */
function filterByPermission(items: MenuItemType[], hasPermission: (p: string) => boolean): MenuProps['items'] {
  return items
    .map((item) => {
      if ('children' in item && item.children) {
        if (item.roles && !hasRequiredRole(item)) return null;
        const filteredChildren = filterByPermission(item.children as MenuItemType[], hasPermission) as NonNullable<
          MenuProps['items']
        >;
        if (filteredChildren.length === 0) return null;
        return { ...item, children: filteredChildren };
      }
      if (item.type === 'divider') return item;
      if (item.permission && !hasPermission(item.permission)) return null;
      if (item.roles && !hasRequiredRole(item)) return null;
      return item;
    })
    .filter(Boolean) as MenuProps['items'];
}

/** Match the most specific menu key for current pathname */
function getSelectedKey(pathname: string): string {
  const allKeys = [
    '/dashboard',
    '/game-profiles',
    '/tasks',
    '/tasks/pipeline',
    '/tasks/recordings',
    '/tasks/marketplace',
    '/devices',
    '/devices/emulators',
    '/devices/windows',
    '/devices/adb-logs',
    '/resources',
    '/resources/template-effectiveness',
    '/resources/annotation',
    '/accounts/users',
    '/accounts/game-accounts',
    '/ops/unattended',
    '/ops/executions',
    '/ops/scheduler',
    '/ops/monitors',
    '/ops/analytics',
    '/ops/sla',
    '/ops/logs',
    '/ai/qa',
    '/ai/skill-editor',
    '/ai/skill-market',
    '/ai/log-analysis',
    '/ai/config',
    '/ai/usage',
    '/system/settings',
    '/system/services',
    '/system/config',
    '/system/api-keys',
    '/system/backup',
    '/system/feature-flags',
    '/system/audit-log',
    '/system/notifications',
    '/system/plugins',
  ];
  let best = '/dashboard';
  for (const key of allKeys) {
    if (pathname === key || pathname.startsWith(key + '/')) {
      if (key.length > best.length) best = key;
    }
  }
  if (
    pathname.startsWith('/tasks/') &&
    !pathname.startsWith('/tasks/pipeline') &&
    !pathname.startsWith('/tasks/recordings') &&
    !pathname.startsWith('/tasks/marketplace')
  ) {
    best = '/tasks';
  }
  return best;
}

/** Calculate which SubMenu should be expanded based on current path */
function getOpenKeys(pathname: string): string[] {
  const segment = '/' + (pathname.split('/')[1] || '');
  const groupMap: Record<string, string> = {
    '/game-profiles': 'game-profiles-group',
    '/tasks': 'tasks-group',
    '/devices': 'devices-group',
    '/resources': 'resources-group',
    '/accounts': 'accounts-group',
    '/ops': 'ops-group',
    '/ai': 'ai-group',
    '/system': 'system-group',
  };
  const groupKey = groupMap[pathname] || groupMap[segment];
  return groupKey ? [groupKey] : [];
}

interface SidebarProps {
  theme?: 'light' | 'dark';
}

export function Sidebar({ theme = 'dark' }: SidebarProps) {
  const navigate = useNavigate();
  const location = useLocation();
  const { hasPermission } = usePermission();
  const locale = useLocale();

  const visibleItems: MenuProps['items'] = useMemo(
    () => filterByPermission(translateMenuItems(menuItemConfigs, locale), hasPermission),
    [hasPermission, locale],
  );

  const selectedKey = getSelectedKey(location.pathname);
  const defaultOpenKeys = getOpenKeys(location.pathname);
  const [openKeys, setOpenKeys] = useState<string[]>(defaultOpenKeys);

  const handleMenuClick: MenuProps['onClick'] = ({ key }) => {
    navigate(key);
  };

  const handleOpenChange: MenuProps['onOpenChange'] = (keys) => {
    setOpenKeys(keys);
  };

  return (
    <Menu
      theme={theme}
      mode="inline"
      selectedKeys={[selectedKey]}
      openKeys={openKeys}
      onOpenChange={handleOpenChange}
      items={visibleItems}
      onClick={handleMenuClick}
      style={{ borderRight: 0 }}
    />
  );
}

export default Sidebar;
