import { http, HttpResponse } from 'msw';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { createPuzzleBackend } from '../test/puzzleBackend';
import { server } from '../test/server';
import { blockStorage } from '../test/storage';
import { forgetPlayer, getPlayerId, PLAYER_ID_KEY } from './player';
import { checkStep, getHint, getPuzzle, newMissingNumber } from './puzzles';

const UUID_V4 = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;

/** A pretend DELETE /players/me that notes the id it was asked to delete. */
function deleteEndpoint(status = 204) {
  const deleted: (string | null)[] = [];
  server.use(
    http.delete('*/api/v1/players/me', ({ request }) => {
      deleted.push(request.headers.get('X-Player-Id'));
      return new HttpResponse(null, { status });
    }),
  );
  return deleted;
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe('getPlayerId', () => {
  it('makes a UUID v4 on first use, stores it, and reuses it', () => {
    expect(window.localStorage.getItem(PLAYER_ID_KEY)).toBeNull();

    const first = getPlayerId();

    expect(first).toMatch(UUID_V4);
    expect(window.localStorage.getItem(PLAYER_ID_KEY)).toBe(first);
    expect(getPlayerId()).toBe(first);
    expect(getPlayerId()).toBe(first);
  });

  it('keeps an id that is already there', () => {
    const existing = '3f2b8c1e-5d4a-4b6f-9a7e-1c2d3e4f5a6b';
    window.localStorage.setItem(PLAYER_ID_KEY, existing);

    expect(getPlayerId()).toBe(existing);
  });

  it('replaces a stored value that is not a UUID v4', () => {
    window.localStorage.setItem(PLAYER_ID_KEY, 'Mia, age 8');

    const id = getPlayerId();

    expect(id).toMatch(UUID_V4);
    expect(window.localStorage.getItem(PLAYER_ID_KEY)).toBe(id);
  });

  it('is null when localStorage throws, and does not crash', () => {
    blockStorage();

    expect(getPlayerId()).toBeNull();
    expect(getPlayerId()).toBeNull();
  });

  it('is null when the id cannot be saved, so nothing is stored under an id that will be lost', () => {
    vi.spyOn(window.localStorage, 'setItem').mockImplementation(() => {
      throw new DOMException('Quota exceeded', 'QuotaExceededError');
    });

    expect(getPlayerId()).toBeNull();
  });

  it('writes nothing to cookies', () => {
    getPlayerId();
    expect(document.cookie).toBe('');
  });
});

describe('the X-Player-Id header', () => {
  it('is sent on every puzzle request, with the same id each time', async () => {
    const backend = createPuzzleBackend();
    server.use(...backend.handlers);

    const created = await newMissingNumber({ level: 1, length: 2 });
    if (created.status !== 'ok') throw new Error('expected a puzzle');
    const puzzleId = created.data.puzzle_id;
    await getPuzzle(puzzleId);
    await checkStep(puzzleId, 0, 3);
    await getHint(puzzleId, 0, 1);

    const id = window.localStorage.getItem(PLAYER_ID_KEY);
    expect(id).toMatch(UUID_V4);
    expect(backend.playerIds).toEqual([id, id, id, id]);
  });

  it('is left out when localStorage throws, and the calls still work', async () => {
    blockStorage();
    const backend = createPuzzleBackend();
    server.use(...backend.handlers);

    const created = await newMissingNumber({ level: 1, length: 2 });
    if (created.status !== 'ok') throw new Error('expected a puzzle');
    const checked = await checkStep(created.data.puzzle_id, 0, 3);
    const hint = await getHint(created.data.puzzle_id, 0, 1);

    expect(checked).toMatchObject({ status: 'ok', data: { correct: true } });
    expect(hint.status).toBe('ok');
    expect(backend.playerIds).toEqual([null, null, null]);
  });
});

describe('forgetPlayer', () => {
  it('calls DELETE with the id, clears the key, and the next request carries a new id', async () => {
    const backend = createPuzzleBackend();
    server.use(...backend.handlers);
    const deleted = deleteEndpoint();
    await newMissingNumber({ level: 1, length: 2 });
    const before = window.localStorage.getItem(PLAYER_ID_KEY);
    expect(before).toMatch(UUID_V4);

    expect(await forgetPlayer()).toBe('forgotten');

    expect(deleted).toEqual([before]);
    expect(window.localStorage.getItem(PLAYER_ID_KEY)).toBeNull();

    await newMissingNumber({ level: 1, length: 2 });
    const after = window.localStorage.getItem(PLAYER_ID_KEY);
    expect(after).toMatch(UUID_V4);
    expect(after).not.toBe(before);
    expect(backend.playerIds).toEqual([before, after]);
  });

  it('does not make an id just to delete it', async () => {
    const deleted = deleteEndpoint();

    expect(await forgetPlayer()).toBe('forgotten');

    expect(deleted).toEqual([]);
    expect(window.localStorage.getItem(PLAYER_ID_KEY)).toBeNull();
  });

  it.each([
    ['the server refuses', () => deleteEndpoint(503)],
    [
      'the server cannot be reached',
      () => server.use(http.delete('*/api/v1/players/me', () => HttpResponse.error())),
    ],
  ])('keeps the id when %s, so it can be tried again', async (_name, arrange) => {
    const id = getPlayerId();
    arrange();

    expect(await forgetPlayer()).toBe('failed');

    expect(window.localStorage.getItem(PLAYER_ID_KEY)).toBe(id);
  });

  it('settles without a request when localStorage throws', async () => {
    blockStorage();
    const deleted = deleteEndpoint();

    expect(await forgetPlayer()).toBe('forgotten');
    expect(deleted).toEqual([]);
  });
});
