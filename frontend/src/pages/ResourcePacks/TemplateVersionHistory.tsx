/**
 * Template version history component (P-013)
 * Displays a timeline of template versions with restore capability
 */
import { useEffect, useState } from 'react';
import { Timeline, Button, Popconfirm, Tag, Spin, Empty, App, theme as antTheme } from 'antd';
import { UndoOutlined } from '@ant-design/icons';
import { fetchTemplateVersions, restoreTemplateVersion, type TemplateVersion } from '@/api/resources';
import { useTranslation, getLocale } from '@/i18n';

interface TemplateVersionHistoryProps {
  /** The template ID to show version history for */
  templateId: number;
}

/**
 * TemplateVersionHistory - displays version history timeline for a template
 * @param props - Component props including templateId
 */
export function TemplateVersionHistory({ templateId }: TemplateVersionHistoryProps) {
  const { token } = antTheme.useToken();
  const { message } = App.useApp();
  const t = useTranslation();
  const [versions, setVersions] = useState<TemplateVersion[]>([]);
  const [loading, setLoading] = useState(false);
  const [restoring, setRestoring] = useState<number | null>(null);

  useEffect(() => {
    loadVersions();
  }, [templateId]);

  /** Load version history for the given template */
  const loadVersions = async () => {
    setLoading(true);
    try {
      const data = await fetchTemplateVersions(templateId);
      setVersions(data);
    } catch {
      message.error(t('resourcePacks.msg_load_versions_failed'));
    } finally {
      setLoading(false);
    }
  };

  /** Restore template to a specific version */
  const handleRestore = async (versionId: number) => {
    setRestoring(versionId);
    try {
      await restoreTemplateVersion(versionId);
      message.success(t('resourcePacks.msg_restore_success'));
      await loadVersions();
    } catch {
      message.error(t('resourcePacks.msg_restore_failed'));
    } finally {
      setRestoring(null);
    }
  };

  if (loading) {
    return <Spin size="small" />;
  }

  if (versions.length === 0) {
    return <Empty description={t('resourcePacks.empty')} image={Empty.PRESENTED_IMAGE_SIMPLE} />;
  }

  return (
    <Timeline
      items={versions.map((version) => ({
        color: 'blue',
        content: (
          <div>
            <div className="gaf-mb-xs">
              <Tag color="blue">v{version.version_number}</Tag>
              {version.comment && (
                <Tag color="default" className="gaf-ml-xs">
                  {version.comment}
                </Tag>
              )}
            </div>
            <div className="gaf-mb-sm gaf-text-xs" style={{ color: token.colorTextTertiary }}>
              {version.created_by} · {new Date(version.created_at).toLocaleString(getLocale())}
            </div>
            <Popconfirm
              title={t('resourcePacks.confirm_restore_title')}
              description={t('resourcePacks.confirm_restore_desc')}
              onConfirm={() => handleRestore(version.id)}
              okText={t('resourcePacks.confirm_ok')}
              cancelText={t('resourcePacks.confirm_cancel')}
            >
              <Button size="small" icon={<UndoOutlined />} loading={restoring === version.id}>
                {t('resourcePacks.btn_restore')}
              </Button>
            </Popconfirm>
          </div>
        ),
      }))}
    />
  );
}

export default TemplateVersionHistory;
