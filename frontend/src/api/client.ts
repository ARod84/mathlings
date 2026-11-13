import createClient from 'openapi-fetch';
import { getPlayerId, PLAYER_ID_HEADER } from './player';
import type { paths } from './schema';

/*
 * The one API client. Its types come from schema.d.ts, which is generated
 * from the repo-root openapi.json with `npm run api:types`.
 *
 * VITE_API_BASE_URL is empty by default, which means "the origin this page
 * came from": in development Vite proxies /api to the backend (see
 * vite.config.ts), so the browser only ever talks to one origin.
 */
const configured: string | undefined = import.meta.env.VITE_API_BASE_URL;

export const apiBaseUrl = configured || window.location.origin;

export const api = createClient<paths>({
  baseUrl: apiBaseUrl,
  // Looked up on every call, not captured once here, so anything that wraps
  // the global fetch later (the mock server in tests, for one) is honored.
  fetch: (request) => globalThis.fetch(request),
});

/*
 * Puzzle requests carry the anonymous player id, when this device has one, so
 * the backend can keep practice history. Without an id (storage blocked) the
 * header is left out and the backend stores nothing. See player.ts.
 */
api.use({
  onRequest({ request, schemaPath }) {
    if (!schemaPath.startsWith('/api/v1/puzzles')) return undefined;
    const playerId = getPlayerId();
    if (playerId !== null) request.headers.set(PLAYER_ID_HEADER, playerId);
    return request;
  },
});
