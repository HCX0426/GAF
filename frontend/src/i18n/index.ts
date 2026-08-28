/**
 * Lightweight i18n framework.
 * Supports zh-CN / en-US / ja-JP / ko-KR, plus "system" (follow browser language).
 * Persists language preference via localStorage; no react-intl dependency.
 */
import { useCallback, useSyncExternalStore } from 'react';
import type { SupportedLocale, RealLocale } from './types';

import { accounts } from './locales/accounts';
import { ailab } from './locales/ailab';
import { analytics } from './locales/analytics';
import { apiKeys } from './locales/apiKeys';
import { auditLog } from './locales/auditLog';
import { backup } from './locales/backup';
import { common } from './locales/common';
import { config } from './locales/config';
import { dashboard } from './locales/dashboard';
import { debug } from './locales/debug';
import { deviceCenter } from './locales/deviceCenter';
import { devices } from './locales/devices';
import { emulator } from './locales/emulator';
import { executions } from './locales/executions';
import { executionReplay } from './locales/executionReplay';
import { featureFlags } from './locales/featureFlags';
import { gameAccounts } from './locales/gameAccounts';
import { gameProfiles } from './locales/gameProfiles';
import { layout } from './locales/layout';
import { login } from './locales/login';
import { logCenter } from './locales/logCenter';
import { marketplace } from './locales/marketplace';
import { monitors } from './locales/monitors';
import { nodePropertyPanel } from './locales/nodePropertyPanel';
import { notifications } from './locales/notifications';
import { oauthCallback } from './locales/oauthCallback';
import { ops } from './locales/ops';
import { pageUnderConstruction } from './locales/pageUnderConstruction';
import { pipelineEditor } from './locales/pipelineEditor';
import { plugins } from './locales/plugins';
import { qa } from './locales/qa';
import { resourcePacks } from './locales/resourcePacks';
import { resources } from './locales/resources';
import { scheduledTasks } from './locales/scheduledTasks';
import { settings } from './locales/settings';
import { setup } from './locales/setup';
import { sidebar } from './locales/sidebar';
import { skills } from './locales/skills';
import { skillMarket } from './locales/skillMarket';
import { sla } from './locales/sla';
import { taskStudio } from './locales/taskStudio';
import { tasks } from './locales/tasks';
import { templateAnnotation } from './locales/templateAnnotation';
import { templateEffectiveness } from './locales/templateEffectiveness';
import { unattendedStrategy } from './locales/unattendedStrategy';
import { windowMgmt } from './locales/windowMgmt';

export type { SupportedLocale, RealLocale } from './types';

