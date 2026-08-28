/**
 * TD-401: NodeTypeLibrary 完整性 + 渲染 smoke
 *
 * 目标①: NODE_TYPE_LIBRARY 派生表的完整性——每个 PipelineNodeType 都必须有
 * label/description/icon/category，防止"注册了类型但前端没标签/图标"的静默缺口
 * （2026-08-26 曾发生 uia_select/uia_scroll 缺 ICON_KEYS 靠 fallback 图标的情况）。
 * 目标②: 组件渲染不崩溃 + 节点可搜索。
 */
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { NODE_TYPE_LIBRARY, NODE_TYPE_CATEGORY, type PipelineNodeType } from '@/types/models';
import { NodeTypeLibrary } from '@/components/Pipeline/NodeTypeLibrary';

// Mock template picker's data source to keep the test hermetic.
vi.mock('@/api/templates', () => ({
  listTemplates: vi.fn().mockResolvedValue({ results: [], count: 0 }),
}));

describe('NodeTypeLibrary 类型库完整性', () => {
  const registered = Object.keys(NODE_TYPE_CATEGORY) as PipelineNodeType[];

  it('每个 PipelineNodeType 在 NODE_TYPE_LIBRARY 中都有完整定义', () => {
    const byType = new Map(NODE_TYPE_LIBRARY.map((d) => [d.type, d]));
    for (const type of registered) {
      const def = byType.get(type);
      expect(def, `NODE_TYPE_LIBRARY 缺少节点: ${type}`).toBeDefined();
      expect(def!.label, `${type} 缺 label`).toBeTruthy();
      expect(def!.description, `${type} 缺 description`).toBeTruthy();
      expect(def!.icon, `${type} 缺 icon key`).toBeTruthy();
      expect(def!.category, `${type} 缺 category`).toBeTruthy();
    }
  });

  it('NODE_TYPE_LIBRARY 无多余节点（与注册表一一对应）', () => {
    expect(NODE_TYPE_LIBRARY.length).toBe(registered.length);
  });

  it('语义层 6 类节点均已暴露', () => {
    for (const type of [
      'uia_set_value',
      'uia_invoke',
      'uia_get_state',
      'uia_get_window_title',
      'uia_select',
      'uia_scroll',
    ]) {
      expect(registered).toContain(type);
    }
  });
});

describe('NodeTypeLibrary 渲染', () => {
  it('渲染节点库并按分类展示「语义操作」节点', () => {
    render(<NodeTypeLibrary />);
    expect(screen.getByText('语义赋值')).toBeDefined();
    expect(screen.getByText('语义滚动')).toBeDefined();
    expect(screen.getByText('模板匹配')).toBeDefined();
  });

  it('搜索框可按名称过滤节点', () => {
    render(<NodeTypeLibrary />);
    const search = screen.getByPlaceholderText(/搜索节点/) as HTMLInputElement;
    fireEvent.change(search, { target: { value: '语义选择' } });
    expect(screen.getByText('语义选择')).toBeDefined();
    // 不匹配的节点应被过滤掉（画面识别下不匹配的模板匹配不再可见）
    expect(screen.queryByText('模板匹配')).toBeNull();
  });
});
