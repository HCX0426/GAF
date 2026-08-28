/**
 * pipeline domain models (s37 split from models.ts — TD-365).
 */

export type PipelineNodeType =
  // Base match nodes (5)
  | 'template_match'
  | 'ocr'
  | 'color_detect'
  | 'feature_match'
  | 'neural_network'
  // Composite match nodes (3) — Phase 2.5 extension
  | 'and_match'
  | 'or_match'
  | 'custom_match'
  // Input nodes (5)
  | 'click'
  | 'swipe'
  | 'long_press'
  | 'key_press'
  | 'text_input'
  // Advanced input nodes (4) — Phase 2.5 extension
  | 'direct_hit'
  | 'multi_swipe'
  | 'multi_scroll'
  | 'multi_touch'
  | 'wheel'
  // Control-flow nodes (4)
  | 'branch'
  | 'loop'
  | 'goto'
  | 'wait'
  | 'random_delay'
  // Maa protocol nodes (5) — Phase 2.5 extension
  | 'jump_back'
  | 'wait_freezes'
  | 'next'
  | 'stop'
  | 'anchor'
  // Device/app nodes (4)
  | 'device_control'
  | 'start_app'
  | 'stop_app'
  | 'monitor'
  | 'notify'
  | 'sub_pipeline'
  // Neural network nodes (2) — Phase 2.5 extension
  | 'nn_classifier'
  | 'nn_regressor'
  // Sort/select node (1) — Phase 2.5 extension
  | 'sort_select'
  // Coord-transform utility (1) — Phase 7.4 extension
  | 'roi_resolver'
  // UIAutomation semantic layer (4) — spec-2026-08-26 P2, accessibility
  // injection (no focus / visibility needed), aligned w/ Trae accessibility.
  | 'uia_set_value'
  | 'uia_invoke'
  | 'uia_get_state'
  | 'uia_get_window_title'
  | 'uia_select'
  | 'uia_scroll'
  // Legacy-but-live agent nodes aligned w/ registry (2026-08-26): any-of
  // template match, swipe-until-hit, plain log output.
  | 'template_match_any'
  | 'swipe_until'
  | 'log_message';

/** Pipeline node status */

export type GafNodeStatus = 'pending' | 'running' | 'success' | 'failed' | 'skipped';

/** GAF Pipeline node data */

export interface GafNodeData {
  label: string;
  nodeType: PipelineNodeType;
  description?: string;
  status?: GafNodeStatus;
  config?: Record<string, unknown>;
}

/** Pipeline node category — 9 types */

export type NodeCategory =
  | '画面操作'
  | '画面识别'
  | '智能识别'
  | '逻辑控制'
  | '等待延迟'
  | '设备控制'
  | '监控触发'
  | '通知告警'
  | '子流程'
  | '语义操作';

/** node category to corresponding color */

export const CATEGORY_COLORS: Record<NodeCategory, string> = {
  画面操作: '#1890ff',
  画面识别: '#52c41a',
  智能识别: '#13c2c2',
  逻辑控制: '#fa8c16',
  等待延迟: '#eb2f96',
  设备控制: '#722ed1',
  监控触发: '#ff4d4f',
  通知告警: '#faad14',
  子流程: '#2f54eb',
  // spec-2026-08-26 P2: 语义层（accessibility 注入通道）独立分类
  语义操作: '#ba7dff',
};

/** node type to category mapping */

export const NODE_TYPE_CATEGORY: Record<PipelineNodeType, NodeCategory> = {
  template_match: '画面识别',
  ocr: '画面识别',
  color_detect: '画面识别',
  feature_match: '画面识别',
  neural_network: '智能识别',
  and_match: '画面识别',
  or_match: '画面识别',
  custom_match: '画面识别',
  click: '画面操作',
  swipe: '画面操作',
  long_press: '画面操作',
  key_press: '画面操作',
  text_input: '画面操作',
  direct_hit: '画面操作',
  multi_swipe: '画面操作',
  multi_scroll: '画面操作',
  multi_touch: '画面操作',
  wheel: '画面操作',
  branch: '逻辑控制',
  loop: '逻辑控制',
  goto: '逻辑控制',
  wait: '等待延迟',
  random_delay: '等待延迟',
  jump_back: '逻辑控制',
  wait_freezes: '逻辑控制',
  next: '逻辑控制',
  stop: '逻辑控制',
  anchor: '逻辑控制',
  sort_select: '逻辑控制',
  device_control: '设备控制',
  start_app: '设备控制',
  stop_app: '设备控制',
  monitor: '监控触发',
  notify: '通知告警',
  sub_pipeline: '子流程',
  nn_classifier: '智能识别',
  nn_regressor: '智能识别',
  roi_resolver: '逻辑控制',
  // spec-2026-08-26 P2: 语义层
  uia_set_value: '语义操作',
  uia_invoke: '语义操作',
  uia_get_state: '语义操作',
  uia_get_window_title: '语义操作',
  uia_select: '语义操作',
  uia_scroll: '语义操作',
  template_match_any: '画面识别',
  swipe_until: '画面操作',
  log_message: '通知告警',
};

