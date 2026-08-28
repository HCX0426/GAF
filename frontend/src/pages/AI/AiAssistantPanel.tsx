import React, { useEffect, useRef, useState } from 'react';
import {
  Button,
  Input,
  Select,
  Space,
  Typography,
  App,
  Card,
  Tag,
  Spin,
  Alert,
  Tabs as AntTabs,
  Empty,
  theme as antTheme,
} from 'antd';
import {
  SendOutlined,
  ClearOutlined,
  RobotOutlined,
  UserOutlined,
  ThunderboltOutlined,
  BulbOutlined,
} from '@ant-design/icons';
import { useNavigate } from 'react-router-dom';
import { useAiLabStore } from '@/stores/useAiLabStore';
import { listPipelines } from '@/api/pipelines';
import { optimizePipeline } from '@/api/ai';
import { useTranslation } from '@/i18n';

const { TextArea } = Input;
const { Text } = Typography;

const MODEL_OPTIONS = [
  { value: 'gpt-4o-mini', label: 'GPT-4o Mini' },
  { value: 'gpt-4o', label: 'GPT-4o' },
  { value: 'deepseek-chat', label: 'DeepSeek Chat' },
  { value: 'qwen-max', label: 'Qwen Max' },
];

/** Generate user bubble style with design token */
const getBubbleStyleUser = (tokenColorPrimary: string): React.CSSProperties => ({
  maxWidth: '80%',
  marginLeft: 'auto',
  marginBottom: 8,
  padding: '10px 14px',
  borderRadius: 16,
  borderBottomRightRadius: 4,
  background: tokenColorPrimary,
  color: '#fff',
  wordBreak: 'break-word',
});

/** Generate assistant bubble style with design token */
const getBubbleStyleAssistant = (tokenColorBgContainer: string, tokenColorText: string): React.CSSProperties => ({
  maxWidth: '80%',
  marginRight: 'auto',
  marginBottom: 8,
  padding: '10px 14px',
  borderRadius: 16,
  borderBottomLeftRadius: 4,
  background: tokenColorBgContainer,
  color: tokenColorText,
  wordBreak: 'break-word',
});

const getTypingDotStyle = (tokenColorTextTertiary: string): React.CSSProperties => ({
  display: 'inline-block',
  width: 8,
  height: 8,
  borderRadius: '50%',
  background: tokenColorTextTertiary,
  margin: '0 2px',
});

