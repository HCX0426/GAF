/**
 * 自动更新模块
 * 使用 electron-updater 实现 Windows 自动更新
 */
import { autoUpdater } from 'electron-updater';
import { BrowserWindow } from 'electron';

/** 检查更新 */
export function checkForUpdates(): void {
  autoUpdater.autoDownload = false;
  autoUpdater.autoInstallOnAppQuit = true;

  autoUpdater.on('update-available', (info) => {
    const windows = BrowserWindow.getAllWindows();
    if (windows.length > 0) {
      windows[0].webContents.send('update-available', {
        version: info.version,
        releaseNotes: info.releaseNotes,
      });
    }
  });

  autoUpdater.on('download-progress', (progressInfo) => {
    const windows = BrowserWindow.getAllWindows();
    if (windows.length > 0) {
      windows[0].webContents.send('update-download-progress', {
        percent: progressInfo.percent,
        transferred: progressInfo.transferred,
        total: progressInfo.total,
      });
    }
  });

  autoUpdater.on('update-downloaded', () => {
    const windows = BrowserWindow.getAllWindows();
    if (windows.length > 0) {
      windows[0].webContents.send('update-downloaded');
    }
  });

  autoUpdater.on('error', (err) => {
    console.error('自动更新错误:', err);
  });

  if (process.env.VITE_DEV_SERVER_URL) {
    return;
  }

  autoUpdater.checkForUpdates().catch(() => {});
}

/** 下载并安装更新 */
export function downloadAndUpdate(): void {
  autoUpdater.downloadUpdate();
}

/** 退出并安装更新 */
export function quitAndInstall(): void {
  autoUpdater.quitAndInstall();
}
