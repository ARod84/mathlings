import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { createPuzzleBackend, CHAIN, type PuzzleBackend } from '../../test/puzzleBackend';
import { server } from '../../test/server';
import { MissingNumber } from './MissingNumber';
import { ROUND_LENGTHS } from './useMissingNumberGame';

// Short pauses, so a whole round plays in well under a second.
const FAST = { advanceMs: 20, finishMs: 20 };

type User = ReturnType<typeof userEvent.setup>;

let backend: PuzzleBackend;
let debug: ReturnType<typeof vi.spyOn>;

beforeEach(() => {
  backend = createPuzzleBackend();
  server.use(...backend.handlers);
  debug = vi.spyOn(console, 'debug').mockImplementation(() => {});
});

afterEach(() => {
  debug.mockRestore();
});

const shell = () => screen.getByRole('region', { name: 'Missing Number Chains' });
const feedback = () => shell().getAttribute('data-feedback');
const options = () => within(screen.getByRole('group', { name: 'Answer choices' }));
const option = (value: number) => options().getByRole('button', { name: String(value) });
const steps = () => within(screen.getByRole('list', { name: 'Steps' })).getAllByRole('listitem');
const currentStep = () => {
  const current = steps().at(-1);
  if (!current) throw new Error('no current step');
  return current;
};
const box = () => within(currentStep()).getByTestId('answer-box');
const action = (name: 'Hint' | 'Check' | 'Reset') => screen.getByRole('button', { name });

/** Renders the game and starts a round at the given level. */
async function start(user: User, label = 'Up to 20', timing = FAST) {
  const view = render(<MissingNumber timing={timing} />);
  await user.click(screen.getByRole('button', { name: label }));
  await screen.findByRole('list', { name: 'Steps' });
  return view;
}

/** Answers the current step correctly and waits for what comes next. */
async function solveStep(user: User, index: number, isLast: boolean) {
  const step = CHAIN[index];
  if (!step) throw new Error(`no fixture step ${index}`);
  await user.click(option(step.answer));
  await user.click(action('Check'));
  if (isLast) return;
  await waitFor(() => expect(steps()).toHaveLength(index + 2));
}

describe('start screen', () => {
  it('offers three levels named by number range, and nothing else to do yet', () => {
    render(<MissingNumber />);

    const levels = within(screen.getByRole('group', { name: 'Number size' }));
    expect(levels.getAllByRole('button').map((button) => button.textContent)).toEqual([
      'Up to 20',
      'Up to 100',
      'Up to 1000',
    ]);
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent(
      'How big should the numbers be?',
    );
    expect(screen.getByText('0 / 5')).toBeInTheDocument();
    for (const name of ['Hint', 'Check', 'Reset'] as const) expect(action(name)).toBeDisabled();
    expect(backend.requests.new).toEqual([]);
  });

  it.each([
    ['Up to 20', 1],
    ['Up to 100', 2],
    ['Up to 1000', 3],
  ])('"%s" asks for a two-step puzzle at level %i', async (label, level) => {
    const user = userEvent.setup();
    await start(user, label);

    expect(backend.requests.new).toEqual([{ level, length: 2, seed: undefined }]);
    expect(screen.getByText('1 / 5')).toBeInTheDocument();
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('Find the missing number');
  });

  it('shows a calm placeholder while the puzzle loads', async () => {
    const user = userEvent.setup();
    backend.delayMs = 150;
    render(<MissingNumber timing={FAST} />);
    await user.click(screen.getByRole('button', { name: 'Up to 20' }));

    expect(screen.getByText('Loading your puzzle')).toBeInTheDocument();
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent(
      'Getting your puzzle ready',
    );
    expect(screen.getByTestId('play-area')).not.toBeEmptyDOMElement();
    expect(await screen.findByRole('list', { name: 'Steps' })).toBeInTheDocument();
  });
});

