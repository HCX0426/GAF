/**
 * Custom Skill Editor - YAML-based skill definition editor
 * Allows users to create and manage custom analysis skills
 */
import React, { useState, useCallback } from 'react';
import {
  Card,
  Button,
  Select,
  Typography,
  Space,
  Alert,
  Modal,
  Tag,
  Form,
  Input,
  App,
  Tabs as AntTabs,
  theme as antTheme,
} from 'antd';
import {
  SaveOutlined,
  DeleteOutlined,
  CopyOutlined,
  PlayCircleOutlined,
  FileTextOutlined,
  SettingOutlined,
} from '@ant-design/icons';
import { fetchCustomSkills, createCustomSkill, deleteCustomSkill } from '@/api/ai';
import { useTranslation } from '@/i18n';

const { TextArea } = Input;
const { Text } = Typography;

/** Custom Skill definition interface */
interface CustomSkill {
  id: string;
  name: string;
  description: string;
  category: string;
  yaml_content: string;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

/** YAML template for different skill types */
const SKILL_TEMPLATES: Record<string, { yaml: string; descriptionKey: string }> = {
  ocr_skill: {
    descriptionKey: 'ailab.template_ocr_description',
    yaml: `# Custom OCR Extraction Skill
name: custom_ocr_extract
version: "1.0"
description: 自定义 OCR 文字提取规则
category: recognition

input:
  type: image_region
  fields:
    - name: region
      type: bbox
      required: true
      description: 目标区域坐标 (x, y, width, height)
    - name: languages
      type: list
      default: ["zh-CN", "en"]
      description: OCR 语言列表

processing:
  engine: rapidocr
  preprocessing:
    - resize: [320, null]
    - normalize: true
  postprocessing:
    - filter_by_confidence: 0.6
    - merge_lines: true

output:
  fields:
    - name: texts
      type: list[string]
      description: 提取的文字列表
    - name: confidence
      type: float
      description: 平均置信度
    - name: bboxes
      type: list[bbox]
      description: 每个文字的边界框`,
  },
  match_skill: {
    descriptionKey: 'ailab.template_match_description',
    yaml: `# Custom Template Match Skill
name: custom_template_match
version: "1.0"
description: 自定义模板匹配检测规则
category: recognition

input:
  type: image_pair
  fields:
    - name: template_path
      type: string
      required: true
      description: 模板图片路径
    - name: threshold
      type: float
      default: 0.8
      range: [0.5, 1.0]
      description: 匹配阈值
    - name: method
      type: enum
      options: [sqdiff, ccorr_normed, ccoeff_normed]
      default: ccorr_normed
      description: 匹配算法

processing:
  method: opencv_template_match
  multi_scale:
    enabled: false
    scale_range: [0.8, 1.2]
    steps: 10

output:
  fields:
    - name: found
      type: bool
      description: 是否找到匹配
    - name: position
      type: point
      description: 匹配位置中心坐标
    - name: confidence
      type: float
      description: 匹配置信度
    - name: bbox
      type: bbox
      description: 匹配区域边界框`,
  },
  analysis_skill: {
    descriptionKey: 'ailab.template_analysis_description',
    yaml: `# Custom Analysis Skill
name: custom_log_analysis
version: "1.0"
description: 自定义日志分析规则
category: analysis

input:
  type: text_log
  fields:
    - name: logs
      type: list[string]
      required: true
      description: 日志行列表
    - name: time_range
      type: tuple[datetime, datetime]
      description: 时间范围过滤

processing:
  engine: regex + LLM
  rules:
    - pattern: "ERROR.*failed"
      action: extract_error_context
      severity: high
    - pattern: "Retry attempt"
      action: count_retries
      severity: medium
    - pattern: "timeout"
      action: detect_timeout_pattern
      severity: high

output:
  fields:
    - name: error_count
      type: int
      description: 错误数量
    - name: retry_count
      type: int
      description: 重试次数
    - name: patterns
      type: list[object]
      description: 发现的模式列表
    - name: suggestions
      type: list[string]
      description: AI 生成的修复建议`,
  },
};

const CATEGORY_OPTIONS = [
  { value: 'recognition', labelKey: 'ailab.category_recognition' },
  { value: 'analysis', labelKey: 'ailab.category_analysis' },
  { value: 'action', labelKey: 'ailab.category_action' },
  { value: 'validation', labelKey: 'ailab.category_validation' },
];

export function CustomSkillEditor() {
  const t = useTranslation();
  const { token } = antTheme.useToken();
  const { message: msgApi } = App.useApp();
  const [skills, setSkills] = useState<CustomSkill[]>([]);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [yamlContent, setYamlContent] = useState('');
  const [skillName, setSkillName] = useState('');
  const [skillDesc, setSkillDesc] = useState('');
  const [skillCategory, setSkillCategory] = useState('analysis');
  const [saving, setSaving] = useState(false);
  const [deleteModalOpen, setDeleteModalOpen] = useState(false);
  const [skillToDelete, setSkillToDelete] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState('editor');

  /** Load saved custom skills */
  const loadSkills = useCallback(async () => {
    try {
      const raw = await fetchCustomSkills();
      const data = Array.isArray(raw) ? raw : raw?.results || [];
      setSkills(Array.isArray(data) ? data : []);
    } catch {
      const stored = localStorage.getItem('gaf_custom_skills');
      if (stored) {
        try {
          setSkills(JSON.parse(stored));
        } catch {
          setSkills([]);
        }
      }
    }
  }, []);

  React.useEffect(() => {
    loadSkills();
  }, [loadSkills]);

  /** Load a skill for editing */
  const handleEdit = (skill: CustomSkill) => {
    setEditingId(skill.id);
    setYamlContent(skill.yaml_content);
    setSkillName(skill.name);
    setSkillDesc(skill.description);
    setSkillCategory(skill.category);
    setActiveTab('editor');
  };

  /** Create new skill from template */
  const handleNewFromTemplate = (templateKey: string) => {
    const template = SKILL_TEMPLATES[templateKey];
    if (!template) return;
    const newId = `custom_${Date.now()}`;
    setEditingId(newId);
    setYamlContent(template.yaml);
    setSkillName(`${t('ailab.prefix_custom')} ${t(template.descriptionKey)}`);
    setSkillDesc(t(template.descriptionKey));
    setSkillCategory(template.yaml.includes('recognition') ? 'recognition' : 'analysis');
    setActiveTab('editor');
  };

  /** Save current editing skill */
  const handleSave = async () => {
    if (!yamlContent.trim()) {
      msgApi.error(t('ailab.msg_yaml_empty'));
      return;
    }
    if (!skillName.trim()) {
      msgApi.error(t('ailab.msg_skill_name_empty'));
      return;
    }

    setSaving(true);
    try {
      const skillData = {
        id: editingId || `custom_${Date.now()}`,
        name: skillName,
        description: skillDesc,
        category: skillCategory,
        yaml_content: yamlContent,
        is_active: true,
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
      };

      await createCustomSkill(skillData);

      if (editingId) {
        setSkills((prev) => prev.map((s) => (s.id === editingId ? { ...skillData, id: s.id } : s)));
      } else {
        setSkills((prev) => [...prev, { ...skillData, id: skillData.id }]);
      }

      localStorage.setItem(
        'gaf_custom_skills',
        JSON.stringify(
          editingId
            ? skills.map((s) => (s.id === editingId ? { ...skillData, id: s.id } : s))
            : [...skills, { ...skillData, id: skillData.id }],
        ),
      );

      msgApi.success(t('ailab.msg_skill_saved'));
    } catch {
      const fallbackSkill: CustomSkill = {
        id: editingId || `custom_${Date.now()}`,
        name: skillName,
        description: skillDesc,
        category: skillCategory,
        yaml_content: yamlContent,
        is_active: true,
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
      };
      const updated = editingId
        ? skills.map((s) => (s.id === editingId ? fallbackSkill : s))
        : [...skills, fallbackSkill];
      setSkills(updated);
      localStorage.setItem('gaf_custom_skills', JSON.stringify(updated));
      msgApi.success(t('ailab.msg_skill_saved_local'));
    } finally {
      setSaving(false);
    }
  };

  /** Delete a skill with confirmation */
  const handleDeleteConfirm = async () => {
    if (!skillToDelete) return;
    try {
      await deleteCustomSkill(skillToDelete);
    } catch {
      // pass - local fallback below
    }
    const updated = skills.filter((s) => s.id !== skillToDelete);
    setSkills(updated);
    localStorage.setItem('gaf_custom_skills', JSON.stringify(updated));
    msgApi.success(t('ailab.msg_deleted'));
    setDeleteModalOpen(false);
    setSkillToDelete(null);
    if (editingId === skillToDelete) {
      setEditingId(null);
      setYamlContent('');
      setSkillName('');
      setSkillDesc('');
    }
  };

  /** Duplicate a skill */
  const handleDuplicate = (skill: CustomSkill) => {
    const newSkill: CustomSkill = {
      ...skill,
      id: `custom_${Date.now()}`,
      name: `${skill.name} (副本)`,
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    };
    setSkills((prev) => [...prev, newSkill]);
    handleEdit(newSkill);
    msgApi.info(t('ailab.msg_duplicated'));
  };

  return (
    <div className="gaf-flex gaf-gap-lg gaf-p-xl gaf-h-full">
      <div className="gaf-overflow-y-auto gaf-flex-shrink-0" style={{ width: 300 }}>
        <Card
          size="small"
          title={t('ailab.card_my_skills')}
          extra={
            <Space size="small">
              <Select
                size="small"
                placeholder={t('ailab.placeholder_new_from_template')}
                className="gaf-w-sm"
                onChange={handleNewFromTemplate}
                options={[
                  { value: 'ocr_skill', label: t('ailab.template_ocr_short') },
                  { value: 'match_skill', label: t('ailab.template_match_short') },
                  { value: 'analysis_skill', label: t('ailab.template_analysis_short') },
                ]}
              />
            </Space>
          }
        >
          {skills.length === 0 && (
            <Alert
              type="info"
              showIcon
              title={t('ailab.empty_no_skills_title')}
              description={t('ailab.empty_no_skills_desc')}
              className="gaf-mb-md"
            />
          )}
          {skills.map((skill) => (
            <div
              key={skill.id}
              onClick={() => handleEdit(skill)}
              className="gaf-mb-xs gaf-cursor-pointer"
              style={{
                padding: '8px 10px',
                borderRadius: 6,
                background: editingId === skill.id ? token.colorPrimaryBg : 'transparent',
                border: editingId === skill.id ? `1px solid ${token.colorPrimaryBorder}` : '1px solid transparent',
              }}
            >
              <div className="gaf-flex-between">
                <Text strong ellipsis className="gaf-text-13" style={{ maxWidth: 160 }}>
                  {skill.name}
                </Text>
                <Tag color={skill.is_active ? 'green' : 'default'} style={{ fontSize: 10 }}>
                  {skill.category}
                </Tag>
              </div>
              <Text type="secondary" ellipsis className="gaf-text-xxs">
                {skill.description}
              </Text>
              <div className="gaf-flex gaf-gap-xs gaf-mt-xs">
                <Button
                  type="link"
                  size="small"
                  icon={<CopyOutlined />}
                  onClick={(e) => {
                    e.stopPropagation();
                    handleDuplicate(skill);
                  }}
                >
                  {t('ailab.btn_copy')}
                </Button>
                <Button
                  type="link"
                  size="small"
                  danger
                  icon={<DeleteOutlined />}
                  onClick={(e) => {
                    e.stopPropagation();
                    setSkillToDelete(skill.id);
                    setDeleteModalOpen(true);
                  }}
                >
                  {t('ailab.btn_delete')}
                </Button>
              </div>
            </div>
          ))}
        </Card>
      </div>

      <Card
        size="small"
        title={
          <span>
            <SettingOutlined /> {t('ailab.card_editor')}
            {editingId && (
              <Text type="secondary" className="gaf-ml-sm" style={{ fontWeight: 'normal' }}>
                {t('ailab.label_editing')}: {skillName}
              </Text>
            )}
          </span>
        }
        className="gaf-flex-col gaf-flex-1"
        styles={{ body: { flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden' } }}
      >
        <AntTabs
          activeKey={activeTab}
          onChange={setActiveTab}
          size="small"
          items={[
            {
              key: 'editor',
              label: (
                <span>
                  <FileTextOutlined /> {t('ailab.tab_yaml_edit')}
                </span>
              ),
              children: (
                <div className="gaf-flex-col gaf-h-full">
                  <Form layout="inline" size="small" className="gaf-mb-md">
                    <Form.Item label={t('ailab.label_name')}>
                      <Input
                        value={skillName}
                        onChange={(e) => setSkillName(e.target.value)}
                        placeholder={t('ailab.placeholder_skill_name')}
                        style={{ width: 180 }}
                      />
                    </Form.Item>
                    <Form.Item label={t('ailab.label_category')}>
                      <Select
                        value={skillCategory}
                        onChange={setSkillCategory}
                        options={CATEGORY_OPTIONS.map((c) => ({ value: c.value, label: t(c.labelKey) }))}
                        style={{ width: 150 }}
                      />
                    </Form.Item>
                    <Form.Item label={t('ailab.label_description')}>
                      <Input
                        value={skillDesc}
                        onChange={(e) => setSkillDesc(e.target.value)}
                        placeholder={t('ailab.placeholder_brief_description')}
                        className="gaf-w-200"
                      />
                    </Form.Item>
                  </Form>

                  <TextArea
                    value={yamlContent}
                    onChange={(e) => setYamlContent(e.target.value)}
                    placeholder={t('ailab.placeholder_yaml_editor')}
                    autoSize={{ minRows: 18, maxRows: 28 }}
                    className="gaf-flex-1 gaf-font-mono gaf-text-13"
                    style={{
                      lineHeight: 1.6,
                      background: token.colorBgLayout,
                      color: token.colorText,
                      borderColor: token.colorBorderSecondary,
                    }}
                  />

                  <div className="gaf-flex gaf-gap-sm gaf-mt-md" style={{ justifyContent: 'flex-end' }}>
                    <Button icon={<PlayCircleOutlined />} disabled={!yamlContent.trim()}>
                      {t('ailab.btn_test_run')}
                    </Button>
                    <Button
                      type="primary"
                      icon={<SaveOutlined />}
                      loading={saving}
                      onClick={handleSave}
                      disabled={!yamlContent.trim()}
                    >
                      {t('ailab.btn_save_skill')}
                    </Button>
                  </div>
                </div>
              ),
            },
            {
              key: 'preview',
              label: (
                <span>
                  <FileTextOutlined /> {t('ailab.tab_structure_preview')}
                </span>
              ),
              children: (
                <pre
                  className="gaf-p-lg gaf-radius-md gaf-font-mono gaf-text-13 gaf-overflow-auto gaf-whitespace-pre-wrap gaf-word-break"
                  style={{ background: token.colorBgLayout, maxHeight: 500 }}
                >
                  {yamlContent ? (
                    <span>
                      {yamlContent.split('\n').map((line, i) => (
                        <div key={`ln-${i}-${line.length}`}>
                          <span
                            className="gaf-mr-md"
                            style={{
                              color: token.colorTextTertiary,
                              userSelect: 'none',
                              display: 'inline-block',
                              width: 30,
                              textAlign: 'right',
                            }}
                          >
                            {i + 1}
                          </span>
                          {line || ' '}
                        </div>
                      ))}
                    </span>
                  ) : (
                    <Text type="secondary">{t('ailab.empty_yaml_input')}</Text>
                  )}
                </pre>
              ),
            },
          ]}
        />
      </Card>

      <Modal
        title={t('ailab.title_confirm_delete')}
        open={deleteModalOpen}
        onOk={handleDeleteConfirm}
        onCancel={() => setDeleteModalOpen(false)}
        okText={t('ailab.btn_delete')}
        cancelText={t('ailab.btn_cancel')}
        okButtonProps={{ danger: true }}
      >
        <p>{t('ailab.confirm_delete_skill_msg')}</p>
      </Modal>
    </div>
  );
}

export default CustomSkillEditor;
