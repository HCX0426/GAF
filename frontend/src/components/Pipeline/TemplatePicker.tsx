import { useState, useEffect, useMemo } from 'react';
import { Modal, Card, Row, Col, Tag, Typography, Button, Spin } from 'antd';
import {
  WindowsOutlined,
  AndroidOutlined,
  SafetyOutlined,
  BugOutlined,
  DeploymentUnitOutlined,
  PictureOutlined,
} from '@ant-design/icons';
import { fetchPipelineTemplates } from '@/api/misc';
import type { ReactNode } from 'react';
import type { PipelineJSON } from '@/utils/pipelineConverter';

interface PipelineTemplate {
  id: string;
  name: string;
  description: string;
  icon: ReactNode;
  tags: string[];
  nodeCount: number;
  pipelineData?: PipelineJSON;
}

const TEMPLATES: PipelineTemplate[] = [
  {
    id: 'login_test',
    name: '登录测试流程',
    description: '打开应用 → 输入账号 → 输入密码 → 点击登录 → 验证结果',
    icon: <SafetyOutlined style={{ fontSize: 32, color: '#52c41a' }} />,
    tags: ['通用'],
    nodeCount: 5,
    pipelineData: {
      name: '登录测试流程',
      nodes: [
        {
          id: 'n1',
          type: 'start_app',
          position: { x: 100, y: 50 },
          data: { label: '启动应用', config: { package_name: 'com.example.app' } },
        },
        {
          id: 'n2',
          type: 'template_match',
          position: { x: 100, y: 150 },
          data: { label: '等待登录界面', config: { template_id: 'login_page', threshold: 0.8 } },
        },
        {
          id: 'n3',
          type: 'click',
          position: { x: 100, y: 250 },
          data: { label: '点击账号输入框', config: { x: 720, y: 400 } },
        },
        {
          id: 'n4',
          type: 'text_input',
          position: { x: 100, y: 350 },
          data: { label: '输入账号密码', config: { text: '{{account}}' } },
        },
        {
          id: 'n5',
          type: 'click',
          position: { x: 100, y: 450 },
          data: { label: '点击登录按钮', config: { x: 720, y: 600 } },
        },
      ],
      edges: [
        { id: 'e1', source: 'n1', target: 'n2' },
        { id: 'e2', source: 'n2', target: 'n3' },
        { id: 'e3', source: 'n3', target: 'n4' },
        { id: 'e4', source: 'n4', target: 'n5' },
      ],
    },
  },
  {
    id: 'app_install',
    name: '应用安装流程',
    description: '打开应用商店 → 搜索 → 下载 → 安装 → 验证',
    icon: <DeploymentUnitOutlined style={{ fontSize: 32, color: '#1890ff' }} />,
    tags: ['Windows', '移动端'],
    nodeCount: 5,
    pipelineData: {
      name: '应用安装流程',
      nodes: [
        {
          id: 'n1',
          type: 'start_app',
          position: { x: 100, y: 50 },
          data: { label: '打开应用商店', config: { package_name: 'com.android.vending' } },
        },
        {
          id: 'n2',
          type: 'click',
          position: { x: 100, y: 150 },
          data: { label: '点击搜索框', config: { x: 540, y: 120 } },
        },
        {
          id: 'n3',
          type: 'text_input',
          position: { x: 100, y: 250 },
          data: { label: '输入应用名', config: { text: '{{app_name}}' } },
        },
        {
          id: 'n4',
          type: 'click',
          position: { x: 100, y: 350 },
          data: { label: '点击安装按钮', config: { x: 360, y: 500 } },
        },
        {
          id: 'n5',
          type: 'wait',
          position: { x: 100, y: 450 },
          data: { label: '等待安装完成', config: { duration: 30000 } },
        },
      ],
      edges: [
        { id: 'e1', source: 'n1', target: 'n2' },
        { id: 'e2', source: 'n2', target: 'n3' },
        { id: 'e3', source: 'n3', target: 'n4' },
        { id: 'e4', source: 'n4', target: 'n5' },
      ],
    },
  },
  {
    id: 'crash_log',
    name: '崩溃日志收集',
    description: '触发操作 → 检测崩溃 → 收集日志 → 上传分析',
    icon: <BugOutlined style={{ fontSize: 32, color: '#ff4d4f' }} />,
    tags: ['调试'],
    nodeCount: 4,
    pipelineData: {
      name: '崩溃日志收集',
      nodes: [
        {
          id: 'n1',
          type: 'click',
          position: { x: 100, y: 50 },
          data: { label: '触发目标操作', config: { x: 720, y: 400 } },
        },
        {
          id: 'n2',
          type: 'monitor',
          position: { x: 100, y: 150 },
          data: { label: '检测异常弹窗', config: { check_type: 'crash_dialog' } },
        },
        {
          id: 'n3',
          type: 'branch',
          position: { x: 100, y: 250 },
          data: { label: '判断是否崩溃', config: { condition: '{{crash_detected}}' } },
        },
        {
          id: 'n4',
          type: 'notify',
          position: { x: 100, y: 350 },
          data: { label: '上报日志', config: { webhook_url: '', include_screenshot: true } },
        },
      ],
      edges: [
        { id: 'e1', source: 'n1', target: 'n2' },
        { id: 'e2', source: 'n2', target: 'n3' },
        { id: 'e3', source: 'n3', target: 'n4', label: '是' },
      ],
    },
  },
  {
    id: 'web_automation',
    name: 'Web 自动化流程',
    description: '打开浏览器 → 导航 → 操作 → 截图 → 验证',
    icon: <WindowsOutlined style={{ fontSize: 32, color: '#722ed1' }} />,
    tags: ['Web'],
    nodeCount: 5,
    pipelineData: {
      name: 'Web 自动化流程',
      nodes: [
        {
          id: 'n1',
          type: 'start_app',
          position: { x: 100, y: 50 },
          data: { label: '打开浏览器', config: { package_name: 'chrome.exe' } },
        },
        {
          id: 'n2',
          type: 'text_input',
          position: { x: 100, y: 150 },
          data: { label: '输入URL', config: { text: '{{target_url}}' } },
        },
        {
          id: 'n3',
          type: 'key_press',
          position: { x: 100, y: 250 },
          data: { label: '回车导航', config: { key: 'enter' } },
        },
        {
          id: 'n4',
          type: 'wait',
          position: { x: 100, y: 350 },
          data: { label: '等待页面加载', config: { duration: 3000 } },
        },
        {
          id: 'n5',
          type: 'click',
          position: { x: 100, y: 450 },
          data: { label: '截图保存', config: { x: 100, y: 100 } },
        },
      ],
      edges: [
        { id: 'e1', source: 'n1', target: 'n2' },
        { id: 'e2', source: 'n2', target: 'n3' },
        { id: 'e3', source: 'n3', target: 'n4' },
        { id: 'e4', source: 'n4', target: 'n5' },
      ],
    },
  },
  {
    id: 'mobile_test',
    name: '移动端测试流程',
    description: '连接设备 → 启动应用 → 执行操作 → 截图对比 → 报告',
    icon: <AndroidOutlined style={{ fontSize: 32, color: '#13c2c2' }} />,
    tags: ['移动端'],
    nodeCount: 5,
    pipelineData: {
      name: '移动端测试流程',
      nodes: [
        {
          id: 'n1',
          type: 'device_control',
          position: { x: 100, y: 50 },
          data: { label: '连接设备', config: { action: 'connect' } },
        },
        {
          id: 'n2',
          type: 'start_app',
          position: { x: 100, y: 150 },
          data: { label: '启动应用', config: { package_name: 'com.example.app' } },
        },
        {
          id: 'n3',
          type: 'click',
          position: { x: 100, y: 250 },
          data: { label: '执行测试操作', config: { x: 540, y: 960 } },
        },
        {
          id: 'n4',
          type: 'ocr',
          position: { x: 100, y: 350 },
          data: { label: 'OCR 文本识别', config: { roi: [0, 0, 1080, 1920], engine: 'rapid' } },
        },
        {
          id: 'n5',
          type: 'notify',
          position: { x: 100, y: 450 },
          data: { label: '发送测试报告', config: { webhook_url: '', include_screenshot: true } },
        },
      ],
      edges: [
        { id: 'e1', source: 'n1', target: 'n2' },
        { id: 'e2', source: 'n2', target: 'n3' },
        { id: 'e3', source: 'n3', target: 'n4' },
        { id: 'e4', source: 'n4', target: 'n5' },
      ],
    },
  },
];

