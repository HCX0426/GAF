/**
 * TD-401: NodePropertyPanel 配置表单分支测试
 *
 * 覆盖 2026-08-26 新增/关键分支:
 * - uia_* 语义节点: 值/选项/方向/幅度/变量名 字段渲染 + 必填校验提示
 * - template_match_any / swipe_until / log_message: 模板列表 + 日志消息/级别
 * - updateConfig 回调: 输入变更触发 onChange
 */
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { NodePropertyPanel } from '@/components/Pipeline/NodePropertyPanel';

// Keep data-fetching on mount hermetic (only reachable for monitor/sub_pipeline,
// mocked so accidental regressions don't hit the network in tests).
vi.mock('@/api/monitors', () => ({
  fetchMonitorRules: vi.fn().mockResolvedValue({ results: [] }),
}));
vi.mock('@/api/pipelines', () => ({
  listPipelines: vi.fn().mockResolvedValue({ results: [] }),
}));

function renderPanel(
  nodeType: string,
  config: Record<string, unknown>,
  onChange: (c: Record<string, unknown>) => void = () => {},
) {
  return render(<NodePropertyPanel nodeId="n1" nodeType={nodeType as never} config={config} onChange={onChange} />);
}

describe('NodePropertyPanel 公共行为', () => {
  it('未选择节点时显示提示', () => {
    render(<NodePropertyPanel />);
    expect(screen.getByText('请选中一个节点查看属性')).toBeDefined();
  });

  it('缺少必填字段时顶部出现 Alert', () => {
    renderPanel('uia_set_value', {});
    expect(screen.getByText(/缺少必填字段/)).toBeDefined();
    // Alert message 为整句 "缺少必填字段: value"（join(', ') 后内嵌字段名）
    expect(screen.getByText(/缺少必填字段: value/)).toBeDefined();
  });
});

describe('uia_set_value', () => {
  it('渲染值字段并回写 onChange', () => {
    const onChange = vi.fn();
    renderPanel('uia_set_value', { value: '', control_name: '地址栏' }, onChange);
    const input = screen.getByDisplayValue('地址栏'); // control_name 输入
    fireEvent.change(input, { target: { value: '搜索栏' } });
    expect(onChange).toHaveBeenCalledWith(expect.objectContaining({ control_name: '搜索栏' }));
    // 值字段 label（antd Form.Item 无 htmlFor，用文本匹配）
    expect(screen.getByText('值')).toBeDefined();
  });
});

describe('uia_select', () => {
  it('渲染选项文本 + 精确匹配开关', () => {
    renderPanel('uia_select', { option: '百度', exact: true });
    expect(screen.getByDisplayValue('百度')).toBeDefined();
    expect(screen.getByText('精确匹配选项名')).toBeDefined();
  });
});

describe('uia_scroll', () => {
  it('渲染方向与幅度选项', () => {
    renderPanel('uia_scroll', { direction: 'down', amount: 'large' });
    expect(screen.getByText('滚动方向')).toBeDefined();
    expect(screen.getByText('滚动幅度')).toBeDefined();
    // Select 当前值展示为已选中文标签
    expect(screen.getByText('下')).toBeDefined();
    expect(screen.getByText('大步')).toBeDefined();
  });

  it('非法方向进入必填 Alert', () => {
    renderPanel('uia_scroll', {});
    expect(screen.getByText(/缺少必填字段: direction/)).toBeDefined();
  });
});

describe('uia_get_state / uia_get_window_title', () => {
  it('uia_get_state 渲染结果变量名 + 控件类型', () => {
    renderPanel('uia_get_state', { var: 'addr_state' });
    expect(screen.getByDisplayValue('addr_state')).toBeDefined();
    expect(screen.getByText('控件类型')).toBeDefined();
  });

  it('uia_get_window_title 渲染结果变量名', () => {
    renderPanel('uia_get_window_title', { var: 'win_title' });
    expect(screen.getByDisplayValue('win_title')).toBeDefined();
  });
});

describe('template_match_any / swipe_until / log_message', () => {
  it('template_match_any 渲染模板列表（每行一个）', () => {
    renderPanel('template_match_any', { templates: ['a.png', 'b.png'], threshold: 0.8 });
    const ta = screen.getByPlaceholderText('每行一个模板名') as HTMLTextAreaElement;
    expect(ta.value).toBe('a.png\nb.png');
    expect(screen.getByText(/模板列表/)).toBeDefined();
  });

  it('template_match_any 缺少模板进入必填 Alert', () => {
    renderPanel('template_match_any', {});
    expect(screen.getByText(/缺少必填字段: templates/)).toBeDefined();
  });

  it('swipe_until 渲染坐标与最大滑动次数', () => {
    renderPanel('swipe_until', { templates: ['t.png'], max_swipes: 5 });
    expect(screen.getByText('最大滑动次数')).toBeDefined();
    expect(screen.getByDisplayValue(/t\.png/)).toBeDefined();
  });

  it('log_message 渲染消息 + 级别', () => {
    renderPanel('log_message', { message: 'hello ${var}', level: 'warning' });
    expect(screen.getByDisplayValue('hello ${var}')).toBeDefined();
    expect(screen.getByText('警告')).toBeDefined();
  });

  it('log_message 缺少消息进入必填 Alert', () => {
    renderPanel('log_message', {});
    expect(screen.getByText(/缺少必填字段: message/)).toBeDefined();
  });
});
