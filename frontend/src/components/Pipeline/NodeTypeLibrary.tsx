import { useState, useMemo } from 'react';
import { Collapse, Input, Typography, Badge, Empty } from 'antd';
import {
  AimOutlined,
  DragOutlined,
  EnterOutlined,
  EditOutlined,
  PictureOutlined,
  ScanOutlined,
  BgColorsOutlined,
  ToolOutlined,
  ClockCircleOutlined,
  BranchesOutlined,
  SyncOutlined,
  ForwardOutlined,
  DesktopOutlined,
  ApartmentOutlined,
  EyeOutlined,
  ThunderboltOutlined,
  PlayCircleOutlined,
  StopOutlined,
  BellOutlined,
  RobotOutlined,
  FieldTimeOutlined,
  // Phase 2.5 extension icons for the 16 new node types
  MergeCellsOutlined,
  SplitCellsOutlined,
  CodeOutlined,
  EnvironmentOutlined,
  SwapOutlined,
  ColumnHeightOutlined,
  ClusterOutlined,
  RetweetOutlined,
  BackwardOutlined,
  HourglassOutlined,
  StepForwardOutlined,
  PoweroffOutlined,
  PushpinOutlined,
  DeploymentUnitOutlined,
  LineChartOutlined,
  SortAscendingOutlined,
  // Phase 7.4 extension icon for roi_resolver
  BorderOuterOutlined,
  // spec-2026-08-26 P2 icons for UIAutomation semantic nodes
  FormOutlined,
  SelectOutlined,
  IdcardOutlined,
  CheckSquareOutlined,
  ArrowsAltOutlined,
  FileTextOutlined,
} from '@ant-design/icons';
import {
  NODE_TYPE_LIBRARY,
  CATEGORY_COLORS,
  type NodeTypeDefinition,
  type NodeCategory,
  type PipelineNodeType,
} from '@/types/models';

const ICON_MAP: Record<string, React.ReactNode> = {
  Click: <AimOutlined />,
  Swipe: <DragOutlined />,
  LongPress: <ThunderboltOutlined />,
  KeyPress: <EnterOutlined />,
  TextInput: <EditOutlined />,
  Template: <PictureOutlined />,
  OCR: <ScanOutlined />,
  ColorDetect: <BgColorsOutlined />,
  Feature: <ToolOutlined />,
  NeuralNetwork: <RobotOutlined />,
  Wait: <ClockCircleOutlined />,
  RandomDelay: <FieldTimeOutlined />,
  Branch: <BranchesOutlined />,
  Loop: <SyncOutlined />,
  Goto: <ForwardOutlined />,
  Device: <DesktopOutlined />,
  StartApp: <PlayCircleOutlined />,
  StopApp: <StopOutlined />,
  Monitor: <EyeOutlined />,
  Notify: <BellOutlined />,
  SubPipeline: <ApartmentOutlined />,
  // Phase 2.5 extension icons — keys must match ICON_KEYS in models.ts
  AndMatch: <MergeCellsOutlined />,
  OrMatch: <SplitCellsOutlined />,
  CustomMatch: <CodeOutlined />,
  DirectHit: <EnvironmentOutlined />,
  MultiSwipe: <SwapOutlined />,
  MultiScroll: <ColumnHeightOutlined />,
  MultiTouch: <ClusterOutlined />,
  Wheel: <RetweetOutlined />,
  JumpBack: <BackwardOutlined />,
  WaitFreezes: <HourglassOutlined />,
  Next: <StepForwardOutlined />,
  Stop: <PoweroffOutlined />,
  Anchor: <PushpinOutlined />,
  NNClassifier: <DeploymentUnitOutlined />,
  NNRegressor: <LineChartOutlined />,
  SortSelect: <SortAscendingOutlined />,
  // Phase 7.4 extension — ROI pre-resolver (rectangular region icon)
  ROIResolver: <BorderOuterOutlined />,
  // spec-2026-08-26 P2 — UIAutomation 语义层 icons (accessibility 注入)
  UiaSetValue: <FormOutlined />,
  UiaInvoke: <SelectOutlined />,
  UiaGetState: <EyeOutlined />,
  UiaWindowTitle: <IdcardOutlined />,
  UiaSelect: <CheckSquareOutlined />,
  UiaScroll: <ArrowsAltOutlined />,
  // 2026-08-26: 存量 agent 节点暴露
  TemplateMatchAny: <PictureOutlined />,
  SwipeUntil: <DragOutlined />,
  LogMessage: <FileTextOutlined />,
};

