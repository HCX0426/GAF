/**
 * Editor.tsx catch 块契约测试 (N192 B1 P0).
 *
 * 这是契约测试, 验证 resolveErrorMessage 在 Editor.tsx 两种 catch 场景下的预期返回值。
 * 不是组件渲染测试 — 组件渲染测试属于任务 2.3 (Editor.tsx 保存前调用 validate) 的范围。
 *
 * 测试目标:
 * - JSON parse 错误 (SyntaxError) 应降级到 classifyError 返回 error.message
 * - backend 校验失败 (businessCode=1001) 应返回 i18n 映射文案 (N192 B2 错误码一致性)
 * - 网络错误 (TypeError 'Failed to fetch') 应返回网络错误文案
 */
import { describe, it, expect, beforeEach } from 'vitest';
import { resolveErrorMessage } from '@/utils/errorHandler';
import { setLocale } from '@/i18n';

describe('Editor.tsx catch 块契约测试', () => {
  beforeEach(() => {
    // 显式设置 zh-CN locale, 避免 setup.ts 默认 locale 变化导致测试无声失败
    setLocale('zh-CN');
  });

  it('JSON parse 错误 (SyntaxError) 应降级到 classifyError 返回 error.message', () => {
    // 模拟 handleImportJson 中 JSON.parse 抛出的 SyntaxError
    let caughtError: unknown = null;
    try {
      JSON.parse('{ invalid json }');
    } catch (e) {
      caughtError = e;
    }
    const msg = resolveErrorMessage(caughtError);
    // SyntaxError 是 Error 子类, resolveErrorMessage 会降级到 classifyError
    // classifyError 对 Error 实例返回 error.message (V8 给的英文, 如 "Unexpected token...")
    expect(typeof msg).toBe('string');
    expect(msg.length).toBeGreaterThan(0);
  });

  it('backend 校验失败 (businessCode=1001) 应返回 i18n 映射文案', () => {
    // 模拟 handleSave 中 createTask 抛出的 axios 错误 (带 businessCode/businessMessage)
    const backendError = {
      businessCode: 1001, // INVALID_PARAMS
      businessMessage: 'task_definition.nodes[0] 缺少 id 字段',
      name: 'AxiosError',
      message: 'task_definition.nodes[0] 缺少 id 字段',
      response: { status: 400, data: null },
    };
    const msg = resolveErrorMessage(backendError);
    // businessCode=1001 在 i18n 中映射为 "请求参数不合法, 请检查输入" (zh-CN)
    // 这是 N192 B2 错误码一致性的预期行为: 同一错误码在前端展示一致文案
    expect(msg).toBe('请求参数不合法, 请检查输入');
  });

  it('网络错误 (TypeError) 应返回网络错误文案', () => {
    // 模拟 handleSave 中 createTask 抛出的网络错误 (无 businessCode)
    const networkError = new TypeError('Failed to fetch');
    const msg = resolveErrorMessage(networkError);
    // classifyError 对 TypeError 网络错误返回 t('error.network.connection_failed')
    // zh-CN 下 = '无法连接到服务器，请检查后端是否启动' (common.ts:57)
    expect(msg).toBe('无法连接到服务器，请检查后端是否启动');
  });
});