/** each node type default config */

export const DEFAULT_NODE_CONFIGS: Record<PipelineNodeType, Record<string, unknown>> = {
  template_match: { threshold: 0.8, template: '', roi: '' },
  ocr: { text: '', roi: '', language: 'chi_sim' },
  color_detect: { target_color: '', roi: '', tolerance: 10 },
  feature_match: { feature_type: 'orb', threshold: 0.7, template: '' },
  neural_network: { model_path: '', input_size: [640, 640], confidence: 0.5 },
  click: { x: 0, y: 0, duration: 100 },
  swipe: { start_x: 0, start_y: 0, end_x: 0, end_y: 0, duration: 300 },
  long_press: { x: 0, y: 0, duration: 1000 },
  key_press: { key: '', modifiers: [] },
  text_input: { text: '', clear_before: false },
  branch: { condition: '', true_branch: '', false_branch: '' },
  loop: { max_iterations: 10, condition: '' },
  goto: { target_node: '' },
  wait: { duration: 1000 },
  random_delay: { min_ms: 500, max_ms: 2000 },
  device_control: { command: '', params: {} },
  start_app: { package_name: '', activity: '' },
  stop_app: { package_name: '', force: false },
  monitor: { event_type: '', threshold: 0 },
  notify: { channel: 'webhook', message: '', level: 'info' },
  sub_pipeline: { pipeline_id: '', parameters: {} },
  // Phase 2.5 extension: 16 new node types — skeleton configs mirror agent
  // node defaults (see agent/src/engine/nodes/*) where applicable.
  and_match: { conditions: [], match_mode: 'all' },
  or_match: { conditions: [], match_mode: 'any' },
  custom_match: { script: '', params: {} },
  direct_hit: { x: 0, y: 0, duration: 100 },
  multi_swipe: { swipes: [], duration: 300 },
  multi_scroll: { direction: 'down', distance: 100, duration: 300 },
  multi_touch: { touches: [], duration: 200 },
  wheel: { x: 0, y: 0, delta_y: 0, delta_x: 0 },
  jump_back: { target_node: '' },
  wait_freezes: { timeout: 5000, threshold: 0.95, interval: 200 },
  next: {},
  stop: { reason: '' },
  anchor: { name: '' },
  nn_classifier: { model_path: '', labels: [], confidence: 0.5 },
  nn_regressor: { model_path: '', output_keys: [], threshold: 0.5 },
  sort_select: { sort_key: '', order: 'asc', select_top: 1 },
  // Phase 7.4 extension: ROI pre-resolver (publishes logical/physical ROI to
  // context variable for downstream nodes via ${var} substitution).
  roi_resolver: { roi: { x: 0, y: 0, w: 0, h: 0 }, coord_type: 'base', output_var: '' },
  // spec-2026-08-26 P2: UIAutomation 语义节点（config 对齐 uia_control.py）。
  // control_name / control_automation_id 二选一即可定位控件。
  uia_set_value: { value: '', control_name: '', control_automation_id: '', timeout: 3 },
  uia_invoke: { control_name: '', control_automation_id: '', timeout: 3 },
  uia_get_state: { control_name: '', control_automation_id: '', control_type: 'edit', timeout: 3 },
  uia_get_window_title: {},
  uia_select: { option: '', control_name: '', control_automation_id: '', exact: true, timeout: 3 },
  uia_scroll: {
    direction: 'down',
    amount: 'small',
    control_name: '',
    control_automation_id: '',
    control_type: 'document',
    timeout: 3,
  },
  // 2026-08-26: config 对齐 agent 端 template_match_any / swipe_until / log_message
  template_match_any: { templates: [], threshold: 0.8, click_on_match: false, method: 'TM_CCOEFF_NORMED' },
  swipe_until: {
    templates: [],
    threshold: 0.8,
    max_swipes: 3,
    delay_between: 0.5,
    click_on_match: false,
    x1: 0,
    y1: 0,
    x2: 0,
    y2: 0,
    duration: 300,
  },
  log_message: { message: '', level: 'info' },
};

