/**
 * C3 (spec 2026-07-30-debug-directory-restructure): page_slug 提取。
 *
 * 从 `window.location.pathname` 提取页面标识, 用于前端错误上报时按页面归集
 * (debug/<YYYYMMDD>/frontend/<page_slug>/<HH>/console.jsonl)。
 *
 * 推取规则 (spec §2.1.3):
 * - 从 `window.location.pathname` 取, 去掉首尾 `/`
 * - `dashboard` → `dashboard`
 * - `tasks/pipeline/123` → `tasks_pipeline` (去掉 id, 保留层级)
 * - `ops/logs` → `ops_logs`
 * - 根路径 `/` → `home`
 * - 含中文的 URL 段保留原样
 *
 * 设计决策:
 * - 纯数字段视为 id 丢弃 (如 `123`), 让 `/tasks/123` 与 `/tasks/456` 归集到同一 bucket
 * - 多层路径用 `_` 连接, 保留层级信息 (如 `tasks_pipeline` 而非 `tasks`)
 * - 不做 URL 解码 (pathname 已是解码后的), 含中文段原样保留
 * - 后端会再做一次 sanitize (defense in depth), 前端只保证基本规则
 */
const ID_PATTERN = /^\d+$/;

/** 安全字符: 字母 / 数字 / 中文 / 下划线 / 连字符 / 点 (允许如 `dashboard.json` 这种 slug)。
 *  其他字符替换为 `_`, 避免 backend 目录名含特殊字符。 */
// 控制字符范围 (\x00-\x1f) 是刻意包含的: 过滤文件名/路径中的 C0 控制字符,
// 防止其进入 debug 目录名 (no-control-regex 豁免 — 该匹配是安全过滤而非误用).
// eslint-disable-next-line no-control-regex
const UNSAFE_CHAR_PATTERN = /[<>:"/\\|?*\x00-\x1f\s]/g;

/** 把 URL pathname 转换为 page_slug。
 *
 * - 空路径 / 根路径 → `home`
 * - 纯 id 段 → 丢弃
 * - 多层路径 → `_` 连接
 * - 不安全字符 → `_`
 * - 总长度限制 40 (与 backend `_MAX_PAGE_SLUG_LEN` 对齐)
 */
export function pathnameToPageSlug(pathname: string): string {
  if (!pathname || typeof pathname !== 'string') {
    return 'home';
  }
  // 去掉首尾 / 后按 / 切分
  const trimmed = pathname.replace(/^\/+|\/+$/g, '');
  if (!trimmed) {
    return 'home';
  }
  const segments = trimmed.split(/\/+/);
  // 过滤纯数字段 (id), 保留层级语义; 过滤空段 (连续 / 产生)
  const kept = segments.filter((seg) => seg && !ID_PATTERN.test(seg));
  if (kept.length === 0) {
    // 全是 id (如 `/123/456`) → 仍归到 `home` 兜底
    return 'home';
  }
  // 替换不安全字符为 _ (避免 backend 目录名含 / : 等)
  const safeKept = kept.map((seg) => seg.replace(UNSAFE_CHAR_PATTERN, '_'));
  const slug = safeKept.join('_');
  // 长度限制 40 (与 backend _MAX_PAGE_SLUG_LEN 对齐, backend 也会再截一次)
  return slug.length > 40 ? slug.slice(0, 40) : slug;
}

/** 从 `window.location.pathname` 提取 page_slug。
 *
 * SSR / 测试环境 (无 window) 返回 `'unknown'`, 与 backend 兜底逻辑对齐。 */
export function getPageSlug(): string {
  try {
    if (typeof window === 'undefined' || !window.location) {
      return 'unknown';
    }
    return pathnameToPageSlug(window.location.pathname);
  } catch {
    // jsdom 等环境下 window.location 访问可能异常, 兜底为 unknown
    return 'unknown';
  }
}