const CATEGORY_ORDER: NodeCategory[] = [
  '画面操作',
  '画面识别',
  '智能识别',
  '逻辑控制',
  '等待延迟',
  '设备控制',
  '监控触发',
  '通知告警',
  '子流程',
  '语义操作',
];

interface NodeTypeLibraryProps {
  onDragStart?: (event: React.DragEvent, nodeType: PipelineNodeType) => void;
  readonly?: boolean;
}

export function NodeTypeLibrary({ onDragStart, readonly }: NodeTypeLibraryProps) {
  const [search, setSearch] = useState('');

  const filteredLibrary = useMemo(() => {
    if (!search.trim()) return NODE_TYPE_LIBRARY;
    const kw = search.toLowerCase();
    return NODE_TYPE_LIBRARY.filter(
      (item) => item.label.toLowerCase().includes(kw) || item.description.toLowerCase().includes(kw),
    );
  }, [search]);

  const grouped = useMemo(() => {
    const map: Record<NodeCategory, NodeTypeDefinition[]> = {
      画面操作: [],
      画面识别: [],
      智能识别: [],
      逻辑控制: [],
      等待延迟: [],
      设备控制: [],
      监控触发: [],
      通知告警: [],
      子流程: [],
      语义操作: [],
    };
    filteredLibrary.forEach((item) => {
      map[item.category].push(item);
    });
    return map;
  }, [filteredLibrary]);

  const collapseItems = CATEGORY_ORDER.filter((cat) => grouped[cat].length > 0).map((cat) => ({
    key: cat,
    label: (
      <span>
        <Badge color={CATEGORY_COLORS[cat]} text={cat} />
        <span className="gaf-ml-xs gaf-text-xs" style={{ color: '#999' }}>
          ({grouped[cat].length})
        </span>
      </span>
    ),
    children: (
      <div className="gaf-flex-col gaf-gap-xs">
        {grouped[cat].map((item) => (
          <div
            key={item.type}
            draggable={!readonly}
            onDragStart={(e) => {
              e.dataTransfer.setData('application/reactflow', item.type);
              e.dataTransfer.effectAllowed = 'move';
              onDragStart?.(e, item.type);
            }}
            className="gaf-flex-center gaf-gap-sm"
            style={{
              padding: '6px 8px',
              borderRadius: 4,
              border: `1px solid ${CATEGORY_COLORS[cat]}40`,
              borderLeft: `3px solid ${CATEGORY_COLORS[cat]}`,
              cursor: readonly ? 'default' : 'grab',
              background: '#fff',
              transition: 'box-shadow 0.2s',
            }}
            onMouseEnter={(e) => {
              if (!readonly) {
                (e.currentTarget as HTMLDivElement).style.boxShadow = '0 2px 6px rgba(0,0,0,0.12)';
              }
            }}
            onMouseLeave={(e) => {
              (e.currentTarget as HTMLDivElement).style.boxShadow = 'none';
            }}
          >
            <span className="gaf-text-md" style={{ color: CATEGORY_COLORS[cat] }}>
              {ICON_MAP[item.icon] || <ToolOutlined />}
            </span>
            <div className="gaf-flex-1" style={{ minWidth: 0 }}>
              <Typography.Text strong className="gaf-text-xs" style={{ display: 'block' }}>
                {item.label}
              </Typography.Text>
              <Typography.Text type="secondary" style={{ fontSize: 10, display: 'block' }} ellipsis>
                {item.description}
              </Typography.Text>
            </div>
          </div>
        ))}
      </div>
    ),
  }));

  return (
    <div className="gaf-flex-col gaf-py-sm gaf-px-md" style={{ height: '100%' }}>
      <Typography.Title level={5} style={{ margin: '4px 0 8px 0' }}>
        节点类型
      </Typography.Title>
      <Input.Search
        placeholder="搜索节点…"
        allowClear
        size="small"
        value={search}
        onChange={(e) => setSearch(e.target.value)}
        className="gaf-mb-sm"
      />
      <div className="gaf-flex-1" style={{ overflow: 'auto' }}>
        {collapseItems.length > 0 ? (
          <Collapse size="small" ghost defaultActiveKey={CATEGORY_ORDER} items={collapseItems} />
        ) : (
          <Empty description="无匹配节点" image={Empty.PRESENTED_IMAGE_SIMPLE} />
        )}
      </div>
    </div>
  );
}

export default NodeTypeLibrary;
