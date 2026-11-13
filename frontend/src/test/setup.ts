import '@testing-library/jest-dom/vitest';
import { cleanup } from '@testing-library/react';
import { afterAll, afterEach, beforeAll, beforeEach } from 'vitest';
import { server } from './server';
import { installMemoryStorage } from './storage';

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }));

// The player id lives in localStorage: every test starts with an empty one.
// (Files that run in the node environment have no window.)
beforeEach(() => {
  if (typeof window !== 'undefined') installMemoryStorage();
});

afterEach(() => {
  cleanup();
  server.resetHandlers();
});

afterAll(() => server.close());
