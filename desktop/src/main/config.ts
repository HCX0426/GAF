/**
 * 应用配置管理
 * 读写本地配置文件（server URL、开机自启、最小化到托盘等）
 */
import fs from 'fs';
import path from 'path';
import { app } from 'electron';

interface AppConfig {
  serverUrl: string;
  minimizeToTray: boolean;
  autoStart: boolean;
  windowBounds: { width: number; height: number; x?: number; y?: number } | null;
}

/** 从 GAF_SERVER_URL 环境变量推导 HTTP base URL（若未设置则使用默认值） */
function deriveDefaultServerUrl(): string {
  const wsPath = process.env.GAF_WS_AGENT_PATH || 'ws/protocol/agents/';
  const wsUrl = process.env.GAF_SERVER_URL || `ws://127.0.0.1:8000/${wsPath}`;
  try {
    const url = new URL(wsUrl);
    const scheme = url.protocol === 'wss:' ? 'https' : 'http';
    return `${scheme}://${url.hostname}${url.port ? `:${url.port}` : ''}`;
  } catch {
    return 'http://127.0.0.1:8000';
  }
}

const DEFAULT_CONFIG: AppConfig = {
  serverUrl: deriveDefaultServerUrl(),
  minimizeToTray: true,
  autoStart: false,
  windowBounds: null,
};

/** 获取配置文件路径 */
function getConfigPath(): string {
  const userDataPath = app.getPath('userData');
  return path.join(userDataPath, 'config.json');
}

/** 加载应用配置 */
export function loadConfig(): AppConfig {
  try {
    const configPath = getConfigPath();
    if (fs.existsSync(configPath)) {
      const content = fs.readFileSync(configPath, 'utf-8');
      return { ...DEFAULT_CONFIG, ...JSON.parse(content) };
    }
  } catch {
    // 配置读取失败，使用默认值
  }
  return { ...DEFAULT_CONFIG };
}

/** 保存应用配置 */
export function saveConfig(config: Partial<AppConfig>): void {
  try {
    const currentConfig = loadConfig();
    const newConfig = { ...currentConfig, ...config };
    const configPath = getConfigPath();
    fs.writeFileSync(configPath, JSON.stringify(newConfig, null, 2), 'utf-8');
  } catch (err) {
    console.error('保存配置失败:', err);
  }
}
