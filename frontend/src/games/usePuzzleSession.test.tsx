import { act, renderHook, waitFor } from '@testing-library/react';
import { http, HttpResponse } from 'msw';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { PLAYER_ID_KEY } from '../api/player';
import { CHAIN, createPuzzleBackend, type PuzzleBackend } from '../test/puzzleBackend';
import { server } from '../test/server';
import { usePuzzleSession, type PuzzleSessionConfig } from './usePuzzleSession';

/*
 * The session on its own, with a config that is not the Missing Number game's:
 * another round size, another kind of plan, another idea of hint tiers. What
 * the game's own screen does with a session is tested in missing-number/.
 */

const FAST = { advanceMs: 5, finishMs: 5 };

type Plan = 'ask' | { length: number };

type Config = PuzzleSessionConfig<'missing-number', Plan, 1 | 2 | 3>;

const hintTiers = vi.fn<Config['hintTiers']>(() => 2);

const [FIRST] = CHAIN;
if (!FIRST) throw new Error('the fixture chain is empty');
const RIGHT = FIRST.answer;
const WRONG = FIRST.options.find((option) => option !== RIGHT) ?? -1;

const CONFIG: Config = {
  game: 'missing-number',
  roundSize: 2,
  asksBackend: (plan) => plan === 'ask',
  fixedLevel: (plan) => (plan === 'ask' ? null : 3),
  choose: (plan, puzzleIndex, recommended) =>
    plan === 'ask'
      ? { level: 2, request: { level: 2, length: recommended?.length ?? 1, seed: puzzleIndex } }
      : { level: 3, request: { level: 3, length: plan.length } },
  hintTiers,
};

let backend: PuzzleBackend;
let nextCalls: (string | null)[];

beforeEach(() => {
  backend = createPuzzleBackend();
  nextCalls = [];
  hintTiers.mockClear();
  server.use(
    ...backend.handlers,
    http.get('*/api/v1/players/me/next', ({ request }) => {
      nextCalls.push(new URL(request.url).searchParams.get('game'));
      return HttpResponse.json({
        level: 2,
        length: 2,
        reason_code: 'consolidate',
        reason: 'for adults',
        focus_rule: null,
        focus: null,
        mastery: [],
      });
    }),
  );
  vi.spyOn(console, 'debug').mockImplementation(() => {});
});

const playing = (session: { current: ReturnType<typeof render>['result']['current'] }) =>
  waitFor(() => expect(session.current.state.phase).toBe('playing'));

function render() {
  return renderHook(() => usePuzzleSession(CONFIG, FAST));
}

async function answer(result: ReturnType<typeof render>['result'], value: number) {
  act(() => result.current.select(value));
  act(() => result.current.check());
  await waitFor(() => expect(result.current.state.checking).toBe(false));
}

