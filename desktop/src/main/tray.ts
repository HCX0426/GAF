/**
 * 系统托盘管理
 * 最小化到托盘、右键菜单、托盘图标通知
 */
import { Tray, Menu, BrowserWindow, app, nativeImage } from 'electron';
import path from 'path';

let tray: Tray | null = null;

/** 创建系统托盘 */
export function createTray(mainWindow: BrowserWindow): Tray {
  const iconPath = path.join(__dirname, '../../resources/tray-icon.png');
  const icon = nativeImage.createFromPath(iconPath);

  tray = new Tray(icon.resize({ width: 16, height: 16 }));
  tray.setToolTip('GAF - 通用自动化框架');

  const contextMenu = Menu.buildFromTemplate([
    {
      label: '显示主窗口',
      click: () => {
        mainWindow.show();
        mainWindow.focus();
      },
    },
    { type: 'separator' },
    {
      label: '检查更新',
      click: () => {
        mainWindow.webContents.send('check-for-updates');
      },
    },
    { type: 'separator' },
    {
      label: '退出',
      click: () => {
        (mainWindow as any)._forceClose = true;
        mainWindow.close();
        app.quit();
      },
    },
  ]);

  tray.setContextMenu(contextMenu);

  tray.on('double-click', () => {
    mainWindow.show();
    mainWindow.focus();
  });

  return tray;
}

/** 显示托盘通知 */
export function showTrayNotification(title: string, body: string): void {
  if (tray) {
    tray.displayBalloon({
      title,
      content: body,
      iconType: 'info',
    });
  }
}
