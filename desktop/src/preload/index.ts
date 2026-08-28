/**
 * Preload 脚本
 * 暴露安全的 IPC API 给渲染进程
 */
import { contextBridge, ipcRenderer } from 'electron';

contextBridge.exposeInMainWorld('electronAPI', {
  getSystemInfo: () => ipcRenderer.invoke('get-system-info'),
  getAutoStart: () => ipcRenderer.invoke('get-auto-start'),
  setAutoStart: (enabled: boolean) => ipcRenderer.invoke('set-auto-start', enabled),
  getAppConfig: () => ipcRenderer.invoke('get-app-config'),
  saveAppConfig: (config: Record<string, unknown>) => ipcRenderer.invoke('save-app-config', config),
  openFileDialog: (options: { title?: string; filters?: Array<{ name: string; extensions: string[] }> }) => ipcRenderer.invoke('open-file-dialog', options),
  openDirectoryDialog: (title?: string) => ipcRenderer.invoke('open-directory-dialog', title),
  openExternal: (url: string) => ipcRenderer.invoke('open-external', url),
  readFile: (filePath: string) => ipcRenderer.invoke('read-file', filePath),
  getServerStatus: () => ipcRenderer.invoke('get-server-status'),

  onUpdateAvailable: (callback: (info: { version: string; releaseNotes: unknown }) => void) => {
    ipcRenderer.on('update-available', (_event, info) => callback(info));
  },
  onUpdateDownloadProgress: (callback: (progress: { percent: number; transferred: number; total: number }) => void) => {
    ipcRenderer.on('update-download-progress', (_event, progress) => callback(progress));
  },
  onUpdateDownloaded: (callback: () => void) => {
    ipcRenderer.on('update-downloaded', () => callback());
  },
  checkForUpdates: () => ipcRenderer.send('check-for-updates'),
});