const messages: Record<RealLocale, Record<string, string>> = {
  'zh-CN': {
    ...accounts['zh-CN'],
    ...ailab['zh-CN'],
    ...analytics['zh-CN'],
    ...apiKeys['zh-CN'],
    ...auditLog['zh-CN'],
    ...backup['zh-CN'],
    ...common['zh-CN'],
    ...config['zh-CN'],
    ...dashboard['zh-CN'],
    ...debug['zh-CN'],
    ...deviceCenter['zh-CN'],
    ...devices['zh-CN'],
    ...emulator['zh-CN'],
    ...executions['zh-CN'],
    ...executionReplay['zh-CN'],
    ...featureFlags['zh-CN'],
    ...gameAccounts['zh-CN'],
    ...gameProfiles['zh-CN'],
    ...layout['zh-CN'],
    ...login['zh-CN'],
    ...logCenter['zh-CN'],
    ...marketplace['zh-CN'],
    ...monitors['zh-CN'],
    ...nodePropertyPanel['zh-CN'],
    ...notifications['zh-CN'],
    ...oauthCallback['zh-CN'],
    ...ops['zh-CN'],
    ...pageUnderConstruction['zh-CN'],
    ...pipelineEditor['zh-CN'],
    ...plugins['zh-CN'],
    ...qa['zh-CN'],
    ...resourcePacks['zh-CN'],
    ...resources['zh-CN'],
    ...scheduledTasks['zh-CN'],
    ...settings['zh-CN'],
    ...setup['zh-CN'],
    ...sidebar['zh-CN'],
    ...skills['zh-CN'],
    ...skillMarket['zh-CN'],
    ...sla['zh-CN'],
    ...taskStudio['zh-CN'],
    ...tasks['zh-CN'],
    ...templateAnnotation['zh-CN'],
    ...templateEffectiveness['zh-CN'],
    ...unattendedStrategy['zh-CN'],
    ...windowMgmt['zh-CN'],
  },
  'en-US': {
    ...accounts['en-US'],
    ...ailab['en-US'],
    ...analytics['en-US'],
    ...apiKeys['en-US'],
    ...auditLog['en-US'],
    ...backup['en-US'],
    ...common['en-US'],
    ...config['en-US'],
    ...dashboard['en-US'],
    ...debug['en-US'],
    ...deviceCenter['en-US'],
    ...devices['en-US'],
    ...emulator['en-US'],
    ...executions['en-US'],
    ...executionReplay['en-US'],
    ...featureFlags['en-US'],
    ...gameAccounts['en-US'],
    ...gameProfiles['en-US'],
    ...layout['en-US'],
    ...login['en-US'],
    ...logCenter['en-US'],
    ...marketplace['en-US'],
    ...monitors['en-US'],
    ...nodePropertyPanel['en-US'],
    ...notifications['en-US'],
    ...oauthCallback['en-US'],
    ...ops['en-US'],
    ...pageUnderConstruction['en-US'],
    ...pipelineEditor['en-US'],
    ...plugins['en-US'],
    ...qa['en-US'],
    ...resourcePacks['en-US'],
    ...resources['en-US'],
    ...scheduledTasks['en-US'],
    ...settings['en-US'],
    ...setup['en-US'],
    ...sidebar['en-US'],
    ...skills['en-US'],
    ...skillMarket['en-US'],
    ...sla['en-US'],
    ...taskStudio['en-US'],
    ...tasks['en-US'],
    ...templateAnnotation['en-US'],
    ...templateEffectiveness['en-US'],
    ...unattendedStrategy['en-US'],
    ...windowMgmt['en-US'],
  },
  'ja-JP': {
    ...accounts['ja-JP'],
    ...ailab['ja-JP'],
    ...analytics['ja-JP'],
    ...apiKeys['ja-JP'],
    ...auditLog['ja-JP'],
    ...backup['ja-JP'],
    ...common['ja-JP'],
    ...config['ja-JP'],
    ...dashboard['ja-JP'],
    ...debug['ja-JP'],
    ...deviceCenter['ja-JP'],
    ...devices['ja-JP'],
    ...emulator['ja-JP'],
    ...executions['ja-JP'],
    ...executionReplay['ja-JP'],
    ...featureFlags['ja-JP'],
    ...gameAccounts['ja-JP'],
    ...gameProfiles['ja-JP'],
    ...login['ja-JP'],
    ...logCenter['ja-JP'],
    ...marketplace['ja-JP'],
    ...monitors['ja-JP'],
    ...nodePropertyPanel['ja-JP'],
    ...notifications['ja-JP'],
    ...oauthCallback['ja-JP'],
    ...ops['ja-JP'],
    ...pageUnderConstruction['ja-JP'],
    ...pipelineEditor['ja-JP'],
    ...plugins['ja-JP'],
    ...qa['ja-JP'],
    ...resourcePacks['ja-JP'],
    ...resources['ja-JP'],
    ...scheduledTasks['ja-JP'],
    ...settings['ja-JP'],
    ...setup['ja-JP'],
    ...sidebar['ja-JP'],
    ...skills['ja-JP'],
    ...skillMarket['ja-JP'],
    ...sla['ja-JP'],
    ...taskStudio['ja-JP'],
    ...tasks['ja-JP'],
    ...templateAnnotation['ja-JP'],
    ...templateEffectiveness['ja-JP'],
    ...unattendedStrategy['ja-JP'],
    ...windowMgmt['ja-JP'],
  },
  'ko-KR': {
    ...accounts['ko-KR'],
    ...ailab['ko-KR'],
    ...analytics['ko-KR'],
    ...apiKeys['ko-KR'],
    ...auditLog['ko-KR'],
    ...backup['ko-KR'],
    ...common['ko-KR'],
    ...config['ko-KR'],
    ...dashboard['ko-KR'],
    ...debug['ko-KR'],
    ...deviceCenter['ko-KR'],
    ...devices['ko-KR'],
    ...emulator['ko-KR'],
    ...executions['ko-KR'],
    ...executionReplay['ko-KR'],
    ...featureFlags['ko-KR'],
    ...gameAccounts['ko-KR'],
    ...gameProfiles['ko-KR'],
    ...layout['ko-KR'],
    ...login['ko-KR'],
    ...logCenter['ko-KR'],
    ...marketplace['ko-KR'],
    ...monitors['ko-KR'],
    ...nodePropertyPanel['ko-KR'],
    ...notifications['ko-KR'],
    ...oauthCallback['ko-KR'],
    ...ops['ko-KR'],
    ...pageUnderConstruction['ko-KR'],
    ...pipelineEditor['ko-KR'],
    ...plugins['ko-KR'],
    ...qa['ko-KR'],
    ...resourcePacks['ko-KR'],
    ...resources['ko-KR'],
    ...scheduledTasks['ko-KR'],
    ...settings['ko-KR'],
    ...setup['ko-KR'],
    ...sidebar['ko-KR'],
    ...skills['ko-KR'],
    ...skillMarket['ko-KR'],
    ...sla['ko-KR'],
    ...taskStudio['ko-KR'],
    ...tasks['ko-KR'],
    ...templateAnnotation['ko-KR'],
    ...templateEffectiveness['ko-KR'],
    ...unattendedStrategy['ko-KR'],
    ...windowMgmt['ko-KR'],
  },
};

