/**
 * Device operation panel with Click/Key/Text/Swipe sub-panels
 * Integrates with Phase R10 Click/Input API endpoints
 * Supports coordinate selection from GafCanvasOverlay
 */
import { useState, useCallback, useEffect } from 'react';
import { Tabs, InputNumber, Input, Button, Select, Space, Typography, App, Card, Tag, Upload, Slider } from 'antd';
import {
  AimOutlined,
  ToolOutlined,
  FontSizeOutlined,
  ArrowsAltOutlined,
  HistoryOutlined,
  CheckCircleOutlined,
  CloseCircleOutlined,
  LoadingOutlined,
  PictureOutlined,
  BgColorsOutlined,
  UploadOutlined,
  AppstoreOutlined,
  InfoCircleOutlined,
} from '@ant-design/icons';
import { clickDevice, inputDevice, templateMatchDevice, colorDetectDevice, appDevice, infoDevice } from '@/api/devices';
import type {
  ClickParams,
  InputParams,
  ClickResult,
  InputResult,
  TemplateMatchResult,
  ColorDetectResult,
  AppActionResult,
  DeviceInfoResult,
} from '@/api/devices';
import { useTranslation } from '@/i18n';

function errMsg(e: unknown, fallback = 'Unknown error'): string {
  return e instanceof Error ? e.message : fallback;
}

/** Operation history entry */
export interface OperationRecord {
  id: number;
  timestamp: string;
  type: 'click' | 'key_press' | 'text_input' | 'swipe' | 'scroll' | 'template_match' | 'color_detect' | 'app' | 'info';
  params: Record<string, unknown>;
  success: boolean;
  method?: string;
  error?: string;
  result?: Record<string, unknown>;
}

interface DeviceOperationPanelProps {
  deviceId: number;
  deviceName?: string;
  /** Resolution of the screenshot frame currently displayed to the user. */
  screenshotWidth?: number;
  screenshotHeight?: number;
  /** Callback when user wants to pick coordinates from canvas */
  onRequestCoordinatePick?: (targetField: 'click' | 'swipeStart' | 'swipeEnd') => void;
  /** Pre-fill coordinate from canvas click */
  prefilledCoordinate?: { x: number; y: number } | null;
  onOperationComplete?: (record: OperationRecord) => void;
}

const { TextArea } = Input;
const { Text } = Typography;

/** Generate unique ID for operation records */
let recordIdCounter = 0;
function nextRecordId(): number {
  recordIdCounter += 1;
  return recordIdCounter;
}

/**
 * Device operation panel with 4 sub-tabs:
 * - Click: Coordinate click with button selection
 * - Key: Keyboard key press
 * - Text: Unicode text input
 * - Swipe: Swipe gesture with coordinates
 */
