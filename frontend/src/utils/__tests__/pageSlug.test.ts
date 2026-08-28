/**
 * C3 spec 2026-07-30: page_slug 提取单测。
 *
 * 验证 pathnameToPageSlug 按 spec §2.1.3 规则提取:
 * - dashboard → dashboard
 * - tasks/pipeline/123 → tasks_pipeline (去 id 保层级)
 * - ops/logs → ops_logs
 * - 根路径 / → home
 * - 含中文段保留
 * - 不安全字符替换为 _
 * - 长度限制 40
 */
import { describe, it, expect } from 'vitest';
import { pathnameToPageSlug, getPageSlug } from '@/utils/pageSlug';

describe('pathnameToPageSlug', () => {
  it('单段路径 → 原样保留', () => {
    expect(pathnameToPageSlug('/dashboard')).toBe('dashboard');
    expect(pathnameToPageSlug('dashboard')).toBe('dashboard');
    expect(pathnameToPageSlug('/dashboard/')).toBe('dashboard');
  });

  it('多层路径 → 下划线连接 (保留层级, 去 id)', () => {
    expect(pathnameToPageSlug('/tasks/pipeline/123')).toBe('tasks_pipeline');
    expect(pathnameToPageSlug('/ops/logs')).toBe('ops_logs');
    expect(pathnameToPageSlug('/tasks/pipeline/456/edit')).toBe('tasks_pipeline_edit');
  });

  it('根路径 → home', () => {
    expect(pathnameToPageSlug('/')).toBe('home');
    expect(pathnameToPageSlug('')).toBe('home');
    expect(pathnameToPageSlug('///')).toBe('home');
  });

  it('纯 id 路径 → home 兜底', () => {
    expect(pathnameToPageSlug('/123')).toBe('home');
    expect(pathnameToPageSlug('/123/456')).toBe('home');
  });

  it('含中文段 → 保留原样', () => {
    expect(pathnameToPageSlug('/tasks/中文页面/123')).toBe('tasks_中文页面');
  });

  it('不安全字符 → 替换为 _', () => {
    // spec §2.1.3: 含中文保留, 但 <>:"/\\|?* 等需替换
    expect(pathnameToPageSlug('/a:b<c')).toBe('a_b_c');
    expect(pathnameToPageSlug('/a b c')).toBe('a_b_c');
  });

  it('长度限制 40', () => {
    const long = '/'.repeat(0) + 'a'.repeat(50);
    const slug = pathnameToPageSlug(long);
    expect(slug.length).toBe(40);
  });

  it('undefined / null / 非字符串 → home', () => {
    expect(pathnameToPageSlug(undefined as unknown as string)).toBe('home');
    expect(pathnameToPageSlug(null as unknown as string)).toBe('home');
    expect(pathnameToPageSlug(123 as unknown as string)).toBe('home');
  });
});

describe('getPageSlug', () => {
  it('从 window.location.pathname 取值 (jsdom 默认 / → home)', () => {
    // vitest jsdom 默认 location.pathname = '/'
    expect(getPageSlug()).toBe('home');
  });

  it('SSR / 无 window 环境 → unknown', () => {
    // 模拟无 window 场景 (getPageSlug 内部 try-catch 兜底)
    const origWindow = globalThis.window;
    // @ts-expect-error 故意删除 window 模拟 SSR
    delete globalThis.window;
    try {
      expect(getPageSlug()).toBe('unknown');
    } finally {
      globalThis.window = origWindow;
    }
  });
});