/** node type definition */

export interface NodeTypeDefinition {
  type: PipelineNodeType;
  label: string;
  description: string;
  icon: string;
  category: NodeCategory;
}

const ICON_KEYS: Record<PipelineNodeType, string> = {
  template_match: 'Template',
  ocr: 'OCR',
  color_detect: 'ColorDetect',
  feature_match: 'Feature',
  neural_network: 'NeuralNetwork',
  click: 'Click',
  swipe: 'Swipe',
  long_press: 'LongPress',
  key_press: 'KeyPress',
  text_input: 'TextInput',
  branch: 'Branch',
  loop: 'Loop',
  goto: 'Goto',
  wait: 'Wait',
  random_delay: 'RandomDelay',
  device_control: 'Device',
  start_app: 'StartApp',
  stop_app: 'StopApp',
  monitor: 'Monitor',
  notify: 'Notify',
  sub_pipeline: 'SubPipeline',
  // Phase 2.5 extension: 16 new icon keys. Each must have a matching
  // entry in NodeTypeLibrary.tsx ICON_MAP (fallback: ToolOutlined).
  and_match: 'AndMatch',
  or_match: 'OrMatch',
  custom_match: 'CustomMatch',
  direct_hit: 'DirectHit',
  multi_swipe: 'MultiSwipe',
  multi_scroll: 'MultiScroll',
  multi_touch: 'MultiTouch',
  wheel: 'Wheel',
  jump_back: 'JumpBack',
  wait_freezes: 'WaitFreezes',
  next: 'Next',
  stop: 'Stop',
  anchor: 'Anchor',
  nn_classifier: 'NNClassifier',
  nn_regressor: 'NNRegressor',
  sort_select: 'SortSelect',
  // Phase 7.4 extension: roi_resolver icon key (fallback: ToolOutlined).
  roi_resolver: 'ROIResolver',
  // spec-2026-08-26 P2: UIAutomation 语义节点 icon keys
  uia_set_value: 'UiaSetValue',
  uia_invoke: 'UiaInvoke',
  uia_get_state: 'UiaGetState',
  uia_get_window_title: 'UiaWindowTitle',
  uia_select: 'UiaSelect',
  uia_scroll: 'UiaScroll',
  // 2026-08-26: template_match_any / swipe_until / log_message icon keys
  template_match_any: 'TemplateMatchAny',
  swipe_until: 'SwipeUntil',
  log_message: 'LogMessage',
};

/** built-in node type library */