const STORAGE_KEY = 'gaf_locale';

/** Detect browser language and map to a real locale. */
function detectBrowserLocale(): RealLocale {
  const browserLang = navigator.language;
  if (browserLang.startsWith('zh')) return 'zh-CN';
  if (browserLang.startsWith('ja')) return 'ja-JP';
  if (browserLang.startsWith('ko')) return 'ko-KR';
  return 'en-US';
}

/** Resolve a supported locale to a real locale (system -> browser detection). */
export function resolveLocale(locale: SupportedLocale): RealLocale {
  if (locale === 'system') return detectBrowserLocale();
  return locale;
}

/** Read stored locale from localStorage; fall back to browser language detection. */
export function getStoredLocale(): SupportedLocale {
  const stored = localStorage.getItem(STORAGE_KEY);
  if (stored === 'zh-CN' || stored === 'en-US' || stored === 'ja-JP' || stored === 'ko-KR' || stored === 'system') {
    return stored;
  }
  return detectBrowserLocale();
}

/** Persist locale preference to localStorage. */
export function setStoredLocale(locale: SupportedLocale): void {
  localStorage.setItem(STORAGE_KEY, locale);
}

/** Translate a key for a given locale (or the current global locale when omitted).
 *  Supports {{placeholder}} interpolation via the optional `params` argument.
 */
export function t(key: string, locale?: SupportedLocale, params?: Record<string, string | number | undefined>): string {
  const loc = resolveLocale(locale || getStoredLocale());
  const template = messages[loc]?.[key] || key;
  if (!params) return template;
  return template.replace(/\{\{(\w+)\}\}/g, (_, name: string) =>
    params[name] !== undefined ? String(params[name]) : `{{${name}}}`,
  );
}

let _locale: SupportedLocale = getStoredLocale();
let _listeners: Array<() => void> = [];

/** Sync <html lang="..."> with the resolved real locale (a11y + SEO). */
function syncDocumentLang(locale: SupportedLocale): void {
  if (typeof document !== 'undefined') {
    document.documentElement.lang = resolveLocale(locale);
  }
}

// Apply the persisted/system locale to <html lang> at module load.
syncDocumentLang(_locale);

/** Return the current global locale. */
export function getLocale(): SupportedLocale {
  return _locale;
}

/** Return the current real locale (resolved from system if needed). */
export function getRealLocale(): RealLocale {
  return resolveLocale(_locale);
}

/** Set the global locale and notify all subscribers. */
export function setLocale(locale: SupportedLocale): void {
  if (locale === _locale) return;
  _locale = locale;
  setStoredLocale(locale);
  syncDocumentLang(locale);
  _listeners.forEach((fn) => fn());
}

/** Subscribe to locale changes; returns an unsubscribe function. */
export function subscribeLocale(fn: () => void): () => void {
  _listeners.push(fn);
  return () => {
    _listeners = _listeners.filter((f) => f !== fn);
  };
}

/**
 * React Hook that re-renders the component on locale change.
 * Uses useSyncExternalStore for tear-free reads.
 */
export function useLocale(): SupportedLocale {
  return useSyncExternalStore(subscribeLocale, getLocale, getLocale);
}

/**
 * React Hook returning a translate function bound to the current locale.
 * The function signature mirrors `t(key, params?)` (locale is auto-filled).
 * Components using this hook re-render on locale change.
 *
 * @example
 *   const t = useTranslation();
 *   t('login.username_required')           // simple lookup
 *   t('login.register_failed', { message }) // with interpolation
 */
export function useTranslation(): (key: string, params?: Record<string, string | number | undefined>) => string {
  const locale = useLocale();
  return useCallback(
    (key: string, params?: Record<string, string | number | undefined>) => t(key, locale, params),
    [locale],
  );
}
