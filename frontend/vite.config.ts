/// <reference types="vitest" />
import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: './src/test/setup.ts',
    env: {
      // MSW registers its handlers on RELATIVE paths. apiFetch prefixes
      // VITE_API_BASE_URL (defaulting to http://localhost:8080) unless this flag is
      // set, so once apiFetch was introduced every request went to an absolute URL
      // and missed every handler — "intercepted a request without a matching request
      // handler". That, not stale assertions, is why the suite went red.
      VITE_USE_MOCK: 'true',
    },
  },
})