export const NODE_TYPE_LIBRARY: NodeTypeDefinition[] = (Object.keys(NODE_TYPE_CATEGORY) as PipelineNodeType[]).map(
  (type) => ({
    type,
    label: (
      {
        template_match: '模板匹配',
        ocr: 'OCR 识别',
        color_detect: '颜色检测',
        feature_match: '特征匹配',
        neural_network: '神经网络推理',
        click: '点击',
        swipe: '滑动',
        long_press: '长按',
        key_press: '按键',
        text_input: '文本输入',
        branch: '分支',
        loop: '循环',
        goto: '跳转',
        wait: '等待',
        random_delay: '随机延迟',
        device_control: '设备控制',
        start_app: '启动应用',
        stop_app: '停止应用',
        monitor: '监控',
        notify: '通知告警',
        sub_pipeline: '子流程',
        // Phase 2.5 extension labels
        and_match: '逻辑与匹配',
        or_match: '逻辑或匹配',
        custom_match: '自定义匹配',
        direct_hit: '直接点击',
        multi_swipe: '多点滑动',
        multi_scroll: '多点滚动',
        multi_touch: '多点触摸',
        wheel: '滚轮操作',
        jump_back: '跳回',
        wait_freezes: '等待冻结',
        next: '下一节点',
        stop: '停止',
        anchor: '锚点',
        nn_classifier: '神经网络分类',
        nn_regressor: '神经网络回归',
        sort_select: '排序选择',
        roi_resolver: 'ROI 坐标解析',
        // spec-2026-08-26 P2: 语义层 labels
        uia_set_value: '语义赋值',
        uia_invoke: '语义触发',
        uia_get_state: '语义读取',
        uia_get_window_title: '窗口标题',
        uia_select: '语义选择',
        uia_scroll: '语义滚动',
        template_match_any: '多模板匹配',
        swipe_until: '滑动直到命中',
        log_message: '日志输出',
      } as Record<PipelineNodeType, string>
    )[type],
    description: (
      {
        template_match: '在屏幕上匹配模板图像',
        ocr: '识别屏幕上的文字',
        color_detect: '检测屏幕指定区域颜色',
        feature_match: 'SIFT/ORB/AKAZE 特征点匹配',
        neural_network: 'ONNX 神经网络模型推理检测',
        click: '在指定坐标点击',
        swipe: '在屏幕上滑动',
        long_press: '在指定坐标长按',
        key_press: '模拟按键操作',
        text_input: '输入文本内容',
        branch: '根据条件分支执行',
        loop: '循环执行子节点',
        goto: '跳转到指定节点',
        wait: '等待指定时间',
        random_delay: '随机等待一段时间',
        device_control: '控制设备设置',
        start_app: '启动指定应用',
        stop_app: '停止指定应用',
        monitor: '监控触发条件',
        notify: '发送通知告警',
        sub_pipeline: '调用子流水线',
        // Phase 2.5 extension descriptions
        and_match: '多条件全匹配（AND 逻辑）',
        or_match: '任一条件匹配（OR 逻辑）',
        custom_match: '执行用户自定义脚本匹配',
        direct_hit: '无识别直接点击指定坐标',
        multi_swipe: '同时执行多点滑动',
        multi_scroll: '多点滚动操作',
        multi_touch: '多点同时触摸',
        wheel: '鼠标滚轮滚动操作',
        jump_back: '跳回上一节点',
        wait_freezes: '等待画面停止变化',
        next: '跳到下一节点',
        stop: '停止流水线执行',
        anchor: '锚点节点（用作跳转目标）',
        nn_classifier: 'ONNX 分类模型推理',
        nn_regressor: 'ONNX 回归模型推理',
        sort_select: '按字段排序并选择结果',
        roi_resolver: '将 base/logical/physical ROI 预解析为 logical 像素并写入上下文变量',
        // spec-2026-08-26 P2: 语义层 descriptions
        uia_set_value: '通过无障碍树给编辑控件注入值（无需焦点/可见）',
        uia_invoke: '通过无障碍树触发按钮控件（无需坐标点击）',
        uia_get_state: '读取控件值/名称/可见性用于验证',
        uia_get_window_title: '读取当前前台窗口标题',
        uia_select: '通过无障碍树在下拉/列表中选择选项',
        uia_scroll: '通过无障碍树滚动可滚动区域（方向/幅度）',
        template_match_any: '任一模板匹配即命中（逐一点击模板中的第一个命中的直击）',
        swipe_until: '按指定方向持续滑动直到任一模板命中',
        log_message: '把 ${var} 变量渲染后的消息写入日志/控制台（调试审计）',
      } as Record<PipelineNodeType, string>
    )[type],
    icon: ICON_KEYS[type],
    category: NODE_TYPE_CATEGORY[type],
  }),
);

/** Pipeline list item */

export interface PipelineListItem {
  id: number;
  name: string;
  description: string;
  version: string;
  created_at: string;
  updated_at: string;
}

/** Pipeline details — matches backend PipelineSerializer */

export interface Pipeline {
  id: number;
  name: string;
  description: string;
  user?: number;
  graph_data: Record<string, unknown>;
  is_template?: boolean;
  estimated_duration_ms?: number | null;
  version: number;
  created_at: string;
  updated_at: string;
}

/** Pipeline snapshot — matches backend PipelineSnapshotSerializer */

export interface PipelineSnapshot {
  id: number;
  version: number;
  graph_data: Record<string, unknown>;
  change_summary: string;
  created_at: string;
}

/** 2FA setup response */
