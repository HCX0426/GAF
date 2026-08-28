import { useState, useCallback, useEffect } from 'react';
import { Timeline, Button, Modal, Select, Spin, Typography, Empty, Tooltip, Tag, Space, theme as antTheme } from 'antd';
import { ClockCircleOutlined, DiffOutlined, RollbackOutlined, ReloadOutlined } from '@ant-design/icons';
import * as pipelineApi from '@/api/pipelines';
import { useTranslation, getLocale } from '@/i18n';

const { Text, Paragraph, Title } = Typography;

interface PipelineVersionHistoryProps {
  pipelineId: number;
  onRollback: (version: number) => void;
}

/** A simple JSON diff engine that compares two parsed JSON objects */
interface DiffLine {
  key: string;
  oldValue: string;
  newValue: string;
  status: 'added' | 'removed' | 'modified' | 'unchanged';
  depth: number;
}

/**
 * Compute a line-by-line diff between two JSON objects.
 * Flattens nested structures into key-value paths for comparison.
 */
function computeJsonDiff(oldObj: Record<string, unknown>, newObj: Record<string, unknown>): DiffLine[] {
  const flatten = (
    obj: Record<string, unknown>,
    prefix = '',
    depth = 0,
  ): Map<string, { value: string; depth: number }> => {
    const result = new Map<string, { value: string; depth: number }>();
    for (const [key, val] of Object.entries(obj)) {
      const path = prefix ? `${prefix}.${key}` : key;
      if (val !== null && typeof val === 'object' && !Array.isArray(val)) {
        const nested = flatten(val as Record<string, unknown>, path, depth + 1);
        nested.forEach((v, k) => result.set(k, v));
      } else {
        result.set(path, { value: JSON.stringify(val, null, 2), depth });
      }
    }
    return result;
  };

  const oldFlat = flatten(oldObj);
  const newFlat = flatten(newObj);
  const allKeys = Array.from(new Set([...oldFlat.keys(), ...newFlat.keys()])).sort();

  return allKeys.map((key) => {
    const oldEntry = oldFlat.get(key);
    const newEntry = newFlat.get(key);

    if (!oldEntry && newEntry) {
      return { key, oldValue: '', newValue: newEntry.value, status: 'added' as const, depth: newEntry.depth };
    }
    if (oldEntry && !newEntry) {
      return { key, oldValue: oldEntry.value, newValue: '', status: 'removed' as const, depth: oldEntry.depth };
    }
    if (oldEntry && newEntry) {
      const isModified = oldEntry.value !== newEntry.value;
      return {
        key,
        oldValue: oldEntry.value,
        newValue: newEntry.value,
        status: isModified ? ('modified' as const) : ('unchanged' as const),
        depth: oldEntry.depth,
      };
    }
    return { key, oldValue: '', newValue: '', status: 'unchanged' as const, depth: 0 };
  });
}

/**
 * Render a single line of the diff view with color coding
 */
function DiffLineView({ line }: { line: DiffLine }) {
  const { token } = antTheme.useToken();
  const indent = '\u00A0\u00A0'.repeat(line.depth * 2);

  if (line.status === 'added') {
    return (
      <div
        style={{ background: token.colorSuccessBg, padding: '2px 8px', borderLeft: `3px solid ${token.colorSuccess}` }}
      >
        <Text type="secondary" className="gaf-text-xxs">
          {indent}+
        </Text>{' '}
        <Text strong className="gaf-text-xs">
          {line.key}
        </Text>
        <br />
        <Text className="gaf-text-xxs" style={{ color: token.colorSuccess }}>
          {indent}
          {line.newValue}
        </Text>
      </div>
    );
  }

  if (line.status === 'removed') {
    return (
      <div style={{ background: token.colorErrorBg, padding: '2px 8px', borderLeft: `3px solid ${token.colorError}` }}>
        <Text type="secondary" className="gaf-text-xxs">
          {indent}-
        </Text>{' '}
        <Text strong className="gaf-text-xs" style={{ textDecoration: 'line-through' }}>
          {line.key}
        </Text>
        <br />
        <Text type="secondary" className="gaf-text-xxs">
          {indent}
          {line.oldValue}
        </Text>
      </div>
    );
  }

  if (line.status === 'modified') {
    return (
      <div
        style={{ background: token.colorWarningBg, padding: '2px 8px', borderLeft: `3px solid ${token.colorWarning}` }}
      >
        <Text type="secondary" className="gaf-text-xxs">
          {indent}~
        </Text>{' '}
        <Text strong className="gaf-text-xs">
          {line.key}
        </Text>
        <br />
        <Text type="secondary" delete className="gaf-text-xxs">
          {indent}
          {line.oldValue}
        </Text>
        <br />
        <Text className="gaf-text-xxs" style={{ color: token.colorPrimary }}>
          {indent}
          {line.newValue}
        </Text>
      </div>
    );
  }

  return (
    <div style={{ padding: '2px 8px', borderLeft: '3px solid transparent' }}>
      <Text type="secondary" className="gaf-text-xxs">
        {indent}
      </Text>{' '}
      <Text className="gaf-text-xs">{line.key}</Text>
      <br />
      <Text type="secondary" className="gaf-text-xxs">
        {indent}
        {line.newValue}
      </Text>
    </div>
  );
}