describe('usePuzzleSession', () => {
  it('starts on the start screen, with the round size from the config', () => {
    const { result } = render();

    expect(result.current.state.phase).toBe('choose-level');
    expect(result.current.roundSize).toBe(2);
    expect(result.current.locked).toBe(true);
    expect(result.current.canHint).toBe(false);
  });

  it('a plan that fixes everything sends its request as it is and never asks the backend', async () => {
    const { result } = render();

    act(() => result.current.start({ length: 2 }));
    // The level the plan fixes is known while the puzzle is still loading.
    expect(result.current.state).toMatchObject({ phase: 'loading', level: 3 });
    await playing(result);

    expect(nextCalls).toEqual([]);
    expect(backend.newBodies).toEqual([{ level: 3, length: 2 }]);
    expect(result.current.state.puzzle?.steps).toHaveLength(2);
  });

  it('a plan that asks the backend names the game, and hands the answer to the config', async () => {
    window.localStorage.setItem(PLAYER_ID_KEY, '2f1c4a52-6d0e-4b7a-9a3e-0c5d8e1f2a3b');
    const { result } = render();

    act(() => result.current.start('ask'));
    expect(result.current.state).toMatchObject({ phase: 'loading', level: null });
    await playing(result);

    expect(nextCalls).toEqual(['missing-number']);
    // length 2 is what /next said; the rest is the config's own.
    expect(backend.newBodies).toEqual([{ level: 2, length: 2, seed: 0 }]);
    expect(result.current.state.level).toBe(2);
  });

  it('without an answer from the backend the config still chooses', async () => {
    // /next fails, so `recommended` is null. The child is not told.
    server.use(http.get('*/api/v1/players/me/next', () => HttpResponse.error()));
    const { result } = render();

    act(() => result.current.start('ask'));
    await playing(result);

    expect(result.current.state.phase).toBe('playing');
    expect(backend.newBodies).toEqual([{ level: 2, length: 1, seed: 0 }]);
  });

  it('the round is as long as the config says', async () => {
    const { result } = render();
    act(() => result.current.start({ length: 1 }));
    await playing(result);

    await answer(result, RIGHT);
    await waitFor(() => expect(result.current.state.feedback).toBe('solved'));
    act(() => result.current.next());
    await waitFor(() => expect(result.current.state.puzzleIndex).toBe(1));
    await playing(result);
    await answer(result, RIGHT);

    // The second puzzle of two ends the round.
    await waitFor(() => expect(result.current.state.feedback).toBe('complete'));
    act(() => result.current.next());
    expect(result.current.state.phase).toBe('choose-level');
  });

  it('hint tiers come from the config, for the hint button and for the automatic hint', async () => {
    const { result } = render();
    act(() => result.current.start({ length: 1 }));
    await playing(result);
    expect(result.current.canHint).toBe(true);

    // Two wrong tries open tier 1 by itself: with two tiers, tier 1 is not the last.
    await answer(result, WRONG);
    expect(result.current.state.hintTier).toBe(0);
    await answer(result, WRONG);
    await waitFor(() => expect(result.current.state.hintTier).toBe(1));
    expect(backend.requests.hint).toHaveLength(1);

    // The config says two tiers, so the second one is the end, whatever the puzzle says.
    act(() => result.current.requestHint());
    await waitFor(() => expect(result.current.state.hintTier).toBe(2));
    expect(result.current.canHint).toBe(false);
    act(() => result.current.requestHint());
    expect(backend.requests.hint).toHaveLength(2);
    expect(hintTiers).toHaveBeenCalledWith(result.current.state.puzzle, 0);
  });

  it('a puzzle from an older version is replaced by one picked the same way', async () => {
    const { result } = render();
    act(() => result.current.start({ length: 2 }));
    await playing(result);
    const first = result.current.state.puzzle?.puzzle_id;

    backend.failNext('check', 410);
    act(() => result.current.select(RIGHT));
    act(() => result.current.check());

    await waitFor(() => expect(result.current.state.puzzle?.puzzle_id).not.toBe(first));
    await playing(result);
    expect(backend.newBodies).toEqual([
      { level: 3, length: 2 },
      { level: 3, length: 2 },
    ]);
    expect(result.current.state.puzzleIndex).toBe(0);
  });

  it('a failed load shows the error, and retry loads the same puzzle of the round', async () => {
    const { result } = render();
    backend.failNext('new', 503);

    act(() => result.current.start({ length: 2 }));
    await waitFor(() => expect(result.current.state.phase).toBe('error'));
    act(() => result.current.retry());
    await playing(result);

    expect(backend.newBodies).toHaveLength(2);
    expect(result.current.state.puzzleIndex).toBe(0);
  });

  it('drops what arrives after the game is left', async () => {
    backend.delayMs = 30;
    const { result, unmount } = render();
    act(() => result.current.start({ length: 2 }));

    unmount();
    await new Promise((resolve) => setTimeout(resolve, 80));

    expect(result.current.state.phase).toBe('loading');
  });
});
