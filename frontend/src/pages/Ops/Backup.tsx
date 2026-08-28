/**
 * backup recover page
 * supports create full backup ( download ZIP), upload backup file recover
 */
import { useState } from 'react';
import { Button, Card, App, Upload, Popconfirm, Typography, Space, Badge } from 'antd';
import { DownloadOutlined, UploadOutlined, WarningOutlined, ScheduleOutlined } from '@ant-design/icons';
import { createBackup, restoreBackup } from '@/api/ops';
import { useTranslation } from '@/i18n';
import PageWrapper from '@/components/Common/PageWrapper';

const { Text } = Typography;

/** backup recover page */
export function BackupPage() {
  const { message } = App.useApp();
  const [creating, setCreating] = useState(false);
  const [restoring, setRestoring] = useState(false);
  const t = useTranslation();

  /** create full backup and trigger browser download */
  const handleCreateBackup = async () => {
    setCreating(true);
    try {
      const blob = await createBackup();
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `gaf_backup_${new Date().toISOString().slice(0, 10)}.zip`;
      a.click();
      URL.revokeObjectURL(url);
      message.success(t('backup.msg_create_success'));
    } catch {
      message.error(t('backup.msg_create_unavailable'));
    } finally {
      setCreating(false);
    }
  };

  /** upload backup file and recover */
  const handleRestore = async (file: File) => {
    setRestoring(true);
    try {
      await restoreBackup(file);
      message.success(t('backup.msg_restore_success'));
    } catch {
      message.warning(t('backup.msg_restore_mock'));
    } finally {
      setRestoring(false);
    }
  };

  return (
    <PageWrapper title={t('backup.page_title')}>
      <Card title={t('backup.card_schedule_title')} className="gaf-mb-lg">
        <Space>
          <Badge status="processing" />
          <Text type="secondary" className="gaf-mb-md gaf-display-block">
            {t('backup.card_schedule_desc')}
          </Text>
          <ScheduleOutlined style={{ opacity: 0.6 }} />
        </Space>
      </Card>

      <Card title={t('backup.card_create_title')} className="gaf-mb-lg">
        <Text type="secondary" className="gaf-mb-md gaf-display-block">
          {t('backup.card_create_desc')}
        </Text>
        <Button type="primary" icon={<DownloadOutlined />} loading={creating} onClick={handleCreateBackup}>
          {t('backup.btn_create')}
        </Button>
      </Card>

      <Card title={t('backup.card_restore_title')}>
        <Text type="secondary" className="gaf-mb-md gaf-display-block">
          {t('backup.card_restore_desc')}
        </Text>
        <Space>
          <Upload
            accept=".zip"
            maxCount={1}
            showUploadList={false}
            beforeUpload={(file) => {
              handleRestore(file);
              return false;
            }}
          >
            <Button icon={<UploadOutlined />} loading={restoring}>
              {t('backup.btn_restore')}
            </Button>
          </Upload>
          <Popconfirm
            title={t('backup.confirm_restore_title')}
            icon={<WarningOutlined style={{ color: 'red' }} />}
            okText={t('backup.confirm_restore_ok')}
            cancelText={t('backup.confirm_restore_cancel')}
          >
            <Button danger icon={<WarningOutlined />}>
              {t('backup.btn_warning')}
            </Button>
          </Popconfirm>
        </Space>
      </Card>
    </PageWrapper>
  );
}

export default BackupPage;