describe('playing a puzzle', () => {
  it('shows only the first step, with an empty box and four option buttons', async () => {
    const user = userEvent.setup();
    await start(user);

    expect(steps()).toHaveLength(1);
    expect(currentStep()).toHaveAttribute('aria-current', 'step');
    expect(box()).toBeEmptyDOMElement();
    expect(box()).toHaveAttribute('data-state', 'empty');
    expect(
      options()
        .getAllByRole('button')
        .map((button) => button.textContent),
    ).toEqual(['2', '3', '19', '4']);
    expect(action('Check')).toBeDisabled();
    // The second step is not in the page yet: its numbers would give this answer away.
    expect(screen.queryByText('5')).not.toBeInTheDocument();
  });

  it('reads each equation naturally to a screen reader', async () => {
    const user = userEvent.setup();
    await start(user);

    expect(currentStep()).toHaveAccessibleName('8 plus box equals 11');
    await user.click(option(3));
    expect(currentStep()).toHaveAccessibleName('8 plus box with 3 equals 11');

    await user.click(action('Check'));
    await waitFor(() => expect(steps()).toHaveLength(2));
    const [solved, current] = steps();
    expect(solved).toHaveAccessibleName('8 plus 3 equals 11');
    expect(current).toHaveAccessibleName('box minus 3 equals 5');
  });

  it('puts a tapped option in the box, and swaps it when another is tapped', async () => {
    const user = userEvent.setup();
    await start(user);

    await user.click(option(2));
    expect(box()).toHaveTextContent('2');
    expect(box()).toHaveAttribute('data-state', 'filled');
    expect(option(2)).toHaveAttribute('aria-pressed', 'true');
    expect(action('Check')).toBeEnabled();

    await user.click(option(3));
    expect(box()).toHaveTextContent('3');
    expect(option(2)).toHaveAttribute('aria-pressed', 'false');
    expect(option(3)).toHaveAttribute('aria-pressed', 'true');
    expect(backend.requests.check).toEqual([]);
  });

  it('plays a whole puzzle: check, next step with the found number highlighted, solved', async () => {
    const user = userEvent.setup();
    // A longer pause before the next step, so the locked moment can be looked at.
    await start(user, 'Up to 20', { advanceMs: 300, finishMs: 20 });
    const puzzleId = 'mnc-1-1-2-1-test';

    await user.click(option(3));
    await user.click(action('Check'));
    await waitFor(() => expect(feedback()).toBe('correct'));
    expect(backend.requests.check).toEqual([{ puzzleId, step: 0, answer: 3 }]);
    // The step locks while "correct" shows.
    expect(option(2)).toBeDisabled();
    expect(action('Check')).toBeDisabled();

    // The next step slides in under the solved one.
    await waitFor(() => expect(steps()).toHaveLength(2));
    const [solved, current] = steps();
    expect(solved).toHaveAttribute('data-state', 'solved');
    expect(within(solved as HTMLElement).getByTestId('answer-box')).toHaveTextContent('3');
    expect(current).toHaveAttribute('data-state', 'current');
    expect(feedback()).toBe('idle');
    // The 3 just found is the highlighted number in "□ − 3 = 5".
    const linked = current?.querySelector('[data-linked]');
    expect(linked).toHaveTextContent('3');
    expect(solved?.querySelector('[data-linked]')).toBeNull();
    expect(box()).toBeEmptyDOMElement();
    // Focus moves to the new step.
    await waitFor(() => expect(current).toHaveFocus());

    await user.click(option(8));
    await user.click(action('Check'));
    expect(await screen.findByTestId('solved-screen')).toBeInTheDocument();
    expect(feedback()).toBe('solved');
    expect(backend.requests.check).toHaveLength(2);
  });

  it('moves on to the next puzzle from the solved screen', async () => {
    const user = userEvent.setup();
    await start(user);
    await solveStep(user, 0, false);
    await solveStep(user, 1, true);

    await user.click(await screen.findByRole('button', { name: 'Next' }));

    await waitFor(() => expect(screen.getByText('2 / 5')).toBeInTheDocument());
    await waitFor(() => expect(steps()).toHaveLength(1));
    expect(backend.requests.new).toHaveLength(2);
    expect(currentStep()).toHaveAccessibleName('8 plus box equals 11');
    expect(feedback()).toBe('idle');
  });

  it('finishes the round after the fifth puzzle, then goes back to the start screen', async () => {
    const user = userEvent.setup();
    await start(user, 'Up to 100');

    for (const [puzzle, length] of ROUND_LENGTHS.entries()) {
      for (let step = 0; step < length; step++) await solveStep(user, step, step === length - 1);
      if (puzzle < ROUND_LENGTHS.length - 1) {
        await user.click(await screen.findByRole('button', { name: 'Next' }));
        await waitFor(() => expect(screen.getByText(`${puzzle + 2} / 5`)).toBeInTheDocument());
        await waitFor(() => expect(steps()).toHaveLength(1));
      }
    }

    const complete = await screen.findByTestId('round-complete-screen');
    expect(feedback()).toBe('complete');
    expect(within(complete).getByText(/all 5 puzzles/)).toBeInTheDocument();
    expect(screen.queryByTestId('solved-screen')).not.toBeInTheDocument();
    // Chain lengths 2, 2, 3, 3, 4, all at the chosen level.
    expect(backend.requests.new.map((request) => request.length)).toEqual([2, 2, 3, 3, 4]);
    expect(backend.requests.new.every((request) => request.level === 2)).toBe(true);

    await user.click(within(complete).getByRole('button', { name: 'Play again' }));
    expect(screen.getByRole('group', { name: 'Number size' })).toBeInTheDocument();
    expect(screen.getByText('0 / 5')).toBeInTheDocument();
    expect(backend.requests.new).toHaveLength(5);
  });
});