/**
 * Pipeline Version History component with diff comparison feature.
 *
 * Displays a Timeline of PipelineSnapshot versions with:
 * - Version number, comment, and created_at
 * - Compare button to open a side-by-side JSON diff modal
 * - Rollback button for each version
 */
export function PipelineVersionHistory({ pipelineId, onRollback }: PipelineVersionHistoryProps) {
  const { token } = antTheme.useToken();
  const t = useTranslation();
  const [snapshots, setSnapshots] = useState<pipelineApi.PipelineSnapshotItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [diffModalOpen, setDiffModalOpen] = useState(false);
  const [compareLeftVersion, setCompareLeftVersion] = useState<number | undefined>(undefined);
  const [compareRightVersion, setCompareRightVersion] = useState<number | undefined>(undefined);
  const [leftSnapshot, setLeftSnapshot] = useState<pipelineApi.PipelineSnapshotItem | null>(null);
  const [rightSnapshot, setRightSnapshot] = useState<pipelineApi.PipelineSnapshotItem | null>(null);
  const [fetchingDiff, setFetchingDiff] = useState(false);
  const [diffLines, setDiffLines] = useState<DiffLine[]>([]);

  const fetchSnapshots = useCallback(() => {
    setLoading(true);
    pipelineApi
      .getPipelineSnapshots(pipelineId)
      .then((data) => setSnapshots(data))
      .catch(() => setSnapshots([]))
      .finally(() => setLoading(false));
  }, [pipelineId]);

  useEffect(() => {
    fetchSnapshots();
  }, [fetchSnapshots]);

  /** Fetch a single version snapshot by version number */
  const fetchSnapshotByVersion = useCallback(
    async (version: number): Promise<pipelineApi.PipelineSnapshotItem | null> => {
      try {
        return await pipelineApi.getPipelineSnapshotByVersion(pipelineId, version);
      } catch {
        return null;
      }
    },
    [pipelineId],
  );

  /** Open the diff comparison modal */
  const handleOpenDiff = useCallback(() => {
    setDiffModalOpen(true);
    setCompareLeftVersion(undefined);
    setCompareRightVersion(undefined);
    setLeftSnapshot(null);
    setRightSnapshot(null);
    setDiffLines([]);
  }, []);

  /** Execute diff comparison between two selected versions */
  const handleCompare = useCallback(async () => {
    if (compareLeftVersion === undefined || compareRightVersion === undefined) return;
    setFetchingDiff(true);
    try {
      const [left, right] = await Promise.all([
        fetchSnapshotByVersion(compareLeftVersion),
        fetchSnapshotByVersion(compareRightVersion),
      ]);
      if (left && right) {
        setLeftSnapshot(left);
        setRightSnapshot(right);
        const oldData = (left.graph_data ?? {}) as Record<string, unknown>;
        const newData = (right.graph_data ?? {}) as Record<string, unknown>;
        setDiffLines(computeJsonDiff(oldData, newData));
      } else {
        setLeftSnapshot(null);
        setRightSnapshot(null);
        setDiffLines([]);
      }
    } catch {
      setLeftSnapshot(null);
      setRightSnapshot(null);
      setDiffLines([]);
    } finally {
      setFetchingDiff(false);
    }
  }, [compareLeftVersion, compareRightVersion, fetchSnapshotByVersion]);

  const versionOptions = snapshots.map((s) => ({
    label: `v${s.version}${s.change_summary ? ` — ${s.change_summary}` : ''}`,
    value: s.version,
  }));

  const diffStats = {
    added: diffLines.filter((l) => l.status === 'added').length,
    removed: diffLines.filter((l) => l.status === 'removed').length,
    modified: diffLines.filter((l) => l.status === 'modified').length,
  };

  return (
    <div className="gaf-py-lg gaf-px-xl">
      <div className="gaf-flex-between gaf-mb-lg">
        <Title level={4} className="gaf-m-0">
          {t('pipelineEditor.history_title')}
        </Title>
        <Space>
          <Tooltip title={t('pipelineEditor.history_refresh')}>
            <Button icon={<ReloadOutlined />} onClick={fetchSnapshots} size="small" aria-label="刷新版本历史" />
          </Tooltip>
        </Space>
      </div>

      {loading ? (
        <div className="gaf-text-center" style={{ padding: 48 }}>
          <Spin description={t('pipelineEditor.history_loading')} />
        </div>
      ) : snapshots.length === 0 ? (
        <Empty description={t('pipelineEditor.history_empty')} />
      ) : (
        <Timeline
          items={snapshots.map((snapshot, index) => ({
            icon: <ClockCircleOutlined className="gaf-text-md" />,
            content: (
              <div className="gaf-flex-between gaf-gap-md" style={{ alignItems: 'flex-start' }}>
                <div className="gaf-flex-1">
                  <Space orientation="vertical" size={2}>
                    <div>
                      <Tag color="blue">v{snapshot.version}</Tag>
                      {index === 0 && <Tag color="green">{t('pipelineEditor.history_latest')}</Tag>}
                    </div>
                    <Paragraph className="gaf-m-0 gaf-text-13" ellipsis={{ rows: 2 }}>
                      {snapshot.change_summary || t('pipelineEditor.history_no_comment')}
                    </Paragraph>
                    <Text type="secondary" className="gaf-text-xs">
                      {new Date(snapshot.created_at).toLocaleString(getLocale())}
                    </Text>
                  </Space>
                </div>
                <Space orientation="vertical" size={4}>
                  <Tooltip title={t('pipelineEditor.history_tooltip_compare')}>
                    <Button size="small" icon={<DiffOutlined />} onClick={handleOpenDiff}>
                      {t('pipelineEditor.history_compare')}
                    </Button>
                  </Tooltip>
                  {index !== 0 && (
                    <Tooltip title={t('pipelineEditor.history_tooltip_rollback')}>
                      <Button size="small" icon={<RollbackOutlined />} onClick={() => onRollback(snapshot.version)}>
                        {t('pipelineEditor.history_rollback')}
                      </Button>
                    </Tooltip>
                  )}
                </Space>
              </div>
            ),
          }))}
        />
      )}

      {/* Version Diff Comparison Modal */}
      <Modal
        title={t('pipelineEditor.history_modal_title')}
        open={diffModalOpen}
        onCancel={() => setDiffModalOpen(false)}
        width={1200}
        footer={[
          <Button key="close" onClick={() => setDiffModalOpen(false)}>
            {t('pipelineEditor.history_btn_close')}
          </Button>,
          <Button
            key="compare"
            type="primary"
            icon={<DiffOutlined />}
            onClick={handleCompare}
            disabled={compareLeftVersion === undefined || compareRightVersion === undefined}
          >
            {t('pipelineEditor.history_btn_start_compare')}
          </Button>,
        ]}
      >
        <div className="gaf-mb-lg">
          <Space orientation="vertical" className="gaf-w-full" size={12}>
            <div className="gaf-flex gaf-gap-lg">
              <div className="gaf-flex-1">
                <Text strong className="gaf-mb-xs gaf-display-block">
                  {t('pipelineEditor.history_left_label')}
                </Text>
                <Select
                  className="gaf-w-full"
                  placeholder={t('pipelineEditor.history_placeholder_left')}
                  options={versionOptions}
                  value={compareLeftVersion}
                  onChange={(v) => setCompareLeftVersion(v)}
                  allowClear
                />
              </div>
              <div className="gaf-flex-1">
                <Text strong className="gaf-mb-xs gaf-display-block">
                  {t('pipelineEditor.history_right_label')}
                </Text>
                <Select
                  className="gaf-w-full"
                  placeholder={t('pipelineEditor.history_placeholder_right')}
                  options={versionOptions}
                  value={compareRightVersion}
                  onChange={(v) => setCompareRightVersion(v)}
                  allowClear
                />
              </div>
            </div>
          </Space>
        </div>

        {fetchingDiff && (
          <div className="gaf-text-center" style={{ padding: 48 }}>
            <Spin description={t('pipelineEditor.history_fetching_diff')} />
          </div>
        )}

        {!fetchingDiff && leftSnapshot && rightSnapshot && diffLines.length > 0 && (
          <>
            <div className="gaf-flex gaf-gap-md gaf-mb-md">
              <Tag color="green">{t('pipelineEditor.history_added', { count: diffStats.added })}</Tag>
              <Tag color="red">{t('pipelineEditor.history_removed', { count: diffStats.removed })}</Tag>
              <Tag color="orange">{t('pipelineEditor.history_modified', { count: diffStats.modified })}</Tag>
              <Text type="secondary" className="gaf-text-xs">
                {t('pipelineEditor.history_compare_v', { left: leftSnapshot.version, right: rightSnapshot.version })}
              </Text>
            </div>
            <div
              className="gaf-flex gaf-overflow-hidden gaf-radius-md"
              style={{
                gap: 1,
                border: `1px solid ${token.colorBorder}`,
              }}
            >
              <div
                className="gaf-flex-1 gaf-overflow-auto"
                style={{ maxHeight: 500, borderRight: `1px solid ${token.colorBorder}` }}
              >
                <div
                  className="gaf-py-sm gaf-px-md"
                  style={{
                    background: token.colorBgLayout,
                    borderBottom: `1px solid ${token.colorBorder}`,
                    position: 'sticky',
                    top: 0,
                    zIndex: 1,
                  }}
                >
                  <Text strong className="gaf-text-13">
                    {t('pipelineEditor.history_left_version', { version: leftSnapshot.version })}
                  </Text>
                </div>
                {diffLines.map((line, idx) => (
                  <div key={`left-${idx}-${line.status}`}>
                    <DiffLineView
                      line={
                        line.status === 'added'
                          ? { ...line, status: 'unchanged', oldValue: '', newValue: line.oldValue }
                          : line
                      }
                    />
                  </div>
                ))}
              </div>
              <div className="gaf-flex-1 gaf-overflow-auto" style={{ maxHeight: 500 }}>
                <div
                  className="gaf-py-sm gaf-px-md"
                  style={{
                    background: token.colorBgLayout,
                    borderBottom: `1px solid ${token.colorBorder}`,
                    position: 'sticky',
                    top: 0,
                    zIndex: 1,
                  }}
                >
                  <Text strong className="gaf-text-13">
                    {t('pipelineEditor.history_right_version', { version: rightSnapshot.version })}
                  </Text>
                </div>
                {diffLines.map((line, idx) => (
                  <div key={`right-${idx}-${line.status}`}>
                    <DiffLineView
                      line={
                        line.status === 'removed'
                          ? { ...line, status: 'unchanged', newValue: '', oldValue: line.newValue }
                          : line
                      }
                    />
                  </div>
                ))}
              </div>
            </div>
          </>
        )}

        {!fetchingDiff && leftSnapshot && rightSnapshot && diffLines.length === 0 && (
          <Empty description={t('pipelineEditor.history_identical')} />
        )}

        {!fetchingDiff && !leftSnapshot && (compareLeftVersion !== undefined || compareRightVersion !== undefined) && (
          <Empty description={t('pipelineEditor.history_fetch_failed')} />
        )}
      </Modal>
    </div>
  );
}

export default PipelineVersionHistory;
