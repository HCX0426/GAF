/**
 * IPC 通信处理
 * 主进程与渲染进程通信、文件对话框、系统信息获取
 */
import { ipcMain, BrowserWindow, dialog, app, shell } from 'electron';
import fs from 'fs';
import path from 'path';
import { setAutoStart, getAutoStart } from './autostart';
import { loadConfig, saveConfig } from './config';

/** 注册所有 IPC 处理器 */
export function registerIpcHandlers(mainWindow: BrowserWindow): void {
  ipcMain.handle('get-system-info', () => {
    return {
      platform: process.platform,
      arch: process.arch,
      electronVersion: process.versions.electron,
      chromeVersion: process.versions.chrome,
      nodeVersion: process.versions.node,
      appVersion: app.getVersion(),
      appPath: app.getAppPath(),
    };
  });

  ipcMain.handle('get-auto-start', () => {
    return getAutoStart();
  });

  ipcMain.handle('set-auto-start', (_event, enabled: boolean) => {
    setAutoStart(enabled);
    return true;
  });

  ipcMain.handle('get-app-config', () => {
    return loadConfig();
  });

  ipcMain.handle('save-app-config', (_event, config: Record<string, unknown>) => {
    saveConfig(config);
    return true;
  });

  ipcMain.handle(
    'open-file-dialog',
    async (
      _event,
      options: {
        title?: string;
        filters?: Array<{ name: string; extensions: string[] }>;
      }
    ) => {
      const result = await dialog.showOpenDialog(mainWindow, {
        title: options.title || '选择文件',
        properties: ['openFile'],
        filters: options.filters || [{ name: '所有文件', extensions: ['*'] }],
      });
      return result.canceled ? null : result.filePaths[0];
    }
  );

  ipcMain.handle('open-directory-dialog', async (_event, title?: string) => {
    const result = await dialog.showOpenDialog(mainWindow, {
      title: title || '选择目录',
      properties: ['openDirectory'],
    });
    return result.canceled ? null : result.filePaths[0];
  });

  ipcMain.handle('open-external', (_event, url: string) => {
    shell.openExternal(url);
  });

  ipcMain.handle('read-file', async (_event, filePath: string) => {
    try {
      const content = fs.readFileSync(filePath, 'utf-8');
      return { success: true, content };
    } catch (err: any) {
      return { success: false, error: err.message };
    }
  });

  ipcMain.handle('get-server-status', async () => {
    try {
      const config = loadConfig();
      const serverUrl = config.serverUrl || (() => {
        const wsUrl = process.env.GAF_SERVER_URL || 'ws://127.0.0.1:8000/ws/protocol/agents/';
        try {
          const url = new URL(wsUrl);
          return `${url.protocol === 'wss:' ? 'https' : 'http'}://${url.hostname}${url.port ? `:${url.port}` : ''}`;
        } catch { return 'http://127.0.0.1:8000'; }
      })();
      const apiPrefix = process.env.GAF_API_PREFIX || 'api/v2';
      const accountsRoute = process.env.GAF_ROUTE_ACCOUNTS || 'accounts';
      const { net } = require('electron');
      const request = net.request(`${serverUrl}/${apiPrefix}/${accountsRoute}/init/health/`);
      return new Promise((resolve) => {
        request.on('response', (response: any) => {
          resolve({ online: response.statusCode === 200, statusCode: response.statusCode });
        });
        request.on('error', () => {
          resolve({ online: false, statusCode: null });
        });
        request.end();
      });
    } catch {
      return { online: false, statusCode: null };
    }
  });
}