export function DeviceOperationPanel({
  deviceId,
  deviceName,
  screenshotWidth,
  screenshotHeight,
  onRequestCoordinatePick,
  prefilledCoordinate,
  onOperationComplete,
}: DeviceOperationPanelProps) {
  const t = useTranslation();
  // Use App.useApp() to get the context-aware message instance instead of the
  // static `message` from 'antd'. The static form cannot consume ConfigProvider
  // theme and triggers the warning:
  //   "Static function can not consume context like dynamic theme. Please use
  //    'App' component instead."
  // The app root already wraps everything in <AntApp> (see App.tsx), so
  // App.useApp() works in any descendant component.
  const { message } = App.useApp();
  const [activeTab, setActiveTab] = useState('click');
  const [loading, setLoading] = useState(false);
  const [history, setHistory] = useState<OperationRecord[]>([]);

  // Safety timeout: if a request hangs, reset loading after 5s so the spinner
  // does not spin forever and the UI remains usable.
  useEffect(() => {
    if (!loading) return;
    const timer = setTimeout(() => {
      setLoading((prev) => {
        if (prev) {
          message.warning(t('devices.operation_timeout'));
        }
        return false;
      });
    }, 5000);
    return () => clearTimeout(timer);
  }, [loading, t]);

  // Click panel state
  const [clickX, setClickX] = useState<number | null>(null);
  const [clickY, setClickY] = useState<number | null>(null);
  const [clickButton, setClickButton] = useState<'left' | 'right' | 'middle'>('left');

  // Key panel state
  const [keyValue, setKeyValue] = useState('');

  // Text panel state
  const [textInput, setTextInput] = useState('');

  // Swipe panel state
  const [swipeX1, setSwipeX1] = useState<number | null>(null);
  const [swipeY1, setSwipeY1] = useState<number | null>(null);
  const [swipeX2, setSwipeX2] = useState<number | null>(null);
  const [swipeY2, setSwipeY2] = useState<number | null>(null);
  const [swipeDuration, setSwipeDuration] = useState(300);

  // Scroll panel state
  const [scrollX, setScrollX] = useState(500);
  const [scrollY, setScrollY] = useState(300);
  const [scrollDelta, setScrollDelta] = useState(-120);

  // Template match panel state
  const [templateBase64, setTemplateBase64] = useState<string>('');
  const [templateName, setTemplateName] = useState<string>('');
  const [templateThreshold, setTemplateThreshold] = useState(0.5);
  const [templateResult, setTemplateResult] = useState<TemplateMatchResult | null>(null);

  // Color detect panel state
  const [colorLowerH, setColorLowerH] = useState(0);
  const [colorLowerS, setColorLowerS] = useState(100);
  const [colorLowerV, setColorLowerV] = useState(100);
  const [colorUpperH, setColorUpperH] = useState(10);
  const [colorUpperS, setColorUpperS] = useState(255);
  const [colorUpperV, setColorUpperV] = useState(255);
  const [colorMinPixels, setColorMinPixels] = useState(50);
  const [colorResult, setColorResult] = useState<ColorDetectResult | null>(null);

  // App management panel state
  const [appPackage, setAppPackage] = useState('');
  const [appFilter, setAppFilter] = useState('');
  const [appResult, setAppResult] = useState<AppActionResult | null>(null);

  // Device info panel state
  const [infoResult, setInfoResult] = useState<DeviceInfoResult | null>(null);

  /** Handle prefilled coordinate from canvas click */
  useEffect(() => {
    if (prefilledCoordinate) {
      if (activeTab === 'click') {
        setClickX(prefilledCoordinate.x);
        setClickY(prefilledCoordinate.y);
      } else if (activeTab === 'swipe') {
        if (swipeX1 === null) {
          setSwipeX1(prefilledCoordinate.x);
          setSwipeY1(prefilledCoordinate.y);
        } else {
          setSwipeX2(prefilledCoordinate.x);
          setSwipeY2(prefilledCoordinate.y);
        }
      }
    }
  }, [prefilledCoordinate, activeTab]);

  /** Add record to history and notify parent */
  const addHistoryRecord = useCallback(
    (record: OperationRecord) => {
      setHistory((prev) => [record, ...prev].slice(0, 50));
      onOperationComplete?.(record);
    },
    [onOperationComplete],
  );

  /** Execute click operation */
  const handleExecuteClick = useCallback(async () => {
    if (clickX === null || clickY === null) {
      message.warning(t('devices.click_coord_required'));
      return;
    }
    setLoading(true);
    try {
      const params: ClickParams = {
        x: clickX,
        y: clickY,
        button: clickButton,
        screenshot_width: screenshotWidth,
        screenshot_height: screenshotHeight,
      };
      const result: ClickResult = await clickDevice(deviceId, params);
      const record: OperationRecord = {
        id: nextRecordId(),
        timestamp: new Date().toISOString(),
        type: 'click',
        params: { ...params },
        success: result.success,
        method: result.method,
        error: result.error,
      };
      addHistoryRecord(record);
      if (result.success) {
        message.success(t('devices.click_success', { method: result.method }));
      } else {
        message.error(t('devices.click_failed', { error: result.error }));
      }
    } catch (err: unknown) {
      message.error(t('devices.click_request_failed', { message: errMsg(err) }));
      addHistoryRecord({
        id: nextRecordId(),
        timestamp: new Date().toISOString(),
        type: 'click',
        params: { x: clickX, y: clickY, button: clickButton },
        success: false,
        error: errMsg(err),
      });
    } finally {
      setLoading(false);
    }
  }, [deviceId, clickX, clickY, clickButton, addHistoryRecord]);

  /** Execute key press operation */
  const handleExecuteKey = useCallback(async () => {
    if (!keyValue.trim()) {
      message.warning(t('devices.key_required'));
      return;
    }
    setLoading(true);
    try {
      const params: InputParams = {
        action: 'key_press',
        key: keyValue.trim(),
      };
      const result: InputResult = await inputDevice(deviceId, params);
      const record: OperationRecord = {
        id: nextRecordId(),
        timestamp: new Date().toISOString(),
        type: 'key_press',
        params: { key: keyValue.trim() },
        success: result.success,
        method: result.method,
        error: result.error,
      };
      addHistoryRecord(record);
      if (result.success) {
        message.success(t('devices.key_success', { method: result.method }));
      } else {
        message.error(t('devices.key_failed', { error: result.error }));
      }
    } catch (err: unknown) {
      message.error(t('devices.key_request_failed', { message: errMsg(err) }));
      addHistoryRecord({
        id: nextRecordId(),
        timestamp: new Date().toISOString(),
        type: 'key_press',
        params: { key: keyValue.trim() },
        success: false,
        error: errMsg(err),
      });
    } finally {
      setLoading(false);
    }
  }, [deviceId, keyValue, addHistoryRecord]);

  /** Execute text input operation */
  const handleExecuteText = useCallback(async () => {
    if (!textInput.trim()) {
      message.warning(t('devices.text_required'));
      return;
    }
    setLoading(true);
    try {
      const params: InputParams = {
        action: 'text_input',
        text: textInput,
      };
      const result: InputResult = await inputDevice(deviceId, params);
      const record: OperationRecord = {
        id: nextRecordId(),
        timestamp: new Date().toISOString(),
        type: 'text_input',
        params: { text: textInput },
        success: result.success,
        method: result.method,
        error: result.error,
      };
      addHistoryRecord(record);
      if (result.success) {
        message.success(t('devices.text_success', { method: result.method }));
      } else {
        message.error(t('devices.text_failed', { error: result.error }));
      }
    } catch (err: unknown) {
      message.error(t('devices.text_request_failed', { message: errMsg(err) }));
      addHistoryRecord({
        id: nextRecordId(),
        timestamp: new Date().toISOString(),
        type: 'text_input',
        params: { text: textInput },
        success: false,
        error: errMsg(err),
      });
    } finally {
      setLoading(false);
    }
  }, [deviceId, textInput, addHistoryRecord]);

  /** Execute swipe operation */
  const handleExecuteSwipe = useCallback(async () => {
    if (swipeX1 === null || swipeY1 === null || swipeX2 === null || swipeY2 === null) {
      message.warning(t('devices.swipe_coord_required'));
      return;
    }
    setLoading(true);
    try {
      const params: InputParams = {
        action: 'swipe',
        x1: swipeX1,
        y1: swipeY1,
        x2: swipeX2,
        y2: swipeY2,
        duration_ms: swipeDuration,
        screenshot_width: screenshotWidth,
        screenshot_height: screenshotHeight,
      };
      const result: InputResult = await inputDevice(deviceId, params);
      const record: OperationRecord = {
        id: nextRecordId(),
        timestamp: new Date().toISOString(),
        type: 'swipe',
        params: { x1: swipeX1, y1: swipeY1, x2: swipeX2, y2: swipeY2, duration_ms: swipeDuration },
        success: result.success,
        method: result.method,
        error: result.error,
      };
      addHistoryRecord(record);
      if (result.success) {
        message.success(t('devices.swipe_success', { method: result.method }));
      } else {
        message.error(t('devices.swipe_failed', { error: result.error }));
      }
    } catch (err: unknown) {
      message.error(t('devices.swipe_request_failed', { message: errMsg(err) }));
      addHistoryRecord({
        id: nextRecordId(),
        timestamp: new Date().toISOString(),
        type: 'swipe',
        params: { x1: swipeX1, y1: swipeY1, x2: swipeX2, y2: swipeY2, duration_ms: swipeDuration },
        success: false,
        error: errMsg(err),
      });
    } finally {
      setLoading(false);
    }
  }, [deviceId, swipeX1, swipeY1, swipeX2, swipeY2, swipeDuration, addHistoryRecord]);

  /** Execute scroll operation */
  const handleExecuteScroll = useCallback(async () => {
    setLoading(true);
    try {
      const params: InputParams = {
        action: 'scroll',
        x: scrollX,
        y: scrollY,
        delta: scrollDelta,
        screenshot_width: screenshotWidth,
        screenshot_height: screenshotHeight,
      };
      const result: InputResult = await inputDevice(deviceId, params);
      const record: OperationRecord = {
        id: nextRecordId(),
        timestamp: new Date().toISOString(),
        type: 'scroll',
        params: { x: scrollX, y: scrollY, delta: scrollDelta },
        success: result.success,
        method: result.method,
        error: result.error,
      };
      addHistoryRecord(record);
      if (result.success) {
        const direction = scrollDelta > 0 ? t('devices.scroll_direction_up') : t('devices.scroll_direction_down');
        message.success(t('devices.scroll_success', { direction, method: result.method }));
      } else {
        message.error(t('devices.scroll_failed', { error: result.error }));
      }
    } catch (err: unknown) {
      message.error(t('devices.scroll_request_failed', { message: errMsg(err) }));
      addHistoryRecord({
        id: nextRecordId(),
        timestamp: new Date().toISOString(),
        type: 'scroll',
        params: { x: scrollX, y: scrollY, delta: scrollDelta },
        success: false,
        error: errMsg(err),
      });
    } finally {
      setLoading(false);
    }
  }, [deviceId, scrollX, scrollY, scrollDelta, addHistoryRecord]);

  /** Handle template file upload - convert to base64 */
  const handleTemplateUpload = useCallback((file: File) => {
    const reader = new FileReader();
    reader.onload = () => {
      const result = reader.result as string;
      // Strip data URL prefix: data:image/png;base64,xxxx
      const base64 = result.includes(',') ? result.split(',')[1] : result;
      setTemplateBase64(base64);
      setTemplateName(file.name);
      setTemplateResult(null);
      message.success(t('devices.template_loaded', { name: file.name }));
    };
    reader.readAsDataURL(file);
    return false; // Prevent auto upload
  }, []);

  /** Execute template match */
  const handleExecuteTemplateMatch = useCallback(async () => {
    if (!templateBase64) {
      message.warning(t('devices.template_required'));
      return;
    }
    setLoading(true);
    try {
      const result = await templateMatchDevice(deviceId, {
        template_base64: templateBase64,
        threshold: templateThreshold,
      });
      setTemplateResult(result);
      const record: OperationRecord = {
        id: nextRecordId(),
        timestamp: new Date().toISOString(),
        type: 'template_match',
        params: { template_name: templateName, threshold: templateThreshold },
        success: result.success && result.matched,
        method: `score=${result.score.toFixed(4)}`,
        error: result.error,
        result: result as unknown as Record<string, unknown>,
      };
      addHistoryRecord(record);
      if (result.success && result.matched) {
        message.success(
          t('devices.template_match_success', {
            score: result.score.toFixed(4),
            x: result.center_x,
            y: result.center_y,
          }),
        );
      } else if (result.success && !result.matched) {
        message.warning(
          t('devices.template_below_threshold', { score: result.score.toFixed(4), threshold: templateThreshold }),
        );
      } else {
        message.error(t('devices.template_match_failed', { error: result.error }));
      }
    } catch (err: unknown) {
      message.error(t('devices.template_request_failed', { message: errMsg(err) }));
      addHistoryRecord({
        id: nextRecordId(),
        timestamp: new Date().toISOString(),
        type: 'template_match',
        params: { template_name: templateName, threshold: templateThreshold },
        success: false,
        error: errMsg(err),
      });
    } finally {
      setLoading(false);
    }
  }, [deviceId, templateBase64, templateName, templateThreshold, addHistoryRecord]);

  /** Click on template match result center */
  const handleClickMatchedCenter = useCallback(async () => {
    if (!templateResult || !templateResult.matched) {
      message.warning(t('devices.no_match_to_click'));
      return;
    }
    setLoading(true);
    try {
      // Prefer client-scaled coordinates (DPI-aware) to avoid click offset on HiDPI displays
      const clickX = templateResult.center_x_client ?? templateResult.center_x;
      const clickY = templateResult.center_y_client ?? templateResult.center_y;
      const result = await clickDevice(deviceId, {
        x: clickX,
        y: clickY,
      });
      if (result.success) {
        message.success(t('devices.match_position_clicked', { x: clickX, y: clickY }));
      } else {
        message.error(t('devices.click_failed', { error: result.error }));
      }
    } catch (err: unknown) {
      message.error(t('devices.click_request_failed', { message: errMsg(err) }));
    } finally {
      setLoading(false);
    }
  }, [deviceId, templateResult]);

  /** Execute color detect */
  const handleExecuteColorDetect = useCallback(async () => {
    setLoading(true);
    try {
      const result = await colorDetectDevice(deviceId, {
        lower_hsv: [colorLowerH, colorLowerS, colorLowerV],
        upper_hsv: [colorUpperH, colorUpperS, colorUpperV],
        min_pixels: colorMinPixels,
      });
      setColorResult(result);
      const record: OperationRecord = {
        id: nextRecordId(),
        timestamp: new Date().toISOString(),
        type: 'color_detect',
        params: {
          lower_hsv: [colorLowerH, colorLowerS, colorLowerV],
          upper_hsv: [colorUpperH, colorUpperS, colorUpperV],
          min_pixels: colorMinPixels,
        },
        success: result.success && result.matched,
        method: `pixels=${result.pixel_count}`,
        error: result.error,
        result: result as unknown as Record<string, unknown>,
      };
      addHistoryRecord(record);
      if (result.success && result.matched) {
        message.success(
          t('devices.color_detected', { pixels: result.pixel_count, x: result.centroid[0], y: result.centroid[1] }),
        );
      } else if (result.success && !result.matched) {
        message.warning(
          t('devices.color_insufficient_pixels', { pixels: result.pixel_count, threshold: colorMinPixels }),
        );
      } else {
        message.error(t('devices.color_detect_failed', { error: result.error }));
      }
    } catch (err: unknown) {
      message.error(t('devices.color_request_failed', { message: errMsg(err) }));
      addHistoryRecord({
        id: nextRecordId(),
        timestamp: new Date().toISOString(),
        type: 'color_detect',
        params: {
          lower_hsv: [colorLowerH, colorLowerS, colorLowerV],
          upper_hsv: [colorUpperH, colorUpperS, colorUpperV],
          min_pixels: colorMinPixels,
        },
        success: false,
        error: errMsg(err),
      });
    } finally {
      setLoading(false);
    }
  }, [
    deviceId,
    colorLowerH,
    colorLowerS,
    colorLowerV,
    colorUpperH,
    colorUpperS,
    colorUpperV,
    colorMinPixels,
    addHistoryRecord,
  ]);

  /** Click on color detect centroid */
  const handleClickColorCentroid = useCallback(async () => {
    if (!colorResult || !colorResult.matched) {
      message.warning(t('devices.no_color_to_click'));
      return;
    }
    setLoading(true);
    try {
      const result = await clickDevice(deviceId, {
        x: colorResult.centroid[0],
        y: colorResult.centroid[1],
      });
      if (result.success) {
        message.success(
          t('devices.color_centroid_clicked', { x: colorResult.centroid[0], y: colorResult.centroid[1] }),
        );
      } else {
        message.error(t('devices.click_failed', { error: result.error }));
      }
    } catch (err: unknown) {
      message.error(t('devices.click_request_failed', { message: errMsg(err) }));
    } finally {
      setLoading(false);
    }
  }, [deviceId, colorResult]);

  /** Execute app management action (launch/force_stop/list/uninstall) */
  const handleAppAction = useCallback(
    async (action: 'launch' | 'force_stop' | 'list' | 'uninstall') => {
      if ((action === 'launch' || action === 'force_stop' || action === 'uninstall') && !appPackage.trim()) {
        message.warning(t('devices.app_package_required'));
        return;
      }
      setLoading(true);
      try {
        const result = await appDevice(deviceId, {
          action,
          package: appPackage.trim() || undefined,
          filter: appFilter.trim() || undefined,
        });
        setAppResult(result);
        const record: OperationRecord = {
          id: nextRecordId(),
          timestamp: new Date().toISOString(),
          type: 'app',
          params: { action, package: appPackage, filter: appFilter },
          success: result.success,
          method: action,
          error: result.error,
          result: result as unknown as Record<string, unknown>,
        };
        addHistoryRecord(record);
        if (result.success) {
          const count = result.data?.count;
          if (action === 'list' && count !== undefined) {
            message.success(t('devices.app_list_success', { count }));
          } else {
            message.success(t('devices.app_action_success', { action }));
          }
        } else {
          message.error(t('devices.app_action_failed', { action, error: result.error }));
        }
      } catch (err: unknown) {
        const msg = errMsg(err, t('devices.op_panel_unknown_error'));
        message.error(t('devices.app_request_failed', { action, message: msg }));
        addHistoryRecord({
          id: nextRecordId(),
          timestamp: new Date().toISOString(),
          type: 'app',
          params: { action, package: appPackage },
          success: false,
          error: msg,
        });
      } finally {
        setLoading(false);
      }
    },
    [deviceId, appPackage, appFilter, addHistoryRecord, t],
  );

  /** Query device info (battery/screen/system) */
  const handleQueryInfo = useCallback(async () => {
    setLoading(true);
    try {
      const result = await infoDevice(deviceId, { query: 'all' });
      setInfoResult(result);
      const record: OperationRecord = {
        id: nextRecordId(),
        timestamp: new Date().toISOString(),
        type: 'info',
        params: { query: 'all' },
        success: result.success,
        method: 'info',
        error: result.error,
        result: result as unknown as Record<string, unknown>,
      };
      addHistoryRecord(record);
      if (result.success) {
        message.success(t('devices.device_info_success'));
      } else {
        message.error(t('devices.device_info_failed', { error: result.error }));
      }
    } catch (err: unknown) {
      const msg = errMsg(err, t('devices.op_panel_unknown_error'));
      message.error(t('devices.device_info_request_failed', { message: msg }));
      addHistoryRecord({
        id: nextRecordId(),
        timestamp: new Date().toISOString(),
        type: 'info',
        params: { query: 'all' },
        success: false,
        error: msg,
      });
    } finally {
      setLoading(false);
    }
  }, [deviceId, addHistoryRecord, t]);

  /** Click panel content */
  const clickPanel = (
    <div className="gaf-w-full gaf-flex-col gaf-gap-md">
      <div className="gaf-form-row">
        <label className="gaf-form-label">{t('devices.op_panel_label_coord')}</label>
        <div className="gaf-form-controls">
          <InputNumber value={clickX} onChange={(v) => setClickX(v)} placeholder="X" min={0} className="gaf-w-xs" />
          <InputNumber value={clickY} onChange={(v) => setClickY(v)} placeholder="Y" min={0} className="gaf-w-xs" />
          {onRequestCoordinatePick && (
            <Button icon={<AimOutlined />} onClick={() => onRequestCoordinatePick('click')} size="small">
              {t('devices.op_panel_btn_pick_from_screenshot')}
            </Button>
          )}
        </div>
      </div>
      <div className="gaf-form-row">
        <label className="gaf-form-label">{t('devices.op_panel_label_button')}</label>
        <div className="gaf-form-controls">
          <Select
            value={clickButton}
            onChange={setClickButton}
            options={[
              { value: 'left', label: t('devices.op_panel_button_left') },
              { value: 'right', label: t('devices.op_panel_button_right') },
              { value: 'middle', label: t('devices.op_panel_button_middle') },
            ]}
            className="gaf-w-sm"
          />
        </div>
      </div>
      <Button type="primary" icon={<AimOutlined />} onClick={handleExecuteClick} loading={loading} block>
        {t('devices.op_panel_btn_execute_click')}
      </Button>
    </div>
  );

  /** Key press panel content */
  const keyPanel = (
    <div className="gaf-w-full gaf-flex-col gaf-gap-md">
      <div className="gaf-form-row">
        <label className="gaf-form-label">{t('devices.op_panel_label_key')}</label>
        <div className="gaf-form-controls gaf-flex-col" style={{ alignItems: 'flex-start' }}>
          <Input
            value={keyValue}
            onChange={(e) => setKeyValue(e.target.value)}
            placeholder={t('devices.op_panel_key_placeholder')}
            onPressEnter={handleExecuteKey}
            style={{ width: 280 }}
          />
          <Text type="secondary" className="gaf-text-xs">
            {t('devices.op_panel_key_hint')}
          </Text>
        </div>
      </div>
      <Button type="primary" icon={<ToolOutlined />} onClick={handleExecuteKey} loading={loading} block>
        {t('devices.op_panel_btn_execute_key')}
      </Button>
    </div>
  );

  /** Text input panel content */
  const textPanel = (
    <div className="gaf-w-full gaf-flex-col gaf-gap-md">
      <div className="gaf-form-row">
        <label className="gaf-form-label">{t('devices.op_panel_label_text')}</label>
        <div className="gaf-form-controls gaf-flex-col" style={{ alignItems: 'flex-start' }}>
          <TextArea
            value={textInput}
            onChange={(e) => setTextInput(e.target.value)}
            placeholder={t('devices.op_panel_text_placeholder')}
            rows={3}
            style={{ width: '100%', maxWidth: 400 }}
          />
        </div>
      </div>
      <Button type="primary" icon={<FontSizeOutlined />} onClick={handleExecuteText} loading={loading} block>
        {t('devices.op_panel_btn_execute_text')}
      </Button>
    </div>
  );

  /** Swipe panel content */
  const swipePanel = (
    <div className="gaf-w-full gaf-flex-col gaf-gap-md">
      <div className="gaf-form-row">
        <label className="gaf-form-label">{t('devices.op_panel_label_swipe_start')}</label>
        <div className="gaf-form-controls">
          <InputNumber value={swipeX1} onChange={(v) => setSwipeX1(v)} placeholder="X1" min={0} className="gaf-w-xs" />
          <InputNumber value={swipeY1} onChange={(v) => setSwipeY1(v)} placeholder="Y1" min={0} className="gaf-w-xs" />
          {onRequestCoordinatePick && (
            <Button icon={<AimOutlined />} onClick={() => onRequestCoordinatePick('swipeStart')} size="small">
              {t('devices.op_panel_btn_pick_start')}
            </Button>
          )}
        </div>
      </div>
      <div className="gaf-form-row">
        <label className="gaf-form-label">{t('devices.op_panel_label_swipe_end')}</label>
        <div className="gaf-form-controls">
          <InputNumber value={swipeX2} onChange={(v) => setSwipeX2(v)} placeholder="X2" min={0} className="gaf-w-xs" />
          <InputNumber value={swipeY2} onChange={(v) => setSwipeY2(v)} placeholder="Y2" min={0} className="gaf-w-xs" />
          {onRequestCoordinatePick && (
            <Button icon={<AimOutlined />} onClick={() => onRequestCoordinatePick('swipeEnd')} size="small">
              {t('devices.op_panel_btn_pick_end')}
            </Button>
          )}
        </div>
      </div>
      <div className="gaf-form-row">
        <label className="gaf-form-label">{t('devices.op_panel_label_swipe_duration')}</label>
        <div className="gaf-form-controls">
          <InputNumber
            value={swipeDuration}
            onChange={(v) => setSwipeDuration(v ?? 300)}
            min={50}
            max={5000}
            step={50}
            className="gaf-w-sm"
          />
          <Text type="secondary">ms</Text>
        </div>
      </div>
      <Button type="primary" icon={<ArrowsAltOutlined />} onClick={handleExecuteSwipe} loading={loading} block>
        {t('devices.op_panel_btn_execute_swipe')}
      </Button>
    </div>
  );

  /** Scroll panel content */
  const scrollPanel = (
    <div className="gaf-w-full gaf-flex-col gaf-gap-md">
      <div className="gaf-form-row">
        <label className="gaf-form-label">{t('devices.op_panel_label_scroll_pos')}</label>
        <div className="gaf-form-controls">
          <InputNumber
            value={scrollX}
            onChange={(v) => setScrollX(v ?? 0)}
            placeholder="X"
            min={0}
            className="gaf-w-xs"
          />
          <InputNumber
            value={scrollY}
            onChange={(v) => setScrollY(v ?? 0)}
            placeholder="Y"
            min={0}
            className="gaf-w-xs"
          />
          {onRequestCoordinatePick && (
            <Button icon={<AimOutlined />} onClick={() => onRequestCoordinatePick('click')} size="small">
              {t('devices.op_panel_btn_pick_from_screenshot')}
            </Button>
          )}
        </div>
      </div>
      <div className="gaf-form-row">
        <label className="gaf-form-label">{t('devices.op_panel_label_scroll_dir')}</label>
        <div className="gaf-form-controls">
          <Select
            value={scrollDelta > 0 ? 'up' : 'down'}
            onChange={(v) => setScrollDelta(v === 'up' ? 120 : -120)}
            options={[
              { value: 'up', label: t('devices.op_panel_scroll_dir_up') },
              { value: 'down', label: t('devices.op_panel_scroll_dir_down') },
            ]}
            className="gaf-w-200"
          />
        </div>
      </div>
      <div className="gaf-form-row">
        <label className="gaf-form-label">{t('devices.op_panel_label_scroll_amount')}</label>
        <div className="gaf-form-controls">
          <InputNumber
            value={Math.abs(scrollDelta)}
            onChange={(v) => {
              const val = v ?? 120;
              setScrollDelta(scrollDelta > 0 ? val : -val);
            }}
            min={1}
            max={1200}
            step={120}
            className="gaf-w-sm"
          />
          <Text type="secondary">
            {t('devices.op_panel_scroll_amount_hint', { count: Math.abs(scrollDelta) / 120 })}
          </Text>
        </div>
      </div>
      <Button type="primary" icon={<FontSizeOutlined />} onClick={handleExecuteScroll} loading={loading} block>
        {t('devices.op_panel_btn_execute_scroll')}
      </Button>
    </div>
  );

  /** Template match panel content */
  const templatePanel = (
    <div className="gaf-w-full gaf-flex-col gaf-gap-md">
      <div className="gaf-form-row">
        <label className="gaf-form-label">{t('devices.op_panel_label_template_image')}</label>
        <div className="gaf-form-controls gaf-flex-col" style={{ alignItems: 'flex-start' }}>
          <Upload
            accept="image/png,image/jpeg,image/bmp"
            showUploadList={false}
            beforeUpload={handleTemplateUpload}
            maxCount={1}
          >
            <Button icon={<UploadOutlined />}>{t('devices.op_panel_btn_upload_template')}</Button>
          </Upload>
          {templateName && (
            <div className="gaf-mt-xs">
              <Tag icon={<PictureOutlined />} color="blue">
                {templateName}
              </Tag>
            </div>
          )}
        </div>
      </div>
      <div className="gaf-form-row">
        <label className="gaf-form-label">{t('devices.op_panel_label_threshold')}</label>
        <div className="gaf-form-controls gaf-flex-col" style={{ alignItems: 'flex-start' }}>
          <Text strong>{templateThreshold.toFixed(2)}</Text>
          <Slider
            min={0.3}
            max={0.95}
            step={0.05}
            value={templateThreshold}
            onChange={setTemplateThreshold}
            marks={{ 0.3: '0.3', 0.5: '0.5', 0.7: '0.7', 0.95: '0.95' }}
            style={{ width: '100%', minWidth: 260 }}
          />
          <Text type="secondary" className="gaf-text-xs">
            {t('devices.op_panel_threshold_hint')}
          </Text>
        </div>
      </div>
      <Button type="primary" icon={<PictureOutlined />} onClick={handleExecuteTemplateMatch} loading={loading} block>
        {t('devices.op_panel_btn_execute_template')}
      </Button>
      {templateResult && (
        <Card size="small" style={{ background: '#fafafa' }}>
          <div className="gaf-text-xs">
            <div>
              <Text strong>{t('devices.op_panel_status_label')}</Text>{' '}
              {templateResult.matched ? (
                <Tag color="success">{t('devices.op_panel_status_matched')}</Tag>
              ) : (
                <Tag color="warning">{t('devices.op_panel_status_below_threshold')}</Tag>
              )}
            </div>
            <div>
              <Text strong>{t('devices.op_panel_score_label')}</Text> {templateResult.score.toFixed(4)}
            </div>
            <div>
              <Text strong>{t('devices.op_panel_scale_label')}</Text> {templateResult.scale.toFixed(2)}
            </div>
            <div>
              <Text strong>{t('devices.op_panel_position_label')}</Text> ({templateResult.x}, {templateResult.y}) - (
              {templateResult.x + templateResult.width}, {templateResult.y + templateResult.height})
            </div>
            <div>
              <Text strong>{t('devices.op_panel_center_label')}</Text> ({templateResult.center_x},{' '}
              {templateResult.center_y})
            </div>
            {templateResult.matched && (
              <Button
                type="primary"
                size="small"
                icon={<AimOutlined />}
                onClick={handleClickMatchedCenter}
                loading={loading}
                className="gaf-mt-sm"
                block
              >
                {t('devices.op_panel_btn_click_match_center', {
                  x: templateResult.center_x,
                  y: templateResult.center_y,
                })}
              </Button>
            )}
          </div>
        </Card>
      )}
    </div>
  );

  /** Color detect panel content */
  const colorPanel = (
    <div className="gaf-w-full gaf-flex-col gaf-gap-md">
      <div className="gaf-form-row">
        <label className="gaf-form-label">{t('devices.op_panel_label_hsv_lower')}</label>
        <div className="gaf-form-controls">
          <Text type="secondary" className="gaf-text-xs">
            H
          </Text>
          <InputNumber
            value={colorLowerH}
            onChange={(v) => setColorLowerH(v ?? 0)}
            min={0}
            max={180}
            style={{ width: 70 }}
          />
          <Text type="secondary" className="gaf-text-xs">
            S
          </Text>
          <InputNumber
            value={colorLowerS}
            onChange={(v) => setColorLowerS(v ?? 0)}
            min={0}
            max={255}
            style={{ width: 70 }}
          />
          <Text type="secondary" className="gaf-text-xs">
            V
          </Text>
          <InputNumber
            value={colorLowerV}
            onChange={(v) => setColorLowerV(v ?? 0)}
            min={0}
            max={255}
            style={{ width: 70 }}
          />
        </div>
      </div>
      <div className="gaf-form-row">
        <label className="gaf-form-label">{t('devices.op_panel_label_hsv_upper')}</label>
        <div className="gaf-form-controls">
          <Text type="secondary" className="gaf-text-xs">
            H
          </Text>
          <InputNumber
            value={colorUpperH}
            onChange={(v) => setColorUpperH(v ?? 0)}
            min={0}
            max={180}
            style={{ width: 70 }}
          />
          <Text type="secondary" className="gaf-text-xs">
            S
          </Text>
          <InputNumber
            value={colorUpperS}
            onChange={(v) => setColorUpperS(v ?? 0)}
            min={0}
            max={255}
            style={{ width: 70 }}
          />
          <Text type="secondary" className="gaf-text-xs">
            V
          </Text>
          <InputNumber
            value={colorUpperV}
            onChange={(v) => setColorUpperV(v ?? 0)}
            min={0}
            max={255}
            style={{ width: 70 }}
          />
        </div>
      </div>
      <div className="gaf-form-row">
        <label className="gaf-form-label">{t('devices.op_panel_label_min_pixels')}</label>
        <div className="gaf-form-controls gaf-flex-col" style={{ alignItems: 'flex-start' }}>
          <Text strong>{colorMinPixels}</Text>
          <Slider
            min={10}
            max={5000}
            step={10}
            value={colorMinPixels}
            onChange={setColorMinPixels}
            style={{ width: '100%', minWidth: 260 }}
          />
          <Text type="secondary" className="gaf-text-xs">
            {t('devices.op_panel_min_pixels_hint')}
          </Text>
        </div>
      </div>
      <div className="gaf-form-row">
        <label className="gaf-form-label">{t('devices.op_panel_label_preset_colors')}</label>
        <div className="gaf-form-controls">
          <Button
            size="small"
            onClick={() => {
              setColorLowerH(0);
              setColorLowerS(100);
              setColorLowerV(100);
              setColorUpperH(10);
              setColorUpperS(255);
              setColorUpperV(255);
            }}
          >
            {t('devices.op_panel_color_red')}
          </Button>
          <Button
            size="small"
            onClick={() => {
              setColorLowerH(35);
              setColorLowerS(100);
              setColorLowerV(100);
              setColorUpperH(85);
              setColorUpperS(255);
              setColorUpperV(255);
            }}
          >
            {t('devices.op_panel_color_green')}
          </Button>
          <Button
            size="small"
            onClick={() => {
              setColorLowerH(100);
              setColorLowerS(100);
              setColorLowerV(100);
              setColorUpperH(130);
              setColorUpperS(255);
              setColorUpperV(255);
            }}
          >
            {t('devices.op_panel_color_blue')}
          </Button>
          <Button
            size="small"
            onClick={() => {
              setColorLowerH(20);
              setColorLowerS(100);
              setColorLowerV(100);
              setColorUpperH(35);
              setColorUpperS(255);
              setColorUpperV(255);
            }}
          >
            {t('devices.op_panel_color_orange')}
          </Button>
          <Button
            size="small"
            onClick={() => {
              setColorLowerH(125);
              setColorLowerS(100);
              setColorLowerV(100);
              setColorUpperH(160);
              setColorUpperS(255);
              setColorUpperV(255);
            }}
          >
            {t('devices.op_panel_color_purple')}
          </Button>
        </div>
      </div>
      <Button type="primary" icon={<BgColorsOutlined />} onClick={handleExecuteColorDetect} loading={loading} block>
        {t('devices.op_panel_btn_execute_color')}
      </Button>
      {colorResult && (
        <Card size="small" style={{ background: '#fafafa' }}>
          <div className="gaf-text-xs">
            <div>
              <Text strong>{t('devices.op_panel_status_label')}</Text>{' '}
              {colorResult.matched ? (
                <Tag color="success">{t('devices.op_panel_status_detected')}</Tag>
              ) : (
                <Tag color="warning">{t('devices.op_panel_status_insufficient')}</Tag>
              )}
            </div>
            <div>
              <Text strong>{t('devices.op_panel_pixels_label')}</Text> {colorResult.pixel_count}
            </div>
            <div>
              <Text strong>{t('devices.op_panel_bbox_label')}</Text> ({colorResult.bbox[0]}, {colorResult.bbox[1]}) - (
              {colorResult.bbox[2]}, {colorResult.bbox[3]})
            </div>
            <div>
              <Text strong>{t('devices.op_panel_centroid_label')}</Text> ({colorResult.centroid[0]},{' '}
              {colorResult.centroid[1]})
            </div>
            {colorResult.matched && (
              <Button
                type="primary"
                size="small"
                icon={<AimOutlined />}
                onClick={handleClickColorCentroid}
                loading={loading}
                className="gaf-mt-sm"
                block
              >
                {t('devices.op_panel_btn_click_color_centroid', {
                  x: colorResult.centroid[0],
                  y: colorResult.centroid[1],
                })}
              </Button>
            )}
          </div>
        </Card>
      )}
    </div>
  );

  /** App management panel */
  const appPanel = (
    <div className="gaf-w-full gaf-flex-col gaf-gap-md">
      <div className="gaf-form-row">
        <label className="gaf-form-label">{t('devices.op_panel_label_package')}</label>
        <div className="gaf-form-controls">
          <Input
            value={appPackage}
            onChange={(e) => setAppPackage(e.target.value)}
            placeholder={t('devices.op_panel_pkg_placeholder')}
            allowClear
            style={{ width: 320 }}
          />
        </div>
      </div>
      <div className="gaf-form-row">
        <label className="gaf-form-label">{t('devices.op_panel_label_filter')}</label>
        <div className="gaf-form-controls">
          <Input
            value={appFilter}
            onChange={(e) => setAppFilter(e.target.value)}
            placeholder={t('devices.op_panel_filter_placeholder')}
            allowClear
            style={{ width: 220 }}
          />
          <Text type="secondary" className="gaf-text-xs">
            {t('devices.op_panel_filter_hint')}
          </Text>
        </div>
      </div>
      <div className="gaf-form-row">
        <label className="gaf-form-label">{t('devices.op_panel_label_action')}</label>
        <div className="gaf-form-controls">
          <Button
            type="primary"
            icon={<AppstoreOutlined />}
            loading={loading}
            onClick={() => handleAppAction('launch')}
          >
            {t('devices.op_panel_btn_launch')}
          </Button>
          <Button danger loading={loading} onClick={() => handleAppAction('force_stop')}>
            {t('devices.op_panel_btn_force_stop')}
          </Button>
          <Button loading={loading} onClick={() => handleAppAction('list')}>
            {t('devices.op_panel_btn_list_apps')}
          </Button>
          <Button danger loading={loading} onClick={() => handleAppAction('uninstall')}>
            {t('devices.op_panel_btn_uninstall')}
          </Button>
        </div>
      </div>
      {appResult && (
        <Card size="small">
          <div className="gaf-flex-between gaf-mb-sm">
            <Text strong>{t('devices.op_panel_result_label')}</Text>
            <Tag color={appResult.success ? 'success' : 'error'}>
              {appResult.success ? t('devices.op_panel_status_success') : t('devices.op_panel_status_failed')}
            </Tag>
          </div>
          {appResult.error && <Text type="danger">{appResult.error}</Text>}
          {appResult.data?.packages && (
            <div style={{ maxHeight: 200, overflowY: 'auto' }}>
              {appResult.data.packages.slice(0, 100).map((pkg) => (
                <div key={pkg} className="gaf-text-sm" style={{ padding: '2px 0' }}>
                  {pkg}
                </div>
              ))}
              {appResult.data.packages.length > 100 && (
                <Text type="secondary" className="gaf-text-sm">
                  {t('devices.op_panel_more_packages', { count: appResult.data.packages.length - 100 })}
                </Text>
              )}
            </div>
          )}
          {appResult.data?.processes && (
            <div style={{ maxHeight: 200, overflowY: 'auto' }}>
              {appResult.data.processes.slice(0, 100).map((proc) => (
                <div key={`${proc.pid}-${proc.name}`} className="gaf-text-sm" style={{ padding: '2px 0' }}>
                  <Tag>{proc.pid}</Tag> {proc.name}
                </div>
              ))}
            </div>
          )}
        </Card>
      )}
    </div>
  );

  /** Device info panel */
  const infoPanel = (
    <div className="gaf-w-full gaf-flex-col gaf-gap-md">
      <Button
        type="primary"
        icon={<InfoCircleOutlined />}
        loading={loading}
        onClick={handleQueryInfo}
        style={{ alignSelf: 'flex-start' }}
      >
        {t('devices.op_panel_btn_query_info')}
      </Button>
      {infoResult && (
        <Card size="small">
          <div className="gaf-flex-between gaf-mb-sm">
            <Text strong>{t('devices.op_panel_device_info_label')}</Text>
            <Tag color={infoResult.success ? 'success' : 'error'}>
              {infoResult.success ? t('devices.op_panel_status_success') : t('devices.op_panel_status_failed')}
            </Tag>
          </div>
          {infoResult.error && <Text type="danger">{infoResult.error}</Text>}
          {infoResult.success && infoResult.data && (
            <div className="gaf-text-sm">
              {infoResult.data.device_type && (
                <div className="gaf-mb-xs">
                  <Text type="secondary">{t('devices.op_panel_device_type_label')}</Text> {infoResult.data.device_type}
                </div>
              )}
              {infoResult.data.screen_width && (
                <div className="gaf-mb-xs">
                  <Text type="secondary">{t('devices.op_panel_screen_res_label')}</Text> {infoResult.data.screen_width}{' '}
                  x {infoResult.data.screen_height}
                </div>
              )}
              {infoResult.data.battery_level !== null && infoResult.data.battery_level !== undefined && (
                <div className="gaf-mb-xs">
                  <Text type="secondary">{t('devices.op_panel_battery_label')}</Text> {infoResult.data.battery_level}%
                  {infoResult.data.battery_charging !== null && infoResult.data.battery_charging !== undefined && (
                    <Tag color={infoResult.data.battery_charging ? 'processing' : 'default'} className="gaf-ml-xs">
                      {infoResult.data.battery_charging
                        ? t('devices.op_panel_battery_charging')
                        : t('devices.op_panel_battery_not_charging')}
                    </Tag>
                  )}
                </div>
              )}
              {infoResult.data.android_version && (
                <div className="gaf-mb-xs">
                  <Text type="secondary">{t('devices.op_panel_android_version_label')}</Text>{' '}
                  {infoResult.data.android_version}
                </div>
              )}
              {infoResult.data.model && (
                <div className="gaf-mb-xs">
                  <Text type="secondary">{t('devices.op_panel_model_label')}</Text> {infoResult.data.model}
                </div>
              )}
              {infoResult.data.os_version && (
                <div className="gaf-mb-xs">
                  <Text type="secondary">{t('devices.op_panel_os_version_label')}</Text> {infoResult.data.os_version}
                </div>
              )}
            </div>
          )}
        </Card>
      )}
    </div>
  );

  /** Operation history display */
  const historyPanel = (
    <div>
      {history.length === 0 ? (
        <Text type="secondary">{t('devices.op_panel_no_history')}</Text>
      ) : (
        <div style={{ maxHeight: 300, overflowY: 'auto' }}>
          {history.map((record) => (
            <Card
              key={record.id}
              size="small"
              className="gaf-mb-sm"
              title={
                <Space>
                  {record.success ? (
                    <CheckCircleOutlined style={{ color: '#52c41a' }} />
                  ) : (
                    <CloseCircleOutlined style={{ color: '#ff4d4f' }} />
                  )}
                  <Tag
                    color={
                      record.type === 'click'
                        ? 'blue'
                        : record.type === 'key_press'
                          ? 'green'
                          : record.type === 'text_input'
                            ? 'orange'
                            : record.type === 'scroll'
                              ? 'cyan'
                              : record.type === 'template_match'
                                ? 'geekblue'
                                : record.type === 'color_detect'
                                  ? 'magenta'
                                  : 'purple'
                    }
                  >
                    {record.type}
                  </Tag>
                  <Text type="secondary" className="gaf-text-xxs">
                    {new Date(record.timestamp).toLocaleTimeString()}
                  </Text>
                </Space>
              }
            >
              <div className="gaf-text-xs">
                <div>
                  <Text strong>{t('devices.op_panel_params_label')}</Text> {JSON.stringify(record.params)}
                </div>
                {record.method && (
                  <div>
                    <Text strong>{t('devices.op_panel_method_label')}</Text> {record.method}
                  </div>
                )}
                {record.error && (
                  <div style={{ color: '#ff4d4f' }}>
                    <Text strong>{t('devices.op_panel_error_label')}</Text> {record.error}
                  </div>
                )}
              </div>
            </Card>
          ))}
        </div>
      )}
    </div>
  );

  const tabItems = [
    {
      key: 'click',
      label: (
        <span>
          <AimOutlined /> {t('devices.op_panel_tab_click')}
        </span>
      ),
      children: clickPanel,
    },
    {
      key: 'key',
      label: (
        <span>
          <ToolOutlined /> {t('devices.op_panel_tab_key')}
        </span>
      ),
      children: keyPanel,
    },
    {
      key: 'text',
      label: (
        <span>
          <FontSizeOutlined /> {t('devices.op_panel_tab_text')}
        </span>
      ),
      children: textPanel,
    },
    {
      key: 'swipe',
      label: (
        <span>
          <ArrowsAltOutlined /> {t('devices.op_panel_tab_swipe')}
        </span>
      ),
      children: swipePanel,
    },
    {
      key: 'scroll',
      label: (
        <span>
          <FontSizeOutlined /> {t('devices.op_panel_tab_scroll')}
        </span>
      ),
      children: scrollPanel,
    },
    {
      key: 'template',
      label: (
        <span>
          <PictureOutlined /> {t('devices.op_panel_tab_template')}
        </span>
      ),
      children: templatePanel,
    },
    {
      key: 'color',
      label: (
        <span>
          <BgColorsOutlined /> {t('devices.op_panel_tab_color')}
        </span>
      ),
      children: colorPanel,
    },
    {
      key: 'app',
      label: (
        <span>
          <AppstoreOutlined /> {t('devices.op_panel_tab_app')}
        </span>
      ),
      children: appPanel,
    },
    {
      key: 'info',
      label: (
        <span>
          <InfoCircleOutlined /> {t('devices.op_panel_tab_info')}
        </span>
      ),
      children: infoPanel,
    },
    {
      key: 'history',
      label: (
        <span>
          <HistoryOutlined /> {t('devices.op_panel_tab_history', { count: history.length })}
        </span>
      ),
      children: historyPanel,
    },
  ];

  return (
    <Card
      size="small"
      title={
        <Space>
          {loading ? <LoadingOutlined spin style={{ color: '#1890ff' }} /> : <ToolOutlined />}
          <Text strong>{t('devices.op_panel_title')}</Text>
          {deviceName && <Text type="secondary">{t('devices.op_panel_title_with_device', { name: deviceName })}</Text>}
        </Space>
      }
    >
      <Tabs
        activeKey={activeTab}
        onChange={setActiveTab}
        items={tabItems}
        size="small"
        tabBarGutter={8}
        className="gaf-tabs-wrap"
        tabBarStyle={{ marginBottom: 0 }}
      />
    </Card>
  );
}

export default DeviceOperationPanel;
