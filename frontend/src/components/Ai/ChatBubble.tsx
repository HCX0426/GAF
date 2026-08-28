/**
 * chat bubble component
 * shows single dialog message, supports user and AI role styles
 */
import { Avatar, Typography, Space } from 'antd';
import { UserOutlined, RobotOutlined } from '@ant-design/icons';

/** message role type */
type ChatRole = 'user' | 'assistant';

/** ChatBubble component props */
interface ChatBubbleProps {
  role: ChatRole;
  content: string;
  timestamp?: string;
  isLoading?: boolean;
}

/** role config */
const ROLE_CONFIG: Record<
  ChatRole,
  { icon: React.ReactNode; label: string; align: 'flex-end' | 'flex-start'; bgColor: string }
> = {
  user: {
    icon: <UserOutlined />,
    label: '用户',
    align: 'flex-end',
    bgColor: '#e6f7ff',
  },
  assistant: {
    icon: <RobotOutlined />,
    label: 'AI 助手',
    align: 'flex-start',
    bgColor: '#f6ffed',
  },
};

/**
 * chat message bubble
 * shows different layouts and styles based on role
 */
export function ChatBubble({ role, content, timestamp, isLoading = false }: ChatBubbleProps) {
  const config = ROLE_CONFIG[role];

  return (
    <div className="gaf-flex-col gaf-mb-lg gaf-px-sm" style={{ alignItems: config.align }}>
      <Space align="start" size={8}>
        {role === 'assistant' && <Avatar icon={config.icon} style={{ backgroundColor: '#52c41a' }} />}
        <div>
          <div className="gaf-text-sm gaf-mb-xs" style={{ color: '#888' }}>
            {config.label}
            {timestamp && <span className="gaf-ml-sm">{timestamp}</span>}
          </div>
          <div
            style={{
              maxWidth: 480,
              padding: '10px 14px',
              borderRadius: 12,
              backgroundColor: config.bgColor,
              border: '1px solid #f0f0f0',
              lineHeight: 1.6,
              whiteSpace: 'pre-wrap',
              wordBreak: 'break-word',
            }}
          >
            {isLoading ? (
              <Typography.Text type="secondary">思考中...</Typography.Text>
            ) : (
              <Typography.Text>{content}</Typography.Text>
            )}
          </div>
        </div>
        {role === 'user' && <Avatar icon={config.icon} style={{ backgroundColor: '#1890ff' }} />}
      </Space>
    </div>
  );
}

export default ChatBubble;
