import '@testing-library/jest-dom';
import { afterEach } from 'vitest';
// mock-socket patches global.WebSocket when imported, providing a working
// implementation for jsdom (which does not implement WebSocket natively).
// Pattern B hooks (useNotificationWebSocket, useLogStream) that call
// `new WebSocket(url)` directly are covered by this global patch.
// Pattern A hooks (useWebSocket, useScreenshotStream, WebSocketProvider) use
// the wsClient singleton and are covered by per-test `vi.mock('@/websocket/client')`.
import { Server as MockSocketServer } from 'mock-socket';

class ResizeObserverMock {
  observe() {}
  unobserve() {}
  disconnect() {}
}

window.ResizeObserver = ResizeObserverMock as unknown as typeof ResizeObserver;

window.matchMedia =
  window.matchMedia ||
  function mockMatchMedia() {
    return {
      matches: false,
      addListener() {},
      removeListener() {},
      addEventListener() {},
      removeEventListener() {},
      dispatchEvent() {
        return false;
      },
    } as unknown as MediaQueryList;
  };

const mockComputedStyle = () =>
  ({
    getPropertyValue: () => '',
  }) as unknown as CSSStyleDeclaration;

Object.defineProperty(window, 'getComputedStyle', {
  value: mockComputedStyle,
  writable: true,
});

// Polyfill: antd rc-table CJS bug references undeclared PerfContext, clsx, and MeasureRow
// as bare globals in Body/index.js (should be _PerfContext.default etc.)
import clsx from 'clsx';
import { createContext, type FunctionComponent } from 'react';

const globalWithPolyfills = globalThis as typeof globalThis & {
  PerfContext?: ReturnType<typeof createContext<unknown>>;
  clsx?: typeof clsx;
  MeasureRow?: FunctionComponent<Record<string, unknown>>;
};

if (!globalWithPolyfills.PerfContext) {
  globalWithPolyfills.PerfContext = createContext<unknown>(undefined as unknown);
}
if (!globalWithPolyfills.clsx) {
  globalWithPolyfills.clsx = clsx;
}
// MeasureRow is only used for column width measurement in browsers; jsdom doesn't
// support layout, so a null-rendering stub is sufficient for tests.
if (!globalWithPolyfills.MeasureRow) {
  globalWithPolyfills.MeasureRow = () => null;
}

// Set default locale for Chinese text assertions in jsdom
if (!localStorage.getItem('gaf_locale')) {
  localStorage.setItem('gaf_locale', 'zh-CN');
}

// Track mock-socket servers so they can be stopped between tests, preventing
// state leakage across the suite. mock-socket intercepts `new WebSocket(url)`
// globally; each Pattern B test creates a server bound to its WS URL.
const mockServers: MockSocketServer[] = [];

afterEach(() => {
  while (mockServers.length > 0) {
    const server = mockServers.pop();
    server?.stop(() => {});
  }
});

export { mockServers, MockSocketServer };
