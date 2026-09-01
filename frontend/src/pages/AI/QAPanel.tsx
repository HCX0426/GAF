/**
 * AI QA Panel — multi-turn Q&A conversations (S4).
 *
 * Backend is the single source of truth: QASession (conversation aggregate)
 * + QAMessage (individual turns). No localStorage fallback — network errors
 * surface to the user instead of silently degrading.
 */
import React, { useEffect, useRef, useState } from 'react';
import { Button, Input, Typography, Spin, Tag, App, Tooltip, Badge, Popconfirm, Select, theme as antTheme } from 'antd';
import {
  SendOutlined,
  RobotOutlined,
  UserOutlined,
  StarOutlined,
  StarFilled,
  HistoryOutlined,
  CodeOutlined,
  DeleteOutlined,
  CopyOutlined,
} from '@ant-design/icons';

import { fetchQASessions, fetchQASessionMessages, askQuestion, markAsKnowledge, deleteQASession } from '@/api/ai';
import { fetchLlmProviderConfig } from '@/api/ai';
import type { QAMessage } from '@/api/ai';
import type { QASession, QAAskRequest } from '@/types/models';
import { useTranslation, getLocale } from '@/i18n';

const { TextArea } = Input;
const { Text, Paragraph } = Typography;

/** Generate user bubble style with design token */
const getBubbleStyleUser = (tokenColorPrimary: string, tokenColorTextLightSolid: string): React.CSSProperties => ({
  maxWidth: '80%',
  marginLeft: 'auto',
  marginBottom: 8,
  padding: '10px 14px',
  borderRadius: 16,
  borderBottomRightRadius: 4,
  background: tokenColorPrimary,
  color: tokenColorTextLightSolid,
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

/** Parse code file references from assistant message text */
function parseCodeRefs(text: string): Array<{ file: string; line?: string; fullRef: string }> {
  const refs: Array<{ file: string; line?: string; fullRef: string }> = [];
  const patterns = [
    /([\w/.-]+\.(py|ts|tsx|js|jsx))[:\s](\d+)/gi,
    /`([^`]+\.(py|ts|tsx|js|jsx))(?::(\d+))?`/gi,
    /\[([^\]]+\.(py|ts|tsx|js|jsx))(?::(\d+))?\]/gi,
  ];
  for (const pat of patterns) {
    let match;
    while ((match = pat.exec(text)) !== null) {
      refs.push({
        file: match[1],
        line: match[3] || undefined,
        fullRef: match[0],
      });
    }
  }
  return refs;
}

export function QAPanel() {
  const t = useTranslation();
  const { message: antMsg } = App.useApp();
  const { token } = antTheme.useToken();
  const [conversations, setConversations] = useState<QASession[]>([]);
  const [activeConvId, setActiveConvId] = useState<number | null>(null);
  const [messages, setMessages] = useState<QAMessage[]>([]);
  const [inputValue, setInputValue] = useState('');
  const [sending, setSending] = useState(false);
  const [loadingConvs, setLoadingConvs] = useState(false);
  const [loadingMsgs, setLoadingMsgs] = useState(false);
  // Model selection from the active LLM provider (available_models / default_model)
  const [modelOptions, setModelOptions] = useState<Array<{ value: string; label: string }>>([]);
  const [selectedModel, setSelectedModel] = useState<string | undefined>(undefined);

  const messagesEndRef = useRef<HTMLDivElement>(null);

  /** Load conversation list from backend */
  const loadConversations = async (selectFirst = false) => {
    setLoadingConvs(true);
    try {
      const qaData = await fetchQASessions();
      const list = qaData?.results || [];
      setConversations(list);
      if (selectFirst && list.length > 0 && activeConvId === null) {
        setActiveConvId(list[0].id);
      }
    } catch {
      antMsg.error(t('ailab.msg_send_failed'));
      setConversations([]);
    } finally {
      setLoadingConvs(false);
    }
  };

  /** Load messages for the active conversation from backend */
  const loadMessages = async (sessionId: number) => {
    setLoadingMsgs(true);
    try {
      const data = await fetchQASessionMessages(sessionId);
      setMessages(data);
    } catch {
      antMsg.error(t('ailab.msg_send_failed'));
      setMessages([]);
    } finally {
      setLoadingMsgs(false);
    }
  };

  useEffect(() => {
    loadConversations(true);
    loadModelOptions();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  /** Load model options from the active LLM provider (Phase 3: QA picks model). */
  const loadModelOptions = async () => {
    try {
      const providers = await fetchLlmProviderConfig();
      const active = providers.find((p) => p.is_active);
      if (!active) return;
      const models = Array.isArray(active.available_models) && active.available_models.length > 0
        ? active.available_models
        : [active.default_model].filter(Boolean);
      const opts = models.map((m: string) => ({ value: m, label: `${m} (${active.provider})` }));
      setModelOptions(opts);
      setSelectedModel((prev) => prev ?? opts[0]?.value ?? active.default_model);
    } catch {
      // provider load failure should not block QA
    }
  };

  /** Auto-scroll to latest message */
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  /** Load messages when active conversation changes */
  useEffect(() => {
    if (activeConvId !== null) {
      loadMessages(activeConvId);
    } else {
      setMessages([]);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeConvId]);

  /** Start a new conversation — clears active selection so the next
   * askQuestion call creates a fresh QASession. */
  const handleNewConversation = () => {
    setActiveConvId(null);
    setMessages([]);
    setInputValue('');
  };

  /** Send a question. Creates a new session when no active conversation,
   * or appends to the existing one via session_id. */
  const handleSend = async () => {
    const trimmed = inputValue.trim();
    if (!trimmed || sending) return;

    setInputValue('');
    setSending(true);

    try {
      const wasNew = activeConvId === null;
      const payload: QAAskRequest = {
        question: trimmed,
        ...(activeConvId !== null ? { session_id: activeConvId } : {}),
      };
      if (selectedModel) payload.model = selectedModel;
      const session = await askQuestion(payload);
      if (wasNew) {
        // Setting activeConvId triggers the useEffect to load messages.
        setActiveConvId(session.id);
      } else {
        // Active conversation unchanged — manually refresh messages.
        await loadMessages(session.id);
      }
      // Refresh conversation list (title / message_count / last_message_at).
      await loadConversations();
    } catch {
      antMsg.error(t('ailab.msg_send_failed'));
    } finally {
      setSending(false);
    }
  };

  /** Handle keyboard event: Enter to send, Shift+Enter for newline */
  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  /** Toggle knowledge entry flag on a session (session-level, not message-level) */
  const handleToggleKnowledge = async (conv: QASession) => {
    try {
      const updated = await markAsKnowledge(conv.id);
      setConversations((prev) => prev.map((c) => (c.id === updated.id ? updated : c)));
      antMsg.success(t('ailab.msg_marked_knowledge'));
    } catch {
      antMsg.error(t('ailab.msg_send_failed'));
    }
  };

  /** Delete a conversation with confirmation */
  const handleDeleteConversation = async (convId: number) => {
    try {
      await deleteQASession(convId);
    } catch {
      antMsg.error(t('ailab.msg_send_failed'));
      return;
    }
    const updated = conversations.filter((c) => c.id !== convId);
    setConversations(updated);
    if (activeConvId === convId) {
      setActiveConvId(updated.length > 0 ? updated[0].id : null);
    }
    antMsg.success(t('ailab.msg_conversation_deleted'));
  };

  /** Render code reference links in message content */
  const renderContentWithCodeRefs = (content: string) => {
    const refs = parseCodeRefs(content);
    if (refs.length === 0)
      return (
        <Paragraph className="gaf-m-0 gaf-text-sm gaf-whitespace-pre-wrap" style={{ lineHeight: 1.6 }}>
          {content}
        </Paragraph>
      );

    const result = content;
    const renderedParts: Array<React.ReactNode> = [];
    let lastIndex = 0;

    const sortedRefs = [...refs].sort((a, b) => content.indexOf(a.fullRef) - content.indexOf(b.fullRef));

    for (const ref of sortedRefs) {
      const idx = result.indexOf(ref.fullRef);
      if (idx === -1) continue;
      if (idx > lastIndex) {
        renderedParts.push(result.substring(lastIndex, idx));
      }
      renderedParts.push(
        <Tooltip key={`${ref.file}-${ref.line}-${idx}`} title={t('ailab.tooltip_open_ref', { ref: ref.fullRef })}>
          <Tag
            color="blue"
            className="gaf-text-xs gaf-cursor-pointer gaf-font-mono"
            onClick={() => antMsg.info(t('ailab.msg_code_ref', { ref: ref.fullRef }))}
          >
            <CodeOutlined /> {ref.file}
            {ref.line ? `:${ref.line}` : ''}
          </Tag>
        </Tooltip>,
      );
      lastIndex = idx + ref.fullRef.length;
    }

    if (lastIndex < result.length) {
      renderedParts.push(result.substring(lastIndex));
    }

    return (
      <span className="gaf-text-sm gaf-whitespace-pre-wrap" style={{ lineHeight: 1.6 }}>
        {renderedParts}
      </span>
    );
  };

  return (
    <div className="gaf-flex gaf-h-full">
      <div
        className="gaf-flex-col gaf-p-md gaf-overflow-y-auto"
        style={{ width: 280, borderRight: `1px solid ${token.colorBorder}` }}
      >
        <div className="gaf-mb-md">
          <Button type="primary" block icon={<HistoryOutlined />} onClick={handleNewConversation}>
            {t('ailab.btn_new_qa')}
          </Button>
        </div>
        <div className="gaf-flex-1 gaf-overflow-y-auto">
          {loadingConvs && (
            <div className="gaf-p-lg gaf-text-center">
              <Spin size="small" />
            </div>
          )}
          {!loadingConvs && conversations.length === 0 && (
            <Text type="secondary" className="gaf-text-center gaf-display-block" style={{ padding: 20 }}>
              {t('ailab.empty_no_conversations')}
            </Text>
          )}
          {conversations.map((conv) => {
            const displayTitle = conv.title || conv.question.slice(0, 50) || t('ailab.label_unnamed_qa');
            const displayDate = conv.last_message_at || conv.created_at;
            return (
              <div
                key={conv.id}
                onClick={() => setActiveConvId(conv.id)}
                className="gaf-flex-between gaf-mb-xs gaf-cursor-pointer gaf-radius-md"
                style={{
                  padding: '8px 10px',
                  background: activeConvId === conv.id ? token.colorPrimaryBg : 'transparent',
                  border: activeConvId === conv.id ? `1px solid ${token.colorPrimaryBorder}` : '1px solid transparent',
                }}
              >
                <div className="gaf-flex-1" style={{ minWidth: 0 }}>
                  <Text ellipsis className="gaf-text-13">
                    {displayTitle}
                  </Text>
                  <div className="gaf-flex gaf-gap-xs" style={{ marginTop: 2 }}>
                    <Badge count={conv.message_count} size="small" style={{ backgroundColor: token.colorPrimary }} />
                    <Text type="secondary" style={{ fontSize: 10 }}>
                      {new Date(displayDate).toLocaleDateString(getLocale())}
                    </Text>
                  </div>
                </div>
                <div className="gaf-flex gaf-gap-xs">
                  <Button
                    type="text"
                    size="small"
                    icon={
                      conv.is_knowledge_entry ? <StarFilled style={{ color: token.colorWarning }} /> : <StarOutlined />
                    }
                    onClick={(e) => {
                      e.stopPropagation();
                      handleToggleKnowledge(conv);
                    }}
                    aria-label={conv.is_knowledge_entry ? '取消收藏' : '收藏'}
                    style={{ opacity: 0.6 }}
                  />
                  <Popconfirm
                    title={t('ailab.confirm_delete_conversation')}
                    onConfirm={() => handleDeleteConversation(conv.id)}
                    okText={t('ailab.btn_delete')}
                    cancelText={t('ailab.btn_cancel')}
                    okButtonProps={{ danger: true }}
                  >
                    <Button
                      type="text"
                      size="small"
                      danger
                      icon={<DeleteOutlined />}
                      aria-label="删除对话"
                      style={{ opacity: 0.45 }}
                      onClick={(e) => e.stopPropagation()}
                    />
                  </Popconfirm>
                </div>
              </div>
            );
          })}
        </div>
      </div>

      <div className="gaf-flex-col gaf-flex-1">
        <div className="gaf-flex-1 gaf-overflow-y-auto" style={{ padding: '16px 20px' }}>
          {loadingMsgs && (
            <div className="gaf-p-lg gaf-text-center">
              <Spin description={t('ailab.msg_thinking')} />
            </div>
          )}
          {!loadingMsgs && messages.length === 0 && !sending && (
            <div className="gaf-p-lg gaf-text-center" style={{ color: token.colorTextTertiary }}>
              {activeConvId === null ? t('ailab.empty_select_or_create_qa') : t('ailab.empty_no_conversations')}
            </div>
          )}
          {messages.map((msg) => (
            <div
              key={msg.id}
              style={
                msg.role === 'user'
                  ? getBubbleStyleUser(token.colorPrimary, token.colorTextLightSolid)
                  : getBubbleStyleAssistant(token.colorBgContainer, token.colorText)
              }
            >
              <div className="gaf-flex-center gaf-mb-xs" style={{ gap: 6 }}>
                {msg.role === 'user' ? <UserOutlined /> : <RobotOutlined />}
                <Text
                  strong
                  className="gaf-text-xs"
                  style={{ color: msg.role === 'user' ? token.colorTextLightSolid : token.colorText }}
                >
                  {msg.role === 'user' ? t('ailab.label_you') : t('ailab.label_ai_assistant')}
                </Text>
              </div>
              <div>{renderContentWithCodeRefs(msg.content)}</div>
              {msg.role === 'assistant' && (
                <div className="gaf-flex gaf-gap-xs" style={{ marginTop: 6 }}>
                  <Button
                    type="link"
                    size="small"
                    icon={<CopyOutlined />}
                    onClick={() => {
                      navigator.clipboard.writeText(msg.content);
                      antMsg.success(t('ailab.msg_copied'));
                    }}
                  >
                    {t('ailab.btn_copy')}
                  </Button>
                </div>
              )}
            </div>
          ))}
          {sending && (
            <div className="gaf-p-lg gaf-text-center">
              <Spin description={t('ailab.msg_thinking')} />
            </div>
          )}
          <div ref={messagesEndRef} />
        </div>

        <div
          className="gaf-py-md gaf-px-lg"
          style={{ borderTop: `1px solid ${token.colorBorder}`, background: token.colorBgLayout }}
        >
          <div className="gaf-flex gaf-gap-sm gaf-mb-sm">
            <Select
              value={selectedModel}
              onChange={setSelectedModel}
              options={modelOptions}
              size="small"
              style={{ width: 260 }}
              placeholder={t('ailab.placeholder_select_default_model')}
              allowClear
            />
            <Text type="secondary" className="gaf-text-xs">
              {t('ailab.help_model_selection')}
            </Text>
          </div>
          <div className="gaf-flex gaf-gap-sm">
            <TextArea
              value={inputValue}
              onChange={(e) => setInputValue(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder={t('ailab.placeholder_input_question')}
              autoSize={{ minRows: 2, maxRows: 4 }}
              disabled={sending}
              className="gaf-flex-1"
            />
            <Button
              type="primary"
              icon={<SendOutlined />}
              onClick={handleSend}
              loading={sending}
              disabled={!inputValue.trim() || sending}
              style={{ alignSelf: 'flex-end' }}
            >
              {t('ailab.btn_send')}
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}

export default QAPanel;
