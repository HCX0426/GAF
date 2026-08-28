import { describe, it, expect } from 'vitest';
import { resolveErrorMessage, getBusinessCode, getBusinessMessage } from '@/utils/errorHandler';

describe('resolveErrorMessage', () => {
  it('reads businessCode and returns mapped i18n message', () => {
    const error = {
      name: 'AxiosError',
      isAxiosError: true,
      response: { status: 400, data: null },
      businessCode: 3001, // DEVICE_OFFLINE
      businessMessage: '设备离线',
      message: '设备离线',
    };
    const msg = resolveErrorMessage(error);
    // 应该精确返回 i18n 中 DEVICE_OFFLINE (3001) 的对应文案, 防止 i18n 失效降级到 businessMessage 漏检
    expect(msg).toBe('设备离线, 请检查设备连接');
  });

  it('falls back to businessMessage when no i18n mapping', () => {
    const error = {
      businessCode: 9999,
      businessMessage: '未知业务错误',
      name: 'AxiosError',
      message: '未知业务错误',
    };
    const msg = resolveErrorMessage(error);
    expect(msg).toBe('未知业务错误');
  });

  it('falls back to network message on TypeError', () => {
    const error = new TypeError('Failed to fetch');
    const msg = resolveErrorMessage(error);
    expect(msg).toBeTruthy();
  });
});

describe('getBusinessCode', () => {
  it('extracts businessCode from axios error', () => {
    const error = { businessCode: 3001, name: 'AxiosError' };
    expect(getBusinessCode(error)).toBe(3001);
  });

  it('returns null on plain errors', () => {
    expect(getBusinessCode(new Error('foo'))).toBeNull();
  });
});

describe('getBusinessMessage', () => {
  it('extracts businessMessage from axios error', () => {
    const error = { businessMessage: '设备离线', name: 'AxiosError' };
    expect(getBusinessMessage(error)).toBe('设备离线');
  });

  it('returns null on plain errors', () => {
    expect(getBusinessMessage(new Error('foo'))).toBeNull();
  });
});

describe('resolveErrorMessage edge cases', () => {
  it('handles null error without throwing', () => {
    const msg = resolveErrorMessage(null);
    expect(typeof msg).toBe('string');
    expect(msg.length).toBeGreaterThan(0);
  });

  it('handles undefined error without throwing', () => {
    const msg = resolveErrorMessage(undefined);
    expect(typeof msg).toBe('string');
    expect(msg.length).toBeGreaterThan(0);
  });

  it('handles plain string error', () => {
    const msg = resolveErrorMessage('something went wrong');
    expect(typeof msg).toBe('string');
    expect(msg.length).toBeGreaterThan(0);
  });

  it('falls back to classifyError when businessMessage is empty string', () => {
    const error = {
      businessCode: 9999, // 未映射
      businessMessage: '', // 空字符串 → 应跳过降级到 classifyError
      name: 'AxiosError',
      message: 'network error',
    };
    const msg = resolveErrorMessage(error);
    expect(msg).not.toBe(''); // 不应该是空字符串
  });

  it('handles businessCode = 0 (SUCCESS) without throwing', () => {
    const error = {
      businessCode: 0,
      businessMessage: 'ok',
      name: 'AxiosError',
    };
    const msg = resolveErrorMessage(error);
    // businessCode=0 应该命中 i18n 'error.codes.0' = '操作成功'
    expect(msg).toBe('操作成功');
  });

  it('handles string-typed businessCode by returning null', () => {
    // getBusinessCode 类型守卫应拒绝字符串
    const error = { businessCode: '3001', name: 'AxiosError' };
    expect(getBusinessCode(error)).toBeNull();
  });

  it('handles NodeErrorCode string mapping', () => {
    // NodeErrorCode 字符串也能通过 resolveErrorMessage 映射
    // 注意: 当前 resolveErrorMessage 只查 businessCode (number|null)
    // 所以这个测试验证 getBusinessCode 对字符串返回 null, 然后降级到 businessMessage
    const error = {
      businessCode: 'NO_MATCH', // 字符串, getBusinessCode 返回 null
      businessMessage: '未找到匹配',
      name: 'AxiosError',
    };
    const msg = resolveErrorMessage(error);
    // businessCode 字符串被拒, 降级到 businessMessage
    expect(msg).toBe('未找到匹配');
  });
});