interface TemplatePickerProps {
  open: boolean;
  onClose: () => void;
  onSelect: (template: PipelineTemplate) => void;
  onSelectId?: (templateId: string) => void;
  showSelectButton?: boolean;
}

export function TemplatePicker({ open, onClose, onSelect, onSelectId, showSelectButton }: TemplatePickerProps) {
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [apiTemplates, setApiTemplates] = useState<PipelineTemplate[] | null>(null);
  const [apiLoading, setApiLoading] = useState(false);

  useEffect(() => {
    if (open) {
      setSelectedId(null);
      setApiLoading(true);
      setApiTemplates(null);
      fetchPipelineTemplates<{ id: number | string; name: string; description?: string; tags?: string[] }[]>()
        .then((data) => {
          if (data && Array.isArray(data) && data.length > 0) {
            setApiTemplates(
              data.map((t) => ({
                id: t.id.toString(),
                name: t.name,
                description: t.description || '',
                icon: <PictureOutlined style={{ fontSize: 32 }} />,
                tags: t.tags || [],
                nodeCount: 0,
              })),
            );
          }
        })
        .catch(() => {
          setApiTemplates(null);
        })
        .finally(() => {
          setApiLoading(false);
        });
    }
  }, [open]);

  const displayTemplates = useMemo(() => apiTemplates || TEMPLATES, [apiTemplates]);

  const handleOk = () => {
    if (selectedId) {
      const template = displayTemplates.find((t) => t.id === selectedId);
      if (template) {
        onSelect(template);
      }
    }
    onClose();
  };

  return (
    <Modal
      title="选择流水线模板"
      open={open}
      onCancel={onClose}
      onOk={handleOk}
      okText="使用模板"
      cancelText="取消"
      width={720}
      okButtonProps={{ disabled: !selectedId }}
    >
      {apiLoading ? (
        <div style={{ textAlign: 'center', padding: 40 }}>
          <Spin description="加载模板列表..." />
        </div>
      ) : (
        <Row gutter={[12, 12]}>
          {displayTemplates.map((template) => (
            <Col key={template.id} span={8}>
              <Card
                size="small"
                hoverable
                style={{
                  borderColor: selectedId === template.id ? '#1890ff' : '#f0f0f0',
                  borderWidth: selectedId === template.id ? 2 : 1,
                }}
                onClick={() => setSelectedId(template.id)}
              >
                <div className="gaf-mb-sm" style={{ textAlign: 'center' }}>
                  {template.icon}
                </div>
                <Typography.Text strong style={{ fontSize: 13, display: 'block', textAlign: 'center' }}>
                  {template.name}
                </Typography.Text>
                <Typography.Paragraph
                  type="secondary"
                  className="gaf-mt-xs gaf-mb-sm gaf-text-xxs"
                  style={{ textAlign: 'center' }}
                  ellipsis={{ rows: 2 }}
                >
                  {template.description}
                </Typography.Paragraph>
                <div style={{ textAlign: 'center' }}>
                  {template.tags.map((tag) => (
                    <Tag key={tag} color="blue" style={{ fontSize: 10 }}>
                      {tag}
                    </Tag>
                  ))}
                  <Tag style={{ fontSize: 10 }}>{template.nodeCount} 个节点</Tag>
                </div>
                {showSelectButton && (
                  <div className="gaf-mt-sm" style={{ textAlign: 'center' }}>
                    <Button
                      type="link"
                      size="small"
                      onClick={(e) => {
                        e.stopPropagation();
                        onSelectId?.(template.id);
                        onClose();
                      }}
                    >
                      选择
                    </Button>
                  </div>
                )}
              </Card>
            </Col>
          ))}
        </Row>
      )}
    </Modal>
  );
}

export type { PipelineTemplate };

export default TemplatePicker;
