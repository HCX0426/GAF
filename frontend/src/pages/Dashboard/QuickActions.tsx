/**
 * fast operation bar component
 *
 * provides dashboard page four items shortcut entry button and enabled task progress show
 */
import { useNavigate } from 'react-router-dom';
import { Card, Row, Col, Button, Tag, App } from 'antd';
import {
  PlusOutlined,
  ImportOutlined,
  DesktopOutlined,
  ThunderboltOutlined,
  PlayCircleOutlined,
} from '@ant-design/icons';
import { useTaskStore } from '@/stores/useTaskStore';
import { useTranslation } from '@/i18n';

export function QuickActions() {
  const { message } = App.useApp();
  const navigate = useNavigate();
  const t = useTranslation();
  const { tasks, executeTask } = useTaskStore();

  const enabledTasks = tasks.filter((t) => t.is_enabled);

  const handleQuickExecute = async () => {
    if (enabledTasks.length === 0) {
      message.warning(t('dashboard.no_executable_tasks'));
      return;
    }
    const task = enabledTasks[0];
    try {
      await executeTask(task.id);
      message.success(t('dashboard.task_started', { name: task.name }));
    } catch {
      message.error(t('dashboard.status_failed'));
    }
  };

  return (
    <Card title={t('dashboard.widget_quick_actions')}>
      <Row gutter={[12, 12]}>
        <Col span={6}>
          <Button type="primary" icon={<PlusOutlined />} block onClick={() => navigate('/tasks')}>
            {t('dashboard.create_task')}
          </Button>
        </Col>
        <Col span={6}>
          <Button icon={<ImportOutlined />} block onClick={() => navigate('/tasks/marketplace')}>
            {t('dashboard.import_market')}
          </Button>
        </Col>
        <Col span={6}>
          <Button icon={<DesktopOutlined />} block onClick={() => navigate('/devices')}>
            {t('dashboard.device_management')}
          </Button>
        </Col>
        <Col span={6}>
          <Button icon={<ThunderboltOutlined />} block onClick={handleQuickExecute}>
            {t('dashboard.quick_execute')}
          </Button>
        </Col>
      </Row>
      {enabledTasks.length > 0 && (
        <div className="gaf-mt-lg">
          <div className="gaf-font-medium gaf-mb-sm">
            <PlayCircleOutlined style={{ marginRight: 6 }} />
            {t('dashboard.enabled_tasks', { count: enabledTasks.length })}
          </div>
          {enabledTasks.slice(0, 5).map((task) => (
            <div key={task.id} className="gaf-mb-md">
              <div className="gaf-flex-between gaf-mb-xs">
                <span>{task.name}</span>
                <Tag color="blue">{t('tasks.status_enabled')}</Tag>
              </div>
            </div>
          ))}
        </div>
      )}
    </Card>
  );
}

export default QuickActions;
