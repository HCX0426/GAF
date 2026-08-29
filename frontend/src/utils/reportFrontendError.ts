/**
 * P0-10 fix (AI 可调试性, 2026-07-27): 前端错误上报工具。
 *
 * 之前前端崩溃只 console.error, 后端/AI 完全看不到。AI 调试任务级失败时
 * 无法区分 "前端渲染崩溃" vs "后端 API 500" vs "agent 执行失败", 三类错误
 * 混在 backend 日志里无法区分。本工具把前端错误 POST 到后端, 后端记入
 * Django logger (gaf_core.frontend_error), AI 调试时 grep 该 logger 即可
 * 看到前端崩溃栈。
 *
 * C3 (spec 2026-07-30-debug-directory-restructure): 上报时附带 trace_id +
 * page_slug, 后端按 page_slug 归集到 debug/<YYYYMMDD>/frontend/<page_slug>/HH/
 * console.jsonl, 让 AI 调试时能 grep trace_id 串联 agent/backend/frontend 三端日志。
 *
 * 设计:
 * - 防抖: 同一 message + source 1 分钟内只上报一次 (避免崩溃循环刷屏)
 * - 非阻塞: 上报失败只 console.warn, 不抛二次错误
 * - 降级: 无网络/后端不可达时静默丢弃 (前端崩溃优先保证 UI 可用)
 * - 上下文: 带 url / userAgent / sessionId / 当前路由 / trace_id / page_slug
 *           (帮 AI 定位现场 + 串联三端日志)
 */
import axios from 'axios';
import { API_PREFIX } from '@/config/app';
import { getPageSlug } from '@/utils/pageSlug';
import { getLastTraceId } from '@/utils/traceId';

/** 已上报错误的去重缓存 (key = message+source, value = 上报时间戳) */
const reportedCache = new Map<string, number>();
/** 去重窗口: 1 分钟内同一错误只上报一次 */
const DEDUP_WINDOW_MS = 60_000;
/** 单次上报最大栈长度 (防止超大栈撑爆 backend 日志) */
const MAX_STACK_LENGTH = 4000;

interface FrontendErrorReport {
  message: string;
  source?: string;
  lineno?: number;
  colno?: number;
  stack?: string;
  error_type?: string;
  /** 触发场景: 'window.onerror' / 'unhandledrejection' / 'error_boundary' */
  trigger: 'window.onerror' | 'unhandledrejection' | 'error_boundary';
  /** 当前页面 URL (含 hash 路由) */
  page_url?: string;
  user_agent?: string;
  /** 会话 ID ( sessionStorage 里随机生成, 同会话内一致) */
  session_id?: string;
  /** C3: trace_id (从 sessionStorage 取最近一次的, 串联 agent/backend 日志) */
  trace_id?: string;
  /** C3: page_slug (从 window.location.pathname 提取, 按 page 归集 console.jsonl) */
  page_slug?: string;
  /** 附加上下文 (如 React ErrorInfo.componentStack) */
  extra?: Record<string, unknown>;
}

/** 获取或创建会话 ID (同一 tab 生命周期内一致) */
function getSessionId(): string {
  const KEY = 'gaf_frontend_session_id';
  let sid = sessionStorage.getItem(KEY);
  if (!sid) {
    sid = `fsess-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
    sessionStorage.setItem(KEY, sid);
  }
  return sid;
}

/** 上报前端错误到后端。非阻塞, 失败只 console.warn。 */
export async function reportFrontendError(
  report: Omit<FrontendErrorReport, 'page_url' | 'user_agent' | 'session_id'>,
): Promise<void> {
  try {
    // 去重: 同一 message+source 1 分钟内只上报一次
    const dedupKey = `${report.message}::${report.source || ''}::${report.trigger}`;
    const now = Date.now();
    const lastReported = reportedCache.get(dedupKey);
    if (lastReported && now - lastReported < DEDUP_WINDOW_MS) {
      return; // 1 分钟内已上报过, 跳过
    }
    reportedCache.set(dedupKey, now);

    // 清理过期缓存项 (防止 Map 无限增长)
    if (reportedCache.size > 100) {
      for (const [k, ts] of reportedCache) {
        if (now - ts > DEDUP_WINDOW_MS) {
          reportedCache.delete(k);
        }
      }
    }

    const fullReport: FrontendErrorReport = {
      ...report,
      stack: report.stack ? report.stack.slice(0, MAX_STACK_LENGTH) : undefined,
      page_url: window.location.href,
      user_agent: navigator.userAgent,
      session_id: getSessionId(),
      // C3: 自动附加 trace_id + page_slug。caller 不需传, 也不应传 — 这两个字段
      // 的"当前值"在出错瞬间确定, 由 reportFrontendError 统一采集避免漏带。
      // trace_id 取 sessionStorage 里最近一次的 (axios 拦截器在每次请求时更新),
      // 为空字符串时表示无 HTTP 请求上下文 (如纯渲染崩溃) — backend 仍会落盘,
      // AI 调试时按 "trace_id 为空" 过滤即可。
      trace_id: getLastTraceId() || '',
      page_slug: getPageSlug(),
    };

    // 用裸 axios (不走 client.ts 拦截器), 避免循环: 拦截器内出错又触发上报
    await axios.post(`${API_PREFIX}/logs/frontend-errors/`, fullReport, {
      headers: { 'Content-Type': 'application/json' },
      timeout: 5000, // 5s 超时, 不阻塞 UI
      // 不带 Authorization header — 前端崩溃时 token 可能不可用,
      // 后端 endpoint 允许匿名上报 (只接收 + 日志, 不返回敏感数据)
    });
  } catch (err) {
    // 上报失败只 warn, 不抛二次错误 (前端崩溃时优先保证 UI 可用)
    console.warn('[reportFrontendError] 上报失败 (非致命):', err);
  }
}

/**
 * 安装全局错误捕获: window.onerror + window.onunhandledrejection。
 * 在 main.tsx 入口调用一次即可。
 */
export function installGlobalErrorHandlers(): void {
  // window.onerror: 捕获同步错误 + 资源加载错误
  window.addEventListener('error', (event) => {
    // 跨域匿名错误 ("Script error." 且无 filename/stack) 无诊断价值,
    // 过滤掉避免污染服务日志与报错计数 (历史噪音治理).
    if (event.message === 'Script error.' && !event.filename) {
      return;
    }
    void reportFrontendError({
      message: event.message || 'Unknown error',
      source: event.filename || undefined,
      lineno: event.lineno || undefined,
      colno: event.colno || undefined,
      stack: event.error?.stack,
      error_type: event.error?.name,
      trigger: 'window.onerror',
    });
  });

  // window.onunhandledrejection: 捕获未 catch 的 Promise rejection
  window.addEventListener('unhandledrejection', (event) => {
    const reason = event.reason;
    const message = reason instanceof Error ? reason.message : String(reason ?? 'Unknown rejection');
    const stack = reason instanceof Error ? reason.stack : undefined;
    const errorType = reason instanceof Error ? reason.name : typeof reason;
    void reportFrontendError({
      message,
      stack,
      error_type: errorType,
      trigger: 'unhandledrejection',
    });
  });
}
