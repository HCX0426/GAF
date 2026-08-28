/**
 * batch import accounts Modal
 * step 1: select import method (CSV upload / TXT paste )
 * step 2: preview parse result, confirm after batch create
 */
import { useState } from 'react';
import { Modal, Steps, Upload, Input, Button, Table, Alert, Space, Tag, App, theme } from 'antd';
import { InboxOutlined } from '@ant-design/icons';
import type { UploadProps } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { batchImportAccounts } from '@/api/accounts';
import { useTranslation } from '@/i18n';

const { Dragger } = Upload;
const { TextArea } = Input;

interface AccountBatchImportProps {
  open: boolean;
  onClose: () => void;
  onComplete: () => void;
}

/** parse after account row */
interface ParsedRow {
  key: string;
  game_name: string;
  username: string;
  password: string;
  server_region: string;
  login_method: string;
  isDuplicate: boolean;
}

/** import summary */
interface ImportSummary {
  total: number;
  created: number;
  skipped: number;
  errors: unknown[];
}

/**
 * batch import accounts component
 * supports CSV file upload and TXT text paste two types method
 */
export function AccountBatchImport({ open, onClose, onComplete }: AccountBatchImportProps) {
  const { message } = App.useApp();
  const { token } = theme.useToken();
  const t = useTranslation();
  const [step, setStep] = useState(0);
  const [importMode, setImportMode] = useState<'csv' | 'txt'>('csv');
  const [rawText, setRawText] = useState('');
  const [parsedRows, setParsedRows] = useState<ParsedRow[]>([]);
  const [summary, setSummary] = useState<ImportSummary | null>(null);
  const [submitting, setSubmitting] = useState(false);

  /**
   * parse CSV text is row array
   */
  const parseCSV = (text: string): Omit<ParsedRow, 'key' | 'isDuplicate'>[] => {
    const lines = text.trim().split(/\r?\n/);
    return lines
      .slice(1)
      .filter(Boolean)
      .map((line) => {
        const cols = line.split(',').map((c) => c.trim().replace(/^"|"$/g, ''));
        return {
          game_name: cols[0] || '',
          username: cols[1] || '',
          password: cols[2] || '',
          server_region: cols[3] || '',
          login_method: cols[4] || 'password',
        };
      });
  };

  /**
   * parse TXT text is row array
   * format: game name, user name, password, server region, login method ( every row one record )
   */
  const parseTXT = (text: string): Omit<ParsedRow, 'key' | 'isDuplicate'>[] => {
    const lines = text.trim().split(/\r?\n/);
    return lines.filter(Boolean).map((line) => {
      const parts = line.split(',');
      return {
        game_name: parts[0]?.trim() || '',
        username: parts[1]?.trim() || '',
        password: parts[2]?.trim() || '',
        server_region: parts[3]?.trim() || '',
        login_method: parts[4]?.trim() || 'password',
      };
    });
  };

  /**
   * detect duplicate row and mark
   */
  const markDuplicates = (rows: Omit<ParsedRow, 'key' | 'isDuplicate'>[]): ParsedRow[] => {
    const seen = new Set<string>();
    return rows.map((row, index) => {
      const dedupeKey = `${row.game_name}|${row.username}`;
      const isDuplicate = seen.has(dedupeKey);
      seen.add(dedupeKey);
      return { ...row, key: String(index), isDuplicate };
    });
  };

  /**
   * handle CSV file upload
   */
  const handleCSVUpload: UploadProps['beforeUpload'] = (file) => {
    const reader = new FileReader();
    reader.onload = (e) => {
      const text = e.target?.result as string;
      const rows = parseCSV(text);
      setParsedRows(markDuplicates(rows));
      setStep(1);
    };
    reader.readAsText(file, 'UTF-8');
    return false;
  };

  /**
   * handle TXT parse
   */
  const handleTxtParse = () => {
    if (!rawText.trim()) {
      message.warning(t('accounts.paste_data'));
      return;
    }
    const rows = parseTXT(rawText);
    setParsedRows(markDuplicates(rows));
    setStep(1);
  };

  /**
   * submit import
   */
  const handleSubmit = async () => {
    if (parsedRows.length === 0) {
      message.warning(t('accounts.no_data'));
      return;
    }
    setSubmitting(true);
    try {
      const accounts = parsedRows.map((row) => ({
        game_name: row.game_name,
        username: row.username,
        password: row.password,
        server_region: row.server_region,
        login_method: row.login_method,
      }));
      const result = await batchImportAccounts({ accounts });
      setSummary(result);
      setStep(2);
      if (result.created > 0) {
        message.success(t('accounts.import_success', { count: result.created }));
      }
    } catch {
      message.error(t('accounts.batch_import_failed'));
    } finally {
      setSubmitting(false);
    }
  };

  /**
   * reset status
   */
  const handleReset = () => {
    setStep(0);
    setImportMode('csv');
    setRawText('');
    setParsedRows([]);
    setSummary(null);
    setSubmitting(false);
  };

  /**
   * preview table column
   */
  const previewColumns: ColumnsType<ParsedRow> = [
    { title: t('accounts.col_game_name_short'), dataIndex: 'game_name', key: 'game_name', width: 100 },
    { title: t('accounts.col_username'), dataIndex: 'username', key: 'username', width: 120 },
    { title: t('accounts.password'), dataIndex: 'password', key: 'password', width: 100, render: () => '********' },
    { title: t('accounts.col_server_region'), dataIndex: 'server_region', key: 'server_region', width: 100 },
    {
      title: t('accounts.col_login_method'),
      dataIndex: 'login_method',
      key: 'login_method',
      width: 100,
      render: (v: string) => <Tag>{v}</Tag>,
    },
  ];

  const duplicateCount = parsedRows.filter((r) => r.isDuplicate).length;

  return (
    <Modal
      title={t('accounts.batch_import_title')}
      open={open}
      onCancel={() => {
        handleReset();
        onClose();
      }}
      width={800}
      footer={
        step === 0 ? (
          <Button
            onClick={() => {
              handleReset();
              onClose();
            }}
          >
            {t('accounts.cancel')}
          </Button>
        ) : step === 1 ? (
          <Space>
            <Button onClick={() => setStep(0)}>{t('accounts.prev_step')}</Button>
            <Button type="primary" onClick={handleSubmit} loading={submitting}>
              {t('accounts.confirm_import')}
            </Button>
          </Space>
        ) : (
          <Space>
            <Button
              onClick={() => {
                handleReset();
                onClose();
                onComplete();
              }}
            >
              {t('accounts.close')}
            </Button>
            <Button type="primary" onClick={handleReset}>
              {t('accounts.continue_import')}
            </Button>
          </Space>
        )
      }
    >
      <Steps
        current={step}
        size="small"
        className="gaf-mb-xl"
        items={[
          { title: t('accounts.step_select_method') },
          { title: t('accounts.step_preview') },
          { title: t('accounts.step_result') },
        ]}
      />

      {/* 步骤 0：选择导入方式 */}
      {step === 0 && (
        <div>
          <Space className="gaf-mb-lg">
            <Button type={importMode === 'csv' ? 'primary' : 'default'} onClick={() => setImportMode('csv')}>
              {t('accounts.csv_upload')}
            </Button>
            <Button type={importMode === 'txt' ? 'primary' : 'default'} onClick={() => setImportMode('txt')}>
              {t('accounts.txt_paste')}
            </Button>
          </Space>

          {importMode === 'csv' && (
            <Dragger name="file" accept=".csv" beforeUpload={handleCSVUpload} showUploadList={false}>
              <p className="ant-upload-drag-icon">
                <InboxOutlined />
              </p>
              <p className="ant-upload-text">{t('accounts.csv_upload_hint')}</p>
              <p className="ant-upload-hint">{t('accounts.csv_format_hint')}</p>
            </Dragger>
          )}

          {importMode === 'txt' && (
            <div>
              <TextArea
                value={rawText}
                onChange={(e) => setRawText(e.target.value)}
                rows={10}
                placeholder={t('accounts.txt_placeholder')}
              />
              <Button type="primary" onClick={handleTxtParse} className="gaf-mt-md">
                {t('accounts.parse_data')}
              </Button>
            </div>
          )}
        </div>
      )}

      {/* 步骤 1：数据预览 */}
      {step === 1 && (
        <div>
          {duplicateCount > 0 && (
            <Alert
              type="warning"
              title={t('accounts.duplicate_warning', { count: duplicateCount })}
              showIcon
              className="gaf-mb-md"
            />
          )}

          <Table
            columns={previewColumns}
            dataSource={parsedRows}
            pagination={false}
            size="small"
            scroll={{ y: 360 }}
            rowClassName={(record) => (record.isDuplicate ? 'ant-table-row-warning' : '')}
            onRow={(record) => ({
              style: record.isDuplicate ? { background: token.colorWarningBg } : {},
            })}
            summary={() => (
              <Table.Summary.Row>
                <Table.Summary.Cell index={0}>
                  {t('accounts.preview_summary', { total: parsedRows.length, duplicate: duplicateCount })}
                </Table.Summary.Cell>
              </Table.Summary.Row>
            )}
          />
        </div>
      )}

      {/* 步骤 2：导入结果 */}
      {step === 2 && summary && (
        <div className="gaf-text-center" style={{ padding: '24px 0' }}>
          <Space orientation="vertical" size="large">
            <div>
              <Tag color="blue">{t('accounts.import_total', { count: summary.total })}</Tag>
              <Tag color="success">{t('accounts.import_success_count', { count: summary.created })}</Tag>
              <Tag color="warning">{t('accounts.import_skipped', { count: summary.skipped })}</Tag>
              <Tag color="error">{t('accounts.import_failed', { count: summary.errors?.length ?? 0 })}</Tag>
            </div>
          </Space>
        </div>
      )}
    </Modal>
  );
}

export default AccountBatchImport;
