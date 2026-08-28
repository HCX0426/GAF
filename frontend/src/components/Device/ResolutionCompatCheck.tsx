/**
 * resolution compatibility check group?
 * auto check device resolution and resource pack resolution compatible?
 */
import { useEffect, useState } from 'react';
import { Alert, Spin, Button, App } from 'antd';
import { checkCompatibility } from '@/api/devices';
import type { CompatibilityCheckResult } from '@/types/models';
import { useTranslation } from '@/i18n';

/** ResolutionCompatCheck component property?*/
interface ResolutionCompatCheckProps {
  deviceId: number;
  resourcePackId: string | null;
}

/**
 * resolution compatibility check panel
 *?resourcePackId not empty when auto call compatible?API, show different status prompts based on result
 */
export function ResolutionCompatCheck({ deviceId, resourcePackId }: ResolutionCompatCheckProps) {
  const { message } = App.useApp();
  const t = useTranslation();
  const [result, setResult] = useState<CompatibilityCheckResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [visible, setVisible] = useState(true);

  useEffect(() => {
    if (!resourcePackId) {
      setResult(null);
      return;
    }

    setLoading(true);
    setVisible(true);

    checkCompatibility(deviceId, Number(resourcePackId))
      .then((res) => {
        setResult(res);
        if (res.is_compatible) {
          const timer = setTimeout(() => setVisible(false), 3000);
          return () => clearTimeout(timer);
        }
      })
      .catch(() => {
        message.error(t('devices.compat_check_failed'));
      })
      .finally(() => {
        setLoading(false);
      });
  }, [deviceId, resourcePackId]);

  /** notify parent to scale by suggestion */
  const handleScaleSuggestion = () => {
    if (!result) return;
    message.info(t('devices.scale_suggestion', { percent: (result.scale_suggestion * 100).toFixed(0) }));
  };

  if (loading) {
    return <Spin size="small" className="gaf-p-sm" style={{ display: 'block' }} />;
  }

  if (!result || !visible) {
    return null;
  }

  /** judge is no approximate compatible ( width high ratio difference in 3%~5% between?*/
  const isApproximate =
    !result.is_compatible &&
    result.width_ratio >= 0.95 &&
    result.width_ratio <= 1.05 &&
    result.height_ratio >= 0.95 &&
    result.height_ratio <= 1.05;

  if (result.is_compatible) {
    return (
      <Alert
        type="success"
        title="分辨率兼容"
        description={result.message || '设备分辨率与资源包分辨率完全兼容'}
        showIcon
        closable
        onClose={() => setVisible(false)}
      />
    );
  }

  if (isApproximate) {
    return (
      <Alert
        type="info"
        title="分辨率基本兼容"
        description={`设备分辨率：${result.device_resolution.width}×${result.device_resolution.height} 与资源包分辨率：${result.pack_resolution.width}×${result.pack_resolution.height} 差异较小，基本兼容`}
        showIcon
        closable
        onClose={() => setVisible(false)}
      />
    );
  }

  return (
    <Alert
      type="warning"
      title="分辨率不兼容"
      description={
        <div>
          <p>
            设备分辨率：{result.device_resolution.width}×{result.device_resolution.height}
            <br />
            资源包分辨率：{result.pack_resolution.width}×{result.pack_resolution.height}
          </p>
          <p>建议缩放比例：{(result.scale_suggestion * 100).toFixed(0)}%</p>
        </div>
      }
      showIcon
      closable
      onClose={() => setVisible(false)}
      action={
        <Button size="small" onClick={handleScaleSuggestion}>
          按建议缩�?
        </Button>
      }
    />
  );
}

export default ResolutionCompatCheck;
