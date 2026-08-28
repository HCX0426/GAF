/**
 * Electron 主进程入口
 * 初始化窗口、托盘、IPC 通信、自动更新
 */
import { app, BrowserWindow } from 'electron';
import path from 'path';
import { createMainWindow } from './window';
import { createTray } from './tray';
import { registerIpcHandlers } from './ipc';
import { checkForUpdates } from './updater';

let mainWindow: BrowserWindow | null = null;

/** 应用就绪回调 */
app.whenReady().then(() => {
  mainWindow = createMainWindow();
  createTray(mainWindow);
  registerIpcHandlers(mainWindow);
  checkForUpdates();

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      mainWindow = createMainWindow();
    }
  });
});

/** 所有窗口关闭回调（macOS 除外） */
app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') {
    app.quit();
  }
});
