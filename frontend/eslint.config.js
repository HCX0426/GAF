import js from '@eslint/js';
import globals from 'globals';
import reactHooks from 'eslint-plugin-react-hooks';
import reactRefresh from 'eslint-plugin-react-refresh';
import tseslint from 'typescript-eslint';
import { defineConfig, globalIgnores } from 'eslint/config';

export default defineConfig([
  globalIgnores(['dist', 'coverage']),
  {
    files: ['**/*.{ts,tsx}'],
    extends: [
      js.configs.recommended,
      tseslint.configs.recommended,
      reactHooks.configs.flat.recommended,
      reactRefresh.configs.vite,
    ],
    languageOptions: {
      globals: globals.browser,
    },
    rules: {
      // TD-409: react-hooks v7 flat recommended 引入了 React Compiler 配套规则
      // (set-state-in-effect / immutability / refs / purity / preserve-manual-memoization).
      // GAF 未启用 React Compiler，这些规则在存量 effect/render 模式上以 error 级
      // 误报 134 条（~80 文件）。降级为 warn 保留可见性，待 Compiler 迁移或
      // effect 重构时再回归 error。
      'react-hooks/set-state-in-effect': 'warn',
      'react-hooks/immutability': 'warn',
      'react-hooks/refs': 'warn',
      'react-hooks/purity': 'warn',
      'react-hooks/preserve-manual-memoization': 'warn',
    },
  },
  // WebSocketProvider 约定导出 Provider 组件 + 配套 useWebSocketContext Hook
  // (react-refresh: 组件文件只应导出组件, Hook 需显式放行)。
  {
    files: ['src/providers/WebSocketProvider.tsx'],
    rules: {
      'react-refresh/only-export-components': ['error', { allowExportNames: ['useWebSocketContext'] }],
    },
  },
  // TD-335 P0 #3: Ban hardcoded Chinese literals to prevent i18n regression.
  // Excludes i18n locale source files and test files (test descriptions often
  // use Chinese for clarity). Set to 'warn' so existing violations don't
  // break the build — incremental cleanup tracked in TD-335.
  {
    files: ['**/*.{ts,tsx}'],
    ignores: [
      'src/i18n/locales/**',
      'src/i18n/LanguageSwitcher.tsx',
      'src/**/*.test.{ts,tsx}',
      'src/**/__tests__/**',
      'e2e/**',
    ],
    rules: {
      'no-restricted-syntax': [
        'warn',
        {
          selector: 'Literal[value=/[\\u4e00-\\u9fff]/]',
          message: 'Avoid hardcoded Chinese in string literals — use i18n t() function (TD-335 P0 #3)',
        },
        {
          selector: 'JSXText[value=/[\\u4e00-\\u9fff]/]',
          message: 'Avoid hardcoded Chinese in JSX text — use i18n t() function (TD-335 P0 #3)',
        },
        {
          selector: 'TemplateElement[value.raw=/[\\u4e00-\\u9fff]/]',
          message: 'Avoid hardcoded Chinese in template literals — use i18n t() function (TD-335 P0 #3)',
        },
      ],
    },
  },
]);
