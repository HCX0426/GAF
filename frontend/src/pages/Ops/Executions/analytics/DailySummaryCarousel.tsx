/**
 * today summary carousel component
 * with Carousel form show unattended task current progress status, supports auto play and manual navigation
 */
import { useState, useEffect, useRef } from 'react';
import { Carousel, Card, Tag, Badge, Spin, Empty, theme } from 'antd';
import type { CarouselRef } from 'antd/es/carousel';
import type { GlobalToken } from 'antd/es/theme/interface';
import { LeftOutlined, RightOutlined } from '@ant-design/icons';
import { useTranslation } from '@/i18n';
import client from '@/api/client';

/** task status type */
type TaskStatus = 'success' | 'running' | 'pending' | 'failed';

/** summary card data */
interface SummaryItem {
  id: string;
  device_name: string;
  account_name: string;
  task_name: string;
  status: TaskStatus;
  description: string;
}

/** DailySummaryCarousel component props */
interface DailySummaryCarouselProps {
  /** auto carousel interval ( milliseconds ), default 5000 */
  autoplayInterval?: number;
}

/** status to label mapping (i18n key) */
const STATUS_LABEL_MAP: Record<TaskStatus, string> = {
  success: 'executions.report_status_success',
  running: 'executions.report_status_running',
  pending: 'executions.report_status_pending',
  failed: 'executions.report_status_failed',
};

/** map task status to its color config using design tokens */
function getStatusConfig(
  status: TaskStatus,
  token: GlobalToken,
): { color: string; label: string; borderColor: string } {
  const colorMap: Record<TaskStatus, string> = {
    success: token.colorSuccess,
    running: token.colorPrimary,
    pending: token.colorWarning,
    failed: token.colorError,
  };
  const color = colorMap[status];
  return { color, label: STATUS_LABEL_MAP[status], borderColor: color };
}

/** F010 fix: map lookup replaces 4-level nested ternary for Antd Badge status */
const BADGE_STATUS_MAP: Record<TaskStatus, 'success' | 'error' | 'processing' | 'warning'> = {
  success: 'success',
  failed: 'error',
  running: 'processing',
  pending: 'warning',
};

/**
 * get today summary data
 */
async function fetchDailySummary(): Promise<SummaryItem[]> {
  // s42 fix: previously fetch('/api/unattended/progress/') — bypassed the axios
  // client (baseURL=/api/v2) AND hit a 404 (real route is
  // /api/v2/scheduler/unattended/progress/), silently swallowed by catch.
  // client request interceptor attaches the auth token automatically.
  const res = await client.get('/scheduler/unattended/progress/');
  return res.data;
}

/**
 * today summary carousel component
 */
export function DailySummaryCarousel({ autoplayInterval = 5000 }: DailySummaryCarouselProps) {
  const t = useTranslation();
  const { token } = theme.useToken();
  const [items, setItems] = useState<SummaryItem[]>([]);
  const [loading, setLoading] = useState(false);
  const carouselRef = useRef<CarouselRef>(null);

  /** load summary data */
  const loadSummary = async () => {
    setLoading(true);
    try {
      const data = await fetchDailySummary();
      // F5 fix (2026-08-28): 空态可能返回非数组 → 守卫后 items.map 不再崩溃
      setItems(Array.isArray(data) ? data : []);
    } catch {
      setItems([]);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadSummary();
  }, []);

  /** switch to previous piece slide */
  const handlePrev = () => carouselRef.current?.prev();

  /** switch to next piece slide */
  const handleNext = () => carouselRef.current?.next();

  /** render single piece summary card */
  const renderCard = (item: SummaryItem) => {
    const config = getStatusConfig(item.status, token);
    const isRunning = item.status === 'running';

    return (
      <div key={item.id} className="gaf-px-sm">
        <Card
          style={{
            borderRadius: 12,
            borderLeft: `4px solid ${config.borderColor}`,
            boxShadow: isRunning ? `0 0 12px ${config.color}40` : '0 2px 8px rgba(0,0,0,0.08)',
            ...(isRunning && { animation: 'breathe 2s ease-in-out infinite' }),
            minHeight: 180,
          }}
        >
          <div className="gaf-flex-col" style={{ gap: 10 }}>
            <div className="gaf-flex-between">
              <Badge
                status={BADGE_STATUS_MAP[item.status]}
                text={
                  <span className="gaf-font-semibold" style={{ fontSize: 15 }}>
                    {item.task_name}
                  </span>
                }
              />
              <Tag color={config.color} className="gaf-m-0">
                {t(config.label)}
              </Tag>
            </div>

            <div className="gaf-flex-col gaf-text-13" style={{ gap: 6 }}>
              <div>
                <span className="gaf-mr-sm" style={{ color: token.colorTextSecondary }}>
                  {t('executions.text_device')}
                </span>
                <span>{item.device_name}</span>
              </div>
              <div>
                <span className="gaf-mr-sm" style={{ color: token.colorTextSecondary }}>
                  {t('executions.text_account')}
                </span>
                <span>{item.account_name}</span>
              </div>
            </div>

            <div
              className="gaf-mt-xs gaf-text-13 gaf-radius-md"
              style={{
                padding: '8px 10px',
                background: token.colorBgLayout,
                color: token.colorTextSecondary,
                lineHeight: '20px',
              }}
            >
              {item.description || t('executions.text_no_description')}
            </div>
          </div>
        </Card>
      </div>
    );
  };

  return (
    <div className="gaf-position-relative">
      {/* 呼吸动画样式 (C 类保留: keyframes 8 位 hex 带 alpha, 无法用 token) */}
      <style>{`
        @keyframes breathe {
          0%, 100% { box-shadow: 0 0 8px #1890ff30; }
          50% { box-shadow: 0 0 20px #1890ff60; }
        }
      `}</style>

      <Spin spinning={loading}>
        {!loading && items.length === 0 ? (
          <Empty description={t('executions.text_no_progress')} />
        ) : (
          <>
            <Carousel
              ref={carouselRef}
              autoplay
              dotPlacement="bottom"
              autoplaySpeed={autoplayInterval}
              style={{ padding: '16px 48px' }}
            >
              {items.map(renderCard)}
            </Carousel>

            {items.length > 1 && (
              <>
                <button
                  onClick={handlePrev}
                  aria-label="上一项"
                  className="gaf-cursor-pointer gaf-position-absolute gaf-flex-center gaf-justify-center"
                  style={{
                    left: 4,
                    top: '50%',
                    transform: 'translateY(-50%)',
                    width: 36,
                    height: 36,
                    borderRadius: '50%',
                    border: `1px solid ${token.colorBorder}`,
                    background: token.colorBgContainer,
                    zIndex: 2,
                    boxShadow: '0 2px 6px rgba(0,0,0,0.12)',
                  }}
                >
                  <LeftOutlined />
                </button>
                <button
                  onClick={handleNext}
                  aria-label="下一项"
                  className="gaf-cursor-pointer gaf-position-absolute gaf-flex-center gaf-justify-center"
                  style={{
                    right: 4,
                    top: '50%',
                    transform: 'translateY(-50%)',
                    width: 36,
                    height: 36,
                    borderRadius: '50%',
                    border: `1px solid ${token.colorBorder}`,
                    background: token.colorBgContainer,
                    zIndex: 2,
                    boxShadow: '0 2px 6px rgba(0,0,0,0.12)',
                  }}
                >
                  <RightOutlined />
                </button>
              </>
            )}
          </>
        )}
      </Spin>
    </div>
  );
}

export default DailySummaryCarousel;
