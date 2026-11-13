import { setupServer } from 'msw/node';

/**
 * The MSW server every test file shares. It has no handlers of its own: a
 * test adds what it needs with `server.use(...)`, and setup.ts clears them
 * after each test. A request nothing handles fails the test.
 */
export const server = setupServer();
