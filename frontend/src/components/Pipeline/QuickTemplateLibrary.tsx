/**
 * Quick template library
 * Left panel showing reusable pre-built Pipeline templates by category
 */
import React, { useEffect, useState } from 'react';
import { Card, Input, Tag, Spin, Button, App } from 'antd';
import { SearchOutlined, PlusOutlined } from '@ant-design/icons';
import { listPipelines } from '@/api/pipelines';
import type { PipelineSummary } from '@/api/pipelines';
import { useTranslation } from '@/i18n';

interface QuickTemplateLibraryProps {
  onSelect: (pipeline: PipelineSummary) => void;
}

/**
 * Quick template library component with search and template listing
 */
const QuickTemplateLibrary: React.FC<QuickTemplateLibraryProps> = ({ onSelect }) => {
  const { message } = App.useApp();
  const t = useTranslation();
  const [templates, setTemplates] = useState<PipelineSummary[]>([]);
  const [search, setSearch] = useState('');
  const [loading, setLoading] = useState(true);

  /** Load template list on mount */
  useEffect(() => {
    listPipelines({ is_template: true })
      .then((r) => setTemplates(r.results))
      .catch(() => message.error(t('pipelineEditor.msg_template_list_load_failed')))
      .finally(() => setLoading(false));
  }, []);

  /** Filter templates by search keyword (name or description) */
  const filtered = templates.filter(
    (t) =>
      t.name.toLowerCase().includes(search.toLowerCase()) ||
      (t.description || '').toLowerCase().includes(search.toLowerCase()),
  );

  return (
    <Card
      title="快速模板库"
      size="small"
      extra={
        <Input
          prefix={<SearchOutlined />}
          size="small"
          placeholder="搜索模板…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          style={{ width: 160 }}
        />
      }
    >
      {loading ? (
        <Spin style={{ display: 'block', textAlign: 'center', padding: 20 }} />
      ) : (
        <div>
          {filtered.map((item) => (
            <div key={item.id} className="gaf-flex-center gaf-py-md" style={{ borderBottom: '1px solid #f0f0f0' }}>
              <div className="gaf-flex-1" style={{ minWidth: 0 }}>
                <div className="gaf-font-medium">{item.name}</div>
                <div style={{ color: '#666', fontSize: 13 }}>
                  {item.description && <span className="gaf-mr-sm">{item.description}</span>}
                  <Tag>v{item.version}</Tag>
                  {item.estimated_duration_ms != null && item.estimated_duration_ms > 0 && (
                    <Tag color="default">{(item.estimated_duration_ms / 1000).toFixed(1)}s</Tag>
                  )}
                </div>
              </div>
              <Button size="small" type="primary" icon={<PlusOutlined />} onClick={() => onSelect(item)}>
                使用
              </Button>
            </div>
          ))}
        </div>
      )}
    </Card>
  );
};

export default QuickTemplateLibrary;
