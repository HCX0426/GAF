/**
 * SystemAnnouncement — system announcement Banner
 *
 * display system announcements at top of Dashboard, supports info/warning/error/success four types type,
 * closeable, used to broadcast important notices, maintenance announcements or new feature launch messages.
 */

import { useState, useMemo, useCallback } from 'react';
import { Alert, Space, Button } from 'antd';
import { BellOutlined, ReloadOutlined } from '@ant-design/icons';

/** announcement type */
type AnnouncementType = 'info' | 'warning' | 'error' | 'success';

/** single announcement data structure */
interface AnnouncementItem {
  id: string;
  title: string;
  content: string;
  type: AnnouncementType;
  timestamp: string;
  closable: boolean;
}

/**
 * map announcement type to Antd Alert type attribute value
 * @param type custom announcement type
 * @returns Antd Alert type string
 */
function mapAlertType(type: AnnouncementType): 'info' | 'warning' | 'error' | 'success' {
  return type;
}

interface SystemAnnouncementProps {
  /** whether to auto-carousel multiple announcements ( default false) */
  autoRotate?: boolean;
  /** carousel interval in ms ( default 5000) */
  rotateInterval?: number;
  /** use custom announcement data (uses mock data if not provided) */
  announcements?: AnnouncementItem[];
}

export function SystemAnnouncement({
  autoRotate = false,
  announcements: externalAnnouncements,
}: SystemAnnouncementProps) {
  const [closedIds, setClosedIds] = useState<Set<string>>(new Set());
  const [currentIndex, setCurrentIndex] = useState(0);

  /** merge externally passed data with default empty array */
  const allAnnouncements = useMemo(() => externalAnnouncements ?? [], [externalAnnouncements]);

  /** filter out closed announcements */
  const visibleAnnouncements = useMemo(
    () => allAnnouncements.filter((a) => !closedIds.has(a.id)),
    [allAnnouncements, closedIds],
  );

  /** close specified announcement */
  const handleClose = useCallback((id: string) => {
    setClosedIds((prev) => new Set(prev).add(id));
  }, []);

  /** redisplay all closed announcements */
  const handleShowAll = useCallback(() => {
    setClosedIds(new Set());
  }, []);

  /** manually switch to next announcement */
  const handleNext = useCallback(() => {
    setCurrentIndex((prev) => (visibleAnnouncements.length > 0 ? (prev + 1) % visibleAnnouncements.length : 0));
  }, [visibleAnnouncements.length]);

  if (visibleAnnouncements.length === 0) {
    return null;
  }

  /* in auto-carousel mode, only show current item */
  if (autoRotate && visibleAnnouncements.length > 1) {
    const current = visibleAnnouncements[currentIndex];
    return (
      <div className="gaf-mb-lg">
        <Alert
          type={mapAlertType(current.type)}
          showIcon
          icon={<BellOutlined />}
          closable={current.closable}
          onClose={() => handleClose(current.id)}
          title={
            <Space>
              <span className="gaf-font-semibold">{current.title}</span>
              <span className="gaf-text-xs" style={{ opacity: 0.7 }}>
                ({currentIndex + 1}/{visibleAnnouncements.length})
              </span>
            </Space>
          }
          description={current.content}
          action={
            <Space>
              <Button size="small" type="text" onClick={handleNext}>
                下一条
              </Button>
              <Button size="small" type="text" onClick={handleShowAll}>
                显示全部
              </Button>
            </Space>
          }
        />
      </div>
    );
  }

  /* default mode: show all visible announcements */
  return (
    <div className="gaf-mb-lg">
      {visibleAnnouncements.map((announcement) => (
        <Alert
          key={announcement.id}
          type={mapAlertType(announcement.type)}
          showIcon
          icon={<BellOutlined />}
          closable={announcement.closable}
          onClose={() => handleClose(announcement.id)}
          style={{ marginBottom: visibleAnnouncements.length > 1 ? 8 : 0 }}
          title={<span className="gaf-font-semibold">{announcement.title}</span>}
          description={announcement.content}
        />
      ))}
      {closedIds.size > 0 && (
        <div className="gaf-mt-xs" style={{ textAlign: 'right' }}>
          <Button size="small" type="link" icon={<ReloadOutlined />} onClick={handleShowAll}>
            恢复已关闭公告 ({closedIds.size})
          </Button>
        </div>
      )}
    </div>
  );
}

export default SystemAnnouncement;
