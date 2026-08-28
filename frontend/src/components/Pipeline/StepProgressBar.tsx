/**
 * step progress bar component
 * vertical directly column step list, show execute status, elapsed when and progress
 *
 * Task 3.6 (P2-6): StepInfo 新增 error_code 字段, failed 状态下展示
 * error.codes.<CODE> 映射后的多语言 Tag, 让多语言用户能看懂错误
 * (N192 B1/B2: 错误提示归一 + 错误码映射), 而非只看到后端中文 error_message。
 */
import {
  CheckCircleOutlined,
  CloseCircleOutlined,
  LoadingOutlined,
  MinusCircleOutlined,
  ForwardOutlined,
} from '@ant-design/icons';
import { Tag } from 'antd';
import type { StepStatus, PipelineNodeType } from '@/types/models';
import { useTranslation } from '@/i18n';

/** step info */
export interface StepInfo {
  index: number;
  name: string;
  status: StepStatus;
  duration?: number;
  nodeType?: PipelineNodeType;
  error_message?: string;
  /** Task 3.6: 节点级错误码 (NO_MATCH/LOW_CONFIDENCE/TIMEOUT/...), 与 agent AutoResult.error_code 对齐 */
  error_code?: string;
}

/** StepProgressBar component props */
interface StepProgressBarProps {
  steps: StepInfo[];
  currentStepIndex?: number;
  onStepClick?: (step: StepInfo) => void;
}

/** format transform cost when show */
function formatDuration(ms: number): string {
  if (ms < 1000) return `${ms}ms`;
  if (ms < 60000) return `${(ms / 1000).toFixed(1)}s`;
  return `${(ms / 60000).toFixed(1)}min`;
}

/** step status to corresponding icon */
function getStatusIcon(status: StepStatus, isCurrent: boolean) {
  switch (status) {
    case 'success':
      return <CheckCircleOutlined className="gaf-text-sm" style={{ color: '#52c41a' }} />;
    case 'running':
      return <LoadingOutlined className="gaf-text-sm" style={{ color: '#1890ff' }} />;
    case 'failed':
      return <CloseCircleOutlined className="gaf-text-sm" style={{ color: '#ff4d4f' }} />;
    case 'skipped':
      return <ForwardOutlined className="gaf-text-sm" style={{ color: '#faad14' }} />;
    default:
      return isCurrent ? (
        <LoadingOutlined className="gaf-text-sm" style={{ color: '#1890ff' }} />
      ) : (
        <MinusCircleOutlined className="gaf-text-sm" style={{ color: '#d9d9d9' }} />
      );
  }
}

/** inject pulse animation keyframes */
function injectPulseKeyframes() {
  if (typeof document === 'undefined') return;
  if (document.getElementById('step-pulse-keyframes')) return;
  const style = document.createElement('style');
  style.id = 'step-pulse-keyframes';
  style.textContent = `
    @keyframes step-pulse {
      0%, 100% { box-shadow: 0 0 0 0 rgba(24, 144, 255, 0.4); }
      50% { box-shadow: 0 0 0 6px rgba(24, 144, 255, 0); }
    }
    @keyframes spin-icon {
      from { transform: rotate(0deg); }
      to { transform: rotate(360deg); }
    }
  `;
  document.head.appendChild(style);
}

/**
 * step progress bar component
 * vertical directly column show step execute status and progress
 */
export function StepProgressBar({ steps, currentStepIndex = -1, onStepClick }: StepProgressBarProps) {
  injectPulseKeyframes();
  // Task 3.6: 用 i18n 把 error_code (NO_MATCH/TIMEOUT/...) 映射为多语言文案,
  // 而非把后端中文 error_message 原文甩给多语言用户 (N192 B1/B2)。
  const t = useTranslation();

  return (
    <div className="gaf-flex-col gaf-py-sm" style={{ gap: 0 }}>
      {steps.map((step, idx) => {
        const isCurrent = idx === currentStepIndex;
        const isCompleted = step.status === 'success';
        const isLast = idx === steps.length - 1;
        // N192 B7 P1: 允许点击 success 和 failed 状态的节点跳转截图
        // (原 isCompleted 守卫排除了 failed, 与 "跳转失败节点截图" 矛盾)
        const isClickable = !!onStepClick && (step.status === 'success' || step.status === 'failed');

        return (
          <div key={step.index} style={{ display: 'flex', alignItems: 'flex-start', minHeight: 36 }}>
            <div className="gaf-flex-col" style={{ alignItems: 'center', width: 20, flexShrink: 0 }}>
              <div
                className="gaf-flex-center"
                style={{
                  width: 20,
                  height: 20,
                  borderRadius: '50%',
                  border: isCurrent ? '2px solid #1890ff' : '2px solid transparent',
                  animation: isCurrent ? 'step-pulse 1.5s ease-in-out infinite' : undefined,
                  cursor: isClickable ? 'pointer' : undefined,
                }}
                onClick={() => {
                  if (isClickable) onStepClick(step);
                }}
              >
                {getStatusIcon(step.status, isCurrent)}
              </div>
              {!isLast && (
                <div
                  className="gaf-flex-1"
                  style={{
                    width: 2,
                    minHeight: 12,
                    marginTop: 2,
                    background: isCompleted ? '#52c41a' : undefined,
                    border: isCompleted ? undefined : '1px dashed #d9d9d9',
                  }}
                />
              )}
            </div>
            <div
              className="gaf-flex-1"
              style={{
                marginLeft: 10,
                cursor: isClickable ? 'pointer' : undefined,
                opacity: step.status === 'pending' && !isCurrent ? 0.5 : 1,
              }}
              onClick={() => {
                if (isClickable) onStepClick(step);
              }}
            >
              <div
                style={{
                  fontSize: 13,
                  fontWeight: isCurrent ? 600 : 400,
                  color: isCurrent ? '#1890ff' : step.status === 'failed' ? '#ff4d4f' : '#333',
                }}
              >
                {step.index}. {step.name}
              </div>
              {step.duration !== undefined && step.status !== 'pending' && (
                <div className="gaf-text-xxs" style={{ color: '#999', marginTop: 1 }}>
                  {formatDuration(step.duration)}
                </div>
              )}
              {step.status === 'failed' && step.error_message && (
                <div className="gaf-text-xxs" style={{ color: '#ff4d4f', marginTop: 2, wordBreak: 'break-word' }}>
                  {step.error_message}
                </div>
              )}
              {step.status === 'failed' && step.error_code && (
                <div className="gaf-text-xxs" style={{ marginTop: 2 }}>
                  <Tag color="error" style={{ marginInlineEnd: 0, fontSize: 11, lineHeight: '16px' }}>
                    {(() => {
                      // Task 3.6: 按 error.codes.<CODE> 映射多语言文案;
                      // i18n 找不到 key 时返回 key 本身, 此时降级展示原始 error_code.
                      const i18nKey = `error.codes.${step.error_code}`;
                      const mapped = t(i18nKey);
                      return mapped && mapped !== i18nKey ? mapped : step.error_code;
                    })()}
                  </Tag>
                </div>
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
}

export default StepProgressBar;
