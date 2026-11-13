import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { NextPuzzle } from '../../api/player';
import { PLAYER_ID_KEY } from '../../api/player';
import { CHAIN, createPuzzleBackend, type PuzzleBackend } from '../../test/puzzleBackend';
import { server } from '../../test/server';
import { blockStorage } from '../../test/storage';
import { MissingNumber } from './MissingNumber';
import { FALLBACK } from './useMissingNumberGame';

const FAST = { advanceMs: 20, finishMs: 20 };

type User = ReturnType<typeof userEvent.setup>;

/** Text that must never reach the child: every adult-facing part of a recommendation. */
const SECRET_REASON = 'Doing well: estimated 97% likely to know the level 1 topic.';
const SECRET_TOPIC = 'Unknown in Addition & Subtraction';

function recommendation(
  level: number,
  length: number,
  extra: Partial<NextPuzzle> = {},
): NextPuzzle {
  return {
    level,
    length,
    reason_code: 'consolidate',
    reason: SECRET_REASON,
    focus_rule: 'ADD_VISIBLE',
    focus: null,
    mastery: [
      { topic_id: 'mt_3JgrHY221M', name: SECRET_TOPIC, level, p_known: 0.9731, observations: 7 },
    ],
    ...extra,
  };
}

let backend: PuzzleBackend;
let debug: ReturnType<typeof vi.spyOn>;
/** What /next answers, one per call; the last one repeats. A number is a failure status. */
let answers: (NextPuzzle | number | 'network')[];
/** One entry per call to /next: the player id header and the game asked for. */
let nextCalls: { playerId: string | null; game: string | null }[];

beforeEach(() => {
  backend = createPuzzleBackend();
  answers = [recommendation(2, 3)];
  nextCalls = [];
  server.use(
    ...backend.handlers,
    http.get('*/api/v1/players/me/next', ({ request }) => {
      nextCalls.push({
        playerId: request.headers.get('X-Player-Id'),
        game: new URL(request.url).searchParams.get('game'),
      });
      const answer = answers.length > 1 ? answers.shift() : answers[0];
      if (answer === 'network') return HttpResponse.error();
      if (typeof answer === 'number') {
        return HttpResponse.json({ detail: 'Unavailable' }, { status: answer });
      }
      return HttpResponse.json(answer);
    }),
  );
  debug = vi.spyOn(console, 'debug').mockImplementation(() => {});
});

afterEach(() => {
  vi.restoreAllMocks();
});

const shell = () => screen.getByRole('region', { name: 'Missing Number Chains' });
const steps = () => within(screen.getByRole('list', { name: 'Steps' })).getAllByRole('listitem');
const option = (value: number) =>
  within(screen.getByRole('group', { name: 'Answer choices' })).getByRole('button', {
    name: String(value),
  });

async function play(user: User) {
  render(<MissingNumber timing={FAST} />);
  await user.click(screen.getByRole('button', { name: 'Play' }));
  await screen.findByRole('list', { name: 'Steps' });
}

/** Solves every step of the puzzle on screen, which is the first `length` steps of CHAIN. */
async function solvePuzzle(user: User, length: number) {
  for (let index = 0; index < length; index++) {
    const step = CHAIN[index];
    if (!step) throw new Error(`no fixture step ${index}`);
    await user.click(option(step.answer));
    await user.click(screen.getByRole('button', { name: 'Check' }));
    if (index < length - 1) await waitFor(() => expect(steps()).toHaveLength(index + 2));
  }
}

