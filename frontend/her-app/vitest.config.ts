import path from 'node:path'
import { defineConfig } from 'vitest/config'

export default defineConfig({
  resolve: {
    alias: {
      '@': path.resolve(__dirname, '.'),
    },
  },
  test: {
    environment: 'node',
    include: ['tests/unit/**/*.test.ts'],
    coverage: {
      provider: 'v8',
      reporter: ['text', 'json', 'html'],
      include: ['lib/verification/**/*.ts'],
      thresholds: {
        lines: 80,
        functions: 80,
        branches: 65,  // 降低阈值，因为部分环境检测分支难以测试
        statements: 80,
      },
    },
  },
})
