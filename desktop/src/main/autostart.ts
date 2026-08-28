/**
 * 开机自启管理
 * Windows 注册表操作实现开机自启
 */
import { app } from 'electron';

const REG_KEY = 'HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run';
const APP_NAME = 'GAF';

/** 获取开机自启状态 */
export function getAutoStart(): boolean {
  if (process.platform !== 'win32') {
    return app.getLoginItemSettings().openAtLogin;
  }

  try {
    const result = require('child_process').execSync(
      `reg query "${REG_KEY}" /v "${APP_NAME}"`,
      { encoding: 'utf-8', windowsHide: true }
    );
    return result.includes(APP_NAME);
  } catch {
    return false;
  }
}

/** 设置开机自启 */
export function setAutoStart(enabled: boolean): void {
  if (process.platform !== 'win32') {
    app.setLoginItemSettings({ openAtLogin: enabled });
    return;
  }

  try {
    if (enabled) {
      const exePath = app.getPath('exe');
      require('child_process').execSync(
        `reg add "${REG_KEY}" /v "${APP_NAME}" /t REG_SZ /d "${exePath}" /f`,
        { windowsHide: true }
      );
    } else {
      require('child_process').execSync(
        `reg delete "${REG_KEY}" /v "${APP_NAME}" /f`,
        { windowsHide: true }
      );
    }
  } catch (err) {
    console.error('设置开机自启失败:', err);
  }
}