describe('start screen', () => {
  it('has one big Play button above a smaller row of ranges', () => {
    render(<MissingNumber />);

    const playButton = screen.getByRole('button', { name: 'Play' });
    const ranges = screen.getByRole('group', { name: 'Or choose a range' });
    expect(within(ranges).getAllByRole('button')).toHaveLength(3);
    expect(screen.getByText('Or choose a range')).toBeInTheDocument();
    // Play comes first in the page, so first for the keyboard and for screen readers.
    expect(
      playButton.compareDocumentPosition(ranges) & Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();
    // Nothing is asked of the server until the child picks something.
    expect(nextCalls).toEqual([]);
    expect(backend.requests.new).toEqual([]);
  });
});

describe('"Play" follows the recommendation', () => {
  it('uses the recommended level and chain length for the first puzzle', async () => {
    const user = userEvent.setup();
    await play(user);

    expect(nextCalls).toHaveLength(1);
    expect(nextCalls[0]?.game).toBe('missing-number');
    expect(backend.requests.new).toEqual([{ level: 2, length: 3, seed: undefined }]);
    expect(screen.getByText('1 / 5')).toBeInTheDocument();
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('Find the missing number');
  });

  it('sends the same player id to /next as to the puzzle routes', async () => {
    const user = userEvent.setup();
    await play(user);

    const id = window.localStorage.getItem(PLAYER_ID_KEY);
    expect(id).not.toBeNull();
    expect(nextCalls[0]?.playerId).toBe(id);
    expect(backend.playerIds).toEqual([id]);
  });

  it('asks /next again before every puzzle, and the round is still five puzzles', async () => {
    // A whole round is about thirty clicks. By default user-event waits on a
    // zero-length timer between the events of each click, and on Windows such
    // a timer takes about 12 ms, which alone brought this test close to the
    // 5 s limit. Nothing here depends on those waits: every result is awaited.
    const user = userEvent.setup({ delay: null });
    // The round adapts as it goes: up a level, longer chains, then back down.
    const plan = [
      [1, 2],
      [1, 3],
      [2, 2],
      [2, 4],
      [1, 2],
    ] as const;
    answers = plan.map(([level, length]) => recommendation(level, length));
    await play(user);

    for (const [index, [, length]] of plan.entries()) {
      expect(nextCalls).toHaveLength(index + 1);
      expect(screen.getByText(`${index + 1} / 5`)).toBeInTheDocument();
      await solvePuzzle(user, length);
      if (index < plan.length - 1) {
        await user.click(await screen.findByRole('button', { name: 'Next' }));
        await waitFor(() => expect(screen.getByText(`${index + 2} / 5`)).toBeInTheDocument());
        await waitFor(() => expect(steps()).toHaveLength(1));
      }
    }

    await screen.findByTestId('round-complete-screen');
    expect(shell()).toHaveAttribute('data-feedback', 'complete');
    expect(nextCalls).toHaveLength(5);
    expect(backend.requests.new.map((request) => [request.level, request.length])).toEqual(plan);

    // "Play again" goes back to the start screen without asking for anything.
    await user.click(screen.getByRole('button', { name: 'Play again' }));
    expect(screen.getByRole('button', { name: 'Play' })).toBeInTheDocument();
    expect(nextCalls).toHaveLength(5);
  });

  it('a chosen range never asks /next', async () => {
    const user = userEvent.setup();
    render(<MissingNumber timing={FAST} />);
    await user.click(screen.getByRole('button', { name: 'Up to 100' }));
    await screen.findByRole('list', { name: 'Steps' });
    await solvePuzzle(user, 2);
    await user.click(await screen.findByRole('button', { name: 'Next' }));
    await waitFor(() => expect(screen.getByText('2 / 5')).toBeInTheDocument());

    expect(nextCalls).toEqual([]);
    expect(backend.requests.new.map((request) => request.level)).toEqual([2, 2]);
  });
});

describe('"Play" falls back quietly', () => {
  it.each([
    ['the server refuses', 503],
    ['the server has an error', 500],
    ['the player is not understood', 422],
    ['there is no answer at all', 'network'],
  ] as const)('to level 1, length 2 when %s', async (_name, failure) => {
    const user = userEvent.setup();
    answers = [failure];
    await play(user);

    expect(FALLBACK).toEqual({ level: 1, length: 2 });
    expect(nextCalls).toHaveLength(1);
    expect(backend.requests.new).toEqual([{ level: 1, length: 2, seed: undefined }]);
    // No message: the child just gets a puzzle.
    expect(screen.queryByText(/couldn.t get your puzzle/)).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Try again' })).not.toBeInTheDocument();
    expect(steps()).toHaveLength(1);
  });

  it('to level 1, length 2 when the answer makes no sense', async () => {
    const user = userEvent.setup();
    answers = [recommendation(7, 3)];
    await play(user);

    expect(backend.requests.new).toEqual([{ level: 1, length: 2, seed: undefined }]);
  });

  it('without calling /next at all when there is no player id', async () => {
    blockStorage();
    const user = userEvent.setup();
    await play(user);

    expect(nextCalls).toEqual([]);
    expect(backend.requests.new).toEqual([{ level: 1, length: 2, seed: undefined }]);
    expect(backend.playerIds).toEqual([null]);

    // And the game still plays.
    await solvePuzzle(user, 2);
    await screen.findByTestId('solved-screen');
  });

  it('keeps trying /next for the later puzzles of the round', async () => {
    const user = userEvent.setup();
    answers = [500, recommendation(3, 4)];
    await play(user);
    await solvePuzzle(user, 2);
    await user.click(await screen.findByRole('button', { name: 'Next' }));
    await waitFor(() => expect(screen.getByText('2 / 5')).toBeInTheDocument());

    expect(backend.requests.new.map((request) => [request.level, request.length])).toEqual([
      [1, 2],
      [3, 4],
    ]);
  });

  it('"Try again" after a failed puzzle asks /next again', async () => {
    const user = userEvent.setup();
    backend.failNext('new', 503);
    render(<MissingNumber timing={FAST} />);
    await user.click(screen.getByRole('button', { name: 'Play' }));

    await user.click(await screen.findByRole('button', { name: 'Try again' }));
    await screen.findByRole('list', { name: 'Steps' });

    expect(nextCalls).toHaveLength(2);
    expect(backend.requests.new).toHaveLength(2);
  });
});

describe('what the child never sees', () => {
  it('no reason, mastery, topic name or focus rule anywhere in the page', async () => {
    const user = userEvent.setup();
    answers = [recommendation(1, 2, { reason_code: 'promote' })];
    const forbidden = [
      SECRET_REASON,
      SECRET_TOPIC,
      'ADD_VISIBLE',
      '0.9731',
      '97%',
      'promote',
      'mt_',
    ];
    const expectClean = () => {
      const page = document.body.innerHTML;
      for (const text of forbidden) expect(page, text).not.toContain(text);
    };

    await play(user);
    expectClean();
    // A wrong answer (the one the backend calls ADD_VISIBLE), then the whole puzzle.
    await user.click(option(19));
    await user.click(screen.getByRole('button', { name: 'Check' }));
    await waitFor(() => expect(shell()).toHaveAttribute('data-feedback', 'incorrect'));
    expectClean();
    await solvePuzzle(user, 2);
    await screen.findByTestId('solved-screen');
    expectClean();
    await user.click(screen.getByRole('button', { name: 'Next' }));
    await waitFor(() => expect(screen.getByText('2 / 5')).toBeInTheDocument());
    expectClean();
  });

  it('the recommendation is logged with console.debug for development, and only there', async () => {
    const user = userEvent.setup();
    const log = vi.spyOn(console, 'log').mockImplementation(() => {});
    await play(user);

    expect(debug).toHaveBeenCalledWith(
      '[missing-number] next',
      expect.objectContaining({ level: 2, length: 3, reason: SECRET_REASON }),
    );
    expect(log).not.toHaveBeenCalled();
  });
});

describe('focus: a mistake the backend wants the next puzzle to target', () => {
  it('is passed to the new-puzzle request when /next gives one', async () => {
    const user = userEvent.setup();
    answers = [recommendation(1, 3, { focus: 'ADD_VISIBLE' })];
    await play(user);

    expect(backend.newBodies).toEqual([{ level: 1, length: 3, focus: 'ADD_VISIBLE' }]);
  });

  it('is not sent at all when /next says null', async () => {
    const user = userEvent.setup();
    answers = [recommendation(1, 3, { focus: null, focus_rule: 'ADD_VISIBLE' })];
    await play(user);

    expect(backend.newBodies).toEqual([{ level: 1, length: 3 }]);
    expect(backend.newBodies[0]).not.toHaveProperty('focus');
  });

  it('follows /next puzzle by puzzle: focused, ordinary, focused', async () => {
    const user = userEvent.setup();
    answers = [
      recommendation(1, 2, { focus: 'POSITION_CONFUSION' }),
      recommendation(1, 2, { focus: null }),
      recommendation(1, 2, { focus: 'POSITION_CONFUSION' }),
    ];
    await play(user);
    for (const puzzle of [2, 3]) {
      await solvePuzzle(user, 2);
      await user.click(await screen.findByRole('button', { name: 'Next' }));
      await waitFor(() => expect(screen.getByText(`${puzzle} / 5`)).toBeInTheDocument());
      await waitFor(() => expect(steps()).toHaveLength(1));
    }

    expect(backend.newBodies.map((body) => body.focus)).toEqual([
      'POSITION_CONFUSION',
      undefined,
      'POSITION_CONFUSION',
    ]);
  });

  it('is never sent for a chosen range or for the fallback', async () => {
    const user = userEvent.setup();
    answers = [500];
    await play(user);
    expect(backend.newBodies).toEqual([{ level: 1, length: 2 }]);
  });

  it('changes nothing the child can see, and the rule name never reaches the page', async () => {
    const user = userEvent.setup();
    answers = [recommendation(1, 2, { focus: 'ANSWER_LEFT_BACKWARDS', focus_rule: null })];
    await play(user);

    expect(document.body.innerHTML).not.toContain('ANSWER_LEFT_BACKWARDS');
    expect(document.body.innerHTML.toLowerCase()).not.toContain('focus');
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('Find the missing number');
    expect(screen.getByText('1 / 5')).toBeInTheDocument();
  });

  it('a puzzle from an older generator still restarts quietly, asking /next again', async () => {
    const user = userEvent.setup();
    answers = [
      recommendation(1, 2, { focus: 'ADD_VISIBLE' }),
      recommendation(1, 2, { focus: null }),
    ];
    await play(user);
    const first = backend.requests.check.length;

    // The server answers 410 Gone to the check: the puzzle is from an older version.
    backend.failNext('check', 410);
    await user.click(option(3));
    await user.click(screen.getByRole('button', { name: 'Check' }));

    await waitFor(() => expect(backend.requests.new).toHaveLength(2));
    await waitFor(() => expect(steps()).toHaveLength(1));
    expect(backend.requests.check).toHaveLength(first + 1);
    expect(nextCalls).toHaveLength(2);
    // The replacement is whatever /next says now, not a copy of the old request.
    expect(backend.newBodies).toEqual([
      { level: 1, length: 2, focus: 'ADD_VISIBLE' },
      { level: 1, length: 2 },
    ]);
    expect(screen.queryByRole('button', { name: 'Try again' })).not.toBeInTheDocument();
    expect(screen.getByText('1 / 5')).toBeInTheDocument();
  });
});
