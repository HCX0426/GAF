/**
 * Editor.tsx 保存前调用 validate API 契约测试 (N192 B3/B5 P1).
 *
 * 这是 API 契约测试, 验证 validateTask 调用正确的端点并返回带 node_id 的 CheckItem 列表,
 * 让前端能定位到具体节点。组件渲染测试不在本文件范围。
 *
 * 测试目标:
 * - POST /tasks/{id}/validate/ 端点路径正确 (无 /api/v2 前缀, 由 client baseURL 处理)
 * - 返回 ValidateResult 含 valid/detail/errors 字段
 * - CheckItem 含 node_id/suggestion 字段用于节点级错误展示
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import type { CheckItem, ValidateResult } from '@/api/tasks';

// Mock the API client — tasks.ts does `import client from './client'`
// so we mock the default export with post/get stubs.
vi.mock('@/api/client', () => ({
  default: {
    post: vi.fn(),
    get: vi.fn(),
  },
}));

import client from '@/api/client';
import { validateTask } from '@/api/tasks';

describe('validateTask API', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('returns ValidateResult with CheckItem array containing node_id', async () => {
    const mockErrors: CheckItem[] = [
      {
        check: 'required_fields',
        status: 'fail',
        message: "节点 'n1' (template_match) 缺少必填字段: template_id",
        node_id: 'n1',
        suggestion: '请在属性面板中填写对应字段',
      },
    ];
    const mockResponse: ValidateResult = {
      valid: false,
      detail: '校验未通过',
      errors: mockErrors,
    };
    (client.post as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      data: mockResponse,
    });

    const result = await validateTask(123);

    expect(result.valid).toBe(false);
    expect(result.detail).toBe('校验未通过');
    expect(result.errors).toHaveLength(1);
    expect(result.errors[0].node_id).toBe('n1');
    expect(result.errors[0].suggestion).toBeTruthy();
    expect(client.post).toHaveBeenCalledWith('/tasks/123/validate/');
  });

  it('returns valid=true with empty errors when backend reports success', async () => {
    (client.post as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      data: { valid: true, detail: '任务定义验证通过', errors: [] },
    });

    const result = await validateTask(456);

    expect(result.valid).toBe(true);
    expect(result.errors).toEqual([]);
    expect(client.post).toHaveBeenCalledWith('/tasks/456/validate/');
  });

  it('returns warn status items in errors array (not filtered client-side)', async () => {
    // 后端已经过滤掉 pass, 只返回 fail + warn; 前端应原样展示
    const mockErrors: CheckItem[] = [
      {
        check: 'orphan_node',
        status: 'warn',
        message: '节点 n2 没有被任何节点引用',
        node_id: 'n2',
        suggestion: '可删除该节点或检查 next_node_id 配置',
      },
      {
        check: 'missing_template',
        status: 'fail',
        message: '节点 n3 引用的模板不存在',
        node_id: 'n3',
        suggestion: '请重新选择模板',
      },
    ];
    (client.post as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      data: { valid: false, detail: '校验未通过', errors: mockErrors },
    });

    const result = await validateTask(789);

    expect(result.errors).toHaveLength(2);
    expect(result.errors[0].status).toBe('warn');
    expect(result.errors[1].status).toBe('fail');
  });
});
