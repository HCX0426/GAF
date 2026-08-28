import React, { useState } from 'react';
import { Radio, Card, Button, Progress, App, Tag, Space, theme as antTheme } from 'antd';
import { RocketOutlined, ForwardOutlined } from '@ant-design/icons';
import { importExamplePacks, getExamplePacks } from '@/api/init';
import { useTranslation } from '@/i18n';

interface ExamplePack {
  id: number;
  name: string;
  description: string;
  pipeline_count: number;
  tags: string[];
}

interface StepRecommendedTemplatesProps {
  onFinish: () => void;
}

/**
 * Step 4: Select recommended templates
 * Three options: BD2-AUTO import / Install example task packs / Skip
 */
const StepRecommendedTemplates: React.FC<StepRecommendedTemplatesProps> = ({ onFinish }) => {
  const t = useTranslation();
  const { message } = App.useApp();
  const { token } = antTheme.useToken();
  const [option, setOption] = useState<string>('examples');
  const [examples, setExamples] = useState<ExamplePack[]>([]);
  const [importing, setImporting] = useState(false);
  const [progress, setProgress] = useState(0);

  /** Load example pack list from API */
  const loadExamples = async () => {
    try {
      const data = await getExamplePacks();
      setExamples(data as unknown as ExamplePack[]);
    } catch {
      message.error('Failed to load templates');
    }
  };

  /** Handle finish button click based on selected option */
  const handleFinish = async () => {
    if (option === 'skip') {
      onFinish();
      return;
    }
    if (option === 'examples') {
      setImporting(true);
      setProgress(30);
      try {
        await importExamplePacks();
        setProgress(100);
        message.success(t('setup.templates.msg_import_success'));
        onFinish();
      } catch {
        message.error(t('setup.templates.msg_import_failed'));
      } finally {
        setImporting(false);
      }
    }
  };

  return (
    <div>
      <Radio.Group
        value={option}
        onChange={(e) => {
          setOption(e.target.value);
          if (e.target.value === 'examples') loadExamples();
        }}
        className="gaf-w-full"
      >
        <Space orientation="vertical" className="gaf-w-full">
          <Radio value="examples">
            <RocketOutlined /> {t('setup.templates.option_examples')}
          </Radio>
          {option === 'examples' && examples.length > 0 && (
            <div>
              {examples.map((item) => (
                <div
                  key={item.id}
                  className="gaf-flex-between gaf-py-md gaf-px-lg"
                  style={{ borderBottom: `1px solid ${token.colorBorderSecondary}` }}
                >
                  <div className="gaf-flex-1" style={{ minWidth: 0 }}>
                    <div className="gaf-font-medium">{item.name}</div>
                    <div className="gaf-text-13" style={{ color: token.colorTextSecondary }}>
                      {item.description}
                    </div>
                  </div>
                  <Space>
                    {item.tags && item.tags.map((tag) => <Tag key={tag}>{tag}</Tag>)}
                    <Tag color="blue">{t('setup.templates.tag_pipeline_count', { count: item.pipeline_count })}</Tag>
                  </Space>
                </div>
              ))}
            </div>
          )}
          <Radio value="skip">
            <ForwardOutlined /> {t('setup.templates.option_skip')}
          </Radio>
        </Space>
      </Radio.Group>
      {importing && <Progress percent={progress} className="gaf-mt-lg" />}
      <Button type="primary" onClick={handleFinish} className="gaf-mt-xl" loading={importing} block size="large">
        {t('setup.btn_finish')}
      </Button>
      <Card size="small" className="gaf-mt-lg" style={{ background: token.colorBgLayout }}>
        <strong>{t('setup.templates.card_title')}</strong>
        <p className="gaf-m-0">{t('setup.templates.card_desc')}</p>
      </Card>
    </div>
  );
};

export default StepRecommendedTemplates;
