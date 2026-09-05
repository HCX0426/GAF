import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';
import path from 'path';

// Vitest config — jsdom environment for @testing-library/react tests
// (vite.config.ts has no test section, so tests need this separate config)
export default defineConfig({
  plugins: [react()],
  // P1 回归 (评审 2026-09-05): vitest 对部分含裸 JSX 的测试文件走 classic
  // JSX 运行时 (React.createElement), 而源码用 react-jsx 自动运行时、测试文件
  // 不 import React → "React is not defined"。jsxInject 给每个被转换文件注入
  // React, 兼容 classic 运行时, 不影响已用自动运行时的文件。
  esbuild: {
    jsxInject: "import React from 'react'",
  },
  resolve: {
    alias: {
      '@': path.resolve(__dirname, 'src'),
    },
  },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./src/test/setup.ts'],
    include: ['src/**/*.{test,spec}.{ts,tsx}'],
    exclude: ['node_modules', 'dist'],
    coverage: {
      provider: 'v8',
      reporter: ['text', 'html', 'lcov'],
      reportsDirectory: './coverage',
      thresholds: {
        lines: 40,
        branches: 30,
        functions: 35,
        statements: 40,
      },
      exclude: [
        'node_modules/',
        'dist/',
        'src/test/**',
        'src/main.tsx',
        'src/vite-env.d.ts',
        '**/*.config.*',
        '**/types/**',
      ],
    },
  },
});