describe('wrong answers', () => {
  it('shows gentle feedback, keeps the box filled, and never shows the diagnosis', async () => {
    const user = userEvent.setup();
    await start(user);

    await user.click(option(19)); // 8 + 11: a mistake the server recognizes
    await user.click(action('Check'));

    await waitFor(() => expect(feedback()).toBe('incorrect'));
    expect(box()).toHaveTextContent('19');
    expect(option(19)).toHaveAttribute('aria-pressed', 'true');
    expect(steps()).toHaveLength(1);
    // The diagnosis is kept for later and logged for developers...
    expect(debug).toHaveBeenCalledWith('[missing-number] diagnosis', {
      matched_rules: ['ADD_VISIBLE'],
      unrecognized: false,
      reteach_topic: { id: 'mt_oIzycTBeE4', name: 'What the equals sign means' },
    });
    // ...but none of it is on the page.
    const page = document.body.textContent ?? '';
    expect(page).not.toContain('ADD_VISIBLE');
    expect(page).not.toContain('What the equals sign means');
    expect(page).not.toContain('mt_oIzycTBeE4');
    expect(document.body.innerHTML).not.toContain('ADD_VISIBLE');
    // And the right answer is not revealed.
    expect(box()).not.toHaveTextContent(/^3$/);
  });

  it('lets the child change the answer and try again', async () => {
    const user = userEvent.setup();
    await start(user);
    await user.click(option(2));
    await user.click(action('Check'));
    await waitFor(() => expect(feedback()).toBe('incorrect'));

    await user.click(option(3));
    expect(feedback()).toBe('idle');
    await user.click(action('Check'));

    await waitFor(() => expect(steps()).toHaveLength(2));
    expect(backend.requests.check.map((request) => request.answer)).toEqual([2, 3]);
  });

  it('opens a hint by itself after two wrong tries on the same step', async () => {
    const user = userEvent.setup();
    await start(user);

    await user.click(option(2));
    await user.click(action('Check'));
    await waitFor(() => expect(feedback()).toBe('incorrect'));
    expect(backend.requests.hint).toEqual([]);
    expect(screen.queryByText('ORBI’s hint')).not.toBeInTheDocument();

    await user.click(option(4));
    await user.click(action('Check'));

    expect(
      await screen.findByText('The = sign means both sides are worth the same.'),
    ).toBeInTheDocument();
    expect(backend.requests.hint).toEqual([{ puzzleId: 'mnc-1-1-2-1-test', step: 0, tier: 1 }]);

    // A third wrong try does not fetch more by itself.
    await user.click(option(19));
    await user.click(action('Check'));
    await waitFor(() => expect(backend.requests.check).toHaveLength(3));
    await waitFor(() => expect(feedback()).toBe('incorrect'));
    expect(backend.requests.hint).toHaveLength(1);
  });

  it('never opens the last hint tier by itself: that one shows the answer', async () => {
    const user = userEvent.setup();
    await start(user);
    await user.click(action('Hint'));
    await screen.findByText(CHAIN[0]?.hints[0] ?? '');
    await user.click(action('Hint'));
    await screen.findByText(CHAIN[0]?.hints[1] ?? '');

    for (const wrong of [2, 4]) {
      await user.click(option(wrong));
      await user.click(action('Check'));
      await waitFor(() => expect(feedback()).toBe('incorrect'));
    }

    expect(backend.requests.hint.map((request) => request.tier)).toEqual([1, 2]);
    expect(screen.queryByText(/so the missing number is 3/)).not.toBeInTheDocument();
  });

  it('counts wrong tries per step', async () => {
    const user = userEvent.setup();
    await start(user);
    await user.click(option(2));
    await user.click(action('Check'));
    await waitFor(() => expect(feedback()).toBe('incorrect'));
    await solveStep(user, 0, false);

    // One wrong try on the new step: no automatic hint yet.
    await user.click(option(9));
    await user.click(action('Check'));
    await waitFor(() => expect(feedback()).toBe('incorrect'));
    expect(backend.requests.hint).toEqual([]);
  });
});

