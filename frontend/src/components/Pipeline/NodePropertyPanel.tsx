import { useState, useCallback, useEffect } from 'react';
import {
  Form,
  Input,
  InputNumber,
  Select,
  Slider,
  Switch,
  Button,
  Checkbox,
  Empty,
  Divider,
  Typography,
  ColorPicker,
  Alert,
  theme as antTheme,
} from 'antd';
import { AimOutlined } from '@ant-design/icons';
import { type PipelineNodeType } from '@/types/models';
import TemplatePicker from './TemplatePicker';
import { fetchMonitorRules } from '@/api/monitors';
import { listPipelines } from '@/api/pipelines';
import { resolveErrorMessage } from '@/utils/errorHandler';
// Task 5.1 (P3, 2026-07-29, N193 已知限制解决): NodePropertyPanel 全量 i18n 化
// 原 100+ 硬编码中文 label + 4 个英文 label + 12 处校验 message 改为 useTranslation
import { useTranslation } from '@/i18n';

interface NodePropertyPanelProps {
  nodeId?: string;
  nodeType?: PipelineNodeType | null;
  config?: Record<string, unknown>;
  onChange?: (config: Record<string, unknown>) => void;
  onRequestScreenshot?: () => void;
}

const { TextArea } = Input;

export function NodePropertyPanel({ nodeId, nodeType, config, onChange, onRequestScreenshot }: NodePropertyPanelProps) {
  const { token } = antTheme.useToken();
  // Task 5.1: i18n hook, 所有硬编码字符串改为 t('npp.xxx')
  const t = useTranslation();
  const [templatePickerOpen, setTemplatePickerOpen] = useState(false);
  const [templateSelectTarget, setTemplateSelectTarget] = useState<string>('template_id');
  // Task 4.25 (P0-5): sub_pipeline JSON 解析错误提示 state, 必须声明否则运行时崩溃
  const [jsonError, setJsonError] = useState<string>('');
  // Task 4.30 (P1-19): monitor/sub_pipeline options 拉取, 替代硬编码空数组
  const [monitorRuleOptions, setMonitorRuleOptions] = useState<{ label: string; value: string }[]>([]);
  const [pipelineOptions, setPipelineOptions] = useState<{ label: string; value: string }[]>([]);
  // Task 4.56 (P1-36, 2026-07-28): fetchMonitorRules/fetchPipelines 错误提示
  // 原 .catch(() => {}) 静默失败, 用户不知道是网络问题还是无规则; 改为用 Alert 展示
  const [fetchRuleError, setFetchRuleError] = useState<string>('');
  const [fetchPipelineError, setFetchPipelineError] = useState<string>('');

  // Task 4.32 (P1-21): 节点级实时 schema 校验 — 检测当前节点缺失的必填字段,
  // 在面板顶部展示 Alert, 让用户切换节点时立即发现配置错误, 不必点"校验"按钮。
  // 与后端 validators.py 的 node_required dict 保持一致 (snake_case canonical),
  // 兼容 legacy camelCase 字段。
  const nodeRequiredFields: Record<string, Array<[string, string | null]>> = {
    click: [
      ['x', null],
      ['y', null],
    ],
    direct_hit: [
      ['x', null],
      ['y', null],
    ],
    swipe: [
      ['x1', null],
      ['y1', null],
      ['x2', null],
      ['y2', null],
    ],
    key_press: [['key', null]],
    text_input: [['text', null]],
    template_match: [
      ['template_id', 'templateId'],
      ['threshold', null],
    ],
    template_match_any: [
      ['templates', null],
      ['threshold', null],
    ],
    ocr: [
      ['engine', null],
      ['language', null],
    ],
    color_detect: [
      ['target_color', null],
      ['tolerance', null],
    ],
    feature_match: [
      ['template_id', null],
      ['min_match_count', null],
    ],
    wait: [['timeout', null]],
    branch: [['condition', null]],
    loop: [['count', 'maxIterations']],
    random_delay: [
      ['min_ms', 'minDelay'],
      ['max_ms', 'maxDelay'],
    ],
    notify: [['channel', 'channels']],
    device_control: [['action', null]],
    monitor: [['rule_id', 'ruleId']],
    sub_pipeline: [['pipeline_id', 'pipelineId']],
    goto: [['target', 'targetLabel']],
    // Task 4.45 (P2-23, 2026-07-28): 补 4 个后端 node_required dict 中的节点类型
    // (login_account/switch_account/switch_resource/captcha_detect),
    // 与 backend/pipeline/validators.py:97-100 字段名口径保持一致。
    login_account: [['account_id', 'accountId']],
    switch_account: [['next_account_id', 'nextAccountId']],
    switch_resource: [['resource_pack_id', 'resourcePackId']],
    captcha_detect: [['targets', null]],
    // spec-2026-08-26 P2: UIAutomation 语义节点必填字段
    uia_set_value: [['value', null]],
    uia_select: [['option', null]],
    uia_scroll: [['direction', null]],
    // 2026-08-26: 存量节点暴露（对齐 backend validators.py node_required）
    swipe_until: [
      ['templates', null],
      ['x1', null],
      ['y1', null],
      ['x2', null],
      ['y2', null],
    ],
    log_message: [['message', null]],
  };

  const missingRequiredFields = useCallback((): string[] => {
    if (!nodeType || !config) return [];
    const required = nodeRequiredFields[nodeType] || [];
    const missing: string[] = [];
    for (const [canonical, legacy] of required) {
      if (config[canonical] === undefined || config[canonical] === null || config[canonical] === '') {
        if (legacy && config[legacy] !== undefined && config[legacy] !== null && config[legacy] !== '') {
          continue; // legacy 字段非空, 视为 filled
        }
        missing.push(canonical);
      }
    }
    return missing;
  }, [nodeType, config]);

  // Task 4.30: 拉取 monitor rules / pipelines 列表填充 options, 让用户能在 UI 选择
  // Task 4.56 (P1-36, 2026-07-28): fetchMonitorRules/fetchPipelines 错误提示
  useEffect(() => {
    if (nodeType !== 'monitor') return;
    let cancelled = false;
    // 切换节点时清空旧错误, 避免上一次失败的状态残留
    setFetchRuleError('');
    fetchMonitorRules({ page: 1, page_size: 100 })
      .then((res) => {
        if (cancelled) return;
        const opts = (res.results || []).map((rule) => ({
          // Task 5.1: i18n 化 default label "规则 #{{id}}"
          label: rule.name || t('npp.mn_rule_default_label', { id: rule.id }),
          value: String(rule.id),
        }));
        setMonitorRuleOptions(opts);
      })
      .catch((err) => {
        if (cancelled) return;
        // 不再静默失败: 用 resolveErrorMessage 解析后端错误码/网络错误, 在面板顶部 Alert 展示
        setFetchRuleError(resolveErrorMessage(err));
      });
    return () => {
      cancelled = true;
    };
  }, [nodeType, t]);

  useEffect(() => {
    if (nodeType !== 'sub_pipeline') return;
    let cancelled = false;
    // 切换节点时清空旧错误, 避免上一次失败的状态残留
    setFetchPipelineError('');
    listPipelines({ page: 1, page_size: 100 })
      .then((res) => {
        if (cancelled) return;
        const opts = (res.results || []).map((p) => ({
          // Task 5.1: i18n 化 default label "Pipeline #{{id}}"
          label: p.name || t('npp.sp_pipeline_default_label', { id: p.id }),
          value: String(p.id),
        }));
        setPipelineOptions(opts);
      })
      .catch((err) => {
        if (cancelled) return;
        // 不再静默失败: 用 resolveErrorMessage 解析后端错误码/网络错误, 在面板顶部 Alert 展示
        setFetchPipelineError(resolveErrorMessage(err));
      });
    return () => {
      cancelled = true;
    };
  }, [nodeType, t]);

  const updateConfig = useCallback(
    (key: string, value: unknown) => {
      if (!config) return;
      const next = { ...config, [key]: value };
      onChange?.(next);
    },
    [config, onChange],
  );

  const updateRoi = useCallback(
    (axis: 'x' | 'y' | 'w' | 'h', value: number | null) => {
      if (!config || config.roi === undefined) return;
      const roi = config.roi as Record<string, number>;
      const nextRoi = { ...roi, [axis]: value ?? 0 };
      const next = { ...config, roi: nextRoi };
      onChange?.(next);
    },
    [config, onChange],
  );

  const renderTemplateSelectButton = (targetKey: string) => (
    <Button
      size="small"
      icon={<AimOutlined />}
      onClick={() => {
        setTemplateSelectTarget(targetKey);
        setTemplatePickerOpen(true);
      }}
    >
      {t('npp.template_picker_btn')}
    </Button>
  );

  const handleTemplateSelect = (templateId: string) => {
    updateConfig(templateSelectTarget, templateId);
  };

  const renderRequiredLabel = (label: string) => (
    <span>
      <span className="gaf-mr-xs" style={{ color: token.colorError }}>
        *
      </span>
      {label}
    </span>
  );

  const renderRoiFields = () => (
    <>
      <Divider plain className="gaf-text-xs" style={{ margin: '8px 0' }}>
        {t('npp.roi_section')}
      </Divider>
      <div className="gaf-flex gaf-gap-sm gaf-flex-wrap">
        <div style={{ flex: '1 1 45%' }}>
          <Form.Item label="X" className="gaf-mb-sm">
            <InputNumber
              size="small"
              min={0}
              value={(config?.roi as Record<string, number>)?.x ?? 0}
              onChange={(v) => updateRoi('x', v)}
              className="gaf-w-full"
            />
          </Form.Item>
        </div>
        <div style={{ flex: '1 1 45%' }}>
          <Form.Item label="Y" className="gaf-mb-sm">
            <InputNumber
              size="small"
              min={0}
              value={(config?.roi as Record<string, number>)?.y ?? 0}
              onChange={(v) => updateRoi('y', v)}
              className="gaf-w-full"
            />
          </Form.Item>
        </div>
        <div style={{ flex: '1 1 45%' }}>
          <Form.Item label="W" className="gaf-mb-sm">
            <InputNumber
              size="small"
              min={0}
              value={(config?.roi as Record<string, number>)?.w ?? 0}
              onChange={(v) => updateRoi('w', v)}
              className="gaf-w-full"
            />
          </Form.Item>
        </div>
        <div style={{ flex: '1 1 45%' }}>
          <Form.Item label="H" className="gaf-mb-sm">
            <InputNumber
              size="small"
              min={0}
              value={(config?.roi as Record<string, number>)?.h ?? 0}
              onChange={(v) => updateRoi('h', v)}
              className="gaf-w-full"
            />
          </Form.Item>
        </div>
      </div>
    </>
  );

  const renderFields = () => {
    if (!nodeType || !config) return null;

    switch (nodeType as PipelineNodeType | string) {
      case 'template_match':
        return (
          <>
            <Form.Item
              label={renderRequiredLabel(t('npp.tm_template'))}
              rules={[{ required: true, message: t('npp.required_template') }]}
              className="gaf-mb-sm"
            >
              {renderTemplateSelectButton('template_id')}
              {(config.template_id as string) && (
                <Typography.Text type="secondary" className="gaf-text-xxs gaf-mt-xs" style={{ display: 'block' }}>
                  {t('npp.template_selected', { id: config.template_id as string })}
                </Typography.Text>
              )}
            </Form.Item>
            <Form.Item label={t('npp.tm_threshold')} className="gaf-mb-sm">
              <Slider
                min={0}
                max={1}
                step={0.01}
                value={config.threshold as number}
                onChange={(v) => updateConfig('threshold', v)}
              />
            </Form.Item>
            {renderRoiFields()}
            <Form.Item label={t('npp.tm_method')} className="gaf-mb-sm">
              <Select
                size="small"
                value={config.match_method as string}
                onChange={(v) => updateConfig('match_method', v)}
                options={[
                  { label: 'TM_CCOEFF_NORMED', value: 'TM_CCOEFF_NORMED' },
                  { label: 'TM_CCORR_NORMED', value: 'TM_CCORR_NORMED' },
                  { label: 'TM_SQDIFF_NORMED', value: 'TM_SQDIFF_NORMED' },
                ]}
                className="gaf-w-full"
              />
            </Form.Item>
          </>
        );

      case 'ocr':
        return (
          <>
            <Form.Item label={t('npp.ocr_engine')} className="gaf-mb-sm">
              <Select
                size="small"
                value={(config.engine as string) || 'rapid'}
                onChange={(v) => updateConfig('engine', v)}
                options={[
                  { label: 'RapidOCR', value: 'rapid' },
                  { label: 'PaddleOCR', value: 'paddle' },
                ]}
                className="gaf-w-full"
              />
            </Form.Item>
            <Form.Item label={t('npp.ocr_language')} className="gaf-mb-sm">
              <Select
                size="small"
                value={config.language as string}
                onChange={(v) => updateConfig('language', v)}
                options={[
                  { label: t('npp.ocr_lang_ch'), value: 'ch' },
                  { label: t('npp.ocr_lang_en'), value: 'en' },
                ]}
                className="gaf-w-full"
              />
            </Form.Item>
            {renderRoiFields()}
            <Form.Item label={t('npp.ocr_expected_text')} className="gaf-mb-sm">
              <Input
                size="small"
                value={config.expected_text as string}
                onChange={(e) => updateConfig('expected_text', e.target.value)}
              />
            </Form.Item>
          </>
        );

      case 'click':
        return (
          <>
            <Form.Item
              label={renderRequiredLabel(t('npp.click_coord'))}
              rules={[{ required: true, message: t('npp.required_coord') }]}
              className="gaf-mb-sm"
            >
              <div className="gaf-flex-center gaf-gap-sm">
                <InputNumber
                  size="small"
                  placeholder="X"
                  value={config.x as number}
                  onChange={(v) => updateConfig('x', v)}
                  className="gaf-flex-1"
                />
                <InputNumber
                  size="small"
                  placeholder="Y"
                  value={config.y as number}
                  onChange={(v) => updateConfig('y', v)}
                  className="gaf-flex-1"
                />
                <Button
                  size="small"
                  icon={<AimOutlined />}
                  onClick={onRequestScreenshot}
                  title={t('npp.screenshot_pick_title')}
                />
              </div>
            </Form.Item>
            <Divider plain className="gaf-text-xs" style={{ margin: '8px 0' }}>
              {t('npp.click_offset_section')}
            </Divider>
            <div className="gaf-flex gaf-gap-sm">
              <Form.Item label="offset_x" className="gaf-mb-sm gaf-flex-1">
                <InputNumber
                  size="small"
                  value={config.offset_x as number}
                  onChange={(v) => updateConfig('offset_x', v)}
                  className="gaf-w-full"
                />
              </Form.Item>
              <Form.Item label="offset_y" className="gaf-mb-sm gaf-flex-1">
                <InputNumber
                  size="small"
                  value={config.offset_y as number}
                  onChange={(v) => updateConfig('offset_y', v)}
                  className="gaf-w-full"
                />
              </Form.Item>
            </div>
            <Form.Item label={t('npp.click_count')} className="gaf-mb-sm">
              <InputNumber
                size="small"
                min={1}
                value={config.count as number}
                onChange={(v) => updateConfig('count', v)}
                className="gaf-w-full"
              />
            </Form.Item>
            <Form.Item label={t('npp.click_interval')} className="gaf-mb-sm">
              <InputNumber
                size="small"
                min={0}
                value={config.interval as number}
                onChange={(v) => updateConfig('interval', v)}
                className="gaf-w-full"
              />
            </Form.Item>
            <Form.Item label={t('npp.click_button')} className="gaf-mb-sm">
              <Select
                size="small"
                value={config.button as string}
                onChange={(v) => updateConfig('button', v)}
                options={[
                  { label: t('npp.click_left'), value: 'left' },
                  { label: t('npp.click_right'), value: 'right' },
                  { label: t('npp.click_middle'), value: 'middle' },
                ]}
                className="gaf-w-full"
              />
            </Form.Item>
          </>
        );

      case 'swipe':
        return (
          <>
            <Divider plain className="gaf-text-xs" style={{ margin: '8px 0' }}>
              {t('npp.swipe_start')}
            </Divider>
            <div className="gaf-flex gaf-gap-sm">
              <Form.Item label="X1" className="gaf-mb-sm gaf-flex-1">
                <InputNumber
                  size="small"
                  value={config.x1 as number}
                  onChange={(v) => updateConfig('x1', v)}
                  className="gaf-w-full"
                />
              </Form.Item>
              <Form.Item label="Y1" className="gaf-mb-sm gaf-flex-1">
                <InputNumber
                  size="small"
                  value={config.y1 as number}
                  onChange={(v) => updateConfig('y1', v)}
                  className="gaf-w-full"
                />
              </Form.Item>
            </div>
            <Divider plain className="gaf-text-xs" style={{ margin: '8px 0' }}>
              {t('npp.swipe_end')}
            </Divider>
            <div className="gaf-flex gaf-gap-sm">
              <Form.Item label="X2" className="gaf-mb-sm gaf-flex-1">
                <InputNumber
                  size="small"
                  value={config.x2 as number}
                  onChange={(v) => updateConfig('x2', v)}
                  className="gaf-w-full"
                />
              </Form.Item>
              <Form.Item label="Y2" className="gaf-mb-sm gaf-flex-1">
                <InputNumber
                  size="small"
                  value={config.y2 as number}
                  onChange={(v) => updateConfig('y2', v)}
                  className="gaf-w-full"
                />
              </Form.Item>
            </div>
            <Form.Item label={t('npp.swipe_duration')} className="gaf-mb-sm">
              <InputNumber
                size="small"
                min={0}
                value={config.duration as number}
                onChange={(v) => updateConfig('duration', v)}
                className="gaf-w-full"
              />
            </Form.Item>
          </>
        );

      case 'key_press':
        return (
          <>
            <Form.Item
              label={renderRequiredLabel(t('npp.kp_key'))}
              rules={[{ required: true, message: t('npp.required_key') }]}
              className="gaf-mb-sm"
            >
              <Input
                size="small"
                placeholder={t('npp.kp_key_placeholder')}
                value={config.key as string}
                onChange={(e) => updateConfig('key', e.target.value)}
              />
            </Form.Item>
            <Form.Item label={t('npp.kp_modifiers')} className="gaf-mb-sm">
              <Checkbox.Group
                options={[
                  { label: 'Ctrl', value: 'ctrl' },
                  { label: 'Shift', value: 'shift' },
                  { label: 'Alt', value: 'alt' },
                ]}
                value={config.modifiers as string[]}
                onChange={(v) => updateConfig('modifiers', v)}
              />
            </Form.Item>
          </>
        );

      case 'text_input':
        return (
          <>
            <Form.Item
              label={renderRequiredLabel(t('npp.ti_text'))}
              rules={[{ required: true, message: t('npp.required_text') }]}
              className="gaf-mb-sm"
            >
              <TextArea rows={3} value={config.text as string} onChange={(e) => updateConfig('text', e.target.value)} />
            </Form.Item>
            <Form.Item label={t('npp.ti_clear_first')} className="gaf-mb-sm">
              <Switch checked={config.clear_first as boolean} onChange={(v) => updateConfig('clear_first', v)} />
            </Form.Item>
          </>
        );

      case 'wait':
        return (
          <>
            <Form.Item label={t('npp.wait_type')} className="gaf-mb-sm">
              <Select
                size="small"
                value={config.wait_type as string}
                onChange={(v) => updateConfig('wait_type', v)}
                options={[
                  { label: t('npp.wait_type_fixed'), value: 'fixed' },
                  { label: t('npp.wait_type_stability'), value: 'stability' },
                  { label: t('npp.wait_type_template'), value: 'template' },
                ]}
                className="gaf-w-full"
              />
            </Form.Item>
            <Form.Item label={t('npp.wait_timeout')} className="gaf-mb-sm">
              <InputNumber
                size="small"
                min={0}
                value={config.timeout as number}
                onChange={(v) => updateConfig('timeout', v)}
                className="gaf-w-full"
              />
            </Form.Item>
            {config.wait_type === 'stability' && (
              <Form.Item label={t('npp.wait_stability_threshold')} className="gaf-mb-sm">
                <Slider
                  min={0}
                  max={1}
                  step={0.01}
                  value={config.stability_threshold as number}
                  onChange={(v) => updateConfig('stability_threshold', v)}
                />
              </Form.Item>
            )}
            {config.wait_type === 'template' && (
              <Form.Item label={t('npp.wait_template')} className="gaf-mb-sm">
                {renderTemplateSelectButton('template_id')}
                {(config.template_id as string) && (
                  <Typography.Text type="secondary" className="gaf-text-xxs gaf-mt-xs" style={{ display: 'block' }}>
                    {t('npp.template_selected', { id: config.template_id as string })}
                  </Typography.Text>
                )}
              </Form.Item>
            )}
          </>
        );

      case 'branch':
        return (
          <>
            <Form.Item
              label={renderRequiredLabel(t('npp.br_condition'))}
              rules={[{ required: true, message: t('npp.required_condition') }]}
              className="gaf-mb-sm"
            >
              <Input
                size="small"
                placeholder={t('npp.br_condition_placeholder')}
                value={config.condition as string}
                onChange={(e) => updateConfig('condition', e.target.value)}
              />
            </Form.Item>
            <Form.Item label={t('npp.br_true_label')} className="gaf-mb-sm">
              <Input size="small" disabled value={config.true_branch as string} />
            </Form.Item>
            <Form.Item label={t('npp.br_false_label')} className="gaf-mb-sm">
              <Input size="small" disabled value={config.false_branch as string} />
            </Form.Item>
          </>
        );

      case 'loop':
        return (
          <>
            <Form.Item label={t('npp.lp_count')} className="gaf-mb-sm">
              <InputNumber
                size="small"
                min={0}
                value={config.count as number}
                onChange={(v) => updateConfig('count', v)}
                className="gaf-w-full"
              />
            </Form.Item>
            <Form.Item label={t('npp.lp_condition')} className="gaf-mb-sm">
              <Input
                size="small"
                placeholder={t('npp.lp_condition_placeholder')}
                value={config.condition as string}
                onChange={(e) => updateConfig('condition', e.target.value)}
              />
            </Form.Item>
            <Form.Item label={t('npp.lp_iterator')} className="gaf-mb-sm">
              <Input
                size="small"
                value={config.iterator_var as string}
                onChange={(e) => updateConfig('iterator_var', e.target.value)}
              />
            </Form.Item>
          </>
        );

      case 'goto':
        return (
          <>
            <Form.Item
              label={renderRequiredLabel(t('npp.gt_target'))}
              rules={[{ required: true, message: t('npp.required_target_node') }]}
              className="gaf-mb-sm"
            >
              <Input
                size="small"
                placeholder={t('npp.gt_target_placeholder')}
                value={config.target as string}
                onChange={(e) => updateConfig('target', e.target.value)}
              />
            </Form.Item>
            <Form.Item label={t('npp.gt_max_jumps')} className="gaf-mb-sm">
              <InputNumber
                size="small"
                min={1}
                value={config.max_jumps as number}
                onChange={(v) => updateConfig('max_jumps', v)}
                className="gaf-w-full"
              />
            </Form.Item>
          </>
        );

      case 'device_control':
        return (
          <>
            <Form.Item label={t('npp.dc_action')} className="gaf-mb-sm">
              <Select
                size="small"
                value={config.action as string}
                onChange={(v) => updateConfig('action', v)}
                options={[
                  { label: t('npp.dc_action_switch_window'), value: 'switch_window' },
                  { label: t('npp.dc_action_launch_app'), value: 'launch_app' },
                  { label: t('npp.dc_action_screenshot'), value: 'screenshot' },
                ]}
                className="gaf-w-full"
              />
            </Form.Item>
            <Form.Item label={t('npp.dc_target')} className="gaf-mb-sm">
              <Input
                size="small"
                placeholder={t('npp.dc_target_placeholder')}
                value={config.target as string}
                onChange={(e) => updateConfig('target', e.target.value)}
              />
            </Form.Item>
            <Form.Item label={t('npp.dc_save_screenshot')} className="gaf-mb-sm">
              <Switch
                checked={config.save_screenshot as boolean}
                onChange={(v) => updateConfig('save_screenshot', v)}
              />
            </Form.Item>
          </>
        );

      case 'monitor':
        return (
          <>
            <Form.Item
              label={renderRequiredLabel(t('npp.mn_rule'))}
              rules={[{ required: true, message: t('npp.required_rule') }]}
              className="gaf-mb-sm"
            >
              <Select
                size="small"
                placeholder={t('npp.mn_rule_placeholder')}
                value={config.rule_id as string}
                onChange={(v) => updateConfig('rule_id', v)}
                // Task 4.39 (P0-11, 2026-07-28): 接入 monitorRuleOptions (Task 4.30 拉取了但漏绑)
                options={monitorRuleOptions}
                className="gaf-w-full"
              />
            </Form.Item>
            <Form.Item label={t('npp.mn_check_interval')} className="gaf-mb-sm">
              <InputNumber
                size="small"
                min={1000}
                step={1000}
                value={config.check_interval as number}
                onChange={(v) => updateConfig('check_interval', v)}
                className="gaf-w-full"
              />
            </Form.Item>
          </>
        );

      case 'sub_pipeline':
        return (
          <>
            <Form.Item
              label={renderRequiredLabel(t('npp.sp_pipeline'))}
              rules={[{ required: true, message: t('npp.required_pipeline') }]}
              className="gaf-mb-sm"
            >
              <Select
                size="small"
                placeholder={t('npp.sp_pipeline_placeholder')}
                value={config.pipeline_id as string}
                onChange={(v) => updateConfig('pipeline_id', v)}
                // Task 4.39 (P0-11, 2026-07-28): 接入 pipelineOptions (Task 4.30 拉取了但漏绑)
                options={pipelineOptions}
                className="gaf-w-full"
              />
            </Form.Item>
            <Form.Item
              label={t('npp.sp_parameters')}
              className="gaf-mb-sm"
              validateStatus={jsonError ? 'error' : ''}
              help={jsonError || undefined}
            >
              <TextArea
                rows={4}
                value={JSON.stringify(config.parameters as Record<string, unknown>, null, 2)}
                onChange={(e) => {
                  try {
                    const parsed = JSON.parse(e.target.value);
                    updateConfig('parameters', parsed);
                    // Task 4.16: 解析成功后清空错误提示
                    setJsonError('');
                  } catch (err) {
                    // Task 4.16: 解析失败时展示错误提示, 让用户看到"哪个字段、为什么不合法"
                    setJsonError((err as Error).message);
                  }
                }}
              />
            </Form.Item>
          </>
        );

      case 'color_detect':
        return (
          <>
            {renderRoiFields()}
            <Form.Item label={t('npp.cd_target_color')} className="gaf-mb-sm">
              <div className="gaf-flex-center gaf-gap-sm">
                <Input
                  size="small"
                  placeholder={t('npp.cd_target_color_placeholder')}
                  value={config.target_color as string}
                  onChange={(e) => updateConfig('target_color', e.target.value)}
                  className="gaf-flex-1"
                />
                <ColorPicker
                  size="small"
                  value={config.target_color as string}
                  onChange={(_, hex) => updateConfig('target_color', hex)}
                />
              </div>
            </Form.Item>
            <Form.Item label={t('npp.cd_tolerance')} className="gaf-mb-sm">
              <Slider
                min={0}
                max={100}
                value={config.tolerance as number}
                onChange={(v) => updateConfig('tolerance', v)}
              />
            </Form.Item>
          </>
        );

      case 'feature_match':
        return (
          <>
            <Form.Item label={t('npp.fm_template')} className="gaf-mb-sm">
              {renderTemplateSelectButton('template_id')}
              {(config.template_id as string) && (
                <Typography.Text type="secondary" className="gaf-text-xxs gaf-mt-xs" style={{ display: 'block' }}>
                  {t('npp.template_selected', { id: config.template_id as string })}
                </Typography.Text>
              )}
            </Form.Item>
            <Form.Item label={t('npp.fm_min_match_count')} className="gaf-mb-sm">
              <InputNumber
                size="small"
                min={1}
                value={config.min_match_count as number}
                onChange={(v) => updateConfig('min_match_count', v)}
                className="gaf-w-full"
              />
            </Form.Item>
            <Form.Item label={t('npp.fm_ratio_threshold')} className="gaf-mb-sm">
              <Slider
                min={0}
                max={1}
                step={0.01}
                value={config.ratio_threshold as number}
                onChange={(v) => updateConfig('ratio_threshold', v)}
              />
            </Form.Item>
          </>
        );

      case 'neural_network':
        return (
          <>
            <Form.Item
              label={renderRequiredLabel(t('npp.nn_model_path'))}
              rules={[{ required: true, message: t('npp.required_model_path') }]}
              className="gaf-mb-sm"
            >
              <Input
                size="small"
                placeholder={t('npp.nn_model_path_placeholder')}
                value={config.model_path as string}
                onChange={(e) => updateConfig('model_path', e.target.value)}
              />
            </Form.Item>
            <Form.Item label={t('npp.nn_backend')} className="gaf-mb-sm">
              <Select
                size="small"
                value={config.backend as string}
                onChange={(v) => updateConfig('backend', v)}
                options={[
                  { label: 'DirectML (Windows)', value: 'dml' },
                  { label: 'CoreML (macOS)', value: 'coreml' },
                  { label: 'CUDA (Linux)', value: 'cuda' },
                  { label: 'CPU', value: 'cpu' },
                ]}
                className="gaf-w-full"
              />
            </Form.Item>
            <Form.Item label={t('npp.nn_confidence')} className="gaf-mb-sm">
              <Slider
                min={0}
                max={1}
                step={0.01}
                value={config.confidence as number}
                onChange={(v) => updateConfig('confidence', v)}
              />
            </Form.Item>
            {renderRoiFields()}
          </>
        );

      case 'long_press':
        return (
          <>
            <Form.Item
              label={renderRequiredLabel(t('npp.click_coord'))}
              rules={[{ required: true, message: t('npp.required_coord') }]}
              className="gaf-mb-sm"
            >
              <div className="gaf-flex-center gaf-gap-sm">
                <InputNumber
                  size="small"
                  placeholder="X"
                  value={config.x as number}
                  onChange={(v) => updateConfig('x', v)}
                  className="gaf-flex-1"
                />
                <InputNumber
                  size="small"
                  placeholder="Y"
                  value={config.y as number}
                  onChange={(v) => updateConfig('y', v)}
                  className="gaf-flex-1"
                />
                <Button
                  size="small"
                  icon={<AimOutlined />}
                  onClick={onRequestScreenshot}
                  title={t('npp.screenshot_pick_title')}
                />
              </div>
            </Form.Item>
            <Form.Item label={t('npp.long_press_duration')} className="gaf-mb-sm">
              <InputNumber
                size="small"
                min={100}
                value={config.duration as number}
                onChange={(v) => updateConfig('duration', v)}
                className="gaf-w-full"
              />
            </Form.Item>
          </>
        );

      case 'random_delay':
        return (
          <>
            <Form.Item label={t('npp.rd_min_ms')} className="gaf-mb-sm">
              <InputNumber
                size="small"
                min={0}
                value={config.min_ms as number}
                onChange={(v) => updateConfig('min_ms', v)}
                className="gaf-w-full"
              />
            </Form.Item>
            <Form.Item label={t('npp.rd_max_ms')} className="gaf-mb-sm">
              <InputNumber
                size="small"
                min={0}
                value={config.max_ms as number}
                onChange={(v) => updateConfig('max_ms', v)}
                className="gaf-w-full"
              />
            </Form.Item>
          </>
        );

      case 'start_app':
        return (
          <>
            <Form.Item
              label={renderRequiredLabel(t('npp.app_package'))}
              rules={[{ required: true, message: t('npp.required_package') }]}
              className="gaf-mb-sm"
            >
              <Input
                size="small"
                placeholder={t('npp.app_package_placeholder')}
                value={config.package_name as string}
                onChange={(e) => updateConfig('package_name', e.target.value)}
              />
            </Form.Item>
            <Form.Item label="Activity" className="gaf-mb-sm">
              <Input
                size="small"
                placeholder={t('npp.app_activity_placeholder')}
                value={config.activity as string}
                onChange={(e) => updateConfig('activity', e.target.value)}
              />
            </Form.Item>
          </>
        );

      case 'stop_app':
        return (
          <>
            <Form.Item
              label={renderRequiredLabel(t('npp.app_package'))}
              rules={[{ required: true, message: t('npp.required_package') }]}
              className="gaf-mb-sm"
            >
              <Input
                size="small"
                placeholder={t('npp.app_package_placeholder')}
                value={config.package_name as string}
                onChange={(e) => updateConfig('package_name', e.target.value)}
              />
            </Form.Item>
            <Form.Item label={t('npp.app_force_stop')} className="gaf-mb-sm">
              <Switch checked={config.force as boolean} onChange={(v) => updateConfig('force', v)} />
            </Form.Item>
          </>
        );

      case 'notify':
        return (
          <>
            <Form.Item label={t('npp.ntf_channel')} className="gaf-mb-sm">
              <Select
                size="small"
                value={config.channel as string}
                onChange={(v) => updateConfig('channel', v)}
                options={[
                  { label: 'Webhook', value: 'webhook' },
                  { label: t('npp.ntf_channel_email'), value: 'email' },
                  { label: t('npp.ntf_channel_dingtalk'), value: 'dingtalk' },
                  { label: t('npp.ntf_channel_wecom'), value: 'wecom' },
                  { label: 'Telegram', value: 'telegram' },
                ]}
                className="gaf-w-full"
              />
            </Form.Item>
            <Form.Item label={t('npp.ntf_level')} className="gaf-mb-sm">
              <Select
                size="small"
                value={config.level as string}
                onChange={(v) => updateConfig('level', v)}
                options={[
                  { label: t('npp.ntf_level_info'), value: 'info' },
                  { label: t('npp.ntf_level_warn'), value: 'warn' },
                  { label: t('npp.ntf_level_error'), value: 'error' },
                  { label: t('npp.ntf_level_critical'), value: 'critical' },
                ]}
                className="gaf-w-full"
              />
            </Form.Item>
            <Form.Item label={t('npp.ntf_message')} className="gaf-mb-sm">
              <TextArea
                rows={3}
                value={config.message as string}
                onChange={(e) => updateConfig('message', e.target.value)}
              />
            </Form.Item>
          </>
        );

      case 'conditional':
        // Task 5.1 (P3, 2026-07-29): conditional 节点 4 个英文 label 改为 i18n
        return (
          <>
            <Form.Item label={t('npp.cond_expression')} className="gaf-mb-sm">
              <TextArea
                rows={3}
                placeholder={t('npp.cond_expression_placeholder')}
                value={config.expression as string}
                onChange={(e) => updateConfig('expression', e.target.value)}
              />
            </Form.Item>
            <Form.Item label={t('npp.cond_true_branch')} className="gaf-mb-sm">
              <Typography.Text type="secondary" className="gaf-text-xs">
                {t('npp.cond_true_desc')}
              </Typography.Text>
            </Form.Item>
            <Form.Item label={t('npp.cond_false_branch')} className="gaf-mb-sm">
              <Typography.Text type="secondary" className="gaf-text-xs">
                {t('npp.cond_false_desc')}
              </Typography.Text>
            </Form.Item>
            <Form.Item label={t('npp.cond_default_direction')} className="gaf-mb-sm">
              <Select
                size="small"
                value={config.default_branch as string}
                onChange={(v) => updateConfig('default_branch', v)}
                options={[
                  { label: t('npp.cond_direction_true'), value: 'true' },
                  { label: t('npp.cond_direction_false'), value: 'false' },
                ]}
                className="gaf-w-full"
              />
            </Form.Item>
          </>
        );

      case 'uia_set_value':
      case 'uia_invoke':
      case 'uia_get_state':
      case 'uia_select':
      case 'uia_scroll':
      case 'uia_get_window_title':
        // spec-2026-08-26 P2: UIAutomation 语义节点配置——accessibility 注入，
        // 通过控件 Name / AutomationId 定位，无需坐标/焦点。
        return (
          <>
            {nodeType === 'uia_set_value' && (
              <Form.Item
                label={renderRequiredLabel(t('npp.uia_value'))}
                rules={[{ required: true, message: t('npp.uia_required_value') }]}
                className="gaf-mb-sm"
              >
                <Input
                  size="small"
                  value={config.value as string}
                  onChange={(e) => updateConfig('value', e.target.value)}
                />
              </Form.Item>
            )}
            {nodeType === 'uia_select' && (
              <Form.Item
                label={renderRequiredLabel(t('npp.uia_option'))}
                rules={[{ required: true, message: t('npp.uia_required_option') }]}
                className="gaf-mb-sm"
              >
                <Input
                  size="small"
                  placeholder={t('npp.uia_var_placeholder')}
                  value={config.option as string}
                  onChange={(e) => updateConfig('option', e.target.value)}
                />
              </Form.Item>
            )}
            {nodeType === 'uia_select' && (
              <Form.Item label={t('npp.uia_exact')} className="gaf-mb-sm">
                <Switch checked={config.exact as boolean} onChange={(v) => updateConfig('exact', v)} />
              </Form.Item>
            )}
            {nodeType === 'uia_scroll' && (
              <>
                <Form.Item
                  label={renderRequiredLabel(t('npp.uia_direction'))}
                  rules={[{ required: true, message: t('npp.uia_required_direction') }]}
                  className="gaf-mb-sm"
                >
                  <Select
                    size="small"
                    value={config.direction as string}
                    onChange={(v) => updateConfig('direction', v)}
                    options={[
                      { label: t('npp.uia_direction_up'), value: 'up' },
                      { label: t('npp.uia_direction_down'), value: 'down' },
                      { label: t('npp.uia_direction_left'), value: 'left' },
                      { label: t('npp.uia_direction_right'), value: 'right' },
                    ]}
                    className="gaf-w-full"
                  />
                </Form.Item>
                <Form.Item label={t('npp.uia_amount')} className="gaf-mb-sm">
                  <Select
                    size="small"
                    value={(config.amount as string) || 'small'}
                    onChange={(v) => updateConfig('amount', v)}
                    options={[
                      { label: t('npp.uia_amount_small'), value: 'small' },
                      { label: t('npp.uia_amount_large'), value: 'large' },
                    ]}
                    className="gaf-w-full"
                  />
                </Form.Item>
              </>
            )}
            {(nodeType === 'uia_get_state' || nodeType === 'uia_scroll') && (
              <Form.Item label={t('npp.uia_control_type')} className="gaf-mb-sm">
                <Select
                  size="small"
                  value={(config.control_type as string) || (nodeType === 'uia_get_state' ? 'edit' : 'document')}
                  onChange={(v) => updateConfig('control_type', v)}
                  options={[
                    { label: t('npp.uia_ct_edit'), value: 'edit' },
                    { label: t('npp.uia_ct_button'), value: 'button' },
                    { label: t('npp.uia_ct_combo'), value: 'combo' },
                    { label: t('npp.uia_ct_document'), value: 'document' },
                  ]}
                  className="gaf-w-full"
                />
              </Form.Item>
            )}
            {(nodeType === 'uia_get_state' || nodeType === 'uia_get_window_title') && (
              <Form.Item label={t('npp.uia_var')} className="gaf-mb-sm">
                <Input
                  size="small"
                  placeholder={t('npp.uia_var_placeholder')}
                  value={config.var as string}
                  onChange={(e) => updateConfig('var', e.target.value)}
                />
              </Form.Item>
            )}
            <Form.Item label={t('npp.uia_control_name')} className="gaf-mb-sm">
              <Input
                size="small"
                placeholder={t('npp.uia_control_name_placeholder')}
                value={config.control_name as string}
                onChange={(e) => updateConfig('control_name', e.target.value)}
              />
            </Form.Item>
            <Form.Item label={t('npp.uia_control_aid')} className="gaf-mb-sm">
              <Input
                size="small"
                value={config.control_automation_id as string}
                onChange={(e) => updateConfig('control_automation_id', e.target.value)}
              />
            </Form.Item>
            {nodeType !== 'uia_get_window_title' && (
              <Form.Item label={t('npp.uia_timeout')} className="gaf-mb-sm">
                <InputNumber
                  size="small"
                  min={1}
                  value={(config.timeout as number) ?? 3}
                  onChange={(v) => updateConfig('timeout', v)}
                  className="gaf-w-full"
                />
              </Form.Item>
            )}
            <Typography.Text type="secondary" className="gaf-text-xxs">
              {t('npp.uia_locator_hint')}
            </Typography.Text>
          </>
        );

      case 'template_match_any':
      case 'swipe_until':
        // 2026-08-26: 存量节点暴露——模板列表（每行一个）+ 通用匹配参数
        return (
          <>
            <Form.Item label={renderRequiredLabel(t('npp.tma_templates'))} className="gaf-mb-sm">
              <TextArea
                rows={3}
                placeholder={t('npp.templates_placeholder')}
                value={((config.templates as string[]) || []).join('\n')}
                onChange={(e) =>
                  updateConfig(
                    'templates',
                    e.target.value
                      .split('\n')
                      .map((s) => s.trim())
                      .filter(Boolean),
                  )
                }
              />
            </Form.Item>
            <Form.Item label={t('npp.tm_threshold')} className="gaf-mb-sm">
              <Slider
                min={0}
                max={1}
                step={0.01}
                value={(config.threshold as number) ?? 0.8}
                onChange={(v) => updateConfig('threshold', v)}
              />
            </Form.Item>
            <Form.Item label={t('npp.tm_method')} className="gaf-mb-sm">
              <Select
                size="small"
                value={(config.method as string) || 'TM_CCOEFF_NORMED'}
                onChange={(v) => updateConfig('method', v)}
                options={[
                  { label: 'TM_CCOEFF_NORMED', value: 'TM_CCOEFF_NORMED' },
                  { label: 'TM_CCORR_NORMED', value: 'TM_CCORR_NORMED' },
                  { label: 'TM_SQDIFF_NORMED', value: 'TM_SQDIFF_NORMED' },
                ]}
                className="gaf-w-full"
              />
            </Form.Item>
            <Form.Item label={t('npp.click_on_match')} className="gaf-mb-sm">
              <Switch checked={config.click_on_match as boolean} onChange={(v) => updateConfig('click_on_match', v)} />
            </Form.Item>
            {nodeType === 'swipe_until' && (
              <>
                <Divider plain className="gaf-text-xs" style={{ margin: '8px 0' }}>
                  {t('npp.swipe_start')}
                </Divider>
                <div className="gaf-flex gaf-gap-sm">
                  <Form.Item label="X1" className="gaf-mb-sm gaf-flex-1">
                    <InputNumber
                      size="small"
                      value={config.x1 as number}
                      onChange={(v) => updateConfig('x1', v)}
                      className="gaf-w-full"
                    />
                  </Form.Item>
                  <Form.Item label="Y1" className="gaf-mb-sm gaf-flex-1">
                    <InputNumber
                      size="small"
                      value={config.y1 as number}
                      onChange={(v) => updateConfig('y1', v)}
                      className="gaf-w-full"
                    />
                  </Form.Item>
                </div>
                <Divider plain className="gaf-text-xs" style={{ margin: '8px 0' }}>
                  {t('npp.swipe_end')}
                </Divider>
                <div className="gaf-flex gaf-gap-sm">
                  <Form.Item label="X2" className="gaf-mb-sm gaf-flex-1">
                    <InputNumber
                      size="small"
                      value={config.x2 as number}
                      onChange={(v) => updateConfig('x2', v)}
                      className="gaf-w-full"
                    />
                  </Form.Item>
                  <Form.Item label="Y2" className="gaf-mb-sm gaf-flex-1">
                    <InputNumber
                      size="small"
                      value={config.y2 as number}
                      onChange={(v) => updateConfig('y2', v)}
                      className="gaf-w-full"
                    />
                  </Form.Item>
                </div>
                <Form.Item label={t('npp.su_max_swipes')} className="gaf-mb-sm">
                  <InputNumber
                    size="small"
                    min={1}
                    value={config.max_swipes as number}
                    onChange={(v) => updateConfig('max_swipes', v)}
                    className="gaf-w-full"
                  />
                </Form.Item>
                <Form.Item label={t('npp.su_delay_between')} className="gaf-mb-sm">
                  <InputNumber
                    size="small"
                    min={0}
                    step={0.1}
                    value={config.delay_between as number}
                    onChange={(v) => updateConfig('delay_between', v)}
                    className="gaf-w-full"
                  />
                </Form.Item>
              </>
            )}
          </>
        );

      case 'log_message':
        return (
          <>
            <Form.Item
              label={renderRequiredLabel(t('npp.lm_message'))}
              rules={[{ required: true, message: t('npp.required_message') }]}
              className="gaf-mb-sm"
            >
              <TextArea
                rows={3}
                placeholder="e.g. 任务执行完成 ${var}"
                value={config.message as string}
                onChange={(e) => updateConfig('message', e.target.value)}
              />
            </Form.Item>
            <Form.Item label={t('npp.lm_level')} className="gaf-mb-sm">
              <Select
                size="small"
                value={(config.level as string) || 'info'}
                onChange={(v) => updateConfig('level', v)}
                options={[
                  { label: t('npp.lm_level_debug'), value: 'debug' },
                  { label: t('npp.lm_level_info'), value: 'info' },
                  { label: t('npp.lm_level_warning'), value: 'warning' },
                  { label: t('npp.lm_level_error'), value: 'error' },
                ]}
                className="gaf-w-full"
              />
            </Form.Item>
          </>
        );

      default:
        return <Empty description={t('npp.unsupported_type')} />;
    }
  };

  if (!nodeId || !nodeType) {
    return (
      <div className="gaf-flex-center gaf-p-xl" style={{ height: '100%' }}>
        <Empty description={t('npp.select_node')} />
      </div>
    );
  }

  const missingFields = missingRequiredFields();

  return (
    <div className="gaf-p-md" style={{ height: '100%', overflow: 'auto' }}>
      <Typography.Title level={5} style={{ margin: '0 0 4px 0' }}>
        {(config && ((config as Record<string, unknown>).label as string)) || t('npp.title')}
      </Typography.Title>
      <Typography.Text type="secondary" className="gaf-text-xs">
        {t('npp.type_label')}: {nodeType}
      </Typography.Text>
      <Divider style={{ margin: '8px 0' }} />
      {missingFields.length > 0 && (
        <Alert
          type="warning"
          showIcon
          title={t('npp.missing_fields_msg', { fields: missingFields.join(', ') })}
          description={t('npp.missing_fields_desc')}
          className="gaf-mb-sm"
        />
      )}
      {jsonError && (
        <Alert
          type="error"
          showIcon
          title={t('npp.json_parse_error_msg')}
          description={jsonError}
          className="gaf-mb-sm"
        />
      )}
      {/* Task 4.56 (P1-36, 2026-07-28): fetchMonitorRules/fetchPipelines 错误提示 */}
      {fetchRuleError && (
        <Alert
          type="error"
          showIcon
          closable
          title={t('npp.fetch_rules_failed')}
          description={fetchRuleError}
          onClose={() => setFetchRuleError('')}
          className="gaf-mb-sm"
        />
      )}
      {fetchPipelineError && (
        <Alert
          type="error"
          showIcon
          closable
          title={t('npp.fetch_pipelines_failed')}
          description={fetchPipelineError}
          onClose={() => setFetchPipelineError('')}
          className="gaf-mb-sm"
        />
      )}
      <Form layout="vertical" size="small">
        {renderFields()}
      </Form>
      <TemplatePicker
        open={templatePickerOpen}
        onClose={() => setTemplatePickerOpen(false)}
        onSelect={() => {}}
        onSelectId={handleTemplateSelect}
        showSelectButton
      />
    </div>
  );
}

export default NodePropertyPanel;
