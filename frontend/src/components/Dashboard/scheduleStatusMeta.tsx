/**
 * 今日日程状态元数据 — 单一权威源 (归一化, 2026-08-29).
 *
 * 背景: TodaySchedule 与 ExecutionQueuePreview 各自维护一份 status → 图标/文案映射,
 * 曾因"只改一处"导致 planned 状态漏加 (N219 教训). 状态集合/文案/语义色统一在此,
 * 组件只做个性化渲染 (TodaySchedule 用 theme token 着色, Preview 用 antd Tag 语义色).
 */
import type { ReactNode } from 'react';
import type { GlobalToken } from 'antd/es/theme/interface';
import {
  CalendarOutlined,
  CheckCircleFilled,
  ClockCircleFilled,
  ExclamationCircleFilled,
  LoadingOutlined,
  MinusCircleFilled,
} from '@ant-design/icons';
import type { ScheduleItemStatus } from '@/types/models/schedule';

/** antd 语义色 preset (Tag color / Theme token 映射键) */
export type StatusTagColor = 'default' | 'processing' | 'success' | 'error' | 'warning';

export interface ScheduleStatusMeta {
  /** 展示文案 */
  label: string;
  /** antd 语义色 (Tag preset; TodaySchedule 经 tokenColorForStatus 映射为主题色) */
  tagColor: StatusTagColor;
  /** 未着色图标 (由消费组件决定上色方式) */
  icon: ReactNode;
}

export const SCHEDULE_STATUS_META: Record<ScheduleItemStatus, ScheduleStatusMeta> = {
  planned: { label: '计划中', tagColor: 'default', icon: <CalendarOutlined /> },
  pending: { label: '待执行', tagColor: 'default', icon: <ClockCircleFilled /> },
  running: { label: '进行中', tagColor: 'processing', icon: <LoadingOutlined /> },
  completed: { label: '已完成', tagColor: 'success', icon: <CheckCircleFilled /> },
  failed: { label: '失败', tagColor: 'error', icon: <ExclamationCircleFilled /> },
  skipped: { label: '已跳过', tagColor: 'warning', icon: <MinusCircleFilled /> },
};

/** 未知/缺省状态兜底 (与历史行为一致: 回落 pending 元数据) */
export function resolveScheduleStatus(status: string | undefined): ScheduleItemStatus {
  return (status && status in SCHEDULE_STATUS_META ? status : 'pending') as ScheduleItemStatus;
}

/** 语义色 → antd theme token (TodaySchedule 的 Timeline/Tag 着色用) */
export function tokenColorForStatus(token: GlobalToken, status: ScheduleItemStatus): string {
  const meta = SCHEDULE_STATUS_META[status] ?? SCHEDULE_STATUS_META.pending;
  const map: Record<StatusTagColor, string> = {
    default: token.colorTextQuaternary,
    processing: token.colorPrimary,
    success: token.colorSuccess,
    error: token.colorError,
    warning: token.colorWarning,
  };
  return map[meta.tagColor];
}