export function AiAssistantPanel() {
  const t = useTranslation();
  const { message } = App.useApp();
  const { token } = antTheme.useToken();
  const messages = useAiLabStore((s) => s.messages);
  const isStreaming = useAiLabStore((s) => s.isStreaming);
  const sendMessage = useAiLabStore((s) => s.sendMessage);
  const clearConversation = useAiLabStore((s) => s.clearConversation);
  const pipelineResult = useAiLabStore((s) => s.pipelineResult);

  const [inputValue, setInputValue] = useState('');
  const [selectedModel, setSelectedModel] = useState('gpt-4o-mini');
  const [activeSubTab, setActiveSubTab] = useState('chat');
  const [pipelines, setPipelines] = useState<Array<{ id: string; name: string }>>([]);
  const [selectedPipelineId, setSelectedPipelineId] = useState<string | null>(null);
  const [optimizing, setOptimizing] = useState(false);
  const [optimizeResult, setOptimizeResult] = useState<Record<string, unknown> | null>(null);

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const navigate = useNavigate();

  /** Load available pipelines for optimization */
  useEffect(() => {
    loadPipelines();
  }, []);

  const loadPipelines = async () => {
    try {
      const pipelineData = await listPipelines({ page_size: 50 });
      const list = pipelineData?.results || [];
      setPipelines(
        list.map((p) => ({
          id: String(p.id),
          name: p.name || `Pipeline #${String(p.id).slice(0, 8)}`,
        })),
      );
    } catch (err) {
      console.error('AI assistant load failed:', err);
    }
  };

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, isStreaming]);

  const handleSend = async () => {
    const trimmed = inputValue.trim();
    if (!trimmed || isStreaming) return;
    setInputValue('');
    try {
      await sendMessage(trimmed);
    } catch {
      message.error(t('ailab.msg_send_failed'));
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const handleOpenPipeline = () => {
    if (pipelineResult) {
      navigate(`/tasks?tab=pipeline&data=${encodeURIComponent(JSON.stringify(pipelineResult))}`);
    }
  };

  /** Request AI optimization suggestions for selected pipeline */
  const handleOptimize = async () => {
    if (!selectedPipelineId) {
      message.warning(t('ailab.msg_select_pipeline_first'));
      return;
    }
    setOptimizing(true);
    setOptimizeResult(null);
    try {
      const data = await optimizePipeline({
        pipeline_id: selectedPipelineId,
        model: selectedModel,
      });
      setOptimizeResult(data);
      message.success(t('ailab.msg_optimize_done'));
    } catch (e: unknown) {
      const errMsg = e instanceof Error ? e.message : t('ailab.msg_optimize_request_failed');
      message.error(t('ailab.msg_optimize_failed', { message: errMsg }));
      setOptimizeResult({ error: errMsg, raw_content: t('ailab.msg_llm_unreachable') });
    } finally {
      setOptimizing(false);
    }
  };

  /** Render optimization result panel */
  const renderOptimizePanel = () => (
    <div className="gaf-p-lg gaf-h-full gaf-overflow-y-auto">
      <Card
        size="small"
        title={
          <span>
            <ThunderboltOutlined /> {t('ailab.card_optimize_suggestions')}
          </span>
        }
        className="gaf-mb-lg"
      >
        <Space orientation="vertical" className="gaf-w-full" size="middle">
          <div>
            <Text strong className="gaf-mb-sm gaf-display-block">
              {t('ailab.label_select_pipeline_to_optimize')}
            </Text>
            <Select
              showSearch
              placeholder={t('ailab.placeholder_select_pipeline')}
              className="gaf-w-full"
              value={selectedPipelineId}
              onChange={setSelectedPipelineId}
              filterOption={(input, option) =>
                ((option?.label as string) || '').toLowerCase().includes(input.toLowerCase())
              }
              options={pipelines.map((p) => ({ value: p.id, label: p.name }))}
            />
          </div>
          <Button
            type="primary"
            icon={<BulbOutlined />}
            onClick={handleOptimize}
            loading={optimizing}
            disabled={!selectedPipelineId}
            block
            size="large"
          >
            {t('ailab.btn_get_optimize_suggestions')}
          </Button>
        </Space>
      </Card>

      {optimizing && (
        <div className="gaf-text-center" style={{ padding: 40 }}>
          <Spin size="large" description={t('ailab.msg_ai_analyzing')} />
        </div>
      )}

      {optimizeResult && !optimizing && (
        <Card
          size="small"
          title={t('ailab.card_optimize_result')}
          extra={
            optimizeResult.error ? (
              <Tag color="red">{t('ailab.tag_analysis_error')}</Tag>
            ) : (
              <Tag color="green">{t('ailab.tag_done')}</Tag>
            )
          }
        >
          {(optimizeResult as Record<string, unknown>).error ? (
            <Alert type="error" description={(optimizeResult as Record<string, unknown>).error as string} />
          ) : (
            <>
              {(optimizeResult.raw_content as string) && (
                <div className="gaf-mb-lg">
                  <Text strong>{t('ailab.label_ai_analysis_report')}</Text>
                  <pre
                    className="gaf-mt-sm gaf-p-md gaf-radius-md gaf-text-13 gaf-whitespace-pre-wrap gaf-overflow-auto gaf-word-break"
                    style={{ background: token.colorBgLayout, maxHeight: 300, lineHeight: 1.7 }}
                  >
                    {optimizeResult.raw_content as string}
                  </pre>
                </div>
              )}
              {optimizeResult.suggestions && (
                <div>
                  <Text strong>{t('ailab.label_structured_suggestions')}</Text>
                  <pre
                    className="gaf-mt-sm gaf-p-md gaf-text-xs gaf-radius-md gaf-overflow-auto gaf-font-mono"
                    style={{ background: token.colorBgLayout, color: token.colorText, maxHeight: 200 }}
                  >
                    {JSON.stringify(optimizeResult.suggestions, null, 2)}
                  </pre>
                </div>
              )}
              {optimizeResult.usage && (
                <div className="gaf-mt-md">
                  <Tag>
                    Token: {(optimizeResult.usage as Record<string, unknown>).input_tokens as number} in /{' '}
                    {(optimizeResult.usage as Record<string, unknown>).output_tokens as number} out
                  </Tag>
                  <Tag color="blue">
                    {t('ailab.label_model')}: {(optimizeResult.usage as Record<string, unknown>).model as string}
                  </Tag>
                  <Tag color="orange">
                    {t('ailab.label_cost')}: ${(optimizeResult.usage as Record<string, unknown>).cost as number}
                  </Tag>
                </div>
              )}
            </>
          )}
        </Card>
      )}

      {!optimizeResult && !optimizing && <Empty description={t('ailab.empty_select_pipeline')} />}
    </div>
  );

  const lastAssistantIndex = [...messages].reverse().findIndex((m) => m.role === 'assistant');
  const lastAssistantMsg = lastAssistantIndex >= 0 ? [...messages].reverse()[lastAssistantIndex] : null;
  const showTyping = isStreaming && lastAssistantMsg && !lastAssistantMsg.content;

  return (
    <div className="gaf-flex-col gaf-h-full">
      <AntTabs
        activeKey={activeSubTab}
        onChange={setActiveSubTab}
        size="small"
        className="gaf-px-lg"
        items={[
          {
            key: 'chat',
            label: (
              <span>
                <RobotOutlined /> {t('ailab.tab_natural_language_create')}
              </span>
            ),
          },
          {
            key: 'optimize',
            label: (
              <span>
                <ThunderboltOutlined /> {t('ailab.tab_smart_optimize')}
              </span>
            ),
          },
        ]}
      />

      {activeSubTab === 'chat' ? (
        <>
          <div
            className="gaf-flex-between gaf-py-md gaf-px-lg"
            style={{ borderBottom: `1px solid ${token.colorBorder}`, background: token.colorBgLayout }}
          >
            <Space>
              <Select
                value={selectedModel}
                onChange={setSelectedModel}
                options={MODEL_OPTIONS}
                size="small"
                style={{ width: 160 }}
              />
            </Space>
            <Button icon={<ClearOutlined />} size="small" onClick={clearConversation} disabled={messages.length === 0}>
              {t('ailab.btn_clear_conversation')}
            </Button>
          </div>

          <div className="gaf-flex-1 gaf-overflow-y-auto" style={{ padding: '16px 20px' }}>
            {messages.map((msg) => (
              <div
                key={msg.id}
                style={
                  msg.role === 'user'
                    ? getBubbleStyleUser(token.colorPrimary)
                    : getBubbleStyleAssistant(token.colorBgContainer, token.colorText)
                }
              >
                <div className="gaf-flex-center gaf-mb-xs" style={{ gap: 6 }}>
                  {msg.role === 'user' ? <UserOutlined /> : <RobotOutlined />}
                  <Text
                    strong
                    className="gaf-text-xs"
                    style={{ color: msg.role === 'user' ? '#fff' : token.colorText }}
                  >
                    {msg.role === 'user' ? t('ailab.label_you') : t('ailab.label_ai_assistant')}
                  </Text>
                </div>
                <div className="gaf-text-sm gaf-whitespace-pre-wrap" style={{ lineHeight: 1.6 }}>
                  {msg.content}
                </div>
                {msg.role === 'assistant' && !!msg.metadata?.pipelineData && (
                  <div className="gaf-mt-sm">
                    <Button
                      type="primary"
                      size="small"
                      style={{ background: token.colorSuccess, borderColor: token.colorSuccess }}
                      onClick={handleOpenPipeline}
                    >
                      {t('ailab.btn_open_in_pipeline_editor')}
                    </Button>
                  </div>
                )}
              </div>
            ))}

            {showTyping && (
              <div
                className="gaf-gap-xs gaf-flex-center"
                style={{ ...getBubbleStyleAssistant(token.colorBgContainer, token.colorText) }}
              >
                <RobotOutlined />
                <span style={getTypingDotStyle(token.colorTextTertiary)} className="typing-dot" />
                <span
                  style={{ ...getTypingDotStyle(token.colorTextTertiary), animationDelay: '0.2s' }}
                  className="typing-dot"
                />
                <span
                  style={{ ...getTypingDotStyle(token.colorTextTertiary), animationDelay: '0.4s' }}
                  className="typing-dot"
                />
              </div>
            )}

            <div ref={messagesEndRef} />
          </div>

          <div
            className="gaf-py-md gaf-px-lg"
            style={{ borderTop: `1px solid ${token.colorBorder}`, background: token.colorBgLayout }}
          >
            <div className="gaf-flex gaf-gap-sm">
              <TextArea
                value={inputValue}
                onChange={(e) => setInputValue(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder={t('ailab.placeholder_input_requirement')}
                autoSize={{ minRows: 2, maxRows: 6 }}
                disabled={isStreaming}
                className="gaf-flex-1"
              />
              <Button
                type="primary"
                icon={<SendOutlined />}
                onClick={handleSend}
                loading={isStreaming}
                disabled={!inputValue.trim() || isStreaming}
                style={{ alignSelf: 'flex-end' }}
              >
                {t('ailab.btn_send')}
              </Button>
            </div>
          </div>
        </>
      ) : (
        renderOptimizePanel()
      )}

      <style>{`
        .typing-dot {
          animation: typingBounce 1.4s infinite ease-in-out;
        }
        .typing-dot:nth-child(2) { animation-delay: 0.2s; }
        .typing-dot:nth-child(3) { animation-delay: 0.4s; }
        @keyframes typingBounce {
          0%, 80%, 100% { opacity: 0.3; transform: scale(0.8); }
          40% { opacity: 1; transform: scale(1); }
        }
      `}</style>
    </div>
  );
}

export default AiAssistantPanel;
