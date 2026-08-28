/**
 * Unified error handling utilities for frontend error classification and message extraction.
 *
 * Provides functions to classify errors (network, auth, server, etc.)
 * and extract user-friendly error messages from various error types.
 *
 * H20: hardcoded Chinese strings are routed through the i18n t() helper so
 * messages follow the user selected locale.
 */

import { t } from '@/i18n';

/**
 * Error classification types.
 *
 * Implemented as a `const` object + union type (rather than `enum`) so the
 * syntax is erasable under `erasableSyntaxOnly` (TS 5.8+). `enum` emits
 * runtime code and is rejected by that flag; this pattern is fully erasable
 * while preserving both value access (`ErrorType.NETWORK`) and type usage
 * (`type: ErrorType`).
 */
export const ErrorType = {
  NETWORK: 'network',
  AUTH: 'auth',
  SERVER: 'server',
  CLIENT: 'client',
  TIMEOUT: 'timeout',
  UNKNOWN: 'unknown',
} as const;

export type ErrorType = (typeof ErrorType)[keyof typeof ErrorType];

/** Classified error result */
export interface ClassifiedError {
  type: ErrorType;
  message: string;
  originalError: unknown;
  statusCode?: number;
}

/**
 * Classify an error into a specific type based on its characteristics.
 *
 * @param error - The caught error object (can be any type)
 * @returns ClassifiedError with type, message, and original error
 */
export function classifyError(error: unknown): ClassifiedError {
  // L9: fetch() throws TypeError for network failures per the Fetch spec.
  // isNetworkError() filters by message to distinguish network errors from
  // programming bugs (e.g. 'Cannot read property of undefined').
  if (error instanceof TypeError && isNetworkError(error)) {
    return {
      type: ErrorType.NETWORK,
      message: t('error.network.connection_failed'),
      originalError: error,
    };
  }

  if (isAxiosError(error)) {
    const status = error.response?.status;

    if (!error.response && error.request) {
      return {
        type: ErrorType.NETWORK,
        message: t('error.network.connection_failed_alt'),
        originalError: error,
      };
    }

    if (error.code === 'ECONNABORTED' || error.message?.includes('timeout')) {
      return {
        type: ErrorType.TIMEOUT,
        message: t('error.timeout'),
        originalError: error,
      };
    }

    if (status === 401 || status === 403) {
      return {
        type: ErrorType.AUTH,
        message: extractErrorMessage(error) || t('error.auth.failed'),
        originalError: error,
        statusCode: status,
      };
    }

    if (status && status >= 400 && status < 500) {
      return {
        type: ErrorType.CLIENT,
        message: extractErrorMessage(error) || t('error.client.bad_request', undefined, { status }),
        originalError: error,
        statusCode: status,
      };
    }

    if (status && status >= 500) {
      return {
        type: ErrorType.SERVER,
        message: t('error.server.internal', undefined, {
          message: extractErrorMessage(error) || t('error.server.unknown'),
        }),
        originalError: error,
        statusCode: status,
      };
    }
  }

  if (error instanceof Error) {
    return {
      type: ErrorType.UNKNOWN,
      message: error.message || t('error.unknown'),
      originalError: error,
    };
  }

  return {
    type: ErrorType.UNKNOWN,
    message: String(error) || t('error.unknown'),
    originalError: error,
  };
}

/**
 * Extract a user-friendly error message from various error types.
 *
 * @param error - The caught error object
 * @returns User-friendly error string
 */
export function getErrorMessage(error: unknown): string {
  const classified = classifyError(error);
  return classified.message;
}

/**
 * Check if an error is a network-related error (TypeError with network message).
 */
function isNetworkError(error: TypeError): boolean {
  const msg = error.message.toLowerCase();
  // L9: broaden 'fetch' keyword to catch browser-specific variants
  // (e.g. 'TypeError: fetch failed' in Node 18+ undici polyfill).
  return (
    msg.includes('failed to fetch') ||
    msg.includes('networkerror') ||
    msg.includes('network request failed') ||
    msg.includes('load failed') ||
    msg.includes('fetch failed')
  );
}

/**
 * Check if an error is an Axios error with response/request properties.
 */
function isAxiosError(
  error: unknown,
): error is { response?: { status?: number; data?: unknown }; request?: unknown; code?: string; message?: string } {
  return (
    typeof error === 'object' && error !== null && 'response' in error && ('request' in error || 'message' in error)
  );
}

/**
 * Extract error detail from Axios response data.
 * Supports both { detail: string } and { error: string } formats.
 */
function extractErrorMessage(error: { response?: { data?: unknown } }): string | null {
  const data = error.response?.data;
  if (!data || typeof data !== 'object') {
    return null;
  }

  const record = data as Record<string, unknown>;
  if (typeof record.detail === 'string') {
    return record.detail;
  }
  if (typeof record.error === 'string') {
    return record.error;
  }
  if (typeof record.message === 'string') {
    return record.message;
  }

  return null;
}

/**
 * 从错误对象中提取 businessCode (后端统一信封的 ErrorCode 数字).
 * 返回 null 表示该错误无 businessCode (非业务错误 / 网络错误).
 */
export function getBusinessCode(error: unknown): number | null {
  if (typeof error === 'object' && error !== null && 'businessCode' in error) {
    const code = (error as { businessCode?: unknown }).businessCode;
    return typeof code === 'number' ? code : null;
  }
  return null;
}

/**
 * 从错误对象中提取 businessMessage (后端统一信封的 message 字段).
 */
export function getBusinessMessage(error: unknown): string | null {
  if (typeof error === 'object' && error !== null && 'businessMessage' in error) {
    const msg = (error as { businessMessage?: unknown }).businessMessage;
    return typeof msg === 'string' ? msg : null;
  }
  return null;
}

/**
 * 解析错误为用户可读消息:
 * 1. 优先按 businessCode 查 i18n error.codes.* 映射表
 * 2. 其次用 businessMessage (后端已经给的中文)
 * 3. 最后用 classifyError 兜底 (网络错误/超时/HTTP 状态码)
 */
export function resolveErrorMessage(error: unknown): string {
  const code = getBusinessCode(error);
  if (code !== null) {
    const i18nKey = `error.codes.${code}`;
    const mapped = t(i18nKey);
    // i18n 找不到 key 时会返回 key 本身; 此时降级到 businessMessage
    if (mapped && mapped !== i18nKey) {
      return mapped;
    }
  }
  const businessMsg = getBusinessMessage(error);
  if (businessMsg) {
    return businessMsg;
  }
  // 兜底: 用 classifyError 处理网络错误 / 超时 / HTTP 4xx 5xx
  return classifyError(error).message;
}
