/**
 * Shared option constants for GameProfile fields.
 *
 * Used by:
 *   - GameProfilesPage (list page): column render
 *   - GameProfileEditorModal (create/edit modal): Select options
 *
 * Extracted to avoid duplicating option arrays across two components.
 * Labels are i18n keys resolved at call site via useTranslation().
 */
import { useCallback, useMemo } from 'react';
import { useTranslation } from '@/i18n';

export interface OptionItem {
  value: string;
  labelKey: string;
}

export const SCREENSHOT_METHOD_OPTIONS: OptionItem[] = [
  { value: 'bitblt', labelKey: 'gameProfiles.method_bitblt' },
  { value: 'dxgi_dupl', labelKey: 'gameProfiles.method_dxgi_dupl' },
  { value: 'wgc', labelKey: 'gameProfiles.method_wgc' },
  { value: 'gdi', labelKey: 'gameProfiles.method_gdi' },
  { value: 'adb', labelKey: 'gameProfiles.method_adb' },
];

export const INPUT_METHOD_OPTIONS: OptionItem[] = [
  { value: 'sendinput', labelKey: 'gameProfiles.method_sendinput' },
  { value: 'postmessage', labelKey: 'gameProfiles.method_postmessage' },
  { value: 'adb', labelKey: 'gameProfiles.method_adb' },
];

export const CONTROL_MODE_OPTIONS: OptionItem[] = [
  { value: 'foreground', labelKey: 'gameProfiles.mode_foreground' },
  { value: 'background', labelKey: 'gameProfiles.mode_background' },
  { value: 'pseudo_background', labelKey: 'gameProfiles.mode_pseudo_background' },
];

export const OCR_LANG_OPTIONS: OptionItem[] = [
  { value: 'ch', labelKey: 'gameProfiles.ocr_chinese' },
  { value: 'en', labelKey: 'gameProfiles.ocr_english' },
  { value: 'ja', labelKey: 'gameProfiles.ocr_japanese' },
  { value: 'ko', labelKey: 'gameProfiles.ocr_korean' },
];

export const DEVICE_TYPE_OPTIONS: OptionItem[] = [
  { value: 'windows', labelKey: 'gameProfiles.device_type_windows' },
  { value: 'emulator', labelKey: 'gameProfiles.device_type_emulator' },
];

export const RESOLUTION_STRATEGY_OPTIONS: OptionItem[] = [
  { value: 'scale', labelKey: 'gameProfiles.strategy_scale' },
  { value: 'crop', labelKey: 'gameProfiles.strategy_crop' },
  { value: 'letterbox', labelKey: 'gameProfiles.strategy_letterbox' },
  { value: 'stretch', labelKey: 'gameProfiles.strategy_stretch' },
];

/** Hook: resolve all GameProfile option arrays with localized labels. */
export function useGameProfileOptions() {
  const t = useTranslation();
  // toLabel 是纯映射函数 (不含 Hook 调用), 由外层 useCallback/useMemo 缓存
  // (rules-of-hooks: Hook 只能在自定义 Hook 顶层调用, 不能在普通函数内)。
  const toLabel = useCallback((opts: OptionItem[]) => opts.map((o) => ({ value: o.value, label: t(o.labelKey) })), [t]);

  return {
    screenshotMethods: useMemo(() => toLabel(SCREENSHOT_METHOD_OPTIONS), [toLabel]),
    inputMethods: useMemo(() => toLabel(INPUT_METHOD_OPTIONS), [toLabel]),
    controlModes: useMemo(() => toLabel(CONTROL_MODE_OPTIONS), [toLabel]),
    ocrLangOptions: useMemo(() => toLabel(OCR_LANG_OPTIONS), [toLabel]),
    resolutionStrategyOptions: useMemo(() => toLabel(RESOLUTION_STRATEGY_OPTIONS), [toLabel]),
    deviceTypeOptions: useMemo(() => toLabel(DEVICE_TYPE_OPTIONS), [toLabel]),
  };
}
