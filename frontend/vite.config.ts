import react from '@vitejs/plugin-react';
import { defineConfig } from 'vitest/config';

export default defineConfig({
  plugins: [react()],
  server: {
    // One origin in development: the browser calls /api on the Vite server, which passes it on.
    proxy: { '/api': 'http://localhost:8000' },
    // shared/ at the repo root holds data both apps read (game-topics.json).
    fs: { allow: ['..'] },
  },
  test: {
    environment: 'jsdom',
    setupFiles: ['./src/test/setup.ts'],
    css: { modules: { classNameStrategy: 'non-scoped' } },
  },
});
