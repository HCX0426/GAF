/**
 * 统一时间格式化工具 (归一化, 2026-08-29).
 *
 * 此前 TodaySchedule/ExecutionQueuePreview/HeaderStatusIndicator/AlertSummary
 * 各自维护一份 try/catch + toLocaleString 的同构函数, 现收敛为单一权威源.
 */

/** ISO 时间 → "HH:MM" (中文 locale 24h); 解析失败原样返回. */
export function formatTimeHM(isoStr: string): string {
  try {
    return new Date(isoStr).toLocaleTimeString('zh-CN', {
      hour: '2-digit',
      minute: '2-digit',
    });
  } catch {
    return isoStr;
  }
}

/** ISO 时间 → "MM-DD HH:MM" (中文 locale); 解析失败原样返回. */
export function formatDateHM(isoStr: string): string {
  try {
    return new Date(isoStr).toLocaleString('zh-CN', {
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
    });
  } catch {
    return isoStr;
  }
}