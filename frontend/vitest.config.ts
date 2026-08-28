import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';
import path from 'path';

// Vitest config — jsdom environment for @testing-library/react tests
// (vite.config.ts has no test section, so tests need this separate config)
export default defineConfig({
  plugins: [react()],
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