describe('hints', () => {
  it('fetches tiers 1, 2 and 3 in turn, then disables the button', async () => {
    const user = userEvent.setup();
    await start(user);
    const hints = CHAIN[0]?.hints ?? [];

    for (const [index, text] of hints.entries()) {
      expect(action('Hint')).toBeEnabled();
      await user.click(action('Hint'));
      expect(await screen.findByText(text)).toBeInTheDocument();
      expect(backend.requests.hint.at(-1)?.tier).toBe(index + 1);
    }

    expect(action('Hint')).toBeDisabled();
    expect(backend.requests.hint).toHaveLength(3);
    // Only the newest tier shows.
    expect(screen.queryByText(hints[0] ?? '')).not.toBeInTheDocument();
  });

  it('starts again from tier 1 on the next step', async () => {
    const user = userEvent.setup();
    await start(user);
    await user.click(action('Hint'));
    await user.click(action('Hint'));
    await screen.findByText(CHAIN[0]?.hints[1] ?? '');

    await solveStep(user, 0, false);

    // The old step's hint is gone, and the new step starts from the first tier.
    expect(screen.queryByText('ORBI’s hint')).not.toBeInTheDocument();
    await user.click(action('Hint'));
    await waitFor(() =>
      expect(backend.requests.hint.at(-1)).toEqual({
        puzzleId: 'mnc-1-1-2-1-test',
        step: 1,
        tier: 1,
      }),
    );
    expect(await screen.findByText(CHAIN[1]?.hints[0] ?? '')).toBeInTheDocument();
    expect(action('Hint')).toBeEnabled();
  });
});

describe('reset', () => {
  it('empties the box of the current step only', async () => {
    const user = userEvent.setup();
    await start(user);
    await solveStep(user, 0, false);
    await user.click(option(9));
    expect(action('Reset')).toBeEnabled();

    await user.click(action('Reset'));

    expect(box()).toBeEmptyDOMElement();
    expect(option(9)).toHaveAttribute('aria-pressed', 'false');
    expect(action('Reset')).toBeDisabled();
    // The solved step above keeps its answer, and nothing was refetched.
    const [solved] = steps();
    expect(within(solved as HTMLElement).getByTestId('answer-box')).toHaveTextContent('3');
    expect(steps()).toHaveLength(2);
    expect(backend.requests.new).toHaveLength(1);
  });
});

describe('keyboard', () => {
  it('picks options with 1 to 4 and checks with Enter', async () => {
    const user = userEvent.setup();
    await start(user);

    await user.keyboard('1');
    expect(box()).toHaveTextContent('2');
    await user.keyboard('4');
    expect(box()).toHaveTextContent('4');
    await user.keyboard('2');
    expect(box()).toHaveTextContent('3');
    expect(option(3)).toHaveAttribute('aria-pressed', 'true');
    // Keys with no option do nothing.
    await user.keyboard('5');
    await user.keyboard('0');
    expect(box()).toHaveTextContent('3');

    await user.keyboard('{Enter}');
    await waitFor(() => expect(steps()).toHaveLength(2));
    expect(backend.requests.check).toEqual([{ puzzleId: 'mnc-1-1-2-1-test', step: 0, answer: 3 }]);

    // Straight on with the keyboard: focus is already on the new step.
    await user.keyboard('3');
    await user.keyboard('{Enter}');
    expect(await screen.findByTestId('solved-screen')).toBeInTheDocument();
  });

  it('Enter with an empty box does nothing', async () => {
    const user = userEvent.setup();
    await start(user);

    await user.keyboard('{Enter}');

    expect(backend.requests.check).toEqual([]);
    expect(feedback()).toBe('idle');
  });

  it('Enter checks even when a tapped option tile has the focus', async () => {
    const user = userEvent.setup();
    await start(user);
    await user.click(option(3));
    expect(option(3)).toHaveFocus();

    await user.keyboard('{Enter}');

    await waitFor(() => expect(steps()).toHaveLength(2));
    expect(backend.requests.check).toHaveLength(1);
  });

  it('Enter on a shell button belongs to that button', async () => {
    const user = userEvent.setup();
    await start(user);
    await user.click(option(2));
    action('Reset').focus();

    await user.keyboard('{Enter}');

    expect(box()).toBeEmptyDOMElement();
    expect(backend.requests.check).toEqual([]);
  });
});

