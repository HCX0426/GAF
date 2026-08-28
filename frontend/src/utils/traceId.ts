/**
 * C1 (spec 2026-07-30): trace_id 全链路贯穿 — 前端 trace_id 生成与存储。
 *
 * 设计:
 * - generateTraceId(): 用 crypto.randomUUID() 生成完整 UUID (与 backend WS 帧
 *   schema UUIDField 格式对齐, 如 550e8400-e29b-41d4-a716-446655440000)
 * - sessionStorage 存储 last_trace_id: 同 tab 生命周期内一致, 跨刷新丢失
 *   (符合 trace_id 语义: 一次用户操作链路的标识, 刷新后是新链路)
 * - request 拦截器读 getLastTraceId() 加 X-Trace-Id header (见 client.ts)
 * - response 拦截器读后端 X-Trace-Id header 更新 sessionStorage (后端是
 *   trace_id 的 source of truth: 若后端生成了不同的 trace_id, 以前端收到的为准)
 */

const TRACE_ID_KEY = 'gaf_last_trace_id';

/**
 * 生成新的 trace_id (UUID v4 格式)。
 * 优先用 crypto.randomUUID(), 降级到 Math.random 拼凑 (老浏览器/测试环境)。
 */
export function generateTraceId(): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID();
  }
  // 降级: RFC4122 v4 UUID 拼凑 (不保证密码学安全, trace_id 场景够用)
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (c) => {
    const r = (Math.random() * 16) | 0;
    const v = c === 'x' ? r : (r & 0x3) | 0x8;
    return v.toString(16);
  });
}

/** 从 sessionStorage 读取 last trace_id (未设置返回空字符串) */
export function getLastTraceId(): string {
  try {
    return sessionStorage.getItem(TRACE_ID_KEY) || '';
  } catch {
    // sessionStorage 不可用 (隐私模式 / SSR) — 降级返回空字符串
    return '';
  }
}

/** 写入 last trace_id 到 sessionStorage */
export function setLastTraceId(id: string): void {
  try {
    sessionStorage.setItem(TRACE_ID_KEY, id);
  } catch {
    // sessionStorage 不可用 — 静默降级 (trace_id 缺失不影响主流程)
  }
}
