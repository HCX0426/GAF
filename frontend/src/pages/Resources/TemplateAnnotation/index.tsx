/**
 * R37-P1 C5 — TemplateAnnotationPage Tabs wrapper
 *
 * Two tabs:
 *   Tab 1 "实时标注" (LiveAnnotationTab) — real-time screenshot stream + ad-hoc
 *     drawing tools (rect/polygon/line/point) + mock template-match preview.
 *     Annotations are NOT persisted (debug flow).
 *   Tab 2 "模板标注" (TemplateAnnotationTab) — pick a ResourcePack + Template,
 *     draw rect annotations on the template image, persist via
 *     /api/v2/resources/annotations/. Annotations reload on template switch.
 *
 * Plan §C5: DeviceCard's test-screenshot button was removed; screenshot testing
 * now lives in Tab 1. Full device operation (click/input/OCR) integration is
 * deferred to R37-P2.
 */
import { Tabs } from 'antd';
import { useTranslation } from '@/i18n';
import PageWrapper from '@/components/Common/PageWrapper';
import LiveAnnotationTab from './LiveAnnotationTab';
import TemplateAnnotationTab from './TemplateAnnotationTab';

export function TemplateAnnotationPage() {
  const t = useTranslation();

  return (
    <PageWrapper>
      <Tabs
        defaultActiveKey="live"
        items={[
          {
            key: 'live',
            label: t('templateAnnotation.tab_live'),
            children: <LiveAnnotationTab />,
          },
          {
            key: 'template',
            label: t('templateAnnotation.tab_template'),
            children: <TemplateAnnotationTab />,
          },
        ]}
      />
    </PageWrapper>
  );
}

export default TemplateAnnotationPage;
