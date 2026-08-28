import { defineConfig, type Plugin } from 'vite';
import react from '@vitejs/plugin-react';
import path from 'path';

/**
 * Vite plugin that provides an ESM wrapper for `react-is` (TD-031).
 *
 * Why: react-is ships CJS-only with named exports assigned via
 * `exports.isFragment = isFragment` inside a wrapped factory. Vite 8's Rolldown
 * pre-bundler cannot statically detect those named exports and only emits a default
 * export. Consumers like `@rc-component/util/es/ref.js` do
 * `import { ForwardRef, isMemo } from 'react-is'` and fail with
 * "does not provide an export named 'isFragment'".
 *
 * Fix: intercept the bare specifier `react-is` and serve a virtual ESM module that
 * imports the pre-bundled default (which IS the full CJS exports object at runtime)
 * and re-exports its named members as proper ESM named exports.
 *
 * Loop avoidance: the virtual module imports via the deep path `react-is/index.js`,
 * which does NOT match the bare-specifier intercept in resolveId, so the import
 * resolves through Vite's normal pre-bundling (which provides the default export).
 */
function reactIsEsmShim(): Plugin {
  const VIRTUAL_ID = '\0virtual:react-is';
  return {
    name: 'react-is-esm-shim',
    enforce: 'pre',
    resolveId(source) {
      // Only intercept the bare specifier; let deep imports like 'react-is/index.js'
      // fall through to Vite's normal resolution so the virtual module can use them
      // to load the actual pre-bundled default without looping.
      if (source === 'react-is') {
        return VIRTUAL_ID;
      }
      return null;
    },
    load(id) {
      if (id !== VIRTUAL_ID) return null;
      // Import the pre-bundled default (the full CJS exports object) and re-export
      // every named member that react-is defines. Pulling them off the default is
      // safe at runtime because the CJS factory populates them on module.exports.
      return [
        "import reactIs from 'react-is/index.js';",
        'const ri = (reactIs && reactIs.default) ? reactIs.default : reactIs;',
        'export const typeOf = ri.typeOf;',
        'export const AsyncMode = ri.AsyncMode;',
        'export const ConcurrentMode = ri.ConcurrentMode;',
        'export const ContextConsumer = ri.ContextConsumer;',
        'export const ContextProvider = ri.ContextProvider;',
        'export const Element = ri.Element;',
        'export const ForwardRef = ri.ForwardRef;',
        'export const Fragment = ri.Fragment;',
        'export const Lazy = ri.Lazy;',
        'export const Memo = ri.Memo;',
        'export const Portal = ri.Portal;',
        'export const Profiler = ri.Profiler;',
        'export const StrictMode = ri.StrictMode;',
        'export const Suspense = ri.Suspense;',
        'export const SuspenseList = ri.SuspenseList;',
        'export const isAsyncMode = ri.isAsyncMode;',
        'export const isConcurrentMode = ri.isConcurrentMode;',
        'export const isContextConsumer = ri.isContextConsumer;',
        'export const isContextProvider = ri.isContextProvider;',
        'export const isElement = ri.isElement;',
        'export const isForwardRef = ri.isForwardRef;',
        'export const isFragment = ri.isFragment;',
        'export const isLazy = ri.isLazy;',
        'export const isMemo = ri.isMemo;',
        'export const isPortal = ri.isPortal;',
        'export const isProfiler = ri.isProfiler;',
        'export const isStrictMode = ri.isStrictMode;',
        'export const isSuspense = ri.isSuspense;',
        'export const isSuspenseList = ri.isSuspenseList;',
        'export const isValidElementType = ri.isValidElementType;',
        'export default ri;',
      ].join('\n');
    },
  };
}

// 从环境变量读取后端地址（N196: 统一配置归一化）
// frontend/.env 文件设置 VITE_BACKEND_HOST / VITE_BACKEND_PORT
const backendHost = process.env.VITE_BACKEND_HOST || '127.0.0.1';
const backendPort = process.env.VITE_BACKEND_PORT || '8000';

export default defineConfig({
  plugins: [react(), reactIsEsmShim()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, 'src'),
    },
  },
  server: {
    host: '127.0.0.1',
    hmr: { overlay: false },
    proxy: {
      '/api': {
        target: `http://${backendHost}:${backendPort}`,
        changeOrigin: true,
      },
      '/ws': {
        target: `ws://${backendHost}:${backendPort}`,
        ws: true,
      },
    },
  },
  optimizeDeps: {
    // Ensure react-is (and its deep index path used by the ESM shim) is pre-bundled
    // so the CJS factory is converted to a default export the shim can consume.
    include: ['react-is', 'react-is/index.js'],
  },
  build: {
    // Manual chunk splitting (TD-025): keep large vendor libs in their own chunks so
    // they cache independently and don't bloat the entry / page chunks. React.lazy on
    // every page route (see App.tsx) handles per-page splitting; this config handles
    // the heavy vendor deps that would otherwise be inlined into the first page chunk
    // each route imports.
    //
    // Rolldown's manualChunks takes a FUNCTION (not the Rollup object form) — return
    // a chunk name to assign the module to that chunk, or null to leave it default.
    rolldownOptions: {
      output: {
        manualChunks(id): string | undefined {
          // Only split node_modules; app code is split per-route by React.lazy.
          if (!id.includes('node_modules')) return undefined;
          // Match on the path segment after node_modules to avoid false positives
          // (e.g. 'react-intl' would match a naive 'react' substring check).
          // Strip everything up to and including 'node_modules/' then inspect.
          const segments = id.split(/[\\/]/);
          const nmIdx = segments.lastIndexOf('node_modules');
          if (nmIdx === -1) return undefined;
          // Handle scoped packages: @scope/name → take scope + name.
          const isScoped = segments[nmIdx + 1].startsWith('@');
          const pkgName = isScoped ? `${segments[nmIdx + 1]}/${segments[nmIdx + 2]}` : segments[nmIdx + 1];

          // React core + router + intl (but NOT react-resizable-panels, react-is, etc.)
          if (
            pkgName === 'react' ||
            pkgName === 'react-dom' ||
            pkgName === 'react-router-dom' ||
            pkgName === 'react-router' ||
            pkgName === 'react-intl'
          ) {
            return 'vendor-react';
          }
          // Ant Design + icons
          if (pkgName === 'antd' || pkgName === '@ant-design') {
            return 'vendor-antd';
          }
          // Monaco editor (heavy, only loaded by code editor pages)
          if (pkgName === 'monaco-editor' || pkgName === '@monaco-editor') {
            return 'vendor-monaco';
          }
          // React Flow (used only by PipelineEditor)
          if (pkgName === '@xyflow') {
            return 'vendor-xyflow';
          }
          // Recharts (used only by analytics dashboards)
          if (pkgName === 'recharts') {
            return 'vendor-recharts';
          }
          // FullCalendar (used only by ScheduledTasks)
          if (pkgName === '@fullcalendar') {
            return 'vendor-fullcalendar';
          }
          return undefined;
        },
      },
    },
  },
});
