import { http, HttpResponse } from 'msw';
import { beforeEach, describe, expect, it } from 'vitest';
import { createPuzzleBackend, type PuzzleBackend } from '../test/puzzleBackend';
import { server } from '../test/server';
import { apiBaseUrl } from './client';
import { checkStep, getHint, getPuzzle, newMissingNumber } from './puzzles';

let backend: PuzzleBackend;

beforeEach(() => {
  backend = createPuzzleBackend();
  server.use(...backend.handlers);
});

async function newPuzzleId(): Promise<string> {
  const result = await newMissingNumber({ level: 1, length: 2 });
  if (result.status !== 'ok') throw new Error('expected a puzzle');
  return result.data.puzzle_id;
}

describe('puzzle API functions', () => {
  it('uses the page origin when no base URL is configured', () => {
    expect(apiBaseUrl).toBe(window.location.origin);
  });

  it('newMissingNumber posts the level and length and returns the puzzle', async () => {
    const result = await newMissingNumber({ level: 2, length: 3 });

    expect(backend.requests.new).toEqual([{ level: 2, length: 3, seed: undefined }]);
    expect(result.status).toBe('ok');
    if (result.status !== 'ok') return;
    expect(result.data.level).toBe(2);
    expect(result.data.steps).toHaveLength(3);
    expect(result.data.steps[0]?.options).toEqual([2, 3, 19, 4]);
  });

  it('passes a seed through when given', async () => {
    await newMissingNumber({ level: 1, length: 2, seed: 42 });
    expect(backend.requests.new[0]?.seed).toBe(42);
  });

  it('getPuzzle fetches a puzzle by id', async () => {
    const puzzleId = await newPuzzleId();
    const result = await getPuzzle(puzzleId);

    expect(backend.requests.get).toEqual([puzzleId]);
    expect(result).toMatchObject({ status: 'ok', data: { puzzle_id: puzzleId, length: 2 } });
  });

  it('checkStep sends the answer and returns the result', async () => {
    const puzzleId = await newPuzzleId();

    const right = await checkStep(puzzleId, 0, 3);
    const wrong = await checkStep(puzzleId, 0, 19);

    expect(backend.requests.check).toEqual([
      { puzzleId, step: 0, answer: 3 },
      { puzzleId, step: 0, answer: 19 },
    ]);
    expect(right).toMatchObject({ status: 'ok', data: { correct: true, next_step: 1 } });
    expect(wrong).toMatchObject({
      status: 'ok',
      data: { correct: false, feedback: 'try_again', next_step: null },
    });
  });

  it('getHint asks for one tier', async () => {
    const puzzleId = await newPuzzleId();
    const result = await getHint(puzzleId, 1, 2);

    expect(backend.requests.hint).toEqual([{ puzzleId, step: 1, tier: 2 }]);
    expect(result).toEqual({
      status: 'ok',
      data: {
        tier: 2,
        text: 'A number take away 3 leaves 5. Put them back together: try 5 + 3.',
      },
    });
  });

  it.each([
    [404, 'notFound'],
    [410, 'gone'],
    [503, 'unavailable'],
    [500, 'unavailable'],
    [422, 'unavailable'],
    ['network', 'network'],
  ] as const)('turns a %s into "%s"', async (failure, status) => {
    const puzzleId = await newPuzzleId();
    const calls = {
      new: () => newMissingNumber({ level: 1, length: 2 }),
      get: () => getPuzzle(puzzleId),
      check: () => checkStep(puzzleId, 0, 3),
      hint: () => getHint(puzzleId, 0, 1),
    };

    for (const [route, call] of Object.entries(calls)) {
      backend.failNext(route as keyof typeof calls, failure);
      expect(await call(), route).toEqual({ status });
    }
  });

  it('an unknown puzzle id is "notFound"', async () => {
    expect(await getPuzzle('mnc-nope')).toEqual({ status: 'notFound' });
    expect(await checkStep('mnc-nope', 0, 1)).toEqual({ status: 'notFound' });
  });

  it('a success with no body is not treated as a puzzle', async () => {
    server.use(
      http.get('*/api/v1/puzzles/:puzzleId', () => new HttpResponse(null, { status: 204 })),
    );
    expect(await getPuzzle('anything')).toEqual({ status: 'unavailable' });
  });

  it('an aborted request settles without throwing', async () => {
    backend.delayMs = 100;
    const controller = new AbortController();
    const pending = newMissingNumber({ level: 1, length: 2 }, controller.signal);
    controller.abort();

    expect(await pending).toEqual({ status: 'network' });
  });
});
