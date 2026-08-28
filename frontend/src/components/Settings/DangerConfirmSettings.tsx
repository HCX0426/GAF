/**
 * DangerConfirmSettings — danger operation confirm settings
 *
 * provides to 6 types of danger operation second confirm switch config, and global total switch.
 * has settings persistence to localStorage (key: gaf_danger_confirm_settings).
 * uses danger color theme visual style, remind user cautious operation.
 */

import { useState, useEffect, useCallback } from 'react';
import { Form, Switch, Card, Button, Divider, Alert, Typography, Space, message } from 'antd';
import { ExclamationCircleOutlined, SaveOutlined } from '@ant-design/icons';

const { Title } = Typography;

/** danger confirm settings data structure */
interface DangerConfirmConfig {
  /** global total switch: close after has danger operation all no need confirm */
  globalEnabled: boolean;
  /** delete task when need confirm */
  deleteTask: boolean;
  /** delete device when need confirm */
  deleteDevice: boolean;
  /** delete account when need confirm */
  deleteAccount: boolean;
  /** delete Pipeline when need confirm */
  deletePipeline: boolean;
  /** clear data when need confirm */
  clearData: boolean;
  /** emergency stop execute when need confirm */
  emergencyStop: boolean;
}

/** localStorage storage key */
const STORAGE_KEY = 'gaf_danger_confirm_settings';

/** default config: has danger operation all need confirm */
const DEFAULT_CONFIG: DangerConfirmConfig = {
  globalEnabled: true,
  deleteTask: true,
  deleteDevice: true,
  deleteAccount: true,
  deletePipeline: true,
  clearData: true,
  emergencyStop: true,
};

/** each switch item config definition */
const SWITCH_ITEMS: { key: keyof DangerConfirmConfig; label: string; description: string }[] = [
  { key: 'deleteTask', label: '删除任务', description: '删除任务前弹出确认对话框' },
  { key: 'deleteDevice', label: '删除设备', description: '移除设备前弹出确认对话框' },
  { key: 'deleteAccount', label: '删除账户', description: '删除游戏账户前弹出确认对话框' },
  { key: 'deletePipeline', label: '删除流程', description: '删除自动化流程前弹出确认对话框' },
  { key: 'clearData', label: '清空数据', description: '批量清空执行记录/日志前弹出确认对话框' },
  { key: 'emergencyStop', label: '紧急停止', description: '紧急停止正在运行的任务前弹出确认对话框' },
];

/**
 * from localStorage load danger confirm settings
 * @returns parse after config object
 */
function loadConfig(): DangerConfirmConfig {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (raw) {
      const parsed = JSON.parse(raw) as Partial<DangerConfirmConfig>;
      return { ...DEFAULT_CONFIG, ...parsed };
    }
  } catch {
    // parse fail use default value
  }
  return DEFAULT_CONFIG;
}

/**
 * applies danger confirm settings save to localStorage
 * @param config to save config object
 */
function saveConfig(config: DangerConfirmConfig): void {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(config));
  } catch {
    // silent failure
  }
}

export function DangerConfirmSettings() {
  const [config, setConfig] = useState<DangerConfirmConfig>(DEFAULT_CONFIG);
  const [messageApi, contextHolder] = message.useMessage();

  /** component mount when load already save config */
  useEffect(() => {
    setConfig(loadConfig());
  }, []);

  /** update single switch item value */
  const handleSwitchChange = useCallback((key: keyof DangerConfirmConfig, value: boolean | string | number) => {
    setConfig((prev) => {
      const next = { ...prev, [key]: value };
      saveConfig(next);
      return next;
    });
  }, []);

  /** recover default config */
  const handleReset = useCallback(() => {
    setConfig(DEFAULT_CONFIG);
    saveConfig(DEFAULT_CONFIG);
    messageApi.success('已恢复默认设置');
  }, [messageApi]);

  return (
    <Card
      style={{ borderLeft: '4px solid #ff4d4f' }}
      title={
        <Space>
          <ExclamationCircleOutlined style={{ color: '#ff4d4f' }} />
          <Title level={4} className="gaf-m-0" style={{ color: '#ff4d4f' }}>
            危险操作确认设置
          </Title>
        </Space>
      }
    >
      {contextHolder}

      <Alert
        type="warning"
        showIcon
        className="gaf-mb-lg"
        title="安全提示"
        description="开启确认后，执行对应危险操作时会弹出二次确认对话框，防止误操作导致不可逆的数据丢失。"
      />

      <Form layout="vertical">
        {/* 全局总开关 */}
        <Form.Item label="全局确认开关" extra="关闭后，以下所有危险操作都将跳过确认步骤直接执行">
          <Switch
            checked={config.globalEnabled}
            onChange={(v) => handleSwitchChange('globalEnabled', v)}
            checkedChildren="已启用"
            unCheckedChildren="已禁用"
            style={{ backgroundColor: config.globalEnabled ? '#ff4d4f' : undefined }}
          />
        </Form.Item>

        <Divider />

        {/* 各类危险操作开关 */}
        {SWITCH_ITEMS.map((item) => (
          <Form.Item key={item.key} label={item.label} extra={item.description}>
            <Switch
              checked={config[item.key]}
              disabled={!config.globalEnabled}
              onChange={(v) => handleSwitchChange(item.key, v)}
              checkedChildren="需确认"
              unCheckedChildren="免确认"
              style={{
                backgroundColor: config.globalEnabled && config[item.key] ? '#ff4d4f' : undefined,
              }}
            />
          </Form.Item>
        ))}

        <Divider />

        {/* 操作按钮区 */}
        <Space>
          <Button
            danger
            icon={<SaveOutlined />}
            onClick={() => {
              saveConfig(config);
              messageApi.success('设置已保存');
            }}
          >
            保存设置
          </Button>
          <Button onClick={handleReset}>恢复默认</Button>
        </Space>
      </Form>
    </Card>
  );
}

export default DangerConfirmSettings;