describe('when the API does not cooperate', () => {
  it('replaces a puzzle from an older version with a fresh one, without a word', async () => {
    const user = userEvent.setup();
    await start(user, 'Up to 1000');
    backend.failNext('check', 410);

    await user.click(option(3));
    await user.click(action('Check'));

    await waitFor(() => expect(backend.requests.new).toHaveLength(2));
    // Same level, same place in the round, same chain length.
    expect(backend.requests.new[1]).toEqual({ level: 3, length: 2, seed: undefined });
    await waitFor(() => expect(steps()).toHaveLength(1));
    expect(box()).toBeEmptyDOMElement();
    expect(screen.getByText('1 / 5')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Try again' })).not.toBeInTheDocument();
    expect(screen.queryByText(/couldn’t get your puzzle/)).not.toBeInTheDocument();
    expect(feedback()).toBe('idle');
  });

  it('does the same when a hint comes back gone', async () => {
    const user = userEvent.setup();
    await start(user);
    backend.failNext('hint', 410);

    await user.click(action('Hint'));

    await waitFor(() => expect(backend.requests.new).toHaveLength(2));
    await waitFor(() => expect(steps()).toHaveLength(1));
    expect(screen.queryByRole('button', { name: 'Try again' })).not.toBeInTheDocument();
  });

  it('shows a friendly message when the backend is not running, and recovers', async () => {
    const user = userEvent.setup();
    backend.failNext('new', 'network');
    render(<MissingNumber timing={FAST} />);
    await user.click(screen.getByRole('button', { name: 'Up to 20' }));

    const retry = await screen.findByRole('button', { name: 'Try again' });
    expect(screen.getByText(/couldn’t get your puzzle just now/)).toBeInTheDocument();
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('Let’s try that again');
    // Nothing technical leaks onto the page.
    expect(document.body.textContent).not.toMatch(/error|fetch|failed|50\d|40\d|undefined|null/i);

    await user.click(retry);

    await screen.findByRole('list', { name: 'Steps' });
    expect(backend.requests.new).toHaveLength(2);
    expect(screen.queryByRole('button', { name: 'Try again' })).not.toBeInTheDocument();
    expect(currentStep()).toHaveAccessibleName('8 plus box equals 11');
  });

  it.each([
    ['unavailable (503)', 503],
    ['not found (404)', 404],
    ['a network failure', 'network'],
  ] as const)('a check that hits %s keeps the child’s place', async (_label, failure) => {
    const user = userEvent.setup();
    await start(user);
    await solveStep(user, 0, false);
    backend.failNext('check', failure);

    await user.click(option(8));
    await user.click(action('Check'));

    const retry = await screen.findByRole('button', { name: 'Try again' });
    expect(screen.getByText(/couldn’t get your puzzle just now/)).toBeInTheDocument();
    expect(document.body.textContent).not.toMatch(/503|404|error/i);

    await user.click(retry);

    // Back where they were, with the same answer sent again: it was right.
    expect(await screen.findByTestId('solved-screen')).toBeInTheDocument();
    expect(backend.requests.new).toHaveLength(1);
    expect(backend.requests.check.map((request) => request.answer)).toEqual([3, 8, 8]);
  });

  it('cancels a request in flight when the child leaves the game', async () => {
    const user = userEvent.setup();
    backend.delayMs = 200;
    const errors = vi.spyOn(console, 'error').mockImplementation(() => {});
    const view = render(<MissingNumber timing={FAST} />);
    await user.click(screen.getByRole('button', { name: 'Up to 20' }));
    await waitFor(() => expect(backend.requests.new).toHaveLength(1));

    view.unmount();
    await new Promise((resolve) => setTimeout(resolve, 300));

    // No state update after leaving, and nothing was retried.
    expect(errors).not.toHaveBeenCalled();
    expect(backend.requests.new).toHaveLength(1);
    errors.mockRestore();
  });
});

describe('leaving', () => {
  it('passes onExit to the shell as the "Games" button', async () => {
    const user = userEvent.setup();
    const onExit = vi.fn();
    render(<MissingNumber onExit={onExit} />);

    await user.click(screen.getByRole('button', { name: 'Back to games' }));

    expect(onExit).toHaveBeenCalledTimes(1);
    expect(shell()).toHaveAttribute('data-house', 'navigators');
  });
});
